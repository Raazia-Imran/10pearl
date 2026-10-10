"""WTQ bill decoder: generate both organizer CSVs from their templates."""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


FIELDS = (
    "provider", "tariff", "sanctioned_load_kw", "bill_month", "reading_date",
    "issue_date", "due_date", "previous_reading", "current_reading",
    "units_consumed", "charges", "total_charges", "taxes", "total_taxes",
    "current_bill", "arrears", "payable_within_due_date",
    "payable_after_due_date",
)
NUMBERS = set(FIELDS) - {
    "provider", "tariff", "bill_month", "reading_date", "issue_date",
    "due_date", "charges", "taxes",
}
CHARGE_TYPES = {
    "energy", "fixed", "fpa", "quarterly_adjustment", "surcharge",
    "meter_rent", "subsidy", "other",
}
TAX_TYPES = {
    "gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax",
}
PROVIDERS = {"KESC": "KE", "KE": "KE", "LESCO": "LESCO", "IESCO": "IESCO"}

EXTRACT_PROMPT = """Read the attached electricity bill carefully. Return only a JSON object with two keys:
"bill": {"provider":null,"tariff":null,"sanctioned_load_kw":null,"bill_month":null,"reading_date":null,"issue_date":null,"due_date":null,"previous_reading":null,"current_reading":null,"units_consumed":null,"charges":[],"total_charges":null,"taxes":[],"total_taxes":null,"current_bill":null,"arrears":null,"payable_within_due_date":null,"payable_after_due_date":null},
"history": [{"month":"YYYY-MM","units":number}] for any visible previous usage months, otherwise [].

Rules: provider KE, LESCO or IESCO. Tariff exactly printed. Month YYYY-MM; dates YYYY-MM-DD. Numbers in PKR without Rs or commas; credits/CR and subsidies negative. Extract visible printed values as printed, never recalculate, round or invent. Covered, absent, blank or unreadable => null. Every bill key must appear. No names, addresses, CNICs, account/reference/consumer/meter numbers, or arbitrary OCR transcript.
Charges = each nonzero printed row from charges section, preserving duplicate types, each {"type":...,"amount":number,"label":"printed nonidentifying line name"}. Types energy, fixed, fpa (including FCA), quarterly_adjustment, surcharge, meter_rent, subsidy, other. Taxes = each nonzero ITEMIZED row in tax/government section, each {"type":...,"amount":number,"label":"printed nonidentifying line name"}. Types gst (including GST on FPA), electricity_duty, income_tax, municipal_tax, other_tax (including TV fee in tax section). KE MUCT (KMC), KMC and Municipal Utility Charges are ALWAYS municipal_tax. Include each tax line's printed label. A single summary line labeled just "Taxes" or "Taxes 15.24%" is a COMBINED TOTAL, not an itemized other_tax: taxes=[] and total_taxes=the printed amount. Classify itemized lines by SECTION. For total_charges copy a PRINTED charge subtotal ("Electricity Charges" or "Net Electricity Charges"); never invent a subtotal by adding charge lines or FPA. If no charge subtotal is printed, total_charges=null. Subtotals only if printed. Arrears printed sign. Due date is last surcharge-free day. If several late payables, choose highest. Current units are printed billed units, not difference of meter readings. History only if a monthly history table is visible; preserve current month separately if printed in a 13-month chart."""

ANSWER_PROMPT = """Answer the attached bill's customer questions in English. Return only JSON mapping each question_id to a nonempty answer string. Use only the image and supplied extracted, nonidentifying facts. Do not reveal names, addresses, account/reference/consumer/meter numbers or CNICs. Be specific: numbers, PKR/units, months, and simple arithmetic when asked. State numerator/denominator for percentages, time window for historical counts, and method for estimates; label estimates. If needed data is absent or unreadable say so, no guessing and no outside tariffs/rates. If ambiguous, state the interpretation or explain both. Do not confuse printed current bill with payable after arrears or late fees. Keep each response concise. Questions JSON follows:\n"""


def request_json(client, model, prompt, image, *, retries=4):
    mime = "image/jpeg" if image.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    payload = [prompt, types.Part.from_bytes(data=image.read_bytes(), mime_type=mime)]
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=payload,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0,
                ),
            )
            value = json.loads(response.text or "")
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object from model")
            return value
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Model response failed for {image.stem}: {type(exc).__name__}") from exc
            wait = min(40, 2 ** attempt * 3 + random.random() * 2)
            print(f"Retry {image.stem} after {type(exc).__name__}; {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)


def number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a bill number")
    if isinstance(value, (float, int)):
        return value
    if not isinstance(value, str):
        raise ValueError("Invalid numeric type")
    cleaned = value.strip().upper().replace(",", "").replace("PKR", "").replace("RS.", "").replace("RS", "").strip()
    credit = cleaned.endswith("CR")
    cleaned = cleaned.removesuffix("CR").strip()
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
        raise ValueError("Ambiguous printed number")
    result = float(cleaned) if "." in cleaned else int(cleaned)
    return -abs(result) if credit else result


def normalized_date(value, fmt):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(fmt, value):
        raise ValueError("Date must be ISO formatted or null")
    if len(value) == 10:
        date.fromisoformat(value)
    else:
        if not 1 <= int(value[-2:]) <= 12:
            raise ValueError("Invalid month")
    return value


def normalize_items(items, allowed):
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("Charges/taxes must be a list")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Charge/tax entry must be an object")
        category = item.get("type")
        label = str(item.get("label") or "").upper()
        if allowed is TAX_TYPES and ("MUCT" in label or "KMC" in label or "MUNICIPAL" in label):
            category = "municipal_tax"
        if category not in allowed:
            raise ValueError(f"Unknown charge/tax category: {category}")
        amount = number(item.get("amount"))
        if amount is None:
            raise ValueError("Charge/tax amount must be numeric")
        if amount != 0:
            result.append({"type": category, "amount": amount})
    return result


def calculation_aids(bill, history):
    """Provide audited arithmetic to the answer model without changing printed bill values."""
    aids = {}
    current = bill.get("current_bill")
    taxes = bill.get("total_taxes")
    if current not in (None, 0) and taxes is not None:
        aids["tax_share_of_current_bill_percent"] = round(100 * taxes / current, 2)
    if bill.get("previous_reading") is not None and bill.get("current_reading") is not None:
        aids["reading_difference_not_necessarily_billed_units"] = round(bill["current_reading"] - bill["previous_reading"], 3)
    previous = [row for row in history if row["month"] != bill.get("bill_month")]
    if previous:
        aids["previous_history_month_count"] = len(previous)
        aids["previous_history_units_sum"] = round(sum(row["units"] for row in previous), 3)
        aids["previous_history_units_average"] = round(aids["previous_history_units_sum"] / len(previous), 3)
    return aids


def normalize_bill(raw, bill_id):
    if not isinstance(raw, dict):
        raise ValueError("Missing bill JSON object")
    bill = {key: raw.get(key, [] if key in ("charges", "taxes") else None) for key in FIELDS}
    expected = PROVIDERS.get(bill_id.split("_", 1)[0].upper())
    provider = str(bill["provider"] or "").upper().replace("K-ELECTRIC", "KE")
    if provider == "KESC":
        provider = "KE"
    if provider and provider not in {"KE", "LESCO", "IESCO"}:
        raise ValueError(f"Unknown provider for {bill_id}")
    if expected and provider and provider != expected:
        raise ValueError(f"Provider disagrees with filename for {bill_id}")
    bill["provider"] = provider or expected
    bill["tariff"] = str(bill["tariff"]).strip() if bill["tariff"] not in (None, "") else None
    bill["bill_month"] = normalized_date(bill["bill_month"], r"\d{4}-\d{2}")
    for key in ("reading_date", "issue_date", "due_date"):
        bill[key] = normalized_date(bill[key], r"\d{4}-\d{2}-\d{2}")
    for key in NUMBERS:
        bill[key] = number(bill[key])
    bill["charges"] = normalize_items(bill["charges"], CHARGE_TYPES)
    raw_taxes = bill["taxes"]
    if isinstance(raw_taxes, list) and len(raw_taxes) == 1 and isinstance(raw_taxes[0], dict):
        label = str(raw_taxes[0].get("label") or "").strip().lower()
        if re.fullmatch(r"taxes(?:\s+\d+(?:\.\d+)?\s*%)?", label):
            if bill["total_taxes"] is None:
                bill["total_taxes"] = number(raw_taxes[0].get("amount"))
            raw_taxes = []
    bill["taxes"] = normalize_items(raw_taxes, TAX_TYPES)
    return bill


def sanitize_history(raw):
    result = []
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            month = normalized_date(item.get("month"), r"\d{4}-\d{2}")
            units = number(item.get("units"))
            if month and units is not None:
                result.append({"month": month, "units": units})
        except ValueError:
            continue
    return result


def load_csv(path, expected):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != expected:
            raise ValueError(f"Incorrect headers in {path}: {reader.fieldnames}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"Malformed CSV row in {path}")
    return rows


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def images_in(folder):
    if not folder.is_dir():
        raise FileNotFoundError(f"Missing bill image folder: {folder}")
    images = {}
    for path in folder.iterdir():
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            if path.stem in images:
                raise ValueError(f"Duplicate bill image: {path.stem}")
            images[path.stem] = path
    return images


def safe_cache_path(folder, bill_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", bill_id):
        raise ValueError("Unsafe bill_id")
    return folder / f"{bill_id}.json"


def run(args):
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY missing; set it in local .env")
    model = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")
    if model != "gemini-3.5-flash-lite":
        raise ValueError("This implementation is configured only for the allowed gemini-3.5-flash-lite model")
    l1 = load_csv(args.level1_template, ["bill_id", "json"])
    l2 = load_csv(args.level2_template, ["bill_id", "question_id", "question", "answer"])
    ids = [row["bill_id"] for row in l1]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Level 1 requires unique nonempty bill IDs")
    images = images_in(args.bills)
    missing = set(ids) - images.keys()
    if missing:
        raise ValueError(f"Missing images: {sorted(missing)}")
    groups = defaultdict(list)
    for row in l2:
        if row["bill_id"] not in ids or not row["question_id"] or not row["question"]:
            raise ValueError("Invalid Level 2 bill/question")
        groups[row["bill_id"]].append(row)
    if set(groups) != set(ids):
        raise ValueError("Every Level 1 bill needs Level 2 questions")
    for bill_id, rows in groups.items():
        if len({row["question_id"] for row in rows}) != len(rows):
            raise ValueError(f"Duplicate question ID for {bill_id}")
    args.cache.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=key)
    answers_by_id = {}
    bills_by_id = {}
    print(f"Matched {len(ids)} bill images and {len(l2)} question rows.", flush=True)
    for index, bill_id in enumerate(ids, 1):
        path = safe_cache_path(args.cache, bill_id)
        cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        bill = normalize_bill(cached["bill"], bill_id) if "bill" in cached else None
        history = sanitize_history(cached.get("history", []))
        if bill is None:
            extracted = request_json(client, model, EXTRACT_PROMPT, images[bill_id])
            bill = normalize_bill(extracted.get("bill", extracted), bill_id)
            history = sanitize_history(extracted.get("history", []))
            cached = {"bill": bill, "history": history}
            path.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        bills_by_id[bill_id] = bill
        expected = [row["question_id"] for row in groups[bill_id]]
        answers = cached.get("answers")
        if not isinstance(answers, dict) or any(not str(answers.get(q, "")).strip() for q in expected):
            questions = [{"question_id": row["question_id"], "question": row["question"]} for row in groups[bill_id]]
            facts = json.dumps({"bill": bill, "history": history, "calculated_aids": calculation_aids(bill, history)}, ensure_ascii=False, separators=(",", ":"))
            prompt = ANSWER_PROMPT + json.dumps(questions, ensure_ascii=False) + "\nExtracted nonidentifying facts: " + facts
            answers = request_json(client, model, prompt, images[bill_id])
            if "answers" in answers and isinstance(answers["answers"], dict):
                answers = answers["answers"]
            if any(not isinstance(answers.get(q), str) or not answers[q].strip() for q in expected):
                raise ValueError(f"Missing answer(s) for {bill_id}: {expected}")
            cached["answers"] = {q: answers[q].strip() for q in expected}
            path.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        answers_by_id[bill_id] = answers
        print(f"[{index}/{len(ids)}] {bill_id}: extraction and {len(expected)} answers ready", flush=True)
        if index < len(ids) and args.pause > 0:
            time.sleep(args.pause)
    out1 = [{"bill_id": row["bill_id"], "json": json.dumps(bills_by_id[row["bill_id"]], ensure_ascii=False, separators=(",", ":"))} for row in l1]
    out2 = [{**row, "answer": " ".join(answers_by_id[row["bill_id"]][row["question_id"]].split())} for row in l2]
    if any(not row["json"] for row in out1) or any(not row["answer"] for row in out2):
        raise ValueError("Refusing to write incomplete outputs")
    write_csv(args.output / "level1.csv", ["bill_id", "json"], out1)
    write_csv(args.output / "level2.csv", ["bill_id", "question_id", "question", "answer"], out2)
    print(f"Generated {args.output / 'level1.csv'} ({len(out1)} rows) and {args.output / 'level2.csv'} ({len(out2)} rows).", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bills", type=Path, required=True)
    parser.add_argument("--level1-template", type=Path, required=True)
    parser.add_argument("--level2-template", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--cache", type=Path, default=Path(".cache"))
    parser.add_argument("--pause", type=float, default=10, help="Seconds between bills to pace free tier")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        run(parse_args())
    except (ValueError, FileNotFoundError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

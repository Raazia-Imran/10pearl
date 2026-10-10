"""WTQ bill decoder: generate both organizer CSVs from their templates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, create_model


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stderr)
LOG = logging.getLogger("bill_decoder")


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


class PrintedLine(BaseModel):
    type: str
    amount: float
    label: str | None = None


class ChargeLine(PrintedLine):
    type: Literal['energy', 'fixed', 'fpa', 'quarterly_adjustment', 'surcharge', 'meter_rent', 'subsidy', 'other']


class TaxLine(PrintedLine):
    type: Literal['gst', 'electricity_duty', 'income_tax', 'municipal_tax', 'other_tax']


class HistoryLine(BaseModel):
    month: str
    units: float


class PaymentLine(BaseModel):
    month: str
    billed_amount: float | None
    payment: float | None


class ExtractedBill(BaseModel):
    provider: str | None
    tariff: str | None
    sanctioned_load_kw: float | None
    bill_month: str | None
    reading_date: str | None
    issue_date: str | None
    due_date: str | None
    previous_reading: float | None
    current_reading: float | None
    units_consumed: float | None
    charges: list[ChargeLine]
    total_charges: float | None
    taxes: list[TaxLine]
    total_taxes: float | None
    current_bill: float | None
    arrears: float | None
    payable_within_due_date: float | None
    payable_after_due_date: float | None


class ExtractionResponse(BaseModel):
    bill: ExtractedBill
    history: list[HistoryLine]
    payments: list[PaymentLine]

EXTRACT_PROMPT = """Read the attached electricity bill carefully as a precision bill auditor. Return only a JSON object with three keys:
"bill": {"provider":null,"tariff":null,"sanctioned_load_kw":null,"bill_month":null,"reading_date":null,"issue_date":null,"due_date":null,"previous_reading":null,"current_reading":null,"units_consumed":null,"charges":[],"total_charges":null,"taxes":[],"total_taxes":null,"current_bill":null,"arrears":null,"payable_within_due_date":null,"payable_after_due_date":null},
"history": [{"month":"YYYY-MM","units":number}] for every visible usage-history month, otherwise [],
"payments": [{"month":"YYYY-MM","billed_amount":number_or_null,"payment":number_or_null}] for each visible BILLING/PAYMENT HISTORY row, otherwise [].

Rules: provider KE, LESCO or IESCO. Tariff exactly printed. Month YYYY-MM; dates YYYY-MM-DD. Numbers in PKR without Rs or commas; credits/CR and subsidies negative. Extract visible printed values as printed, never recalculate, round or invent. Covered, absent, blank or unreadable => null. Every bill key must appear. No names, addresses, CNICs, account/reference/consumer/meter numbers, or arbitrary OCR transcript.
Charges = each nonzero printed row from charges section, preserving duplicate types, each {"type":...,"amount":number,"label":"printed nonidentifying line name"}. Types energy, fixed, fpa (including FCA), quarterly_adjustment, surcharge, meter_rent, subsidy, other. If a LESCO/IESCO breakdown shows only a "Total Electricity Charges" line and no finer energy lines, include that line once as an energy charge. Do not also add "Net Electricity Charges" as a duplicate charge. A separately printed "Total FPA" in the bill charges breakdown is an fpa charge line even if outside the printed net electricity subtotal. Taxes = each nonzero ITEMIZED row in tax/government section, each {"type":...,"amount":number,"label":"printed nonidentifying line name"}. Types gst (including GST on FPA), electricity_duty, income_tax, municipal_tax, other_tax (including TV fee in tax section). KE MUCT (KMC), KMC and Municipal Utility Charges are ALWAYS municipal_tax. Include each tax line's printed label. A single summary line labeled just "Taxes" or "Taxes 15.24%" is a COMBINED TOTAL, not an itemized other_tax: taxes=[] and total_taxes=the printed amount. Classify itemized lines by SECTION. For total_charges copy a PRINTED charge subtotal ("Electricity Charges" or "Net Electricity Charges"); never invent a subtotal by adding charge lines or FPA. If no charge subtotal is printed, total_charges=null. Subtotals only if printed. Arrears printed sign. Due date is last surcharge-free day. If several late payables, choose highest. Current units are printed billed units, not difference of meter readings. In a MULTI-ROW meter table, choose the previous/current readings on the row whose printed units match units_consumed. If no single row matches, use null for both readings; never calculate or combine meter rows. History only if a monthly history table is visible; preserve current month separately if printed in a 13-month chart."""

EXTRACT_PROMPT += """\nAdditional layout rules: Read BOTH halves of a 12-month history table. Preserve the minus sign on net export units and credit bills. In KE, the 13-month units chart and the separate three-row billing/payment table have DIFFERENT coverage: never invent twelve payment rows. Include only printed financial history values; a printed zero payment is 0, a blank payment is null. Do not confuse status EX with solar export; EX alone is not proof of net metering. Ignore handwriting and meter photographs when a clearly labelled printed bill value exists. In detailed LESCO layouts, the charges-section TOTAL and government-section TOTAL are the subtotals. A Total FPA in the totals column may combine the detailed fuel charge and its taxes: when a detailed fuel charge already appears, do NOT add the composite Total FPA again to charges. ED ON FPA is electricity_duty and GST ON FPA is gst, retaining them as separate tax entries. The main printed meter table is authoritative; peak/off-peak rows alone do not imply solar export. Keep unreadable printed values null instead of copying a handwritten correction."""

ANSWER_PROMPT = """Answer the attached bill's customer questions in English. Return only JSON mapping each question_id to a nonempty answer string. Use only the image and supplied extracted, nonidentifying facts. Do not reveal names, addresses, account/reference/consumer/meter numbers or CNICs. Be specific: numbers, PKR/units, months, and simple arithmetic when asked. State numerator/denominator for percentages, time window for historical counts, and method for estimates; label estimates. If needed data is absent or unreadable say 'Information not available on bill' and explain what is missing, no guessing and no outside tariffs/rates. If ambiguous, state the interpretation or explain both. Do not confuse printed current bill with payable after arrears or late fees. Solar requires explicit import/export, net-metering or bidirectional evidence; EX status and peak/off-peak registers alone are NOT proof. If only standard consumption is shown, describe it as appearing standard and give the evidence. For fuel adjustment read the original FPA/FCA line and its associated month, including Urdu messages. Distinguish the fuel charge itself from Total FPA including related taxes. For late fees give BOTH printed surcharge tiers and their date windows; do not report only the highest late payable. A computed tax percentage is an effective ratio, not an officially printed tax rate. Distinguish the last twelve completed months from the current month. Payments recorded are not proof of on-time payment. Never claim twelve months of financial history when only three are printed. Use supplied Python-computed answers verbatim where present; do not recalculate them. Keep each response concise. Questions JSON follows:\n"""


def request_json(client, model, prompt, image, *, retries=4, schema=None):
    mime = "image/jpeg" if image.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    payload = [prompt, types.Part.from_bytes(data=image.read_bytes(), mime_type=mime)]
    for attempt in range(retries):
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                **({"response_schema": schema} if schema else {}),
            )
            response = client.models.generate_content(
                model=model,
                contents=payload,
                config=config,
            )
            parsed = getattr(response, "parsed", None)
            value = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
            if value is None:
                value = json.loads(response.text or "")
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object from model")
            return value
        except Exception as exc:
            status = getattr(exc, "code", None)
            if status in {400, 401, 403, 404}:
                raise RuntimeError(f"API rejected {image.stem} (HTTP {status}); check model, key or schema") from exc
            if attempt == retries - 1:
                raise RuntimeError(f"Model response failed for {image.stem}: {type(exc).__name__}") from exc
            wait = min(40, 2 ** attempt * 3 + random.random() * 2)
            LOG.warning("[Bill: %s] Retry after %s in %.1fs", image.stem, type(exc).__name__, wait)
            time.sleep(wait)


def number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a bill number")
    if isinstance(value, (float, int)):
        if not math.isfinite(value):
            raise ValueError("Nonfinite bill number")
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
        if allowed is CHARGE_TYPES:
            if re.search(r"\bQUARTERLY\b|\bQTA\b", label):
                category = "quarterly_adjustment"
            elif re.search(r"\bFPA\b|\bFCA\b|FUEL PRICE ADJUSTMENT", label):
                category = "fpa"
            elif "SUBSID" in label or "RELIEF" in label:
                category = "subsidy"
            elif "METER RENT" in label or "SERVICE RENT" in label:
                category = "meter_rent"
            elif "SURCHARGE" in label:
                category = "surcharge"
            elif "FIXED" in label:
                category = "fixed"
        if allowed is TAX_TYPES and ("MUCT" in label or "KMC" in label or "MUNICIPAL" in label):
            category = "municipal_tax"
        elif allowed is TAX_TYPES and ("GST" in label or "SALES TAX" in label):
            category = "gst"
        elif allowed is TAX_TYPES and ("ELECTRICITY DUTY" in label or re.search(r"\bED\b", label)):
            category = "electricity_duty"
        elif allowed is TAX_TYPES and "INCOME TAX" in label:
            category = "income_tax"
        if category not in allowed:
            raise ValueError(f"Unknown charge/tax category: {category}")
        amount = number(item.get("amount"))
        if amount is None:
            raise ValueError("Charge/tax amount must be numeric")
        if allowed is CHARGE_TYPES and category == "subsidy":
            amount = -abs(amount)
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


def shift_month(month, offset):
    year, value = map(int, month.split("-"))
    year, value = divmod(year * 12 + value - 1 + offset, 12)
    return f"{year:04d}-{value + 1:02d}"


def deterministic_answers(bill, history, payments, questions):
    """Compute grounded numerical answers by question text, never by a bill ID."""
    result = {}
    month = bill.get("bill_month")
    if not month:
        return result
    by_month = {r["month"]: r["units"] for r in history}
    wanted = [shift_month(month, -n) for n in range(12, 0, -1)]
    past = [(m, by_month[m]) for m in wanted if m in by_month]
    full = len(past) == 12
    current = bill.get("units_consumed")
    payment_map = {r["month"]: r for r in payments}
    finance = [payment_map[m] for m in wanted if m in payment_map]
    fmt = lambda value: f"{value:,.2f}".rstrip("0").rstrip(".")
    window = f"{wanted[0]} to {wanted[-1]}, excluding the current month"
    for row in questions:
        q = row["question"].lower()
        answer = None
        if "highest units" in q and full:
            highest = max(u for _, u in past)
            matches = ", ".join(m for m, u in past if u == highest)
            answer = f"{matches} had the highest consumption: {fmt(highest)} units among the previous 12 months ({window})."
        elif "same month last year" in q and current is not None:
            last_year = shift_month(month, -12)
            if last_year in by_month:
                old = by_month[last_year]
                delta = current - old
                direction = "more" if delta > 0 else "fewer" if delta < 0 else "the same number of"
                comparison = f"{fmt(abs(delta))} {direction} units" if delta != 0 else "the same number of units"
                answer = f"{'Yes' if delta > 0 else 'No'}. {month}: {fmt(current)} units; {last_year}: {fmt(old)} units. This month used {comparison}."
        elif "average monthly units" in q and full:
            total = sum(u for _, u in past)
            average = total / 12
            answer = f"The previous 12 months averaged {fmt(average)} units/month ({fmt(total)} / 12; {window})."
            if current is not None:
                delta = current - average
                answer += f" This month is {fmt(current)} units, {fmt(abs(delta))} {'above' if delta >= 0 else 'below'} that average."
        elif "summer" in q and "winter" in q and full:
            summer = [(m, u) for m, u in past if int(m[-2:]) in {6, 7, 8}]
            winter = [(m, u) for m, u in past if int(m[-2:]) in {12, 1, 2}]
            if len(summer) == len(winter) == 3:
                st, wt = sum(u for _, u in summer), sum(u for _, u in winter)
                answer = (f"Summer ({', '.join(m for m, _ in summer)}) totals {fmt(st)} units; "
                          f"winter ({', '.join(m for m, _ in winter)}) totals {fmt(wt)} units. "
                          f"Summer is {fmt(abs(st - wt))} units {'higher' if st >= wt else 'lower'} in total "
                          f"({fmt(st / 3)} versus {fmt(wt / 3)} units/month).")
        elif "paying every bill" in q and finance:
            known = [r for r in finance if r.get("billed_amount") is not None and r.get("payment") is not None]
            zero = [r["month"] for r in known if r["billed_amount"] > 0 and r["payment"] == 0]
            partial = [r["month"] for r in known if r["billed_amount"] > 0 and r["payment"] > 0 and r["payment"] + 1 < r["billed_amount"]]
            if len(finance) == len(known) == 12:
                if zero or partial:
                    answer = "No. "
                    if zero:
                        answer += f"Zero payment is recorded for {', '.join(zero)}. "
                    if partial:
                        answer += f"Payment is below the billed amount for {', '.join(partial)}. "
                    answer += "These are recorded history entries; later settlement is not established by this table."
                else:
                    answer = "Yes, the 12 displayed months record payments covering the billed amounts, allowing PKR 1 rounding differences. This does not establish that payments were on time."
            else:
                detail = "zero payments: " + ", ".join(zero) if zero else "payments are recorded for the readable displayed rows"
                answer = f"A complete 12-month payment record is not available on bill. Only {len(finance)} financial-history months are shown ({detail}); the usage chart does not prove payment."
        elif "last 3 months" in q:
            months = [shift_month(month, -n) for n in (3, 2, 1)]
            if all(m in by_month for m in months):
                units = [by_month[m] for m in months]
                delta = units[-1] - units[0]
                trend = "increased steadily" if units[0] < units[1] < units[2] else "decreased steadily" if units[0] > units[1] > units[2] else "fluctuated"
                answer = f"For the last three completed months: " + "; ".join(f"{m}: {fmt(by_month[m])} units" for m in months)
                answer += f". Consumption {trend}, with a net {'increase' if delta >= 0 else 'decrease'} of {fmt(abs(delta))} units."
                if current is not None:
                    recent = [shift_month(month, -2), shift_month(month, -1), month]
                    answer += " Including this bill instead: " + ", ".join(f"{m}: {fmt(current if m == month else by_month[m])}" for m in recent) + " units."
        elif "expect to consume next month" in q and full:
            target = shift_month(month, 1)
            analogue = shift_month(target, -12)
            if analogue in by_month:
                answer = f"Estimate: {fmt(by_month[analogue])} units for {target}, using the same calendar month last year ({analogue}) as a seasonal baseline. One annual cycle cannot establish a reliable forecast; weather and usage changes may alter it."
            else:
                answer = f"Estimate: {fmt(sum(u for _, u in past) / 12)} units, using the preceding 12-month mean. This is a baseline, not a guaranteed forecast."
        elif "spread my electricity cost evenly" in q:
            amounts = [r["billed_amount"] for r in finance if r.get("billed_amount") is not None]
            if len(amounts) == 12:
                total = sum(amounts)
                answer = f"Set aside approximately PKR {fmt(total / 12)} per month: the 12 displayed bills total PKR {fmt(total)}, divided by 12 ({window}). This is a historical budget estimate; future rates may change."
            elif amounts:
                answer = f"The annual average cannot be established: only {len(amounts)} billed amounts are printed. A provisional budget is PKR {fmt(sum(amounts) / len(amounts))}/month, their mean (PKR {fmt(sum(amounts))} / {len(amounts)}), not a verified 12-month average."
            else:
                answer = "Information not available on bill: twelve monthly billed amounts are needed to calculate an annual monthly budget."
        elif "same units as last month" in q:
            last = shift_month(month, -1)
            amount = bill.get("current_bill")
            if last in by_month and current is not None and current > 0 and amount is not None and amount >= 0 and by_month[last] >= 0:
                fixed = sum(r["amount"] for r in bill["charges"] if r["type"] in {"fixed", "meter_rent"})
                estimate = fixed + (amount - fixed) * by_month[last] / current
                answer = f"Rough estimate: PKR {fmt(estimate)} for {fmt(by_month[last])} units ({last}). Method: PKR {fmt(fixed)} fixed charges + (PKR {fmt(amount)} current bill - PKR {fmt(fixed)}) × {fmt(by_month[last])}/{fmt(current)}. It excludes arrears and late fees and assumes the remaining charges scale proportionally; slabs, peak/off-peak mix and lagged FPA can change the result."
            else:
                answer = "Information not available on bill for a defensible proportional estimate: positive current units, current bill and last month's billed units are required; net export/credit cases need additional tariff information."
        if answer:
            result[row["question_id"]] = answer
    return result


def checkpoint(path, value):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def review_flags(bill):
    """Attention flags only: bills can legitimately contain adjustments and rounding."""
    flags = []
    if bill["taxes"] and bill["total_taxes"] is not None:
        total = sum(item["amount"] for item in bill["taxes"])
        if abs(total - bill["total_taxes"]) > 1:
            flags.append(f"Itemized taxes {total:g} differ from printed total_taxes {bill['total_taxes']:g}; inspect tax section")
    if bill["charges"] and bill["total_charges"] is not None:
        total = sum(item["amount"] for item in bill["charges"])
        if abs(total - bill["total_charges"]) > 1:
            flags.append(f"Charge rows sum to {total:g}, printed total_charges is {bill['total_charges']:g}; inspect subtotal scope and FPA")
    if bill["previous_reading"] is not None and bill["current_reading"] is not None and bill["units_consumed"] is not None:
        delta = bill["current_reading"] - bill["previous_reading"]
        if abs(delta - bill["units_consumed"]) > 1:
            flags.append("Printed units differ from first meter reading difference; inspect net metering or multiplier")
    elif bill["units_consumed"] is not None:
        flags.append("Meter readings missing while units are printed; inspect whether a single row matches current units")
    if bill["issue_date"] and bill["due_date"] and bill["due_date"] < bill["issue_date"]:
        flags.append("Due date precedes issue date; inspect year/month")
    return flags


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
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
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
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=120_000))
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    answers_by_id = {}
    bills_by_id = {}
    review_by_id = {}
    failures = {}
    LOG.info("Matched %d bill images and %d question rows", len(ids), len(l2))
    for index, bill_id in enumerate(ids, 1):
        try:
            path = safe_cache_path(args.cache, bill_id)
            questions = [{"question_id": row["question_id"], "question": row["question"]} for row in groups[bill_id]]
            fingerprint = hashlib.sha256(images[bill_id].read_bytes() + json.dumps([model, code_hash, questions], sort_keys=True).encode()).hexdigest()
            try:
                cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except (ValueError, OSError):
                LOG.warning("[Bill: %s] Invalid checkpoint; regenerating", bill_id)
                cached = {}
            if not isinstance(cached, dict) or cached.get("fingerprint") != fingerprint:
                cached = {}
            bill = normalize_bill(cached["bill"], bill_id) if "bill" in cached else None
            history = sanitize_history(cached.get("history", []))
            payments = cached.get("payments", [])
            if bill is None:
                extracted = request_json(client, model, EXTRACT_PROMPT, images[bill_id], schema=ExtractionResponse)
                bill = normalize_bill(extracted.get("bill", extracted), bill_id)
                history = sanitize_history(extracted.get("history", []))
                payments = []
                for entry in extracted.get("payments", []):
                    pm = normalized_date(entry.get("month"), r"\d{4}-\d{2}")
                    if pm:
                        payments.append({"month": pm, "billed_amount": number(entry.get("billed_amount")), "payment": number(entry.get("payment"))})
                cached = {"fingerprint": fingerprint, "bill": bill, "history": history, "payments": payments}
                checkpoint(path, cached)
            bills_by_id[bill_id] = bill
            review_by_id[bill_id] = review_flags(bill)
            expected = [row["question_id"] for row in groups[bill_id]]
            answers = cached.get("answers")
            if not isinstance(answers, dict) or any(not isinstance(answers.get(q), str) or not answers[q].strip() for q in expected):
                computed = deterministic_answers(bill, history, payments, questions)
                pending = [q for q in questions if q["question_id"] not in computed]
                facts = json.dumps({"bill": bill, "history": history, "payments": payments, "calculated_aids": calculation_aids(bill, history), "python_computed_answers": computed}, ensure_ascii=False, separators=(",", ":"))
                answers = {}
                if pending:
                    prompt = ANSWER_PROMPT + json.dumps(pending, ensure_ascii=False) + "\nExtracted nonidentifying facts: " + facts
                    answer_schema = create_model("BillAnswers", **{q["question_id"]: (str, ...) for q in pending})
                    answers = request_json(client, model, prompt, images[bill_id], schema=answer_schema)
                answers.update(computed)
                if any(not isinstance(answers.get(q), str) or not answers[q].strip() for q in expected):
                    raise ValueError(f"Missing answer(s) for {bill_id}: {expected}")
                cached["answers"] = {q: answers[q].strip() for q in expected}
                checkpoint(path, cached)
            answers_by_id[bill_id] = answers
            LOG.info("[Bill: %s] %d/%d extraction and %d answers ready", bill_id, index, len(ids), len(expected))
        except Exception as exc:
            cause = exc.__cause__ or exc
            status = getattr(cause, "code", None)
            failures[bill_id] = type(cause).__name__ + (f" HTTP {status}" if status else "")
            LOG.error("[Bill: %s] Failed: %s; continuing from checkpoints", bill_id, failures[bill_id])
        finally:
            if index < len(ids) and args.pause > 0:
                time.sleep(args.pause)
    if failures:
        raise RuntimeError(f"Incomplete bills {failures}; successful bill checkpoints saved, rerun after resolving errors")
    out1 = [{"bill_id": row["bill_id"], "json": json.dumps(bills_by_id[row["bill_id"]], ensure_ascii=False, separators=(",", ":"))} for row in l1]
    out2 = [{**row, "answer": " ".join(answers_by_id[row["bill_id"]][row["question_id"]].split())} for row in l2]
    if any(not row["json"] for row in out1) or any(not row["answer"] for row in out2):
        raise ValueError("Refusing to write incomplete outputs")
    write_csv(args.output / "level1.csv", ["bill_id", "json"], out1)
    write_csv(args.output / "level2.csv", ["bill_id", "question_id", "question", "answer"], out2)
    (args.output / "review.json").write_text(json.dumps(review_by_id, indent=2), encoding="utf-8")
    LOG.info("Generated %s (%d rows) and %s (%d rows)", args.output / "level1.csv", len(out1), args.output / "level2.csv", len(out2))
    LOG.info("Review attention flags in %s; differences may be legitimate printed adjustments", args.output / "review.json")


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
        LOG.error("%s", error)
        raise SystemExit(1) from error

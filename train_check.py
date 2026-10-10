"""Rehearse extraction on a training image and compare the published KE reference."""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from main import ANSWER_PROMPT, EXTRACT_PROMPT, calculation_aids, normalize_bill, request_json, sanitize_history


GOLD = {
    "provider": "KE", "tariff": "A1-R", "sanctioned_load_kw": 3,
    "bill_month": "2026-04", "reading_date": "2026-04-03",
    "issue_date": "2026-04-07", "due_date": "2026-04-21",
    "previous_reading": 8819, "current_reading": 8970, "units_consumed": 151,
    "charges": [
        {"type": "fixed", "amount": 900},
        {"type": "energy", "amount": 1054},
        {"type": "energy", "amount": 663.51},
        {"type": "quarterly_adjustment", "amount": 52.91},
        {"type": "fpa", "amount": 125.27},
        {"type": "surcharge", "amount": 64.93},
    ],
    "total_charges": 2860.62,
    "taxes": [
        {"type": "electricity_duty", "amount": 29.41},
        {"type": "gst", "amount": 520.21},
        {"type": "municipal_tax", "amount": 20},
    ],
    "total_taxes": 569.62, "current_bill": 3430.24, "arrears": -0.53,
    "payable_within_due_date": 3430, "payable_after_due_date": 3716,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="One training image or a folder containing all five images")
    parser.add_argument("--repeat", type=int, default=1, choices=(1, 2), help="Run each image twice and report fields that change")
    parser.add_argument("--answers", action="store_true", help="Also rehearse two guide sample questions on KESC_0008")
    args = parser.parse_args()
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        parser.error("GEMINI_API_KEY is missing in local .env")
    model = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")
    if model != "gemini-3.5-flash-lite":
        parser.error("Only the approved gemini-3.5-flash-lite is configured")
    images = sorted(path for path in args.image.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}) if args.image.is_dir() else [args.image]
    if not images:
        parser.error("No training images found")
    client = genai.Client(api_key=key)
    failures = 0
    for index, image in enumerate(images):
        runs = []
        for attempt in range(args.repeat):
            raw = request_json(client, model, EXTRACT_PROMPT, image)
            bill = normalize_bill(raw.get("bill", raw), image.stem)
            runs.append((bill, sanitize_history(raw.get("history", []))))
            if attempt < args.repeat - 1:
                time.sleep(10)
        bill, history = runs[0]
        print(image.name)
        print(json.dumps({"bill": bill, "history": history}, indent=2, ensure_ascii=False))
        if args.repeat == 2:
            other_bill, other_history = runs[1]
            changed = {field: {"first": bill[field], "second": other_bill[field]} for field in bill if bill[field] != other_bill[field]}
            if history != other_history:
                changed["history"] = {"first": history, "second": other_history}
            print("Repeatability:", "stable" if not changed else json.dumps(changed, indent=2))
            failures += bool(changed)
        if image.stem == "KESC_0008":
            differences = {field: {"expected": expected, "actual": bill[field]} for field, expected in GOLD.items() if bill[field] != expected}
            print("Golden comparison:", "all fields match" if not differences else json.dumps(differences, indent=2))
            failures += bool(differences)
            if args.answers:
                questions = [
                    {"question_id": "S1", "question": "How much of my bill is taxes?"},
                    {"question_id": "S2", "question": "How many months in my history went above 200 units?"},
                ]
                prompt = ANSWER_PROMPT + json.dumps(questions) + "\nExtracted nonidentifying facts: " + json.dumps({"bill": bill, "history": history, "calculated_aids": calculation_aids(bill, history)})
                time.sleep(10)
                answers = request_json(client, model, prompt, image)
                if isinstance(answers.get("answers"), dict):
                    answers = answers["answers"]
                print("Guide sample Level 2 answers:", json.dumps(answers, indent=2, ensure_ascii=False))
                if not all(isinstance(answers.get(q), str) and answers[q].strip() for q in ("S1", "S2")):
                    failures += 1
                    print("Sample answer check failed: S1 and S2 must both be nonempty")
        if index < len(images) - 1:
            time.sleep(10)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

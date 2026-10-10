"""Rehearse extraction on a training image and compare the published KE reference."""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from main import EXTRACT_PROMPT, normalize_bill, request_json, sanitize_history


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
        raw = request_json(client, model, EXTRACT_PROMPT, image)
        bill = normalize_bill(raw.get("bill", raw), image.stem)
        print(image.name)
        print(json.dumps({"bill": bill, "history": sanitize_history(raw.get("history", []))}, indent=2, ensure_ascii=False))
        if image.stem == "KESC_0008":
            differences = {field: {"expected": expected, "actual": bill[field]} for field, expected in GOLD.items() if bill[field] != expected}
            print("Golden comparison:", "all fields match" if not differences else json.dumps(differences, indent=2))
            failures += bool(differences)
        if index < len(images) - 1:
            time.sleep(10)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

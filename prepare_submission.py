"""Audit organizer results and create a submission ZIP from an explicit file allowlist."""

import argparse
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

from main import CHARGE_TYPES, FIELDS, NUMBERS, TAX_TYPES


SOURCE = ("README.md", ".env.example", "requirements.txt", "main.py", "prepare_submission.py", "test_api.py")
SIZE_LIMIT = 15 * 1024 * 1024


def read_csv(path, columns):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != columns:
            raise ValueError(f"Wrong columns in {path}: {reader.fieldnames}")
        result = list(reader)
    if any(None in row for row in result):
        raise ValueError(f"Malformed row in {path}")
    return result


def audit(template, output):
    l1_fields = ["bill_id", "json"]
    l2_fields = ["bill_id", "question_id", "question", "answer"]
    expected_1 = read_csv(template / "level1.csv", l1_fields)
    expected_2 = read_csv(template / "level2.csv", l2_fields)
    actual_1 = read_csv(output / "level1.csv", l1_fields)
    actual_2 = read_csv(output / "level2.csv", l2_fields)
    if not (len(expected_1) == len(actual_1) == 10 and len(expected_2) == len(actual_2) == 120):
        raise ValueError("Expected 10 Level 1 and 120 Level 2 rows")
    for original, current in zip(expected_1, actual_1):
        if original["bill_id"] != current["bill_id"] or not current["json"]:
            raise ValueError("Level 1 ID/order/JSON mismatch")
        value = json.loads(current["json"])
        if not isinstance(value, dict) or set(value) != set(FIELDS):
            raise ValueError(f"Wrong JSON keys for {original['bill_id']}")
        if value["provider"] not in {"KE", "LESCO", "IESCO"}:
            raise ValueError("Invalid provider")
        for field in NUMBERS:
            val = value[field]
            if val is not None and (isinstance(val, bool) or not isinstance(val, (int, float))):
                raise ValueError(f"Invalid number for {field}")
        for name, allowed in (("charges", CHARGE_TYPES), ("taxes", TAX_TYPES)):
            if not isinstance(value[name], list):
                raise ValueError(f"Invalid {name}")
            for item in value[name]:
                if set(item) != {"type", "amount"} or item["type"] not in allowed or isinstance(item["amount"], bool) or not isinstance(item["amount"], (int, float)):
                    raise ValueError(f"Invalid {name} item")
        for field, pattern in (("bill_month", r"\d{4}-\d{2}"), ("reading_date", r"\d{4}-\d{2}-\d{2}"), ("issue_date", r"\d{4}-\d{2}-\d{2}"), ("due_date", r"\d{4}-\d{2}-\d{2}")):
            if value[field] is not None and (not isinstance(value[field], str) or not re.fullmatch(pattern, value[field])):
                raise ValueError(f"Invalid {field}")
    for original, current in zip(expected_2, actual_2):
        if any(original[field] != current[field] for field in ("bill_id", "question_id", "question")) or not current["answer"].strip():
            raise ValueError("Level 2 ID/question/order/answer mismatch")
    print("Audit passed: 10 JSON objects and 120 nonempty answers; templates preserved.")


def package(repo, output, destination, video):
    for filename in SOURCE:
        if not (repo / filename).is_file():
            raise FileNotFoundError(f"Missing source/{filename}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
        for filename in ("level1.csv", "level2.csv"):
            archive.write(output / filename, f"output/{filename}")
        for filename in SOURCE:
            archive.write(repo / filename, f"source/{filename}")
        if video:
            if video.suffix.lower() not in {".mp4", ".mov", ".webm"}:
                raise ValueError("Demo must be MP4, MOV or WEBM")
            archive.write(video, f"demo/demo{video.suffix.lower()}")
    if destination.stat().st_size > SIZE_LIMIT:
        destination.unlink()
        raise ValueError("ZIP exceeds 15 MiB; omit or compress video")
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt ZIP entry")
        names = archive.namelist()
        if any(name.endswith("/.env") or name == ".env" for name in names):
            raise ValueError("Secret .env included")
    print(f"Created {destination} ({destination.stat().st_size / 1024 / 1024:.2f} MiB)")
    print("ZIP members:", ", ".join(names))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates", type=Path, default=Path("test/csv"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--zip", type=Path, default=Path("submission.zip"))
    parser.add_argument("--demo", type=Path)
    args = parser.parse_args()
    audit(args.templates, args.output)
    package(Path(__file__).resolve().parent, args.output, args.zip, args.demo)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

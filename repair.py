"""Targeted, image-grounded checkpoint verification without editing scored CSVs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import main
from pydantic import create_model


VERIFY = """Independently reread ONLY the requested fields from the original bill image.
Ignore previous guesses. Return the required structured JSON; do not include personal identifiers.
Numbers must be copied from PRINTED labelled fields, not calculated from other totals.
Carefully distinguish visually similar leading digits in the Taxes summary. An empty
arrears box is null, even when other arithmetic suggests zero. For late_payables,
return EVERY printed after-due payable amount, including both date tiers, not surcharges.
For history and payments read BOTH halves of the history table, including the first row
overlapped by a header. Read month, units, billed amount and payment on that same row.
Do not omit a readable first row; do not infer or invent any row. Return all printed
rows. Payments of zero are 0; blanks are null. Dates/months use ISO format.
Only return fields requested by the response schema. Missing/unreadable scalar fields
are null. No outside information or training sample values may be used.
"""


def history_month(value):
    """Normalize a printed month label without discarding a history row."""
    text = str(value).strip().replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"(?i)\bsept(?=[\s\-/]|$)", "Sep", text)
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text)
    if match:
        return main.normalized_date(f"{int(match[1]):04d}-{int(match[2]):02d}", r"\d{4}-\d{2}")
    for fmt in ("%Y-%m-%d", "%b-%y", "%b-%Y", "%b %y", "%b %Y", "%B-%y", "%B-%Y", "%B %y", "%B %Y", "%m/%Y", "%m-%Y", "%b/%y", "%b/%Y", "%b%y", "%B%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    raise ValueError(f"Unreadable history month label: {text!r}; verification response saved for diagnosis")


def repair(args):
    main.load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY missing in local .env")
    model = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")
    if model != "gemini-3.5-flash-lite":
        raise ValueError("Only gemini-3.5-flash-lite is permitted by this implementation")
    client = main.genai.Client(api_key=key, http_options=main.types.HttpOptions(timeout=120_000))
    images = main.images_in(args.bills)
    rows = main.load_csv(args.templates / "level2.csv", ["bill_id", "question_id", "question", "answer"])
    groups = defaultdict(list)
    for row in rows:
        groups[row["bill_id"]].append({"question_id": row["question_id"], "question": row["question"]})
    requested = defaultdict(set)
    for spec in args.fields:
        bill_id, separator, fields = spec.partition(":")
        if not separator:
            raise ValueError("--fields entries must be BILL_ID:field,field")
        for field in fields.split(","):
            if field not in main.NUMBERS:
                raise ValueError(f"Unsupported verification field: {field}")
            requested[bill_id].add(field)
    ids = sorted(set(requested) | set(args.history) | set(args.late))
    if not ids:
        raise ValueError("Select --fields, --history or --late")
    code_hash = hashlib.sha256(Path(main.__file__).read_bytes()).hexdigest()
    verifier_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for bill_id in ids:
        image = images[bill_id]
        questions = groups[bill_id]
        path = main.safe_cache_path(args.cache, bill_id)
        cached = json.loads(path.read_text(encoding="utf-8"))
        fingerprint = hashlib.sha256(image.read_bytes() + json.dumps([model, code_hash, questions], sort_keys=True).encode()).hexdigest()
        if cached.get("fingerprint") != fingerprint:
            raise ValueError(f"Checkpoint does not match current image/code/questions: {bill_id}; do not delete it")
        fields = sorted(requested[bill_id])
        signature = hashlib.sha256(json.dumps([fingerprint, verifier_hash, fields, bill_id in args.history, bill_id in args.late]).encode()).hexdigest()
        if not args.force and signature in cached.get("verified_repairs", []):
            main.LOG.info("[Bill: %s] Verified checkpoint reused", bill_id)
            continue
        bill = main.normalize_bill(cached["bill"], bill_id)
        history = main.sanitize_history(cached.get("history", []))
        payments = cached.get("payments", [])
        answers = dict(cached["answers"])
        schema_fields = {field: (float | None, ...) for field in fields if field != "payable_after_due_date"}
        if "payable_after_due_date" in fields:
            schema_fields["late_payables"] = (list[float], ...)
        if bill_id in args.history:
            schema_fields.update(history=(list[main.HistoryLine], ...), payments=(list[main.PaymentLine], ...))
        if schema_fields:
            schema = create_model("VerifiedPrintedFields", **schema_fields)
            prompt = VERIFY + "\nRequested fields: " + ", ".join(schema_fields) + "\nBill month context: " + str(bill["bill_month"])
            response_path = path.with_suffix(".verification_response.json")
            if response_path.exists() and not args.force:
                raw = json.loads(response_path.read_text(encoding="utf-8"))
                schema.model_validate(raw)
            else:
                raw = main.request_json(client, model, prompt, image, schema=schema)
                main.checkpoint(response_path, raw)
            verified = schema.model_validate(raw).model_dump()
            for field in fields:
                if field == "payable_after_due_date":
                    values = [main.number(v) for v in verified["late_payables"]]
                    bill[field] = max(values) if values else None
                else:
                    bill[field] = main.number(verified[field])
            if bill_id in args.history:
                history = [{"month": history_month(r["month"]), "units": main.number(r["units"])} for r in verified["history"]]
                payments = [{"month": history_month(r["month"]),
                             "billed_amount": main.number(r["billed_amount"]),
                             "payment": main.number(r["payment"])} for r in verified["payments"]]
                for name, entries in (("history", history), ("payments", payments)):
                    if len({r["month"] for r in entries}) != len(entries):
                        raise ValueError(f"Duplicate {name} month: {bill_id}")
                wanted = {main.shift_month(bill["bill_month"], -n) for n in range(1, 13)}
                missing = wanted - {r["month"] for r in history} | wanted - {r["month"] for r in payments}
                if missing:
                    row_schema = create_model("MissingPrintedRows", history=(list[main.HistoryLine], ...), payments=(list[main.PaymentLine], ...))
                    row_prompt = (VERIFY + "\nReread these specific history months: " + json.dumps(sorted(missing)) +
                                  "\nThe FIRST data row on EACH half overlaps the MONTH/UNITS/BILL/PAYMENT header. "
                                  "Read the numbers immediately under/overlapping the header, not just rows below it. "
                                  "Return only the requested months and printed numbers; do not invent a row.")
                    row_image = getattr(args, "history_image", None) or image
                    extra = main.request_json(client, model, row_prompt, row_image, schema=row_schema)
                    extra = row_schema.model_validate(extra).model_dump()
                    for name, entries in (("history", history), ("payments", payments)):
                        merged = {r["month"]: r for r in entries}
                        for row in extra[name]:
                            row["month"] = history_month(row["month"])
                            if row["month"] in missing:
                                merged[row["month"]] = row
                        entries[:] = sorted(merged.values(), key=lambda r: r["month"])
                if not wanted.issubset({r["month"] for r in history}) or not wanted.issubset({r["month"] for r in payments}):
                    raise ValueError(f"Reread still lacks a full 12-month history for {bill_id}; original checkpoint retained")
            bill = main.normalize_bill(bill, bill_id)
            answers.update(main.deterministic_answers(bill, history, payments, questions))
        if bill_id in args.late:
            pending = [q for q in questions if "late payment surcharge" in q["question"].lower()]
            if not pending:
                raise ValueError(f"No late-payment question for {bill_id}")
            schema = create_model("VerifiedLateAnswers", **{q["question_id"]: (str, ...) for q in pending})
            prompt = (main.ANSWER_PROMPT + json.dumps(pending) +
                      "\nIndependently inspect the entire payment totals panel and both printed date tiers. "
                      "A first late amount can be printed twice in two locations; do not mistake that "
                      "for absence of the second tier. State both surcharge amounts and inclusive date windows. "
                      "A tier labelled AFTER a cutoff starts the following day, not on that cutoff. "
                      "Give dates as YYYY-MM-DD where legible. Distinguish the added surcharge from total payable. "
                      "Do not use previous answer text or external tariff rates.")
            verified_answers = schema.model_validate(main.request_json(client, model, prompt, image, schema=schema)).model_dump()
            if any(not value.strip() for value in verified_answers.values()):
                raise ValueError(f"Empty verified answer for {bill_id}")
            answers.update(verified_answers)
        if any(not isinstance(answers.get(q["question_id"]), str) or not answers[q["question_id"]].strip() for q in questions):
            raise ValueError(f"Incomplete answers for {bill_id}")
        backup = path.with_suffix(".before_repair.json")
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        cached.update(bill=bill, history=history, payments=payments, answers=answers)
        cached.setdefault("verified_repairs", []).append(signature)
        main.checkpoint(path, cached)
        main.LOG.info("[Bill: %s] Image verification saved; fields=%s, history rows=%d", bill_id, fields, len(history))
    main.run(argparse.Namespace(bills=args.bills, level1_template=args.templates / "level1.csv",
                               level2_template=args.templates / "level2.csv", output=args.output,
                               cache=args.cache, pause=0))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bills", type=Path, default=Path("test/bills"))
    parser.add_argument("--templates", type=Path, default=Path("test/csv"))
    parser.add_argument("--cache", type=Path, default=Path(".cache_test"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--fields", nargs="*", default=[])
    parser.add_argument("--history", nargs="*", default=[])
    parser.add_argument("--history-image", type=Path, help="Optional cropped history region from the same bill")
    parser.add_argument("--late", nargs="*", default=[])
    parser.add_argument("--force", action="store_true", help="Reread already verified selections")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        repair(parse_args())
    except Exception:
        main.LOG.exception("Targeted verification failed; existing outputs and unrepaired checkpoints are retained")
        raise SystemExit(1)

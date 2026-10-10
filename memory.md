# Working memory and handoff

Updated 10 October 2026, 13:23 Pakistan time.

## Environment and authorization
Repository https://github.com/Raazia-Imran/10pearl, main. User's Windows clone D:\10pearl-repo. Private GEMINI_API_KEY remains in ignored local .env. Runtime exclusively gemini-3.5-flash-lite. ChatGPT/OpenAI Codex coding assistance disclosed. Never request, print or commit the key.

## Rules
Guide is final authority. Single ZIP upload by 13:30 PKT unless organizers announce extension. Exact original CSV headers/order/IDs/questions; 10 Level 1 objects, exactly 18 fields; 120 nonempty Level 2 answers. Printed values, null for absent/blank, negative credits/subsidies, no identifiers. No manual scored CSV edits or hardcoded test values. ZIP <=15,000,000 bytes with both outputs, all runnable source, README, pinned direct dependencies and .env.example. Exclude .env. Optional demo <=3 minutes.

## Actual generated outputs audited
User supplied generated level1(1).csv, level2(1).csv and review.json. Actual row/schema/type/date/template checks passed: 10/120, all 18 fields, 120 unique question pairs, zero empty answers, no string null/N/A, no PII found, all subsidies negative. This does not establish image accuracy.
Confirmed image discrepancies: IESCO_0002 total_taxes read 3516 but printed 8516; first 2025-08 history/payment row omitted (printed units721, billed/payment80594). This corrupts Q2,Q5,Q6,Q7,Q8,Q10,Q11. Correct previous history units total4129, average344.08; summer1658 vs winter473; yearly bill sum320007, monthly budget26667.25. IESCO_0003 Q4 omitted printed second late tier (62 through2026-10-15,124 after). KESC_0003 Q4 wrongly begins second tier on cutoff2026-09-27 rather than after. LESCO_0008 blank arrears became0, should null; highest late payable2051, not1981. These are audit observations only, never runtime hardcoded values. Detailed LESCO FPA not doubled; KE financial history correctly limited to three rows. Other numerical answers checked against printed history. LESCO_0001/0002 cutoff text printed partly clipped as01-CT; do not invent missing date glyphs.

## Repair pushed and local tests
Added repair.py, documented it, included it in prepare_submission.py SOURCE allowlist. main.py untouched intentionally: its SHA fingerprints existing successful caches. repair.py rereads selected fields/history/late question from ORIGINAL image with typed permitted model; verifies fingerprint; regenerates Python numerical answers; atomically replaces only selected checkpoints; keeps original backup; reruns original pipeline to write all outputs. It has no hardcoded bill values and no manual scored cell edits. Verified repairs reuse cache identically. Mocked tests passed four requests, backups, unaffected checkpoints, null/highest late selection, history calculations, 10/120 template preservation, identical rerun. Original full pipeline regression tests also passed. Actual Gemini repairs still require user's local key and visual check.

## User's immediate command
Set-Location "D:\10pearl-repo"
git pull origin main
python repair.py --bills "test\bills" --templates "test\csv" --cache ".cache_test" --fields "IESCO_0002:total_taxes" "LESCO_0008:arrears,payable_after_due_date" --history IESCO_0002 --late IESCO_0003 KESC_0003

Await regenerated output/level1.csv and output/level2.csv for final validation. If repair errors, original outputs and checkpoints remain; inspect traceback, do not delete all caches. Then package using python prepare_submission.py --templates "test\csv" --output "output" --zip "submission.zip". Portal submission/receipt not yet observed. Prioritize valid upload before deadline; no guarantee of full marks.

# Design — CLI and answer style

## User journey
Operator places organizer `test/bills` images and two unchanged templates alongside source, sets a local key in `.env`, runs one documented command, and receives `output/level1.csv` plus `output/level2.csv`. Console shows stage and count, not private data. A second verification command checks counts, schema and package. A GUI is optional and lower priority than reliable output.

## Console experience
```text
10 images matched to 10 Level 1 rows; 120 questions across 10 bills.
[1/10] IESCO_0002  extraction ✓  answers 12/12 ✓
...
Validation: Level 1 10/10; Level 2 120/120; unchanged template columns ✓
Submission ZIP: 12.4 MB, required members ✓, secrets absent ✓
```
These lines are illustrative, not observed outputs. On failures print bill_id, stage and actionable error, save successfully completed bill checkpoints, exit nonzero if any cell would be empty. Never claim success when the API failed.

## Prompt design
Extraction system guidance: read only visible bill; return allowed structured JSON; no PII; distinguish printed subtotal from sum; preserve charge/tax section and duplicate line items; credits negative; no inference for hidden/blurred/absent values; capture safe month/unit history separately. Schema-first output and JSON-mode where supported. Ask for evidence for uncertain fields internally, then omit it from scored Level 1 JSON.

Answer system guidance: answer every original question ID in English from the attached image and sanitized evidence only; give exact printed values, units and simple calculations; explain estimates; disclose ambiguity; say missing instead of guessing; never output PII. Return a JSON mapping `question_id -> answer` for reliable parsing. Responses should be short, direct and specific; for numerical claims include enough computation to audit.

## Accuracy checks
- KESC_0008 expected values in guide §5.7: KE, A1-R, 3 kW, 2026-04, 151 units, charges 2860.62, taxes 569.62, current 3430.24, arrears -0.53, due 3430, late 3716. This is the one provided reference; manually inspect image against expected data as a development check.
- LESCO and IESCO training samples cover their distinct layouts and partially obscured fields. Exercise rotations, small text, credits and mixed Urdu if present; do not assume the training file labels encode dates/amounts.
- Prevent answers that treat `payable_within_due_date` as `current_bill` or fold arrears into taxes.
- For history questions, distinguish previous 12 months from the current month. State which months are counted if ambiguous.

## Demo storyboard (only after submission outputs validate)
Keep <=3 minutes and small enough for <=15 MB ZIP: run CLI; show image with identifiers covered; show key Level 1 JSON fields and several Level 2 answers for same bill; show both generated test CSVs and final validation. Windows Snipping Tool recorder: Win+Shift+R. Hide environment variables, API key, account numbers and personal data. A terminal-first demonstration satisfies the guide; no hosted app is required.

# Working memory and handoff

Updated 10 October 2026, 12:53 Pakistan time.

## Environment and authorization
Repository: https://github.com/Raazia-Imran/10pearl, main. User's Windows clone: D:\\10pearl-repo. Private working GEMINI_API_KEY is in local ignored .env. Only gemini-3.5-flash-lite is used at runtime. ChatGPT / OpenAI Codex coding assistance is disclosed in README. Do not request, print or commit the key.

## Rules
Participant guide is final authority. Submit one ZIP by 13:30 PKT unless organizers explicitly change the deadline. Exact original CSV headers/rows/IDs/questions: Level 1 10 rows with all 18 fields; Level 2 120 nonempty answers. Printed bill values only, null for missing, negative credits/subsidies, no identifiers. No manual scored CSV edits or hard-coded test values. ZIP <=15,000,000 bytes includes outputs, all runnable source, README, exact direct dependency pins and .env.example, never .env. Optional video <=3 minutes.

## Observed inputs and verification
Test folder is live: https://drive.google.com/drive/folders/1MkiTNs-lBSFwET9R--RBCx7FiatO9zQp. Ten attached images and both blank templates were read. Test IDs: IESCO_0002, IESCO_0003, IESCO_0005, KESC_0002, KESC_0003, KESC_0005, KESC_0006, LESCO_0001, LESCO_0002, LESCO_0008. All 120 rows use twelve question types about solar, history maxima, FPA period, late tiers, year comparisons, average units, seasons, payment history, trends, forecast, budget and approximate bill.
User's latest training run passed KESC_0008 golden comparison and sample numerical answers. All five training images were run on the prior version. New code was syntax checked and tested with mocked responses using the ACTUAL released templates: arithmetic edge cases, 10/120 rows, exact template preservation, cache reuse, changed-image invalidation, ZIP allowlist. These checks do not verify live model image accuracy.

## Current code
main.py extracts typed bill fields plus usage/payment history. Python computes nine numerical question types when evidence permits; one typed Gemini request handles remaining visual questions per bill. Models never infer twelve KE financial rows from a thirteen-month usage chart (only three financial rows are printed). Detailed LESCO composite Total FPA is not added twice. Categories are typed enums; printed labels normalize QTA/MUCT/ED on FPA. Estimates state method/limitations. Cache includes image/code/model/question fingerprints, atomic writes, timeout/backoff, bill-level recovery. Packaging validates finite numbers, calendar dates, single-line JSON, exact row counts/order and <=15MB. Actual key remains unavailable in agent environment.

## Next action
User was instructed to pull and run main.py on test/bills and test/csv with --cache ".cache_test" --pause 12. Await GENERATED output/level1.csv, output/level2.csv and output/review.json for image-by-image review. Do not assume attached blank templates are outputs. Keep checkpoints for restart. Fix code and regenerate if errors emerge; never hand-fill results. Then package and inspect submission.zip, optional demo if time, user uploads once and keeps receipt. Final scored output generation and portal submission are NOT yet observed.

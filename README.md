# Utility Bill Decoder — WTQ Build Track 2026

Python 3.11+ CLI using Google's Gemini 3.5 Flash-Lite to read KE, LESCO and IESCO bill images and answer the organizer's 12 questions per bill. The program generates both output CSVs directly from the original templates. No hosted service is needed.

## Setup (Windows Command Prompt)

```bat
cd /d "D:\10pearl-repo"
python --version
python -m pip install -r requirements.txt
copy .env.example .env
```

Edit only your local `.env` and replace the placeholder with the Google AI Studio key you already tested. If `.env` already contains `GEMINI_API_KEY`, keep it. Never commit or include `.env` in the submission. The model is `gemini-3.5-flash-lite`; `MODEL_NAME` may be omitted because this is the default.

Before the test release, download all five training images to `train\bills` and run `python train_check.py "train\bills"`. It prints each extraction and compares KESC_0008 to every field in the guide's published expected JSON. For repeatability, run `python train_check.py "train\bills" --repeat 2`: it reports any changing fields and exits nonzero. A nonzero exit means inspect the image; it does not prove which run is correct. Running one image also works.

To rehearse Level 2 before the real test questions arrive, run `python train_check.py "train\bills\KESC_0008.png" --answers`. It asks the two **sample** questions in guide §6.2. Inspect that the tax answer uses PKR 569.62 / 3,430.24 (about 16.6%) and the history answer counts July and August 2025, 239 and 203 units. These sample questions are not the released test questions.

Download the organizer's `test/bills/` images and *both original* `test/csv/` templates to the corresponding paths below. These files are released at 12:30 Pakistan time. For PowerShell, use `Set-Location "D:\10pearl-repo"` instead of `cd /d`.

```text
D:\10pearl-repo\
  main.py
  prepare_submission.py
  requirements.txt
  .env
  test\bills\ (10 PNG/JPG images)
  test\csv\level1.csv
  test\csv\level2.csv
```

## Run

```bat
python main.py --bills "test\bills" --level1-template "test\csv\level1.csv" --level2-template "test\csv\level2.csv" --output "output" --cache ".cache_test" --pause 12
python prepare_submission.py --templates "test\csv" --output "output" --zip "submission.zip"
```

The first command writes `output/level1.csv` and `output/level2.csv`. The second checks the original template columns/row order, all 10 JSON objects, 120 nonempty answers, required schema and ZIP contents/size. It packs exactly the required result files and source allowlist under `output/` and `source/`. Upload `submission.zip` once at https://build.womentechquest.com/submit before 1:30 PM Pakistan time. Do not upload the GitHub repository alone.

Inspect `output/review.json` before packaging. It flags inconsistent printed totals, taxes, readings and dates for manual review; flags are not automatic corrections because net metering, FPA and adjustments can legitimately differ. Compare suspicious values and a sample of Level 2 numeric answers directly with the images. Fix the prompt/code and regenerate rather than editing CSV cells. Delete a `.cache/<bill_id>.json` file to force that bill to be processed again.

For the optional <=3-minute demo, record the image, command, a few values/answers and both generated CSVs, then run `python prepare_submission.py --demo "demo.mp4"` to include it only if the ZIP remains <=15 MB. If the video is large, omit it and prioritize the submission.

## Implementation

The code matches each template `bill_id` to an image, asks the allowed multimodal model for the specified billing schema and nonidentifying monthly usage history, normalizes printed values and types, then submits all questions for that bill in one image-grounded request. A per-bill `.cache/` checkpoint helps reruns after quota/timeouts; retry transient failures. Rows are generated with Python's `csv` module, preserving the original fields and order. No customer identifiers are requested or emitted; unavailable bill fields are `null`. Rate pacing defaults to ten seconds between bills; use `--pause 15` if a lower account limit requires it. Checkpoints are keyed by the image content, source code, model and exact questions. Changed input or code automatically invalidates old results. Keep the cache on restart; delete only a specific bill checkpoint if a fresh model read is needed. Cache and CSV writes use atomic replacement.

The model may make reading or reasoning mistakes on difficult scans. Review the printed due/late totals, itemized charges/taxes, signs, history chart and numeric answers against the images before uploading. Correct the code or prompt and regenerate outputs; never manually edit scored result cells. The training sample KESC_0008 has the guide's full expected JSON in §5.7, useful as a reference check.

## Numerical answer validation

The same released question types are handled from extracted evidence and question text, without hard-coded bill values. Python calculates history maxima, same-month year comparisons, twelve-month averages, summer/winter totals, recent trends, seasonal baseline forecasts, recorded payment coverage, historical budgets and rough bill estimates. The previous twelve completed months exclude the current month. Three-month KE financial history is never presented as twelve months. Estimates state their assumptions and are not exact tariff predictions. Printed Level 1 values are never changed to make arithmetic reconcile.

Gemini performs typed extraction of all eighteen bill fields, usage history and billing/payment history in one request per bill. Remaining visual questions are answered together in one typed response. Both charge and tax categories are schema enums. API calls have a two-minute timeout, bounded backoff, bill-level failure recovery and resumable checkpoints. A failed bill prevents a misleading complete submission.

Local tests with the actual released template structure verified 10/120 rows, exact headers/IDs/questions/order, arithmetic edge cases, cache reuse and invalidation, and the ZIP allowlist. These used mocked API responses; they do not establish live image accuracy. Check the real outputs against the bills before submitting.

## AI usage and dependencies

- Runtime model: **Gemini 3.5 Flash-Lite**, model ID `gemini-3.5-flash-lite`, via Google Gemini API / Google AI Studio free API key and `google-genai==2.29.0`. It reads bill images, extracts structured values and drafts English answers. No other runtime LLM or AI extraction service is used.
- AI tools used to help write code and planning documentation: **ChatGPT / OpenAI Codex**. The participant guide expressly permits AI coding assistants. If other tools are used later, add their actual names here before packaging.
- Other services: none. Local libraries: `python-dotenv==1.2.4`, `pydantic==2.14.0` for typed Gemini extraction responses, plus Python standard library `csv`, `json`, `zipfile`, etc. OCR/invoice-agent services: none.
- Python: 3.11 or later. `requirements.txt` pins all three direct non-standard packages exactly.

The real key is read as `GEMINI_API_KEY` from the local `.env`; `.env.example` contains a placeholder and the actual nonsecret model name. The application rejects any model name other than the permitted `gemini-3.5-flash-lite`.

## Targeted image verification

Use `repair.py` when image review finds a suspicious numeric field, missing history row or incomplete late-payment answer. It calls the same permitted model for selected image regions/fields, validates the reread, regenerates Python numerical answers and writes both CSVs through the original pipeline. It does not hard-code bill values or manually edit scored CSV cells. `--fields BILL_ID:field,field` selects numeric fields; `--history BILL_ID` rereads a complete twelve-month usage/payment table; `--late BILL_ID` rereads the late-payment question. Original checkpoints are backed up before replacement; verified selections are reused on rerun. The tool rejects checkpoints whose image, main code or questions have changed. Keep existing successful checkpoints.

```bat
python repair.py --bills "test\bills" --templates "test\csv" --cache ".cache_test" --fields "BILL_ID:total_taxes" --history BILL_ID
```

Replace `BILL_ID` with an actual template ID. After verification, inspect the regenerated CSVs against the image and run `prepare_submission.py` as above. Mocked tests cover targeted requests, backup preservation, calculation regeneration, 10/120 output integrity and identical cached reruns; actual Gemini readings still require visual review.

## Complete source and runtime disclosure

Runtime inference and all image verification use only Google's `gemini-3.5-flash-lite`, via `google-genai==2.29.0`. Coding, planning, refactoring, tests and review were assisted by ChatGPT / OpenAI Codex. Google AI Studio supplies the participant's API key; no OpenAI API, paid cloud model, separate OCR engine, hosted backend, database or trained/fine-tuned model is used. Google Cloud credits are not required by this implementation. If the participant used any additional coding assistant, its actual name must be added to this disclosure before submission; do not list a tool merely because it was available.

`main.py` contains the extraction and answer prompts, typed schemas, normalization, deterministic arithmetic, retry policy, checkpoint fingerprinting and original-template CSV writer. `repair.py` performs additional evidence-based image verification for selected fields, overlapping history rows, month-keyed financial entries and late-payment tiers. `prepare_submission.py` validates CSV structure and creates the allowlisted ZIP. `train_check.py` exercises sample images and the published golden sample; `test_api.py` checks basic API access. `.env.example` documents supported variables without credentials; `requirements.txt` pins direct dependencies. README is the operating manual. No program contains hard-coded scored bill amounts or manually filled question answers.

### Environment and reproducibility

Only `GEMINI_API_KEY` is required. `MODEL_NAME` defaults to the permitted model and is checked explicitly. `MODEL_PROVIDER` is disclosure metadata, not a provider switch. Install dependencies with `python -m pip install -r requirements.txt`, retain the local private `.env`, and preserve `.cache_test`. Do not overwrite a working key with the example placeholder. Environment-variable examples and operational defaults are documented in `.env.example`; timeouts, temperature, retry limits and response schema are in source. Temperature zero does not guarantee identical independent model reads; validated checkpoint reuse produces identical saved results for unchanged inputs. Changing main code, questions, image or model invalidates original fingerprints. Verification preserves main.py and the successful base checkpoints.

### Verification and known limitations

Financial rereads use a required response property for every previous-month key, reducing accidental shifts between dates and BILL/PAYMENT columns. Python then calculates payment coverage and annual budgets from those rows. Late-fee verification extracts numeric surcharge tiers and the printed cutoff; Python constructs the first late day from the actual bill due date plus one day and starts the higher tier after the cutoff. Both retain the original image as authority. Optional history crops must come from the same source bill and contain no added/corrected numbers. Cropping assists readability; it is not model training. Source-level mocked tests verify arithmetic, schemas, checkpoints, date windows and file packaging; they do not prove every live image reading is correct. Template/type checks and image accuracy are separate checks. Printed inconsistencies and rounding are retained rather than silently reconciled.

### Submission and demo

ZIP structure is `output/level1.csv`, `output/level2.csv`, and `source/` containing every runnable source file, README, requirements and `.env.example`. Optional `demo/demo.mp4` (or .mov/.webm) is added only with the packaging `--demo` argument. The archive excludes customer images, checkpoints, generated review diagnostics and real `.env`. It must remain at most 15,000,000 bytes. Do not copy folders or modify scored cells manually.

Record a concise demo of at most three minutes, preferably about one minute: explain the CLI and sole runtime model, show the command producing 10 extraction rows and 120 answers, display one nonidentifying extraction and one calculation, show checkpoint reuse and the packaging audit. Do not display the private .env, account/customer identifiers or API key. Save the video beside the source as `demo.mp4` and package using `python prepare_submission.py --templates "test\\csv" --output "output_checked" --zip "submission_checked.zip" --demo "demo.mp4"`. If the video makes the ZIP exceed the limit, omit it and upload the valid result/source ZIP. Use the organizer-announced extended deadline and portal instructions, not the README's original schedule, if the schedule changes. A successful packaging message is not proof of portal upload; retain the submission receipt.

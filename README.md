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

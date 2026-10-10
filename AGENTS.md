# Agent instructions — 10pearl WTQ Build Track

Read [prd.md](prd.md), [rules.md](rules.md), [architecture.md](architecture.md), [design.md](design.md), [tasks.md](tasks.md) and [memory.md](memory.md) before changing implementation. The [participant guide](https://drive.google.com/file/d/1FIzOuil-oJ2nuiempoMDkZojyRivzI1U/view) is the final authority if these notes conflict. Timezone is Pakistan Standard Time; submission is 10 October 2026 by 13:30. Keep a runnable artifact ahead of polish.

## Work order
1. Inspect repo and five training images. Implement an image-to-structured-data pipeline using only the configured, allowed `gemini-3.5-flash-lite` model. Existing `test_api.py` confirms the user's local key works; never print or commit it.
2. Validate Level 1 structure, number/date/sign conversion and provider-specific layouts. Compare KESC_0008 to guide section 5.7. Never infer covered data or correct printed arithmetic.
3. Implement Level 2 answering from image plus sanitized extracted evidence, batched by bill, with deterministic numerical checks. Actual questions are unknown until release.
4. Read both organizer templates unchanged. Match images to `bill_id`. Write `output/level1.csv` and `output/level2.csv` with the csv library. Preserve all original input columns and row order.
5. At 12:30 run on test images; resolve exceptions and empty cells, then build and inspect a ZIP <=15 MB. Record optional <=3-minute demo only after valid outputs exist. Submit once before 13:30.

## Non-negotiable guardrails
- Allowed runtime LLM list is in [rules.md](rules.md); default to user's working free Gemini key. AI coding helpers are allowed and must be listed by actual name in submission `source/README.md`.
- Avoid real `.env`, secrets, personal identifying details in Git commits, logs, prompts, answers, output, demo, and ZIP. Image calls will necessarily send the provided bill to the chosen model; do not reproduce identifier regions in text.
- All schema keys present; unavailable = null; list unavailable = []; nonzero printed lines only; duplicates kept. Distinguish `KESC` filename from `KE` JSON provider.
- No fabricated figures. Do not silently replace missing answers with plausible values. Make error states visible, retry transient API errors, checkpoint completed bills to survive rate limits and reruns.
- Tests should target challenge-specific failure modes: KESC_0008 golden example; CSV 10/120 headers/order/nonempty; numeric/date types; no secrets; ZIP content and size. Avoid time-consuming speculative features.
- Only the program fills result files. No manual edits to scored CSV cells. Keep exact pinned package versions, complete source and reproducible commands.

## Local workflow
User's Windows repo is `D:\10pearl-repo`; prior scratch folder `D:\ALL PROJECTS\10pearl` is separate. Use `cd /d "D:\10pearl-repo"` in Command Prompt or `Set-Location "D:\10pearl-repo"` in PowerShell. Local `.env` already exists and is ignored; inspect variable *names*, never display values. Commit source/docs; do not commit `.env`, downloaded personal bills, generated ZIP, or answer files unless explicitly intended.

## Handoff
Update [memory.md](memory.md) with implemented facts, tested evidence, current blocker, next exact command and submission state. Do not claim a test or submission succeeded unless observed.

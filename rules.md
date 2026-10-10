# Rules and grading contract

Primary reference: [WTQ Build Track Participant Guide](https://drive.google.com/file/d/1FIzOuil-oJ2nuiempoMDkZojyRivzI1U/view), especially §§3,5–9. Follow the guide when wording here differs.

| Item | Required rule |
| --- | --- |
| Deadline | 10 October 2026, by 13:30 Pakistan time; one ZIP, one submission, no resubmission. |
| Test release | 12:30; 10 unseen bills and 10-row / 120-row CSV templates. |
| Runtime | Python 3.11+ or Node 22+; exact version pins and run instructions. |
| LLMs allowed | Claude Haiku 4.5 (`claude-haiku-4-5`), Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`), Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`), GPT-4.1 mini (`gpt-4.1-mini`), GPT-5 mini (`gpt-5-mini`). Other LLMs disqualify. |
| Free option | Gemini 3.5 Flash-Lite via Google AI Studio key; guide lists free tier 15 RPM, 250K TPM, 500 requests/day. No paid OpenAI key needed. |
| AI help | Chatbots and coding assistants allowed; disclose every AI tool used to write code in `source/README.md`, plus every runtime model/API/service actually used. |
| Prohibited | Azure services and invoice/receipt extraction agents, including Azure prebuilt-invoice, Textract AnalyzeExpense and Mindee. Local OCR such as Tesseract/PaddleOCR is allowed. |
| ZIP | <=15 MB; `output/level1.csv`, `output/level2.csv`, `source/README.md`, `source/.env.example`, complete source, exactly pinned requirements. Optional `demo/demo.mp4` / .mov / .webm <=3 min. |
| Secret hygiene | Never package the real `.env` or API key; placeholders only in example. |

## Extraction rules (§5)
All 18 root keys: provider, tariff, sanctioned_load_kw, bill_month, reading_date, issue_date, due_date, previous_reading, current_reading, units_consumed, charges, total_charges, taxes, total_taxes, current_bill, arrears, payable_within_due_date, payable_after_due_date. All keys must exist; a missing value is JSON null (arrays []); use real JSON numbers. Provider `KE` for KESC filenames. Tariff exact. Load is kW. Dates normalized YYYY-MM-DD, month YYYY-MM. Values are printed amounts in PKR, without currency/comma; never recalculate or round the bill's printed values. Preserve sign for arrears and CR; subsidy negative. No names, addresses, CNIC, account/reference/consumer/meter numbers.

Charges: each nonzero printed line in *charges section*, duplicate types separate. Types: energy, fixed, fpa (FPA/FCA), quarterly_adjustment (QTA), surcharge, meter_rent, subsidy, other. Taxes: each nonzero line in *tax/government section*, classify by location; types gst (including GST on FPA), electricity_duty, income_tax, municipal_tax (KE MUCT/KMC), other_tax (incl TV fee if in tax section). If only combined tax total appears, `taxes=[]` and printed `total_taxes`. Printed subtotal or null. Late payable: highest of several late amounts.

## Answer rules (§6)
120 original questions, one answer per row, in English. Ground solely in the bill; calculate averages, differences, counts and percentages correctly; state interpretation if ambiguous; label and explain estimates; say unavailable when input isn't shown. Do not include identifiers.

## Output rules (§7)
Write from templates programmatically, never manual edits. Preserve headers and row order, bill_id/question_id/question byte-for-byte as CSV field values. Use UTF-8 and standard CSV quoting; JSON must occupy one line of its cell. No empty result cells. Inspect both resulting CSVs and ZIP before the single upload.

## Scoring (§8)
Extraction 30; answer quality 30; engineering 15; AI design 15; completeness/reproducibility 10; demo up to 5 extra. Accuracy and completed output take precedence over presentation.

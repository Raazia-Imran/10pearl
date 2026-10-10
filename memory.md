# Working memory and handoff

Updated 10 October 2026, before the 12:30 Pakistan time test release. This file records observed facts, not generated conclusions or unverified success.

## Known environment
- GitHub repository: https://github.com/Raazia-Imran/10pearl, default branch `main`. Before these planning files it contained `.gitignore`, `README.md`, `test_api.py`.
- User's Windows clone: `D:\10pearl-repo`. Earlier scratch folder `D:\ALL PROJECTS\10pearl` is separate. The user ran `python test_api.py` in the clone and observed `API test successful.`; commit `09be799` was pushed. The user copied a local `.env` into the clone but did not stage it. Do not expose its contents.
- User has a Google AI Studio API key under project `Bol-ai`; Gemini usage screen showed `Gemini 3.5 Flash Lite`. Free option is expressly allowed by guide §9.
- Competition folder: https://drive.google.com/drive/folders/1FSKmeJs5bUYYigS9YATJQ8Fm8diW-XNl. Guide PDF is [here](https://drive.google.com/file/d/1FIzOuil-oJ2nuiempoMDkZojyRivzI1U/view). Training images: IESCO_0004.jpg, KESC_0004.png, KESC_0008.png, LESCO_0005.png, LESCO_0006.png. Test folder was empty when checked before release.
- Guide says AI coding assistants and chatbots are allowed, but every AI tool used must be listed in the submission README. Allowed runtime model `gemini-3.5-flash-lite`; no OpenAI payment required. No disallowed model may be called.
- Actual test images and 12 test questions are unknown until 12:30. Do not assert sample questions are the test questions.

## Reference checks
Guide §5.7 gold KESC_0008: provider KE, tariff A1-R, sanctioned 3, bill month 2026-04, reading 2026-04-03, issue 2026-04-07, due 2026-04-21, readings 8819/8970, units 151; charges fixed900, energy1054, energy663.51, QTA52.91, FPA125.27, surcharge64.93; total charges2860.62; ED29.41, GST520.21, municipal20, total taxes569.62; current3430.24; arrears -0.53; due3430; late3716.

## Current status and next step
Planning documents created from full participant guide. **Implementation, test run, final CSVs, ZIP and portal submission have not yet been verified.** Next: implement and run the image pipeline in the repo; obtain test folder and both templates at 12:30; generate and audit CSVs; submit one ZIP before 13:30. Update this section as steps complete. See [tasks.md](tasks.md) for ordered actions.

# Report - s2t-bru - 2026-04-08

## Summary
- Installing Bruno CLI into `F:\DevTools\Portable\BrunoCli`.
- Building a Bruno collection for the useful `speech2text.ru` requests from the captured browser log.
- Adding `cmd` and Python wrappers so the collection can be driven from scripts.
- Extracting live `speech2text.ru` cookies from the local Yandex Browser profile and applying them to the Bruno environment.

## Files
- `F:\Projects\s2t-bru\collection\bruno.json` - Bruno collection root config.
- `F:\Projects\s2t-bru\collection\collection.bru` - shared collection headers and docs.
- `F:\Projects\s2t-bru\collection\environments\local.bru` - default runtime variables.
- `F:\Projects\s2t-bru\collection\10-open-a-list.bru` - main list page request.
- `F:\Projects\s2t-bru\collection\15-get-current-rate.bru` - current rate request.
- `F:\Projects\s2t-bru\collection\20-open-job.bru` - job page request by `job_id`.
- `F:\Projects\s2t-bru\collection\30-check-queue.bru` - queue poll request by `job_id`.
- `F:\Projects\s2t-bru\collection\40-download-txt.bru` - text download request by `audio_file_name`.
- `F:\Projects\s2t-bru\collection\50-download-wav.bru` - wav download request by `job_id` and `audio_file_name`.
- `F:\Projects\s2t-bru\collection\60-get-csrf-token.bru` - csrf token request.
- `F:\Projects\s2t-bru\collection\70-bind-to-ws.bru` - websocket bind POST request.
- `F:\Projects\s2t-bru\speech2text.py` - importable Python wrapper and CLI entry point.
- `F:\Projects\s2t-bru\speech2text.cmd` - cmd launcher for the Python wrapper.
- `F:\Projects\s2t-bru\README.md` - usage and constraints.
- `F:\Projects\s2t-bru\.env.example` - example environment variable set.
- `F:\DevTools\Portable\bin\bru.cmd` - stable Bruno CLI launcher via portable Node.
- `F:\DevTools\Portable\bin\bru.ps1` - PowerShell launcher for the same Bruno CLI.

## Rationale
- The captured browser log was noisy, so only same-origin `speech2text.ru` endpoints were promoted into the collection.
- Bruno CLI was installed into `F:\DevTools\Portable\BrunoCli` and exposed through `F:\DevTools\Portable\bin` to match the existing DevTools layout.
- The Python wrapper writes Bruno JSON reports to `F:\Projects\s2t-bru\tmp` so Python scripts can consume structured results without scraping console output.
- The second desktop capture still did not contain literal cookie values, so the valid session had to be extracted from Yandex Browser's Chromium cookie store instead of the text export.

## Issues
- The captured file did not include a same-origin upload request, so the collection does not yet cover the upload/start-of-job step.
- Raw `bru run` must be launched from the collection root; the wrappers already enforce that.
- Cookie refresh is manual right now: the current `local.bru` contains a working session captured on `2026-04-08`, but it can expire later.

## Functions
- `Speech2TextBruClient.run_request` (`F:\Projects\s2t-bru\speech2text.py`) - runs one Bruno request or the whole collection with env overrides and structured JSON output.
- `build_parser` (`F:\Projects\s2t-bru\speech2text.py`) - defines the task-specific CLI surface for `cmd` and Python-driven runs.
- `_result_summary_lines` (`F:\Projects\s2t-bru\speech2text.py`) - prints a small ASCII summary without raw Bruno Unicode output.

## Next steps
- Add the missing upload request if a new browser capture includes it.
- Refresh `cookie_header` in `local.bru` if the current `speech2text.ru` session expires.

## 2026-04-08 Update

### Summary
- Added `transcribe-file` and `transcribe-url` commands to the Python/CMD wrapper.
- Added `speech2text_site.py` with two execution paths: direct HTTP for local files and Chromium automation for source URLs.
- Installed `requests` and `playwright` into `F:\DevTools\Python311` because the earlier Bruno-only wrapper was not enough for upload/start/transcript extraction.

### Files
- `F:\Projects\s2t-bru\speech2text.py` - extended CLI parser and dispatch for `transcribe-file` and `transcribe-url`.
- `F:\Projects\s2t-bru\speech2text_site.py` - new runtime module for upload/start/poll/extract logic and browser-driven URL submission.
- `F:\Projects\s2t-bru\speech2text.cmd` - forces `PYTHONUTF8=1` for readable Cyrillic transcript output in `cmd.exe`.
- `F:\Projects\s2t-bru\README.md` - updated usage examples and the newly confirmed endpoint map.

### Rationale
- The local-file flow can be reproduced from the observed API: `POST /yii/upload/upload` -> `GET /a-list?to_wav=...` -> `GET /interactive?wtimecode=...txt`.
- The source-URL flow depends on browser fingerprint JavaScript on `/a-list`, so it is not a clean pure-HTTP replay on the current site.
- Parsing the interactive page gives the real transcript text, while `to_txt` itself only returns frontend HTML/iframe glue.

### Verification
- `python -m py_compile` passed for `speech2text.py` and `speech2text_site.py`.
- `speech2text.py --help` shows the new subcommands.
- A live Playwright prototype earlier on `2026-04-08 16:06 +03:00` successfully uploaded `clone_20260408_033734_session.wav` and extracted transcript text from `/interactive?wtimecode=...txt`.
- The final end-to-end verification runs for both `transcribe-file` and `transcribe-url` are currently redirected by `speech2text.ru` to `registration-with-confirmation`, and the CLI now surfaces that service-side failure explicitly instead of silently returning misleading success.

### Issues
- The current site session/rate/anti-bot state is unstable: even `get_current_rate` can now land on `registration-with-confirmation`.
- Because of that service-side redirect, the new commands are syntactically verified and error-handling verified, but the last live end-to-end rerun was blocked by the site rather than the local code.

## 2026-04-08 Publish Update

### Summary
- Refactored the repo to use relative paths and env-driven runtime config instead of hardcoded `F:` paths.
- Added `app.py` as a FastAPI/Vercel API wrapper around the existing Speech2Text runtime.
- Added deploy artifacts: `.gitignore`, `.vercelignore`, `requirements.txt`, `vercel.json`, and a Vercel deploy button in `README.md`.
- Published the repo to GitHub and deployed a Vercel preview.

### Files
- `s2t_config.py` - shared path/env resolution for local CLI and Vercel runtime.
- `speech2text.py` - portable CLI with `--env-file`, `transcript`, and relative defaults.
- `speech2text_site.py` - shared HTTP/browser runtime for queue, transcript fetch, and file transcription attempts.
- `app.py` - FastAPI app exposing `/api/health`, `/api/rate`, `/api/queue/{job_id}`, `/api/transcript/{job_id}`, `/api/transcribe-file`, and `/api/transcribe-url`.
- `speech2text.cmd` - repo-relative Windows launcher with optional `S2T_PYTHON_EXE`.
- `README.md` - GitHub/Vercel usage guide and deploy button.
- `collection/environments/local.bru.example` - safe Bruno env template without a live cookie.
- `tests/test_transcript_parsing.py` - unit coverage for transcript parsing/formatting.

### Rationale
- The repo had to become cloneable and deployable before publishing; hardcoded portable paths would have broken both GitHub consumers and Vercel.
- Cookie-based auth was moved to env/default resolution so the deploy can work without storing secrets in git.
- The Vercel API wraps the same runtime code as the local CLI, which avoids maintaining two separate implementations.

### Verification
- `python -m py_compile s2t_config.py speech2text_site.py speech2text.py app.py` -> pass.
- `python -m unittest discover -s tests -v` -> `2` tests passed.
- `speech2text.cmd queue --job-id 2026-04-08-14-44-19-4909` -> exit code `0`, HTTP `200`.
- `speech2text.cmd transcript --job-id 2026-04-08-14-44-19-4909 --timeout-seconds 15` -> transcript returned successfully.
- Local `uvicorn app:app` smoke check -> `/api/health` and `/api/transcript/2026-04-08-14-44-19-4909?timecodes=true` returned `200`.
- GitHub repo published: `https://github.com/VolcharaVasiliy/speech2text-cookie-api`.
- Vercel preview ready: `https://speech2text-cookie-pp1jqae53-basils-projects-4f73ea6d.vercel.app`.
- Latest pushed commit: `16f31d1fedcd24b666fd1f7c09d25d0e25bbe3db`.

### Issues
- `GET /api/rate` is currently returning the site's registration HTML instead of JSON; the same regression now appears in Bruno, so this is a live service-side state issue rather than only an API wrapper bug.
- `transcribe-file` is still vulnerable to `registration-with-confirmation` redirects from `speech2text.ru`, even with a live cookie.
- `transcribe-url` requires a local Chromium executable and is not a reliable Vercel path.

### Next steps
- Refresh the browser cookie/session if `speech2text.ru` stops accepting the current one.
- If file upload must work from Vercel consistently, capture and replicate whatever extra anti-bot/browser signals the site currently expects.

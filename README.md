# speech2text-cookie-api

Portable toolkit for `speech2text.ru` with three layers:

- local CLI for `cmd.exe`, PowerShell, and Python scripts
- direct HTTP runtime for authenticated file transcription
- Vercel-ready FastAPI wrapper that reads the site cookie from environment variables

The repo is designed so the same codebase can be:

- cloned and used locally from Windows
- pushed to GitHub without leaking a live cookie
- deployed to Vercel as an API

## What is inside

- `speech2text.py` - main CLI entry point
- `speech2text.cmd` - Windows launcher
- `speech2text_site.py` - direct site runtime for upload, queue polling, and transcript extraction
- `app.py` - FastAPI app used by Vercel
- `s2t_config.py` - shared config and path resolution
- `collection/` - Bruno collection for the captured same-origin requests
- `collection/environments/local.bru.example` - Bruno env template without secrets
- `requirements.txt` - API/runtime dependencies
- `vercel.json` - Vercel function config

## Environment Variables

Required:

- `S2T_COOKIE_HEADER` - full `Cookie` header from an authenticated `speech2text.ru` browser session

Optional:

- `S2T_BASE_URL` - defaults to `https://speech2text.ru`
- `S2T_ACCEPT_LANGUAGE` - defaults to `ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7`
- `S2T_USER_AGENT` - defaults to a desktop Chromium UA
- `S2T_BROWSER_EXE` - required only for browser-driven URL transcription
- `S2T_ENV_FILE` - override Bruno env file location
- `S2T_REPORTS_ROOT` - override JSON report output directory
- `S2T_PYTHON_EXE` - override Python used by `speech2text.cmd`

Backward compatibility:

- `S2T_COOKIE` is accepted as an alias for `S2T_COOKIE_HEADER`
- `S2T_AUDIO_FILE` is accepted as an alias for `S2T_AUDIO_FILE_NAME`

## Quick Start

### 1. Local CLI

Use the Windows launcher:

```bat
speech2text.cmd rate
speech2text.cmd transcript --job-id 2026-04-08-14-44-19-4909
speech2text.cmd transcribe-file --file F:\downloads\sample.wav --timecodes
speech2text.cmd transcribe-file --file F:\downloads\sample.wav --text-out F:\downloads\sample.txt
```

Or call Python directly:

```bat
python speech2text.py rate
python speech2text.py transcribe-file --file .\sample.wav
```

If you want Bruno defaults locally:

```bat
copy collection\environments\local.bru.example collection\environments\local.bru
```

Then paste your live cookie into `collection\environments\local.bru`.

### 2. Local API

Install dependencies:

```bat
python -m pip install -r requirements.txt
```

Run locally:

```bat
python -m uvicorn app:app --host 127.0.0.1 --port 8787
```

Open:

- `http://127.0.0.1:8787/`
- `http://127.0.0.1:8787/docs`

### 3. Vercel Deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/VolcharaVasiliy/speech2text-cookie-api&project-name=speech2text-cookie-api&repository-name=speech2text-cookie-api&env=S2T_COOKIE_HEADER,S2T_BASE_URL,S2T_ACCEPT_LANGUAGE,S2T_USER_AGENT&envDescription=Provide%20your%20speech2text.ru%20Cookie%20header%20and%20optional%20HTTP%20defaults.&envLink=https://github.com/VolcharaVasiliy/speech2text-cookie-api%23environment-variables)

Manual deploy:

```bat
vercel deploy -y -e S2T_COOKIE_HEADER="YOUR_COOKIE"
```

## API Endpoints

### `GET /`

Runtime info and route list.

### `GET /api/health`

Checks whether the API is up and whether the cookie env is configured.

### `GET /api/rate`

Reads `GET /a-list?get_current_rate=1` through the configured authenticated session.

Example:

```bat
curl https://YOUR-DEPLOYMENT.vercel.app/api/rate
```

### `GET /api/queue/{job_id}`

Polls queue status for an existing job.

Example:

```bat
curl https://YOUR-DEPLOYMENT.vercel.app/api/queue/2026-04-08-14-44-19-4909
```

### `GET /api/transcript/{job_id}`

Waits for transcript segments and returns normalized text.

Query parameters:

- `timecodes=true|false`
- `timeout_seconds=60`

Example:

```bat
curl "https://YOUR-DEPLOYMENT.vercel.app/api/transcript/2026-04-08-14-44-19-4909?timecodes=true"
```

### `POST /api/transcribe-file`

Uploads a local file to `speech2text.ru`, starts conversion, polls `/interactive?wtimecode=...txt`, and returns the transcript.

Multipart form fields:

- `file` - required
- `timecodes` - optional boolean
- `timeout_seconds` - optional float

Example:

```bat
curl -X POST ^
  -F "file=@F:\downloads\sample.wav" ^
  -F "timecodes=true" ^
  https://YOUR-DEPLOYMENT.vercel.app/api/transcribe-file
```

PowerShell example:

```powershell
$form = @{
  file = Get-Item 'F:\downloads\sample.wav'
  timecodes = 'true'
}
Invoke-RestMethod -Uri 'https://YOUR-DEPLOYMENT.vercel.app/api/transcribe-file' -Method Post -Form $form
```

Python example:

```python
import requests

with open(r"F:\downloads\sample.wav", "rb") as handle:
    response = requests.post(
        "https://YOUR-DEPLOYMENT.vercel.app/api/transcribe-file",
        files={"file": ("sample.wav", handle, "audio/wav")},
        data={"timecodes": "true"},
        timeout=300,
    )
response.raise_for_status()
print(response.json()["result"]["transcript"])
```

### `POST /api/transcribe-url`

Browser-assisted source URL transcription.

Form fields:

- `source_url` - required
- `headed` - optional boolean
- `timecodes` - optional boolean
- `timeout_seconds` - optional float

Important:

- this flow requires a real Chromium executable
- it is meant mainly for local machines
- on Vercel it will usually return `501` unless a browser is available

## Bruno Usage

If Bruno CLI is installed and reachable through `BRU_CMD` or `bru` on `PATH`, the raw captured requests are still available:

```bat
speech2text.cmd rate
speech2text.cmd queue --job-id 2026-04-08-14-44-19-4909
speech2text.cmd txt --audio-file 2026-04-08-14-44-19-4909.wav
```

Or directly:

```bat
bru run collection\15-get-current-rate.bru --env-file collection\environments\local.bru
```

## Python Usage

```python
from speech2text import Speech2TextBruClient
from speech2text_site import Speech2TextSiteClient

bru = Speech2TextBruClient()
rate = bru.run_request("rate")
print(rate.report_path)

site = Speech2TextSiteClient()
result = site.transcribe_file(r"F:\downloads\sample.wav")
print(result.job_id)
print(result.transcript)
```

## Deployment Notes

- `collection/environments/local.bru` is intentionally ignored by git and Vercel
- the deploy expects the live cookie to come from environment variables, not from the repo
- Vercel writes reports to `/tmp/s2t-bru-reports`
- local runs write reports to `tmp/reports`

## Limitations

- `speech2text.ru` can redirect authenticated calls to anti-bot or registration pages at any time
- source URL transcription depends on browser-side fingerprint logic and is less stable than direct file upload
- if the cookie expires, all authenticated requests start failing until you refresh `S2T_COOKIE_HEADER`

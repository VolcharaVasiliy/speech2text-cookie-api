from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from s2t_config import (
    default_browser_executable,
    default_env_file,
    load_runtime_defaults,
)
from speech2text_site import SiteActionResult, Speech2TextSiteClient


APP_VERSION = "0.2.0"
app = FastAPI(
    title="Speech2Text Cookie API",
    version=APP_VERSION,
    description=(
        "API wrapper for speech2text.ru using an authenticated Cookie header "
        "from environment variables."
    ),
)


def build_site_client() -> Speech2TextSiteClient:
    env_file = default_env_file()
    defaults = load_runtime_defaults(env_file)
    return Speech2TextSiteClient(
        base_url=defaults.get("base_url"),
        env_file=env_file,
        browser_executable=default_browser_executable(),
    )


def serialize_result(result: SiteActionResult) -> dict:
    payload = result.to_report()
    payload["report_path"] = str(result.report_path) if result.report_path else None
    return payload


def raise_runtime_error(error: Exception) -> None:
    if isinstance(error, FileNotFoundError):
        raise HTTPException(status_code=400, detail=str(error)) from error
    if isinstance(error, RuntimeError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/")
def root() -> dict:
    defaults = load_runtime_defaults(default_env_file())
    browser_path = default_browser_executable()
    return {
        "name": "speech2text-cookie-api",
        "version": APP_VERSION,
        "docs_url": "/docs",
        "cookie_configured": bool(defaults.get("cookie_header")),
        "browser_available": browser_path.is_file(),
        "browser_executable": str(browser_path),
        "routes": {
            "health": "/api/health",
            "rate": "/api/rate",
            "queue": "/api/queue/{job_id}",
            "transcript": "/api/transcript/{job_id}",
            "transcribe_file": "/api/transcribe-file",
            "transcribe_url": "/api/transcribe-url",
        },
        "required_env": [
            "S2T_COOKIE_HEADER",
        ],
        "optional_env": [
            "S2T_BASE_URL",
            "S2T_ACCEPT_LANGUAGE",
            "S2T_USER_AGENT",
            "S2T_BROWSER_EXE",
        ],
    }


@app.get("/api/health")
def health() -> dict:
    defaults = load_runtime_defaults(default_env_file())
    return {
        "ok": True,
        "cookie_configured": bool(defaults.get("cookie_header")),
        "vercel": bool(os.getenv("VERCEL")),
    }


@app.get("/api/rate")
def rate() -> dict:
    client = build_site_client()
    try:
        payload = client.get_current_rate()
    except Exception as error:
        raise_runtime_error(error)
    return {"ok": True, "data": payload}


@app.get("/api/queue/{job_id}")
def queue(job_id: str) -> dict:
    client = build_site_client()
    try:
        payload = client.check_queue(job_id)
    except Exception as error:
        raise_runtime_error(error)
    return {"ok": True, "job_id": job_id, "data": payload}


@app.get("/api/transcript/{job_id}")
def transcript(
    job_id: str,
    timecodes: bool = False,
    timeout_seconds: float = 60.0,
) -> dict:
    client = build_site_client()
    try:
        result = client.get_transcript(
            job_id,
            include_timecodes=timecodes,
            timeout_seconds=timeout_seconds,
        )
    except Exception as error:
        raise_runtime_error(error)
    return {"ok": True, "result": serialize_result(result)}


@app.post("/api/transcribe-file")
async def transcribe_file(
    file: UploadFile = File(...),
    timecodes: bool = Form(False),
    timeout_seconds: float = Form(180.0),
) -> dict:
    suffix = Path(file.filename or "upload.bin").suffix
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as temp_file:
            temp_path = Path(temp_file.name)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)

        client = build_site_client()
        result = client.transcribe_file(
            temp_path,
            include_timecodes=timecodes,
            timeout_seconds=timeout_seconds,
        )
    except Exception as error:
        raise_runtime_error(error)
    finally:
        await file.close()
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return {"ok": True, "result": serialize_result(result)}


@app.post("/api/transcribe-url")
def transcribe_url(
    source_url: str = Form(...),
    headed: bool = Form(False),
    timecodes: bool = Form(False),
    timeout_seconds: float = Form(360.0),
) -> dict:
    browser_path = default_browser_executable()
    if not browser_path.is_file():
        raise HTTPException(
            status_code=501,
            detail=(
                "Browser-driven URL transcription requires a local Chromium executable. "
                "Set S2T_BROWSER_EXE or use this endpoint only in local environments."
            ),
        )

    client = build_site_client()
    try:
        result = client.transcribe_url(
            source_url,
            headed=headed,
            include_timecodes=timecodes,
            timeout_seconds=timeout_seconds,
            browser_executable=browser_path,
        )
    except Exception as error:
        raise_runtime_error(error)

    return {"ok": True, "result": serialize_result(result)}

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from s2t_config import (
    DEFAULT_ACCEPT_LANGUAGE,
    DEFAULT_USER_AGENT,
    default_browser_executable,
    default_env_file,
    default_reports_root,
    load_runtime_defaults,
)


DEFAULT_BROWSER_EXE = default_browser_executable()
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
}
INTERACTIVE_LINK_SELECTOR = 'a[href*="/interactive?wtimecode="]'
INTERACTIVE_HREF_RE = re.compile(r"/interactive\?wtimecode=([^&]+)\.txt")
TIME_STRING_RE = re.compile(
    r'<div[^>]*class="time-string"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
SPEAKER_RE = re.compile(
    r'<h6[^>]*class="[^"]*speaker-button[^"]*"[^>]*>.*?'
    r'<span[^>]*class="[^"]*speaker-name[^"]*"[^>]*>(.*?)</span>.*?</h6>',
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
TIMECODE_LINE_RE = re.compile(
    "^(?P<time>\\d{2}:\\d{2}:\\d{2})\\s+[\\u2013\\u2014-]\\s+(?P<text>.+)$"
)


@dataclass
class TranscriptSegment:
    speaker: str | None
    timecode: str | None
    text: str


@dataclass
class SiteActionResult:
    mode: str
    source_value: str
    job_id: str
    interactive_url: str
    transcript: str
    segments: list[TranscriptSegment]
    audio_file_name: str | None = None
    source_file_name: str | None = None
    browser_url: str | None = None
    started_request_url: str | None = None
    report_path: Path | None = None
    meta: dict[str, Any] | None = None

    def to_report(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "source_value": self.source_value,
            "job_id": self.job_id,
            "interactive_url": self.interactive_url,
            "transcript": self.transcript,
            "segments": [asdict(segment) for segment in self.segments],
            "audio_file_name": self.audio_file_name,
            "source_file_name": self.source_file_name,
            "browser_url": self.browser_url,
            "started_request_url": self.started_request_url,
            "meta": self.meta or {},
        }


def _clean_html(value: str) -> str:
    return html.unescape(TAG_RE.sub("", value)).replace("\xa0", " ").strip()


def _parse_interactive_segments(html_text: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []

    speaker_iter = SPEAKER_RE.finditer(html_text)
    time_iter = TIME_STRING_RE.finditer(html_text)
    markers: list[tuple[int, str, str]] = []

    for match in speaker_iter:
        markers.append((match.start(), "speaker", _clean_html(match.group(1))))
    for match in time_iter:
        markers.append((match.start(), "segment", match.group(1)))

    markers.sort(key=lambda item: item[0])
    current_speaker: str | None = None

    for _, kind, payload in markers:
        if kind == "speaker":
            current_speaker = payload or None
            continue

        cleaned = _clean_html(payload)
        parsed = TIMECODE_LINE_RE.match(cleaned)
        if parsed:
            timecode = parsed.group("time")
            text = parsed.group("text").strip()
        else:
            timecode = None
            text = cleaned
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                speaker=current_speaker,
                timecode=timecode,
                text=text,
            )
        )

    return segments


def _compose_transcript(
    segments: list[TranscriptSegment],
    *,
    include_timecodes: bool,
) -> str:
    if not segments:
        return ""

    speakers = {segment.speaker for segment in segments if segment.speaker}
    include_speakers = len(speakers) > 1
    lines: list[str] = []

    for segment in segments:
        parts: list[str] = []
        if include_timecodes and segment.timecode:
            parts.append(f"[{segment.timecode}]")
        if include_speakers and segment.speaker:
            parts.append(f"{segment.speaker}:")
        parts.append(segment.text)
        lines.append(" ".join(parts))

    return "\n".join(lines)


class Speech2TextSiteClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        env_file: Path | None = None,
        reports_root: Path | None = None,
        browser_executable: Path | None = None,
    ) -> None:
        self.env_file = env_file or default_env_file()
        defaults = load_runtime_defaults(self.env_file)
        self.base_url = (base_url or defaults.get("base_url") or "https://speech2text.ru").rstrip("/")
        self.reports_root = reports_root or default_reports_root()
        self.browser_executable = browser_executable or default_browser_executable()

    def get_current_rate(
        self,
        *,
        cookie_header: str | None = None,
        accept_language: str | None = None,
        user_agent: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        session = self._build_session(
            cookie_header=cookie_header,
            accept_language=accept_language,
            user_agent=user_agent,
        )
        response = session.get(
            f"{self.base_url}/a-list?get_current_rate=1",
            headers={
                "Accept": "*/*",
                "Referer": f"{self.base_url}/a-list",
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_json_response(response, "get_current_rate")

    def check_queue(
        self,
        job_id: str,
        *,
        cookie_header: str | None = None,
        accept_language: str | None = None,
        user_agent: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        session = self._build_session(
            cookie_header=cookie_header,
            accept_language=accept_language,
            user_agent=user_agent,
        )
        response = session.get(
            f"{self.base_url}/a-list?check_queue={job_id}",
            headers={
                "Accept": "*/*",
                "Referer": f"{self.base_url}/a-list?conver_new_file={job_id}",
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_json_response(response, "check_queue")

    def get_transcript(
        self,
        job_id: str,
        *,
        cookie_header: str | None = None,
        accept_language: str | None = None,
        user_agent: str | None = None,
        include_timecodes: bool = False,
        timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 2.0,
        report_path: str | Path | None = None,
        text_out: str | Path | None = None,
    ) -> SiteActionResult:
        session = self._build_session(
            cookie_header=cookie_header,
            accept_language=accept_language,
            user_agent=user_agent,
        )
        interactive_url = f"{self.base_url}/interactive?wtimecode={job_id}.txt"
        segments, interactive_meta = self._wait_for_interactive_segments_http(
            session,
            interactive_url,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        result = SiteActionResult(
            mode="transcript",
            source_value=job_id,
            job_id=job_id,
            interactive_url=interactive_url,
            transcript=_compose_transcript(segments, include_timecodes=include_timecodes),
            segments=segments,
            meta={"strategy": "http", "interactive_meta": interactive_meta},
        )
        self._finalize_result(result, report_path=report_path, text_out=text_out)
        return result

    def transcribe_file(
        self,
        file_path: str | Path,
        *,
        cookie_header: str | None = None,
        accept_language: str | None = None,
        user_agent: str | None = None,
        include_timecodes: bool = False,
        timeout_seconds: float = 180.0,
        poll_interval_seconds: float = 2.0,
        report_path: str | Path | None = None,
        text_out: str | Path | None = None,
    ) -> SiteActionResult:
        resolved_file_path = Path(file_path)
        if not resolved_file_path.is_file():
            raise FileNotFoundError(f"Missing local file: {resolved_file_path}")

        try:
            result = self._transcribe_file_via_http(
                resolved_file_path,
                cookie_header=cookie_header,
                accept_language=accept_language,
                user_agent=user_agent,
                include_timecodes=include_timecodes,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
        except Exception as http_error:
            result = self._transcribe_file_via_browser(
                resolved_file_path,
                include_timecodes=include_timecodes,
                timeout_seconds=timeout_seconds,
            )
            result.meta = result.meta or {}
            result.meta["fallback_reason"] = str(http_error)

        self._finalize_result(result, report_path=report_path, text_out=text_out)
        return result

    def transcribe_url(
        self,
        source_url: str,
        *,
        headed: bool = False,
        include_timecodes: bool = False,
        timeout_seconds: float = 360.0,
        report_path: str | Path | None = None,
        text_out: str | Path | None = None,
        browser_executable: str | Path | None = None,
    ) -> SiteActionResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        executable = Path(browser_executable) if browser_executable else self.browser_executable
        if not executable.is_file():
            raise FileNotFoundError(f"Missing browser executable: {executable}")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=str(executable),
                headless=not headed,
            )
            context = browser.new_context(
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )
            page = context.new_page()

            try:
                page.goto(
                    f"{self.base_url}/",
                    wait_until="domcontentloaded",
                    timeout=int(timeout_seconds * 1000),
                )
                self._accept_cookie_banner(page)
                existing_links = self._collect_interactive_hrefs(page)

                page.locator("#downloadurl_source").fill(source_url)
                page.locator("#downloadurl_source").press("Tab")

                href = self._wait_for_new_interactive_href(
                    page,
                    existing_links=existing_links,
                    timeout_seconds=timeout_seconds,
                    action_label="URL submission",
                )
                if href is None:
                    raise RuntimeError("Speech2Text did not expose a new transcript link.")

                job_match = INTERACTIVE_HREF_RE.search(href)
                if not job_match:
                    raise RuntimeError(f"Could not parse job id from {href}")
                job_id = job_match.group(1)

                interactive_url = f"{self.base_url}{href}"
                segments = self._wait_for_interactive_segments_page(
                    page,
                    interactive_url=interactive_url,
                    timeout_seconds=timeout_seconds,
                )
                transcript = _compose_transcript(
                    segments,
                    include_timecodes=include_timecodes,
                )

                result = SiteActionResult(
                    mode="transcribe-url",
                    source_value=source_url,
                    job_id=job_id,
                    interactive_url=interactive_url,
                    transcript=transcript,
                    segments=segments,
                    browser_url=page.url,
                    meta={
                        "browser_executable": str(executable),
                        "headed": headed,
                    },
                )
            except PlaywrightTimeoutError as error:
                current_url = page.url
                if "registration-with-confirmation" in current_url:
                    raise RuntimeError(
                        "Speech2Text redirected URL submission to "
                        "registration-with-confirmation. "
                        "The site rejected the current browser session/fingerprint."
                    ) from error
                raise RuntimeError(
                    "Timed out while waiting for Speech2Text URL transcription. "
                    f"Last browser URL: {current_url}"
                ) from error
            finally:
                context.close()
                browser.close()

        self._finalize_result(result, report_path=report_path, text_out=text_out)
        return result

    def _transcribe_file_via_http(
        self,
        file_path: Path,
        *,
        cookie_header: str | None,
        accept_language: str | None,
        user_agent: str | None,
        include_timecodes: bool,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> SiteActionResult:
        session = self._build_session(
            cookie_header=cookie_header,
            accept_language=accept_language,
            user_agent=user_agent,
        )
        csrf_token = self._fetch_csrf_token(session)

        upload_started_at = time.perf_counter()
        upload_payload = self._upload_file(
            session,
            file_path,
            csrf_token,
        )
        upload_elapsed_ms = int((time.perf_counter() - upload_started_at) * 1000)

        raw_compleat = upload_payload["compleat"]
        compleat = json.loads(raw_compleat) if isinstance(raw_compleat, str) else raw_compleat
        job_id = compleat[0]
        audio_file_name = compleat[1]
        source_file_name = compleat[2]

        start_response = session.get(
            f"{self.base_url}/a-list"
            f"?to_wav={audio_file_name}&conver_new_file={job_id}&fromiframe=1",
            headers={"Referer": f"{self.base_url}/a-list?"},
            timeout=timeout_seconds,
        )
        interactive_url = f"{self.base_url}/interactive?wtimecode={job_id}.txt"
        segments, interactive_meta = self._wait_for_interactive_segments_http(
            session,
            interactive_url,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        transcript = _compose_transcript(
            segments,
            include_timecodes=include_timecodes,
        )

        return SiteActionResult(
            mode="transcribe-file",
            source_value=str(file_path),
            job_id=job_id,
            interactive_url=interactive_url,
            transcript=transcript,
            segments=segments,
            audio_file_name=audio_file_name,
            source_file_name=source_file_name,
            started_request_url=str(start_response.url),
            meta={
                "strategy": "http",
                "upload_elapsed_ms": upload_elapsed_ms,
                "upload_payload": upload_payload,
                "interactive_meta": interactive_meta,
            },
        )

    def _transcribe_file_via_browser(
        self,
        file_path: Path,
        *,
        include_timecodes: bool,
        timeout_seconds: float,
    ) -> SiteActionResult:
        from playwright.sync_api import sync_playwright

        if not self.browser_executable.is_file():
            raise FileNotFoundError(f"Missing browser executable: {self.browser_executable}")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=str(self.browser_executable),
                headless=True,
            )
            context = browser.new_context(
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )
            page = context.new_page()
            try:
                page.goto(
                    f"{self.base_url}/",
                    wait_until="domcontentloaded",
                    timeout=int(timeout_seconds * 1000),
                )
                self._accept_cookie_banner(page)
                existing_links = self._collect_interactive_hrefs(page)
                page.locator("input[type=file].dz-hidden-input").first.set_input_files(str(file_path))
                href = self._wait_for_new_interactive_href(
                    page,
                    existing_links=existing_links,
                    timeout_seconds=timeout_seconds,
                    action_label="file upload",
                )
                if href is None:
                    raise RuntimeError("Speech2Text did not expose a new transcript link after file upload.")

                job_match = INTERACTIVE_HREF_RE.search(href)
                if not job_match:
                    raise RuntimeError(f"Could not parse job id from {href}")
                job_id = job_match.group(1)
                interactive_url = f"{self.base_url}{href}"
                segments = self._wait_for_interactive_segments_page(
                    page,
                    interactive_url=interactive_url,
                    timeout_seconds=timeout_seconds,
                )
                transcript = _compose_transcript(
                    segments,
                    include_timecodes=include_timecodes,
                )
                return SiteActionResult(
                    mode="transcribe-file",
                    source_value=str(file_path),
                    job_id=job_id,
                    interactive_url=interactive_url,
                    transcript=transcript,
                    segments=segments,
                    audio_file_name=f"{job_id}.wav",
                    source_file_name=file_path.name,
                    browser_url=page.url,
                    meta={
                        "strategy": "browser",
                        "browser_executable": str(self.browser_executable),
                    },
                )
            finally:
                context.close()
                browser.close()

    def _build_session(
        self,
        *,
        cookie_header: str | None,
        accept_language: str | None,
        user_agent: str | None,
    ) -> requests.Session:
        defaults = load_runtime_defaults(self.env_file)
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        session.headers["Accept-Language"] = (
            accept_language or defaults.get("accept_language") or DEFAULT_HEADERS["Accept-Language"]
        )
        session.headers["User-Agent"] = (
            user_agent or defaults.get("user_agent") or DEFAULT_HEADERS["User-Agent"]
        )
        resolved_cookie_header = cookie_header or defaults.get("cookie_header")
        if resolved_cookie_header:
            session.headers["Cookie"] = resolved_cookie_header
        return session

    def _fetch_csrf_token(self, session: requests.Session) -> str:
        response = session.get(
            f"{self.base_url}/yii/security/csrf-token",
            headers={
                "Accept": "application/json,text/plain,*/*",
                "Referer": f"{self.base_url}/a-list?",
            },
            timeout=60,
        )
        response.raise_for_status()
        token_html = self._parse_json_response(response, "csrf-token")
        if not isinstance(token_html, str):
            raise RuntimeError("Unexpected csrf-token payload type.")
        token_match = re.search(r'value="([^"]+)"', token_html)
        if token_match is None:
            raise RuntimeError("Could not extract CSRF token from /yii/security/csrf-token.")
        return token_match.group(1)

    def _upload_file(
        self,
        session: requests.Session,
        file_path: Path,
        csrf_token: str,
    ) -> dict[str, Any]:
        upload_id = str(uuid4())
        payload = {
            "dzuuid": upload_id,
            "dzchunkindex": "0",
            "dztotalfilesize": str(file_path.stat().st_size),
            "dzchunksize": "104857600",
            "dztotalchunkcount": "1",
            "dzchunkbyteoffset": "0",
            "MAX_FILE_SIZE": "42949672960",
            "languageID": "autdct",
            "speakersID": "autdct",
            "_csrf-frontend": csrf_token,
        }
        with file_path.open("rb") as file_handle:
            response = session.post(
                f"{self.base_url}/yii/upload/upload",
                data=payload,
                files={
                    "UploadFileForm[userfile][]": (
                        file_path.name,
                        file_handle,
                        "application/octet-stream",
                    )
                },
                headers={
                    "Accept": "application/json",
                    "Referer": f"{self.base_url}/a-list?",
                    "Origin": self.base_url,
                },
                timeout=180,
            )
        response.raise_for_status()
        upload_payload = self._parse_json_response(response, "upload")
        if not isinstance(upload_payload, dict):
            raise RuntimeError("Unexpected upload response type.")
        if upload_payload.get("status") != "success":
            raise RuntimeError(f"Speech2Text upload failed: {upload_payload}")
        if "compleat" not in upload_payload:
            raise RuntimeError(f"Speech2Text upload response has no compleat payload: {upload_payload}")
        return upload_payload

    def _wait_for_interactive_segments_http(
        self,
        session: requests.Session,
        interactive_url: str,
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> tuple[list[TranscriptSegment], dict[str, Any]]:
        deadline = time.monotonic() + timeout_seconds
        last_status = {
            "attempts": 0,
            "last_url": interactive_url,
        }

        while time.monotonic() < deadline:
            last_status["attempts"] += 1
            response = session.get(
                interactive_url,
                headers={"Referer": f"{self.base_url}/a-list?"},
                timeout=max(30.0, poll_interval_seconds + 10.0),
            )
            response.raise_for_status()
            last_status["last_url"] = str(response.url)
            segments = _parse_interactive_segments(response.text)
            if segments:
                return segments, last_status
            time.sleep(poll_interval_seconds)

        raise RuntimeError(
            f"Timed out waiting for transcript on {interactive_url} "
            f"after {last_status['attempts']} attempts."
        )

    def _parse_json_response(self, response: requests.Response, label: str) -> Any:
        try:
            return response.json()
        except ValueError as error:
            preview = response.text[:400].strip()
            raise RuntimeError(
                f"Expected JSON from {label}, got {response.headers.get('content-type', 'unknown')}: {preview}"
            ) from error

    def _accept_cookie_banner(self, page: Any) -> None:
        for label in ("\u041f\u043e\u043d\u044f\u0442\u043d\u043e", "OK"):
            try:
                page.get_by_role("button", name=label).click(timeout=2_000)
                return
            except Exception:
                continue

    def _collect_interactive_hrefs(self, page: Any) -> set[str]:
        hrefs: set[str] = set()
        for index in range(page.locator(INTERACTIVE_LINK_SELECTOR).count()):
            href = page.locator(INTERACTIVE_LINK_SELECTOR).nth(index).get_attribute("href")
            if href:
                hrefs.add(href)
        return hrefs

    def _wait_for_new_interactive_href(
        self,
        page: Any,
        *,
        existing_links: set[str],
        timeout_seconds: float,
        action_label: str = "transcription request",
    ) -> str | None:
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            current_url = page.url
            if "registration-with-confirmation" in current_url:
                raise RuntimeError(
                    f"Speech2Text redirected {action_label} to registration-with-confirmation."
                )

            hrefs = [
                href
                for href in self._collect_interactive_hrefs(page)
                if href not in existing_links
            ]
            if hrefs:
                return hrefs[0]

            page.wait_for_timeout(1_000)

        return None

    def _wait_for_interactive_segments_page(
        self,
        page: Any,
        *,
        interactive_url: str,
        timeout_seconds: float,
    ) -> list[TranscriptSegment]:
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            page.goto(
                interactive_url,
                wait_until="domcontentloaded",
                timeout=int(min(timeout_seconds, 60.0) * 1000),
            )
            raw_segments = page.evaluate(
                """
                () => {
                  let speaker = null;
                  const items = [];
                  for (const node of document.querySelectorAll('h6.speaker-button, div.time-string')) {
                    if (node.matches('h6.speaker-button')) {
                      const speakerNode = node.querySelector('.speaker-name');
                      speaker = speakerNode ? speakerNode.innerText.trim() : node.innerText.trim();
                      continue;
                    }
                    const text = node.innerText.replace(/\\s+/g, ' ').trim();
                    const match = text.match(/^(\\d{2}:\\d{2}:\\d{2})\\s+[\\u2013\\u2014-]\\s+(.+)$/u);
                    items.push({
                      speaker,
                      timecode: match ? match[1] : null,
                      text: match ? match[2].trim() : text,
                    });
                  }
                  return items;
                }
                """
            )
            segments = [
                TranscriptSegment(
                    speaker=item.get("speaker"),
                    timecode=item.get("timecode"),
                    text=item.get("text", "").strip(),
                )
                for item in raw_segments
                if item.get("text", "").strip()
            ]
            if segments:
                return segments
            page.wait_for_timeout(2_000)

        raise RuntimeError(
            f"Timed out waiting for transcript segments on {interactive_url}."
        )

    def _finalize_result(
        self,
        result: SiteActionResult,
        *,
        report_path: str | Path | None,
        text_out: str | Path | None,
    ) -> None:
        self.reports_root.mkdir(parents=True, exist_ok=True)
        resolved_report_path = (
            Path(report_path)
            if report_path
            else self.reports_root / f"{result.mode}-{uuid4().hex}.json"
        )
        resolved_report_path.write_text(
            json.dumps(result.to_report(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.report_path = resolved_report_path

        if text_out:
            Path(text_out).write_text(result.transcript, encoding="utf-8")

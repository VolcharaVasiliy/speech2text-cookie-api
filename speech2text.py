from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from s2t_config import (
    default_browser_executable,
    default_bru_cmd,
    default_env_file,
    default_nodejs_root,
    default_reports_root,
    load_runtime_defaults,
    resolve_collection_root,
    resolve_project_root,
)
from speech2text_site import SiteActionResult, Speech2TextSiteClient


PROJECT_ROOT = resolve_project_root()
COLLECTION_ROOT = resolve_collection_root()
REPORTS_ROOT = default_reports_root()
REQUEST_FILES = {
    "list": COLLECTION_ROOT / "10-open-a-list.bru",
    "rate": COLLECTION_ROOT / "15-get-current-rate.bru",
    "job": COLLECTION_ROOT / "20-open-job.bru",
    "queue": COLLECTION_ROOT / "30-check-queue.bru",
    "txt": COLLECTION_ROOT / "40-download-txt.bru",
    "wav": COLLECTION_ROOT / "50-download-wav.bru",
    "csrf": COLLECTION_ROOT / "60-get-csrf-token.bru",
    "bind-ws": COLLECTION_ROOT / "70-bind-to-ws.bru",
}

ENV_OPTION_NAMES = (
    "base_url",
    "accept_language",
    "user_agent",
    "cookie_header",
    "job_id",
    "audio_file_name",
    "client_id",
)

REQUIRED_BY_REQUEST = {
    "job": ("job_id",),
    "queue": ("job_id",),
    "txt": ("audio_file_name",),
    "wav": ("job_id", "audio_file_name"),
    "bind-ws": ("client_id",),
}


@dataclass
class BruRunResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    report_path: Path
    report: dict | list | None


class Speech2TextBruClient:
    def __init__(
        self,
        bru_cmd: Path | None = None,
        collection_root: Path = COLLECTION_ROOT,
        env_file: Path | None = None,
        nodejs_root: Path | None = None,
        reports_root: Path = REPORTS_ROOT,
    ) -> None:
        self.bru_cmd = bru_cmd or default_bru_cmd()
        self.collection_root = Path(collection_root)
        self.env_file = env_file or default_env_file()
        self.nodejs_root = nodejs_root or default_nodejs_root()
        self.reports_root = Path(reports_root)

    def run_request(
        self,
        request_name: str,
        *,
        base_url: str | None = None,
        accept_language: str | None = None,
        user_agent: str | None = None,
        cookie_header: str | None = None,
        job_id: str | None = None,
        audio_file_name: str | None = None,
        client_id: str | None = None,
        report_path: str | Path | None = None,
        print_stdout: bool = False,
    ) -> BruRunResult:
        if not self.bru_cmd:
            raise FileNotFoundError(
                "Bruno CLI was not found. Set BRU_CMD or put `bru` on PATH."
            )

        if request_name == "all":
            target = self.collection_root
            recursive = True
        else:
            target = REQUEST_FILES.get(request_name)
            recursive = False
            if target is None:
                raise ValueError(f"Unknown request name: {request_name}")

        env_values = {
            "base_url": base_url,
            "accept_language": accept_language,
            "user_agent": user_agent,
            "cookie_header": cookie_header,
            "job_id": job_id,
            "audio_file_name": audio_file_name,
            "client_id": client_id,
        }

        missing = [
            field
            for field in REQUIRED_BY_REQUEST.get(request_name, ())
            if not env_values.get(field)
        ]
        if missing:
            raise ValueError(
                f"Request '{request_name}' requires: {', '.join(missing)}"
            )

        self.reports_root.mkdir(parents=True, exist_ok=True)
        resolved_report_path = (
            Path(report_path)
            if report_path
            else self.reports_root / f"{request_name}-{uuid4().hex}.json"
        )

        cmd = [
            str(self.bru_cmd),
            "run",
            str(target),
            "--env-file",
            str(self.env_file),
            "--output",
            str(resolved_report_path),
            "--format",
            "json",
        ]
        if recursive:
            cmd.append("-r")

        for name in ENV_OPTION_NAMES:
            value = env_values.get(name)
            if value is not None:
                cmd.extend(["--env-var", f"{name}={value}"])

        process_env = os.environ.copy()
        if self.nodejs_root:
            process_env["PATH"] = f"{self.nodejs_root}{os.pathsep}{process_env.get('PATH', '')}"

        completed = subprocess.run(
            cmd,
            cwd=self.collection_root,
            env=process_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if print_stdout and completed.stdout:
            print(completed.stdout, end="")
        if print_stdout and completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")

        report = None
        if resolved_report_path.exists():
            report = json.loads(resolved_report_path.read_text(encoding="utf-8"))

        return BruRunResult(
            command=cmd,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            report_path=resolved_report_path,
            report=report,
        )


def _add_common_arguments(subparser: argparse.ArgumentParser) -> None:
    common_options = {
        "base_url": ("--base-url", "Override the Speech2Text base URL."),
        "accept_language": (
            "--accept-language",
            "Override the Accept-Language header value.",
        ),
        "user_agent": ("--user-agent", "Override the User-Agent header value."),
        "cookie_header": (
            "--cookie",
            "Full Cookie header value for authenticated requests.",
        ),
        "env_file": (
            "--env-file",
            "Optional Bruno env file. Defaults to collection/environments/local.bru(.example).",
        ),
        "report_path": ("--report-path", "Optional output path for the JSON report."),
    }
    for destination, (flag, help_text) in common_options.items():
        subparser.add_argument(flag, dest=destination, help=help_text)


def _add_job_argument(subparser: argparse.ArgumentParser, required: bool) -> None:
    subparser.add_argument("--job-id", required=required, help="Speech2Text job id.")


def _add_audio_argument(subparser: argparse.ArgumentParser, required: bool) -> None:
    subparser.add_argument(
        "--audio-file",
        dest="audio_file_name",
        required=required,
        help="Audio filename used by the site endpoints.",
    )


def _add_transcribe_arguments(subparser: argparse.ArgumentParser, *, default_timeout: int) -> None:
    _add_common_arguments(subparser)
    subparser.add_argument(
        "--timeout-seconds",
        type=float,
        default=default_timeout,
        help="How long to wait for the transcript before failing.",
    )
    subparser.add_argument(
        "--text-out",
        help="Optional UTF-8 text output path for the final transcript.",
    )
    subparser.add_argument(
        "--timecodes",
        action="store_true",
        help="Include [HH:MM:SS] prefixes in the final transcript output.",
    )


def _add_browser_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--headed",
        action="store_true",
        help="Run Chromium with a visible window instead of headless mode.",
    )
    subparser.add_argument(
        "--browser-exe",
        default=str(default_browser_executable()),
        help="Override the Chromium executable used for browser-driven URL submission.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Speech2Text requests from CMD or Python."
    )
    subparsers = parser.add_subparsers(dest="request_name", required=True)

    for name in ("list", "rate", "csrf", "all"):
        subparser = subparsers.add_parser(name)
        _add_common_arguments(subparser)

    for name in ("job", "queue"):
        subparser = subparsers.add_parser(name)
        _add_common_arguments(subparser)
        _add_job_argument(subparser, required=True)

    for name in ("txt",):
        subparser = subparsers.add_parser(name)
        _add_common_arguments(subparser)
        _add_audio_argument(subparser, required=True)

    subparser = subparsers.add_parser("wav")
    _add_common_arguments(subparser)
    _add_job_argument(subparser, required=True)
    _add_audio_argument(subparser, required=True)

    subparser = subparsers.add_parser("bind-ws")
    _add_common_arguments(subparser)
    subparser.add_argument("--client-id", required=True, help="Client id for /bind-to-ws.")

    subparser = subparsers.add_parser("transcript")
    _add_transcribe_arguments(subparser, default_timeout=60)
    _add_job_argument(subparser, required=True)

    subparser = subparsers.add_parser("transcribe-file")
    _add_transcribe_arguments(subparser, default_timeout=180)
    subparser.add_argument(
        "--file",
        required=True,
        help="Absolute or relative path to a local audio/video file.",
    )

    subparser = subparsers.add_parser("transcribe-url")
    _add_transcribe_arguments(subparser, default_timeout=360)
    _add_browser_arguments(subparser)
    subparser.add_argument(
        "--source-url",
        required=True,
        help="Public source URL accepted by speech2text.ru.",
    )

    return parser


def _result_summary_lines(result: BruRunResult) -> Iterable[str]:
    yield f"Exit code: {result.returncode}"
    yield f"Report: {result.report_path}"
    iteration = None
    if isinstance(result.report, list) and result.report:
        iteration = result.report[0]
    elif isinstance(result.report, dict):
        iteration = result.report

    if iteration and iteration.get("results"):
        first = iteration["results"][0]
        response = first.get("response") or {}
        status = response.get("status")
        name = first.get("name") or first.get("request", {}).get("name")
        if name:
            yield f"Request: {name}"
        if status is not None:
            yield f"HTTP status: {status}"


def _site_result_summary_lines(result: SiteActionResult) -> Iterable[str]:
    yield f"Report: {result.report_path}"
    yield f"Mode: {result.mode}"
    yield f"Job id: {result.job_id}"
    if result.audio_file_name:
        yield f"Audio file: {result.audio_file_name}"
    yield f"Interactive: {result.interactive_url}"
    yield f"Transcript lines: {len(result.transcript.splitlines())}"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    env_file = Path(args.env_file) if getattr(args, "env_file", None) else default_env_file()
    env_defaults = load_runtime_defaults(env_file)

    client = Speech2TextBruClient(
        env_file=env_file,
        reports_root=REPORTS_ROOT,
    )
    site_client = Speech2TextSiteClient(
        base_url=getattr(args, "base_url", None) or env_defaults.get("base_url", "https://speech2text.ru"),
        env_file=env_file,
        reports_root=REPORTS_ROOT,
        browser_executable=Path(getattr(args, "browser_exe", str(default_browser_executable()))),
    )

    try:
        if args.request_name == "transcript":
            result = site_client.get_transcript(
                args.job_id,
                cookie_header=getattr(args, "cookie_header", None),
                accept_language=getattr(args, "accept_language", None),
                user_agent=getattr(args, "user_agent", None),
                include_timecodes=args.timecodes,
                timeout_seconds=args.timeout_seconds,
                report_path=getattr(args, "report_path", None),
                text_out=getattr(args, "text_out", None),
            )
            for line in _site_result_summary_lines(result):
                print(line)
            print()
            print(result.transcript)
            return 0

        if args.request_name == "transcribe-file":
            result = site_client.transcribe_file(
                args.file,
                cookie_header=getattr(args, "cookie_header", None),
                accept_language=getattr(args, "accept_language", None),
                user_agent=getattr(args, "user_agent", None),
                include_timecodes=args.timecodes,
                timeout_seconds=args.timeout_seconds,
                report_path=getattr(args, "report_path", None),
                text_out=getattr(args, "text_out", None),
            )
            for line in _site_result_summary_lines(result):
                print(line)
            print()
            print(result.transcript)
            return 0

        if args.request_name == "transcribe-url":
            result = site_client.transcribe_url(
                args.source_url,
                headed=args.headed,
                include_timecodes=args.timecodes,
                timeout_seconds=args.timeout_seconds,
                report_path=getattr(args, "report_path", None),
                text_out=getattr(args, "text_out", None),
                browser_executable=getattr(args, "browser_exe", None),
            )
            for line in _site_result_summary_lines(result):
                print(line)
            print()
            print(result.transcript)
            return 0

        result = client.run_request(
            args.request_name,
            base_url=getattr(args, "base_url", None),
            accept_language=getattr(args, "accept_language", None),
            user_agent=getattr(args, "user_agent", None),
            cookie_header=getattr(args, "cookie_header", None),
            job_id=getattr(args, "job_id", None),
            audio_file_name=getattr(args, "audio_file_name", None),
            client_id=getattr(args, "client_id", None),
            report_path=getattr(args, "report_path", None),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    for line in _result_summary_lines(result):
        print(line)

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

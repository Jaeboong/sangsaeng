from __future__ import annotations

import ctypes
import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from src.pipeline import main as pipeline_main


def _application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _configure_console() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except OSError:
            pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def _message_box(message: str, *, success: bool) -> None:
    if sys.platform != "win32":
        return
    icon = 0x40 if success else 0x10
    ctypes.windll.user32.MessageBoxW(
        None,
        message,
        "상생 리포트 자동화",
        icon | 0x0,
    )


def _failure_message(stderr_text: str) -> str:
    detail = ""
    for line in reversed(stderr_text.splitlines()):
        if line.startswith("error="):
            detail = line.removeprefix("error=").strip()
            break
    if not detail:
        detail = "알 수 없는 오류"
    return (
        "처리를 완료하지 못했습니다.\n\n"
        f"원인: {detail}\n\n"
        "입력 CSV는 data/input 폴더에 넣어 주세요.\n"
        "상세 기록: output/logs의 최신 로그"
    )


def main() -> int:
    _configure_console()
    root = _application_root()
    os.chdir(root)

    arguments = sys.argv[1:]
    no_dialog = "--no-dialog" in arguments
    arguments = [argument for argument in arguments if argument != "--no-dialog"]
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = pipeline_main(arguments)

    if not no_dialog:
        if exit_code == 0:
            _message_box(
                "처리가 완료되었습니다.\n\n"
                "구글시트와 output 폴더의 결과를 확인해 주세요.",
                success=True,
            )
        else:
            _message_box(
                _failure_message(stderr_buffer.getvalue()),
                success=False,
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

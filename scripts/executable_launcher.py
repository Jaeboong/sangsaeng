from __future__ import annotations

import ctypes
import os
import sys
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


def main() -> int:
    _configure_console()
    root = _application_root()
    os.chdir(root)

    arguments = sys.argv[1:]
    no_dialog = "--no-dialog" in arguments
    arguments = [argument for argument in arguments if argument != "--no-dialog"]
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
                "처리를 완료하지 못했습니다.\n\n"
                ".env, data/input, secret 설정과 output/logs의 최신 로그를 확인해 주세요.",
                success=False,
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

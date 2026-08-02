from __future__ import annotations

import unittest

from scripts.executable_launcher import _failure_message


class ExecutableLauncherTest(unittest.TestCase):
    def test_failure_message_exposes_pipeline_error(self) -> None:
        message = _failure_message(
            "pipeline_status=failed\nerror=CSV 파일 없음: C:\\work\\data\\input\n"
        )

        self.assertIn("원인: CSV 파일 없음: C:\\work\\data\\input", message)
        self.assertIn("data/input", message)
        self.assertIn("output/logs", message)

    def test_failure_message_has_fallback(self) -> None:
        self.assertIn("원인: 알 수 없는 오류", _failure_message(""))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from rotation_radar.logging_utils import format_status_message, format_warning_message, log_status, log_warning


class LoggingUtilsTests(unittest.TestCase):
    def test_format_status_message_keeps_message_text(self) -> None:
        self.assertEqual(format_status_message("Saved data/file.csv"), "Saved data/file.csv")

    def test_format_warning_message_adds_warning_prefix_once(self) -> None:
        self.assertEqual(format_warning_message("missing file"), "Warning: missing file")
        self.assertEqual(format_warning_message("Warning: missing file"), "Warning: missing file")

    def test_log_helpers_write_to_stdout(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            log_status("status ok")
            log_warning("watch this")

        self.assertEqual(buffer.getvalue(), "status ok\nWarning: watch this\n")


if __name__ == "__main__":
    unittest.main()

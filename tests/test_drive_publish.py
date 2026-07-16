from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from rotation_radar import drive_publish
from rotation_radar.drive_publish import classify_drive_publish_error, google_oauth_warning_messages, resolve_google_oauth_config


class DrivePublishTests(unittest.TestCase):
    def test_resolve_google_oauth_config_trims_env_values_without_logging_secrets(self) -> None:
        config = resolve_google_oauth_config(
            {
                "GOOGLE_OAUTH_REFRESH_TOKEN": " refresh-token ",
                "GOOGLE_OAUTH_CLIENT_ID": " client-id ",
                "GOOGLE_OAUTH_CLIENT_SECRET": " client-secret ",
            }
        )

        self.assertTrue(config.is_complete)
        self.assertEqual(config.refresh_token, "refresh-token")
        self.assertEqual(config.client_id, "client-id")
        self.assertEqual(config.client_secret, "client-secret")

    def test_resolve_google_oauth_config_marks_missing_secret_incomplete(self) -> None:
        config = resolve_google_oauth_config(
            {
                "GOOGLE_OAUTH_REFRESH_TOKEN": "refresh-token",
                "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            }
        )

        self.assertFalse(config.is_complete)

    def test_google_oauth_warning_messages_prioritize_refresh_token_update(self) -> None:
        messages = google_oauth_warning_messages(Exception("invalid_grant: Token has been expired or revoked."))

        self.assertIn("請重新授權並更新 GitHub secret GOOGLE_OAUTH_REFRESH_TOKEN", messages[0])
        self.assertIn("Google OAuth 憑證失敗", messages[1])

    def test_classify_drive_publish_error_labels_common_failure_modes(self) -> None:
        cases = {
            "invalid_grant: token revoked": "oauth_refresh_token",
            "429 RESOURCE_EXHAUSTED quota exceeded": "rate_limited",
            "403 insufficient permissions": "permission",
            "404 file not found": "not_found",
            "temporary network failure": "unknown",
        }

        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(classify_drive_publish_error(Exception(message)), expected)

    def test_publish_defaults_to_fixed_public_pdf_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "latest.html"
            html_path.write_text("<html></html>", encoding="utf-8")
            public_pdf = Path(drive_publish.__file__).resolve().parent.parent / "public_report" / "台股股票族群輪動雷達_每日台股報告.pdf"

            with (
                patch.object(sys, "argv", ["drive_publish", "--html", str(html_path), "--date", "2026-06-08"]),
                patch.dict("os.environ", {}, clear=True),
                patch.object(drive_publish, "render_report_pdf", return_value=public_pdf) as render_pdf,
                patch.object(drive_publish, "upload_file_to_drive", return_value="https://drive.example/file") as upload_file,
            ):
                drive_publish.main()

            render_pdf.assert_called_once_with(html_path, public_pdf)
            upload_file.assert_called_once()
            self.assertEqual(upload_file.call_args.args[0], public_pdf)
            self.assertEqual(upload_file.call_args.kwargs["file_name"], "台股股票族群輪動雷達_每日台股報告.pdf")
            self.assertTrue(upload_file.call_args.kwargs["make_public"])

    def test_env_flag_accepts_common_true_values(self) -> None:
        with patch.dict("os.environ", {"ROTATION_ENABLE_DATED_BACKUP": "true"}, clear=True):
            self.assertTrue(drive_publish._env_flag("ROTATION_ENABLE_DATED_BACKUP"))

    def test_fixed_drive_pdf_modified_after_cycle_start_is_current(self) -> None:
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "radar", "name": drive_publish.PUBLIC_FIXED_FILE_NAME, "modifiedTime": "2026-07-15T08:30:00Z"}]
        }

        with patch.object(drive_publish, "build_google_drive_service", return_value=(service, "OAuth")):
            current = drive_publish.is_public_report_current(date(2026, 7, 15), "folder")

        self.assertTrue(current)

    def test_stale_fixed_drive_pdf_is_not_current(self) -> None:
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "radar", "name": drive_publish.PUBLIC_FIXED_FILE_NAME, "modifiedTime": "2026-07-15T06:00:00Z"}]
        }

        with patch.object(drive_publish, "build_google_drive_service", return_value=(service, "OAuth")):
            current = drive_publish.is_public_report_current(date(2026, 7, 15), "folder")

        self.assertFalse(current)


if __name__ == "__main__":
    unittest.main()

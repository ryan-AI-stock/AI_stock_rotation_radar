from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()

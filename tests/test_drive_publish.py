from __future__ import annotations

import unittest

from rotation_radar.drive_publish import google_oauth_warning_messages, resolve_google_oauth_config


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


if __name__ == "__main__":
    unittest.main()

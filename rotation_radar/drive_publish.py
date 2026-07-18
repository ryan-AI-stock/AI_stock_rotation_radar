from __future__ import annotations

import argparse
import multiprocessing
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .logging_utils import log_warning


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
BACKUP_FOLDER_ID = "16SmfPgMMIs7MWteeX1h2EkhSIEaGvpHn"
PUBLIC_FOLDER_ID = "16SmfPgMMIs7MWteeX1h2EkhSIEaGvpHn"
PRIVATE_FOLDER_ID = "1O6Se-HfI7ZDTQ-LWeAO6f8vtvoLcCzIj"
BACKUP_FILE_TEMPLATE = "台股股票族群輪動雷達_每日台股報告.pdf"
PUBLIC_FIXED_FILE_NAME = "台股股票族群輪動雷達_每日台股報告.pdf"
PRIVATE_FIXED_FILE_NAME = "私人策略操作總覽_每日報告.pdf"
ENABLE_DATED_BACKUP_ENV = "ROTATION_ENABLE_DATED_BACKUP"


@dataclass(frozen=True)
class GoogleOAuthConfig:
    refresh_token: str
    client_id: str
    client_secret: str

    @property
    def is_complete(self) -> bool:
        return bool(self.refresh_token and self.client_id and self.client_secret)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the rotation radar report PDF to Google Drive.")
    parser.add_argument("--html", default="reports/latest.html", help="Generated HTML report path.")
    parser.add_argument(
        "--private-html",
        default="reports/private_strategy_daily.html",
        help="Private strategy-report HTML path.",
    )
    parser.add_argument("--date", help="Report date, YYYY-MM-DD. Defaults to current Asia/Taipei date.")
    parser.add_argument("--skip-upload", action="store_true", help="Render PDFs only; do not upload to Google Drive.")
    parser.add_argument(
        "--check-current-report",
        action="store_true",
        help="Exit 0 when the fixed Drive PDF is current for --date; exit 3 otherwise.",
    )
    parser.add_argument(
        "--skip-public-upload",
        action="store_true",
        help="Render PDF without updating the fixed public PDF on Drive. Dated backup upload is deprecated and disabled unless ROTATION_ENABLE_DATED_BACKUP=true.",
    )
    args = parser.parse_args()

    report_date = _report_date(args.date)
    public_folder_id = os.environ.get("ROTATION_PUBLIC_REPORT_DRIVE_FOLDER_ID") or PUBLIC_FOLDER_ID
    private_folder_id = os.environ.get("ROTATION_PRIVATE_REPORT_DRIVE_FOLDER_ID") or PRIVATE_FOLDER_ID
    public_file_id = os.environ.get("ROTATION_PUBLIC_REPORT_DRIVE_FILE_ID", "")
    if args.check_current_report:
        current = is_public_report_current(
            report_date.date(),
            public_folder_id,
            public_file_id.strip() or None,
        )
        print(f"drive_report_current={str(current).lower()} report_date={report_date.date().isoformat()}")
        raise SystemExit(0 if current else 3)

    html_path = Path(args.html)
    if not html_path.exists():
        raise SystemExit(f"Report HTML not found: {html_path}")
    private_html_path = Path(args.private_html)
    if not private_html_path.exists():
        raise SystemExit(f"Private trading-guide HTML not found: {private_html_path}")
    assert_public_report_safe(html_path)

    date_key = report_date.strftime("%Y%m%d")
    enable_dated_backup = _env_flag(ENABLE_DATED_BACKUP_ENV)

    public_pdf = Path(__file__).resolve().parent.parent / "public_report" / PUBLIC_FIXED_FILE_NAME
    public_pdf = render_report_pdf(html_path, public_pdf)
    if not public_pdf:
        raise SystemExit("PDF render failed; aborting Drive publish.")

    print(f"已產生免費觀眾固定 PDF：{public_pdf}")
    private_pdf = Path(__file__).resolve().parent.parent / "private_report" / PRIVATE_FIXED_FILE_NAME
    private_pdf = render_report_pdf(private_html_path, private_pdf)
    if not private_pdf:
        raise SystemExit("Private PDF render failed; aborting Drive publish.")
    print(f"已產生私人操作指南 PDF：{private_pdf}")
    backup_pdf: Path | None = None
    if enable_dated_backup:
        # Deprecated: kept only for manual rollback. The default publishing path
        # now creates a single fixed public PDF for the free audience.
        backup_pdf = Path(__file__).resolve().parent.parent / "reports" / BACKUP_FILE_TEMPLATE.format(date_key=date_key)
        backup_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(public_pdf, backup_pdf)
        print(f"已產生自用備份 PDF（deprecated）：{backup_pdf}")
    else:
        print(f"{ENABLE_DATED_BACKUP_ENV}=false，略過 dated backup PDF：{BACKUP_FILE_TEMPLATE.format(date_key=date_key)}")
    if args.skip_upload:
        print("skip-upload=true，僅產生 PDF，不上傳 Google Drive。")
        return

    private_link = upload_file_to_drive(
        private_pdf,
        private_folder_id,
        "application/pdf",
        file_name=PRIVATE_FIXED_FILE_NAME,
        make_public=False,
    )
    if private_link:
        print(f"已上傳或更新私人操作指南 PDF：{private_link}")
    else:
        raise SystemExit("私人操作指南 Google Drive PDF 上傳失敗，發布流程中止。")

    if enable_dated_backup and backup_pdf:
        backup_folder_id = (
            os.environ.get("ROTATION_REPORT_DRIVE_FOLDER_ID")
            or BACKUP_FOLDER_ID
        )
        backup_link = upload_file_to_drive(
            backup_pdf,
            backup_folder_id,
            "application/pdf",
            file_name=backup_pdf.name,
            make_public=False,
        )
        if backup_link:
            print(f"已上傳或更新自用備份 PDF（deprecated）：{backup_link}")
        else:
            raise SystemExit("自用備份 Google Drive PDF 上傳失敗，發布流程中止。")

    if args.skip_public_upload:
        print("skip-public-upload=true，略過免費觀眾固定 PDF 上傳。")
        return

    public_link = upload_file_to_drive(
        public_pdf,
        public_folder_id,
        "application/pdf",
        file_name=PUBLIC_FIXED_FILE_NAME,
        make_public=True,
        file_id=public_file_id.strip() or None,
    )
    if public_link:
        print(f"已上傳或更新免費觀眾固定 PDF：{public_link}")
    else:
        raise SystemExit("免費觀眾 Google Drive PDF 上傳失敗，發布流程中止。")


def render_report_pdf(html_path: Path, output_path: Path) -> Path | None:
    output = Path(output_path)
    if not output.is_absolute():
        output = Path(__file__).resolve().parent.parent / output
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"開始產生 PDF：{output}")
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    process = ctx.Process(target=_render_report_pdf_worker, args=(str(html_path.resolve()), str(output), result_queue))
    timeout_seconds = int(os.environ.get("PDF_RENDER_TIMEOUT_SECONDS", "60"))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(10)
        if output.exists() and output.stat().st_size > 0:
            print(f"Warning: PDF 子程序逾時但檔案已產生，繼續使用：{output}")
            return output
        print("Warning: PDF 子程序逾時且未產生有效檔案")
        return None

    if process.exitcode != 0:
        message = _queue_message(result_queue)
        print(f"Warning: 產生 PDF 失敗：{message or f'exit code {process.exitcode}'}")
        return None
    if output.exists() and output.stat().st_size > 0:
        print(f"PDF 已產生：{output}")
        return output
    print("Warning: PDF 子程序結束但未產生有效檔案")
    return None


def assert_public_report_safe(html_path: Path) -> None:
    html = html_path.read_text(encoding="utf-8")
    private_markers = (
        "正式 0050 訊號 / 00631L 執行",
        "CD blocked trading dates",
        "00631L 實際部位",
        "私人操作指南 | 不公開發布",
    )
    leaked = [marker for marker in private_markers if marker in html]
    if leaked:
        raise SystemExit(f"Public report contains private trading content: {', '.join(leaked)}")


def _render_report_pdf_worker(html_path: str, output_path: str, result_queue) -> None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page(viewport={"width": 900, "height": 1260}, device_scale_factor=1)
            page.goto(Path(html_path).as_uri(), wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1_000)
            page.pdf(
                path=output_path,
                print_background=True,
                prefer_css_page_size=True,
            )
            browser.close()
    except Exception as exc:
        result_queue.put(str(exc))
        raise


def _queue_message(result_queue) -> str:
    try:
        return result_queue.get_nowait()
    except Exception:
        return ""


def upload_file_to_drive(
    file_path: Path,
    folder_id: str,
    mime_type: str,
    file_name: str,
    make_public: bool = False,
    file_id: str | None = None,
) -> str | None:
    if not folder_id:
        print("Warning: 未設定 Google Drive folder_id，跳過上傳")
        return None
    try:
        from googleapiclient.http import MediaFileUpload
    except Exception as exc:
        print(f"Warning: 未安裝 Google Drive API 套件，跳過上傳：{exc}")
        return None

    service, auth_mode = build_google_drive_service()
    if not service:
        print("Warning: 未設定 Google OAuth 憑證，已保留本機 PDF 但跳過上傳")
        return None

    try:
        print(f"使用 Google Drive {auth_mode} 憑證上傳 PDF：{file_name}")
        media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=False)
        target = None
        if file_id:
            try:
                target = service.files().get(
                    fileId=file_id,
                    fields="id,name,webViewLink",
                    supportsAllDrives=True,
                ).execute()
            except Exception as exc:
                print(f"Warning: 固定 file_id 無法讀取，改用檔名搜尋：{exc}")

        if not target:
            query = (
                f"'{folder_id}' in parents and "
                f"name = '{_drive_name_query(file_name)}' and "
                "trashed = false"
            )
            existing = service.files().list(
                q=query,
                fields="files(id,name,webViewLink)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute().get("files", [])
            target = existing[0] if existing else None

        if target:
            uploaded = service.files().update(
                fileId=target["id"],
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            ).execute()
            print(f"已更新 Google Drive PDF：{uploaded.get('name')}｜file_id={uploaded.get('id')}")
        else:
            uploaded = service.files().create(
                body={"name": file_name, "parents": [folder_id]},
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            ).execute()
            print(f"已建立 Google Drive PDF：{uploaded.get('name')}｜file_id={uploaded.get('id')}")

        if make_public:
            try:
                service.permissions().create(
                    fileId=uploaded["id"],
                    body={"type": "anyone", "role": "reader"},
                    supportsAllDrives=True,
                ).execute()
            except Exception as exc:
                print(f"Warning: 設定公開讀取失敗，請確認 Drive 權限：{exc}")
        return uploaded.get("webViewLink")
    except Exception as exc:
        print(f"Warning: 上傳 Google Drive PDF 失敗：{exc}")
        return None


def is_public_report_current(
    report_date: date,
    folder_id: str,
    file_id: str | None = None,
) -> bool:
    """Use the fixed Drive PDF modified time as the scheduled completion authority."""
    if not folder_id:
        return False
    service, _auth_mode = build_google_drive_service()
    if not service:
        return False
    try:
        file_info = None
        if file_id:
            file_info = service.files().get(
                fileId=file_id,
                fields="id,name,modifiedTime",
                supportsAllDrives=True,
            ).execute()
        if not file_info:
            query = (
                f"'{folder_id}' in parents and "
                f"name = '{_drive_name_query(PUBLIC_FIXED_FILE_NAME)}' and "
                "trashed = false"
            )
            files = service.files().list(
                q=query,
                fields="files(id,name,modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute().get("files", [])
            file_info = files[0] if files else None
        if not file_info or not file_info.get("modifiedTime"):
            return False
        modified = datetime.fromisoformat(file_info["modifiedTime"].replace("Z", "+00:00")).astimezone(TAIPEI_TZ)
        cycle_start = datetime.combine(report_date, time(15, 0), tzinfo=TAIPEI_TZ)
        return modified >= cycle_start
    except Exception as exc:
        print(f"Warning: 無法檢查 Google Drive 當日 Radar 報告，繼續產報避免漏產：{exc}")
        return False


def build_google_drive_service():
    try:
        from googleapiclient.discovery import build
    except Exception as exc:
        print(f"Warning: 未安裝 Google Drive API 套件：{exc}")
        return None, ""

    credentials, auth_mode = _build_google_drive_credentials()
    if not credentials:
        return None, ""
    return build("drive", "v3", credentials=credentials, cache_discovery=False), auth_mode


def _build_google_drive_credentials():
    oauth_config = resolve_google_oauth_config(os.environ)
    if not oauth_config.is_complete:
        log_warning("未設定 Google OAuth 憑證，跳過 Google Drive 操作")
        return None, ""

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        credentials = Credentials(
            token=None,
            refresh_token=oauth_config.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=oauth_config.client_id,
            client_secret=oauth_config.client_secret,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        credentials.refresh(Request())
        return credentials, "OAuth"
    except Exception as exc:
        for message in google_oauth_warning_messages(exc):
            log_warning(message)
        return None, ""


def resolve_google_oauth_config(env: Mapping[str, str]) -> GoogleOAuthConfig:
    return GoogleOAuthConfig(
        refresh_token=env.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip(),
        client_id=env.get("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        client_secret=env.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
    )


def google_oauth_warning_messages(exc: Exception) -> list[str]:
    messages: list[str] = []
    if classify_drive_publish_error(exc) == "oauth_refresh_token":
        messages.append("Google OAuth refresh token 已失效或被撤銷，請重新授權並更新 GitHub secret GOOGLE_OAUTH_REFRESH_TOKEN")
    messages.append(f"Google OAuth 憑證失敗：{exc}")
    return messages


def classify_drive_publish_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "invalid_grant" in message or "invalid_token" in message or "expired" in message or "revoked" in message:
        return "oauth_refresh_token"
    if "rate limit" in message or "quota" in message or "429" in message or "resource_exhausted" in message:
        return "rate_limited"
    if "permission" in message or "forbidden" in message or "403" in message or "insufficient" in message:
        return "permission"
    if "not found" in message or "404" in message:
        return "not_found"
    return "unknown"


def _drive_name_query(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


def _report_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(TAIPEI_TZ)
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"Invalid --date value, expected YYYY-MM-DD: {raw}") from exc
    return parsed.replace(tzinfo=TAIPEI_TZ)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    main()

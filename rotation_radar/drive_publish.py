from __future__ import annotations

import argparse
import multiprocessing
import os
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
BACKUP_FOLDER_ID = "1UsIMl0BOH0_K0awNwiQfoJnsCpXyXyMC"
PUBLIC_FOLDER_ID = "1jSHKWt8KkkewswQfeVyBPFCT7jL1dp8_"
BACKUP_FILE_TEMPLATE = "每日題材輪動雷達_{date_key}.pdf"
PUBLIC_FIXED_FILE_NAME = "每日題材輪動雷達.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the rotation radar report PDF to Google Drive.")
    parser.add_argument("--html", default="reports/latest.html", help="Generated HTML report path.")
    parser.add_argument("--date", help="Report date, YYYY-MM-DD. Defaults to current Asia/Taipei date.")
    parser.add_argument("--skip-upload", action="store_true", help="Render PDFs only; do not upload to Google Drive.")
    parser.add_argument("--skip-public-upload", action="store_true", help="Upload only the dated backup PDF, not the fixed public PDF.")
    args = parser.parse_args()

    html_path = Path(args.html)
    if not html_path.exists():
        raise SystemExit(f"Report HTML not found: {html_path}")

    report_date = _report_date(args.date)
    date_key = report_date.strftime("%Y%m%d")

    backup_pdf = render_report_pdf(html_path, Path("reports") / BACKUP_FILE_TEMPLATE.format(date_key=date_key))
    if not backup_pdf:
        raise SystemExit("PDF render failed; aborting Drive publish.")
    public_pdf = Path(__file__).resolve().parent.parent / "public_report" / PUBLIC_FIXED_FILE_NAME
    public_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(backup_pdf, public_pdf)

    print(f"已產生自用備份 PDF：{backup_pdf}")
    print(f"已產生免費觀眾固定 PDF：{public_pdf}")
    if args.skip_upload:
        print("skip-upload=true，僅產生 PDF，不上傳 Google Drive。")
        return

    backup_folder_id = (
        os.environ.get("ROTATION_REPORT_DRIVE_FOLDER_ID")
        or BACKUP_FOLDER_ID
    )
    public_folder_id = (
        os.environ.get("ROTATION_PUBLIC_REPORT_DRIVE_FOLDER_ID")
        or PUBLIC_FOLDER_ID
    )
    public_file_id = os.environ.get("ROTATION_PUBLIC_REPORT_DRIVE_FILE_ID", "")

    backup_link = upload_file_to_drive(
        backup_pdf,
        backup_folder_id,
        "application/pdf",
        file_name=backup_pdf.name,
        make_public=False,
    )
    if backup_link:
        print(f"已上傳或更新自用備份 PDF：{backup_link}")
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
    refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not (refresh_token and client_id and client_secret):
        print("Warning: 未設定 Google OAuth 憑證，跳過 Google Drive 操作")
        return None, ""

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        credentials.refresh(Request())
        return credentials, "OAuth"
    except Exception as exc:
        msg = str(exc)
        if "invalid_grant" in msg or "invalid_token" in msg or "expired" in msg.lower() or "revoked" in msg.lower():
            print("Warning: Google OAuth refresh token 已失效或被撤銷，請重新授權並更新 GitHub secret GOOGLE_OAUTH_REFRESH_TOKEN")
        print(f"Warning: Google OAuth 憑證失敗：{exc}")
        return None, ""


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


if __name__ == "__main__":
    main()

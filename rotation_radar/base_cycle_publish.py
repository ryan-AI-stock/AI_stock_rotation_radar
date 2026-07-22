from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from .drive_publish import PRIVATE_FOLDER_ID, _fixed_report_current, render_report_pdf, upload_file_to_drive


FIXED_FILE_NAME = "強勢股低基期Top10_每日追蹤報告.pdf"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", default="reports/current_base_cycle_top10_daily.html")
    parser.add_argument("--date", required=True)
    parser.add_argument("--check-current-report", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    folder = os.environ.get("ROTATION_PRIVATE_REPORT_DRIVE_FOLDER_ID") or PRIVATE_FOLDER_ID
    if args.check_current_report:
        current = _fixed_report_current(report_date, folder, FIXED_FILE_NAME)
        print(f"base_cycle_report_current={str(current).lower()} report_date={args.date}")
        raise SystemExit(0 if current else 3)
    pdf = Path("private_report") / FIXED_FILE_NAME
    rendered = render_report_pdf(Path(args.html), pdf)
    if not rendered:
        raise SystemExit("Base-cycle report PDF render failed")
    if args.skip_upload:
        return
    link = upload_file_to_drive(rendered, folder, "application/pdf", file_name=FIXED_FILE_NAME, make_public=False)
    if not link:
        raise SystemExit("Base-cycle report Drive upload failed")
    print(f"已更新私人基期追蹤報告：{link}")


if __name__ == "__main__":
    main()

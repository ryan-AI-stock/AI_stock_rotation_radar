from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from .drive_publish import (
    PRIVATE_FOLDER_ID,
    _fixed_report_current,
    render_report_pdf,
    upload_file_to_drive,
)


FIXED_FILE_NAME = "最新版個股模型V4-D_Top1每日追蹤報告.pdf"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", default="reports/formal_v4d_top1_daily.html")
    parser.add_argument("--date", required=True)
    parser.add_argument("--check-current-report", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    folder = os.environ.get(
        "ROTATION_PRIVATE_REPORT_DRIVE_FOLDER_ID", PRIVATE_FOLDER_ID
    )
    if args.check_current_report:
        current = _fixed_report_current(report_date, folder, FIXED_FILE_NAME)
        print(
            f"v4d_top1_report_current={str(current).lower()} report_date={args.date}"
        )
        raise SystemExit(0 if current else 1)
    pdf = Path("private_report") / FIXED_FILE_NAME
    rendered = render_report_pdf(Path(args.html), pdf)
    if rendered is None:
        raise SystemExit("V4-D Top1 PDF rendering failed")
    if args.skip_upload:
        return
    link = upload_file_to_drive(
        rendered,
        folder,
        "application/pdf",
        file_name=FIXED_FILE_NAME,
        make_public=False,
    )
    if not link:
        raise SystemExit("V4-D Top1 PDF upload failed")
    print(link)


if __name__ == "__main__":
    main()

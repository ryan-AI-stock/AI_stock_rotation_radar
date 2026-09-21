import unittest
from datetime import date
from rotation_radar.publication_audit import pdf_date, last_completed_week, assess


class PublicationAuditTests(unittest.TestCase):
    def test_dates_from_labels_not_news(self):
        self.assertEqual(pdf_date('daily_pdf', '新聞2026-09-21\n2026/09/18 收盤後整理'), '2026-09-18')
        self.assertEqual(pdf_date('weekly_pdf', '2026/09/18｜第38週'), '2026-09-18')
        self.assertEqual(pdf_date('radar_pdf', '產出時間：2026-09-18'), '2026-09-18')
        with self.assertRaises(ValueError):
            pdf_date('daily_pdf', 'modifiedTime 2026-09-18')

    def test_weekly_midweek_and_holiday(self):
        self.assertEqual(last_completed_week(date(2026,9,21), set(), set()), date(2026,9,18))
        self.assertEqual(last_completed_week(date(2026,9,18), set(), set()), date(2026,9,18))
        self.assertEqual(last_completed_week(date(2026,9,17), set(), {date(2026,9,18)}), date(2026,9,17))

    def test_future_not_success(self):
        self.assertEqual(assess('2026-09-18', '2026-09-21'), 'unexpected_future')
        self.assertEqual(assess('2026-09-18', '2026-09-17'), 'stale')

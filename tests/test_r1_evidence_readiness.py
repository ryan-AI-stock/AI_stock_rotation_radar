import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.evidence_readiness import materialize


class R1EvidenceReadinessTest(unittest.TestCase):
    def test_eps_revision_progress_exposes_horizon_dates_without_backfill(self):
        from r1.evidence_readiness import _eps_revision_progress
        with TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("2026-10-02.json").write_text(json.dumps({
                "rows": [{"ticker": "2408", "fiscal_year": 2027, "mean_eps": 100, "status": "READY"}],
            }), encoding="utf-8")
            result = _eps_revision_progress(root, as_of_date="2026-10-03", fiscal_year=2027)
            self.assertEqual(result["first_observation_date"], "2026-10-02")
            self.assertEqual(result["earliest_calendar_eligibility"], {
                "1w": "2026-10-09", "4w": "2026-10-30", "12w": "2026-12-25",
            })
            self.assertEqual(result["ready_counts"], {"1w": 0, "4w": 0, "12w": 0})
    def test_missing_files_block_every_ticker(self):
        with TemporaryDirectory() as folder:
            result = materialize(config_path="config/r1.json", consensus_path=Path(folder) / "none.csv",
                                 catalyst_path=Path(folder) / "none2.csv", as_of_date="2026-10-01")
        self.assertEqual(result["requested_ticker_count"], 14)
        self.assertEqual(result["trade_ready_count"], 0)
        self.assertEqual(result["component_score_ready_count"], 0)
        self.assertFalse(result["action_policy_approved"])
        self.assertFalse(result["active_in_trade_decision"])

    def test_catalyst_requires_two_independent_source_families(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            consensus = root / "consensus.csv"
            evidence = root / "evidence.csv"
            catalysts = root / "events.csv"
            consensus.write_text(
                "ticker,fiscal_year,mean_eps,median_eps,high_eps,low_eps,analyst_count,source,published_at,available_at,retrieved_at,quality,status\n"
                "2330,2027,100,100,,,10,x,2026-09-01,2026-09-01,2026-10-01,MEDIUM,READY\n",
                encoding="utf-8",
            )
            evidence.write_text(
                "ticker,fiscal_year,source_url,source_family,source_tier,available_at,note\n"
                "2330,2027,https://a,a,1,2026-09-01,x\n"
                "2330,2027,https://b,b,2,2026-09-01,x\n",
                encoding="utf-8",
            )
            header = ("event_date,ticker,event_type,description,source_url,source_family,source_tier,"
                      "impact_direction,impact_score,confidence,expiry_weeks,affected_bottleneck,"
                      "published_at,available_at,retrieved_at\n")
            catalysts.write_text(
                header
                + "2026-09-01,2330,CAPACITY_EXPANSION,x,https://a/1,same,1,UP,80,0.8,12,compute,2026-09-01,2026-09-01,2026-10-01\n"
                + "2026-09-02,2330,CAPACITY_TIGHTNESS,x,https://a/2,same,2,UP,80,0.8,12,compute,2026-09-02,2026-09-02,2026-10-01\n",
                encoding="utf-8",
            )
            result = materialize(
                config_path="config/r1.json", consensus_path=consensus,
                catalyst_path=catalysts, consensus_evidence_path=evidence,
                catalyst_evidence_path=root / "missing-catalyst-evidence.csv",
                daily_source_root=root / "missing-daily-sources",
                as_of_date="2026-10-01",
            )
            row = next(item for item in result["rows"] if item["ticker"] == "2330")
            self.assertTrue(row["consensus_ready"])
            self.assertFalse(row["catalyst_ready"])

    def test_price_chip_requires_twenty_complete_dates(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            daily = root / "daily"
            daily.mkdir()
            for day in range(1, 21):
                target = f"2026-09-{day:02d}"
                (daily / f"{target}.json").write_text(json.dumps({
                    "date": target,
                    "price_rows": [{"ticker": "2330", "close": 100}],
                    "chip_rows": [
                        {"ticker": "2330", "family": "institutional"},
                        {"ticker": "2330", "family": "margin_short"},
                    ],
                }), encoding="utf-8")
            result = materialize(
                config_path="config/r1.json", consensus_path=root / "none.csv",
                catalyst_path=root / "none2.csv", daily_source_root=daily,
                as_of_date="2026-10-01",
            )
            row = next(item for item in result["rows"] if item["ticker"] == "2330")
            self.assertTrue(row["price_chip_ready"])
            self.assertFalse(row["current_chip_ready"])
            self.assertEqual(row["price_chip_coverage"]["institutional_days"], 20)

    def test_current_chip_requires_both_exact_date_families(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            daily = root / "daily"
            daily.mkdir()
            target = "2026-10-01"
            (daily / f"{target}.json").write_text(json.dumps({
                "date": target,
                "price_rows": [{"ticker": "2330", "close": 100}],
                "chip_rows": [
                    {"ticker": "2330", "family": "institutional"},
                    {"ticker": "2330", "family": "margin_short"},
                ],
            }), encoding="utf-8")
            result = materialize(
                config_path="config/r1.json", consensus_path=root / "none.csv",
                catalyst_path=root / "none2.csv", daily_source_root=daily,
                as_of_date=target,
            )
            row = next(item for item in result["rows"] if item["ticker"] == "2330")
            self.assertTrue(row["current_chip_ready"])
            self.assertEqual(result["current_chip_ready_count"], 1)

    def test_valuation_and_all_revision_horizons_are_independent_readiness_gates(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            history = root / "history"
            history.mkdir()
            for snapshot_date in ("2026-07-01", "2026-09-01", "2026-09-25", "2026-10-02"):
                history.joinpath(f"{snapshot_date}.json").write_text(json.dumps({
                    "rows": [{
                        "ticker": "2330", "fiscal_year": 2027,
                        "mean_eps": 100, "status": "READY",
                    }],
                }), encoding="utf-8")
            valuation = root / "valuation.csv"
            valuation.write_text(
                "ticker,data_date,next_year_forward_pe,five_year_percentile,five_year_median_pe,source_url,retrieved_at,quality\n"
                "2330,2026-10-02,17.6,0.77,16.0,https://example.test,2026-10-02,HIGH\n",
                encoding="utf-8",
            )
            result = materialize(
                config_path="config/r1.json", consensus_path=root / "none.csv",
                catalyst_path=root / "none2.csv", daily_source_root=root / "daily",
                valuation_reference_path=valuation, consensus_history_root=history,
                as_of_date="2026-10-02",
            )
            row = next(item for item in result["rows"] if item["ticker"] == "2330")
            self.assertTrue(row["valuation_ready"])
            self.assertTrue(row["eps_revision_ready"])


if __name__ == "__main__":
    unittest.main()

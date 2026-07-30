import unittest

import pandas as pd

from rotation_radar.v4d_top1_signal import (
    EXCLUDED_INDUSTRIES,
    INDUSTRY_CODE_NAMES,
    extend_adjusted_with_official_raw,
)


class V4DTop1SignalTests(unittest.TestCase):
    def test_excluded_industry_codes_resolve_to_formal_names(self) -> None:
        excluded_codes = {"02", "04", "06", "11", "12"}
        self.assertEqual(
            {INDUSTRY_CODE_NAMES[code] for code in excluded_codes},
            EXCLUDED_INDUSTRIES,
        )

    def test_official_raw_extension_uses_last_accepted_adjustment_factor(self) -> None:
        adjusted = pd.DataFrame(
            {
                "ticker": ["1234"],
                "date": [pd.Timestamp("2026-07-22")],
                "adjusted_analysis_close": [50.0],
            }
        )
        historical_raw = pd.DataFrame(
            {
                "ticker": ["1234"],
                "date": [pd.Timestamp("2026-07-22")],
                "raw_close": [100.0],
            }
        )
        recent = pd.DataFrame(
            {
                "ticker": ["1234"],
                "date": [pd.Timestamp("2026-07-23")],
                "close": [110.0],
            }
        )

        result = extend_adjusted_with_official_raw(
            adjusted, historical_raw, recent
        )

        value = result.loc[
            result["date"].eq(pd.Timestamp("2026-07-23")),
            "adjusted_analysis_close",
        ].iloc[0]
        self.assertEqual(value, 55.0)


if __name__ == "__main__":
    unittest.main()

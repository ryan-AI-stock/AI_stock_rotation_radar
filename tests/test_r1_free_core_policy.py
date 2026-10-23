import json
from pathlib import Path
import unittest

from r1.recommendations import (
    CHALLENGER_HEALTHY_THRESHOLD,
    INCUMBENT_WEAK_THRESHOLD,
    MINIMUM_SCORE_ADVANTAGE,
)
from r1.v05_rank import CORE_WEIGHTS


class R1FreeCorePolicyTest(unittest.TestCase):
    def test_runtime_weights_and_rotation_guards_match_policy(self):
        policy = json.loads(Path("config/r1_v05_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["ranking_weights"], CORE_WEIGHTS)
        guards = policy["long_hold_rotation_guardrails"]
        self.assertEqual(guards["minimum_core_score_advantage"], MINIMUM_SCORE_ADVANTAGE)
        self.assertEqual(guards["incumbent_weak_threshold"], INCUMBENT_WEAK_THRESHOLD)
        self.assertEqual(guards["challenger_healthy_threshold"], CHALLENGER_HEALTHY_THRESHOLD)


if __name__ == "__main__":
    unittest.main()

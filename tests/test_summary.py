import unittest

from app.analysis import summarize

THRESHOLDS = {"doubtful": 0.03, "bad": 0.06, "very_bad": 0.12}


def d(player, kind, error, forced=False, action="", cube=None):
    return {"player": player, "kind": kind, "error": error, "forced": forced, "action": action, "cube": cube}


NOT_CLOSE = {"nd": 0.2, "dt": -0.3, "dp": 1.0}
CLOSE = {"nd": 0.7, "dt": 0.65, "dp": 1.0}


class Summarize(unittest.TestCase):
    def test_counts_classes_and_pr_per_player(self):
        decisions = [
            d(1, "checker", 0.0), d(1, "checker", 0.05), d(1, "checker", 0.2), d(1, "checker", 0.0, forced=True),
            d(1, "cube", 0.0, action="No double", cube=NOT_CLOSE), d(1, "cube", 0.0, action="No double", cube=CLOSE),
            d(2, "take", 0.13, action="Pass", cube=CLOSE), d(2, "checker", 0.07),
        ]
        self.assertEqual(
            summarize(decisions, THRESHOLDS),
            {
                1: {"checker": {"decisions": 3, "doubtful": 1, "bad": 0, "very_bad": 1, "error": 0.25},
                    "cube": {"decisions": 1, "doubtful": 0, "bad": 0, "very_bad": 0, "error": 0.0},
                    "pr": 31.25},
                2: {"checker": {"decisions": 1, "doubtful": 0, "bad": 1, "very_bad": 0, "error": 0.07},
                    "cube": {"decisions": 1, "doubtful": 0, "bad": 0, "very_bad": 1, "error": 0.13},
                    "pr": 50.0},
            },
        )

    def test_player_without_decisions_has_no_pr(self):
        self.assertEqual(summarize([d(1, "checker", 0.0, forced=True)], THRESHOLDS)[1]["pr"], None)


if __name__ == "__main__":
    unittest.main()

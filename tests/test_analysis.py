import unittest

from app.analysis import checker_error, classify, double_error, review_state, take_error

XG_STYLE = {"doubtful": 0.02, "bad": 0.04, "very_bad": 0.08}


def candidates(*equities):
    return [{"move": f"m{i}", "equity": e} for i, e in enumerate(equities)]


class CheckerError(unittest.TestCase):
    def test_best_move_played_costs_nothing(self):
        self.assertEqual(checker_error(candidates(0.25, 0.1), 0), 0.0)

    def test_error_is_distance_to_best(self):
        self.assertAlmostEqual(checker_error(candidates(0.742, 0.636, 0.608), 1), 0.106)

    def test_best_is_found_even_if_list_is_unsorted(self):
        self.assertAlmostEqual(checker_error(candidates(-0.5, -0.4, -0.9), 2), 0.5)


class DoubleError(unittest.TestCase):
    CASES = [
        # nd, dt, dp, doubled, expected error
        ("correct no double", 0.40, 0.30, 1.0, False, 0.0),
        ("wrong double", 0.40, 0.30, 1.0, True, 0.10),
        ("missed double/take", 0.807, 0.918, 1.0, False, 0.111),
        ("correct double/take", 0.807, 0.918, 1.0, True, 0.0),
        ("missed double/pass", 0.85, 1.30, 1.0, False, 0.15),
        ("too good, played on", 1.13, 1.80, 1.0, False, 0.0),
        ("too good, doubled out", 1.13, 1.80, 1.0, True, 0.13),
    ]

    def test_cases(self):
        for name, nd, dt, dp, doubled, expected in self.CASES:
            with self.subTest(name):
                self.assertAlmostEqual(double_error(nd, dt, dp, doubled), expected)


class TakeError(unittest.TestCase):
    CASES = [
        ("correct take", 0.918, 1.0, True, 0.0),
        ("wrong pass", 0.918, 1.0, False, 0.082),
        ("wrong take", 1.30, 1.0, True, 0.30),
        ("correct pass", 1.30, 1.0, False, 0.0),
    ]

    def test_cases(self):
        for name, dt, dp, took, expected in self.CASES:
            with self.subTest(name):
                self.assertAlmostEqual(take_error(dt, dp, took), expected)


class Classify(unittest.TestCase):
    def test_boundaries(self):
        cases = [(0.0, None), (0.0199, None), (0.02, "doubtful"), (0.0399, "doubtful"),
                 (0.04, "bad"), (0.0799, "bad"), (0.08, "very_bad"), (1.5, "very_bad")]
        self.assertEqual([classify(e, XG_STYLE) for e, _ in cases], [c for _, c in cases])


class ReviewState(unittest.TestCase):
    def decisions(self):
        # (player, error, seen)
        rows = [(1, 0.05, True), (1, 0.30, False), (2, 0.025, False), (2, 0.10, True), (1, 0.01, False)]
        return [{"player": p, "error": e, "seen_at": "2026-11-11T10:00:00" if seen else None} for p, e, seen in rows]

    def test_counts_mistakes_of_both_players(self):
        self.assertEqual(review_state(self.decisions(), XG_STYLE, side=None, mark=None),
                         {"mistakes": 4, "seen": 2, "auto": False, "reviewed": False, "mark": None})

    def test_counts_only_my_side_once_every_mistake_is_seen(self):
        self.assertEqual(review_state(self.decisions(), XG_STYLE, side=2, mark=None),
                         {"mistakes": 2, "seen": 1, "auto": False, "reviewed": False, "mark": None})
        seen = [{**d, "seen_at": "x"} for d in self.decisions()]
        self.assertEqual(review_state(seen, XG_STYLE, side=2, mark=None)["reviewed"], True)

    def test_a_match_without_mistakes_is_not_reviewed_by_itself(self):
        self.assertEqual(review_state([], XG_STYLE, side=None, mark=None)["reviewed"], False)

    def test_manual_mark_wins(self):
        self.assertEqual(
            [review_state(self.decisions(), XG_STYLE, side=1, mark=m)["reviewed"] for m in (1, 0)],
            [True, False],
        )


if __name__ == "__main__":
    unittest.main()

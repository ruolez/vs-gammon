import unittest

from app.analysis import checker_error, classify, double_error, take_error

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


if __name__ == "__main__":
    unittest.main()

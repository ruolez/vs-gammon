import unittest

from app.analysis import grade_checker, grade_cube, is_correct

LEGAL = [
    {"text": "13/7 13/9", "equity": 0.40, "full": True},
    {"text": "24/18 13/9", "equity": 0.37, "full": True},
    {"text": "6/off", "equity": 0.55, "full": False},
    {"text": "24/14", "equity": 0.10, "full": False},
]
CUBE = {"nd": 0.807, "dt": 0.918, "dp": 1.0}
THRESHOLDS = {"doubtful": 0.03, "bad": 0.06, "very_bad": 0.12}


class GradeChecker(unittest.TestCase):
    def test_best_full_depth_move(self):
        self.assertEqual(grade_checker(LEGAL, 0), {"error": 0.0, "approx": False})

    def test_error_against_best_full_depth_move(self):
        graded = grade_checker(LEGAL, 1)
        self.assertEqual((round(graded["error"], 6), graded["approx"]), (0.03, False))

    def test_low_depth_estimate_is_flagged_and_never_beats_best(self):
        self.assertEqual(
            [(round(grade_checker(LEGAL, i)["error"], 6), grade_checker(LEGAL, i)["approx"]) for i in (2, 3)],
            [(0.0, True), (0.3, True)],
        )

    def test_index_out_of_range(self):
        with self.assertRaises(ValueError):
            grade_checker(LEGAL, 9)


class GradeCube(unittest.TestCase):
    def test_answers(self):
        cases = [("cube", "double", 0.0), ("cube", "no_double", 0.111), ("take", "take", 0.0), ("take", "pass", 0.082)]
        self.assertEqual([(k, a, round(grade_cube(k, CUBE, a), 6)) for k, a, _ in cases], cases)

    def test_answer_must_fit_the_decision(self):
        with self.assertRaises(ValueError):
            grade_cube("cube", CUBE, "take")


class IsCorrect(unittest.TestCase):
    def test_below_doubtful_counts_as_correct(self):
        self.assertEqual([is_correct(e, THRESHOLDS) for e in (0.0, 0.0299, 0.03, 0.2)], [True, True, False, False])


if __name__ == "__main__":
    unittest.main()

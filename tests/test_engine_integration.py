import os
import unittest

from app.engine.runner import EngineError, gnubg_available, run_analysis

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@unittest.skipUnless(gnubg_available(), "gnubg is only installed in the container")
class AnalyseGalaxyMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_analysis(os.path.join(FIXTURES, "galaxy_3pt.mat"), plies=2, threads=4)
        cls.decisions = cls.result["decisions"]

    def find(self, game_no, move_no, kind, player):
        return next(d for d in self.decisions
                    if (d["game_no"], d["move_no"], d["kind"], d["player"]) == (game_no, move_no, kind, player))

    def test_match_and_games(self):
        self.assertEqual(
            (self.result["match"], [(g["score1"], g["score2"], g["crawford"], g["winner"]) for g in self.result["games"]]),
            ({"match_length": 3, "player1": "chessgamm0n", "player2": "fishsoup"}, [(0, 0, False, 1), (2, 0, True, 1)]),
        )

    def test_double_and_take_on_line_15(self):
        double, take = self.find(1, 15, "cube", 1), self.find(1, 15, "take", 2)
        self.assertEqual(
            (double["action"], double["best"], double["error"], take["action"], take["best"], take["error"]),
            ("Double", "Double, take", 0.0, "Take", "Take", 0.0),
        )

    def test_cube_is_two_owned_by_taker_afterwards(self):
        move = self.find(1, 16, "checker", 2)
        self.assertEqual((move["cube_value"], move["cube_owner"], move["dice"]), (2, 2, [6, 6]))

    def test_sixes_mistake_matches_gnubg_grading(self):
        move = self.find(1, 16, "checker", 2)
        self.assertEqual((move["gnubg_skill"], round(move["error"], 3)), ("bad", 0.107))

    def test_no_cube_decisions_in_crawford_game(self):
        self.assertEqual([d for d in self.decisions if d["game_no"] == 2 and d["kind"] != "checker"], [])

    def test_gnubg_graded_errors_agree_with_ours(self):
        thresholds = {"doubtful": 0.03, "bad": 0.06, "very_bad": 0.12}
        from app.analysis import classify
        def gnubg_class(skill):
            return skill.replace(" ", "_") if skill else None

        mismatched = [
            (d["game_no"], d["move_no"], d["kind"], d["player"], d["gnubg_skill"], round(d["error"], 4))
            for d in self.decisions
            if classify(d["error"], thresholds) != gnubg_class(d["gnubg_skill"])
        ]
        self.assertEqual(mismatched, [])


@unittest.skipUnless(gnubg_available(), "gnubg is only installed in the container")
class AnalyseBadFile(unittest.TestCase):
    def test_garbage_input_raises_engine_error(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".mat", delete=False) as f:
            f.write("this is not a match file\n")
        with self.assertRaises(EngineError):
            run_analysis(f.name, plies=0, threads=1, timeout=120)


if __name__ == "__main__":
    unittest.main()

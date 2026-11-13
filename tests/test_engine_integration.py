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


@unittest.skipUnless(gnubg_available(), "gnubg is only installed in the container")
class DeeperAnalysisWithGnubg(unittest.TestCase):
    MAT = os.path.join(FIXTURES, "galaxy_3pt.mat")
    CHECKER = {"game_no": 1, "move_no": 3, "kind": "checker", "player": 1}

    def run_job(self, mode, settings, decision=None, moves=None):
        from app.engine import deep
        from app.engine.runner import run_deep
        lines = []
        job = {"mode": mode, "decision": decision or self.CHECKER, "threads": 4, "base_plies": 2, "moves": moves,
               "settings": deep.eval_settings(settings) if mode == "eval" else deep.rollout_settings(settings)}
        result = run_deep(self.MAT, job, on_line=lambda line: lines.append(deep.parse_progress(line)))
        return result["decision"], [p for p in lines if p]

    def test_three_ply_evaluates_the_top_moves_deeper(self):
        decision, _ = self.run_job("eval", {"checker": {"plies": 3}, "moves": {"count": 3, "within": 0.2}})
        depths = [c.get("plies") for c in decision["candidates"]]
        self.assertEqual((depths[:3], decision["action"]), ([3, 3, 3], "18/13"))

    def test_rollout_of_chosen_moves_reports_progress(self):
        moves = [[[13, 9], [6, 5]], [[18, 14], [14, 13]]]
        decision, progress = self.run_job("rollout", {"trials": 72, "seed": 1, "checker": {"plies": 0},
                                                      "cube": {"plies": 0}}, moves=moves)
        rolled = sorted(c["move"] for c in decision["candidates"] if c.get("rollout"))
        self.assertEqual((rolled, {c["rollout"]["trials"] for c in decision["candidates"] if c.get("rollout")},
                          progress[-1]), (["13/9 6/5", "18/13"], {72}, {"done": 72, "total": 72}))

    def test_cube_rollout(self):
        decision, _ = self.run_job("rollout", {"trials": 36, "seed": 1, "checker": {"plies": 0}, "cube": {"plies": 0}},
                                   decision={"game_no": 1, "move_no": 15, "kind": "cube", "player": 1})
        self.assertEqual((decision["action"], decision["cube"]["rollout"]["trials"]), ("Double", 36))

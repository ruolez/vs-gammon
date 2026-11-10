import unittest

from app.engine.walk import walk_match
from app.position import flip_frame, onroll_frame
from tests.test_position import BAR_PAIR


class FakeHelpers:
    def __init__(self):
        self.conversions = []

    def board_pair(self, position_id):
        return BAR_PAIR

    def move_text(self, move, board_pair):
        return " ".join(f"{a}/{b}" for a, b in move)

    def mwc_to_emg(self, mwc, cube, owner, on_roll, match_length, score, crawford):
        self.conversions.append((round(mwc, 3), cube, owner, on_roll, match_length, score, crawford))
        return round(mwc * 2 - 1, 6)


def mv(move, equity):
    return {"type": "eval", "move": move, "probs": [0.5, 0.1, 0.0, 0.1, 0.0], "score": equity}


def cube_analysis(nd, dt):
    return {"probs": [0.6, 0.2, 0.0, 0.1, 0.0], "nd-cubeful-eq": nd, "dt-cubeful-eq": dt}


GAME = [
    {"action": "move", "player": "X", "dice": [3, 1], "move": [[8, 5], [6, 5]], "board": "P1",
     "analysis": {**cube_analysis(0.55, 0.53), "moves": [mv([[13, 10], [24, 23]], 0.2), mv([[8, 5], [6, 5]], 0.15),
                                                          {**mv([[24, 21], [24, 23]], 0.5), "evalcontext": {"plies": 0}}],
                  "imove": 1, "skill": "doubtful"}},
    {"action": "move", "player": "O", "dice": [6, 6], "move": [[25, 19]], "board": "P2",
     "analysis": {"moves": [mv([[25, 19]], -0.3)], "imove": 0}},
    {"action": "move", "player": "X", "dice": [4, 4], "move": [], "board": "P3",
     "analysis": cube_analysis(0.60, 0.65)},
    {"action": "move", "player": "O", "dice": [2, 1], "move": [[13, 11], [6, 5]], "board": "P4",
     "analysis": {"moves": [mv([[13, 11], [6, 5]], -0.4), mv([[24, 23], [13, 11]], -0.45)], "imove": 0}},
    {"action": "double", "player": "X", "board": "P5", "analysis": cube_analysis(0.70, 0.80)},
    {"action": "take", "player": "O"},
    {"action": "move", "player": "X", "dice": [5, 2], "move": [[13, 8], [13, 11]], "board": "P6",
     "analysis": {"moves": [mv([[13, 8], [13, 11]], 0.4), mv([[13, 6]], 0.3)], "imove": 0}},
    {"action": "double", "player": "O", "board": "P7", "analysis": cube_analysis(0.62, 0.70)},
    {"action": "drop", "player": "X"},
]

MATCH = {
    "match-info": {"match-length": 7, "X": {"name": "alice"}, "O": {"name": "bob"}},
    "games": [
        {"info": {"score-X": 2, "score-O": 3, "winner": "O", "points-won": 2, "resigned": False}, "game": GAME},
        {"info": {"score-X": 2, "score-O": 5, "crawford": True, "winner": "X", "points-won": 1}, "game": []},
    ],
}


def summary(d):
    return (d["kind"], d["player"], d["move_no"], d["cube_value"], d["cube_owner"], d["action"], round(d["error"], 6))


class WalkMatch(unittest.TestCase):
    def setUp(self):
        self.helpers = FakeHelpers()
        self.result = walk_match(MATCH, self.helpers)
        self.decisions = self.result["decisions"]

    def test_decision_sequence(self):
        self.assertEqual(
            [summary(d) for d in self.decisions],
            [
                ("cube", 1, 1, 1, 0, "No double", 0.0),
                ("checker", 1, 1, 1, 0, "8/5 6/5", 0.05),
                ("checker", 2, 1, 1, 0, "25/19", 0.0),
                ("cube", 1, 2, 1, 0, "No double", 0.1),
                ("checker", 2, 2, 1, 0, "13/11 6/5", 0.0),
                ("cube", 1, 3, 1, 0, "Double", 0.0),
                ("take", 2, 3, 1, 0, "Take", 0.0),
                ("checker", 1, 4, 2, 2, "13/8 13/11", 0.0),
                ("cube", 2, 4, 2, 2, "Double", 0.0),
                ("take", 1, 5, 2, 2, "Pass", 0.6),
            ],
        )

    def test_low_ply_candidates_are_dropped(self):
        self.assertEqual(
            [c["move"] for c in self.decisions[1]["candidates"]],
            ["13/10 24/23", "8/5 6/5"],
        )

    def test_best_action_texts(self):
        self.assertEqual(
            [d["best"] for d in self.decisions],
            ["No double, take", "13/10 24/23", "25/19", "Double, take", "13/11 6/5", "Double, take",
             "Take", "13/8 13/11", "Double, take", "Take"],
        )

    def test_forced_moves_are_marked(self):
        self.assertEqual([d["forced"] for d in self.decisions if d["kind"] == "checker"], [False, True, False, False])

    def test_mwc_converted_with_cube_state_before_the_double(self):
        self.assertEqual(
            self.helpers.conversions[-2:],
            [(0.62, 2, 1, 1, 7, (2, 3), False), (0.7, 2, 1, 1, 7, (2, 3), False)],
        )

    def test_take_decision_is_seen_from_the_doubler(self):
        take = self.decisions[6]
        self.assertEqual(
            (take["on_roll"], take["player"], take["cube"]),
            (1, 2, {"nd": 0.4, "dt": 0.6, "dp": 1.0, "probs": [0.6, 0.2, 0.0, 0.1, 0.0]}),
        )

    def test_board_is_in_player1_frame(self):
        self.assertEqual(
            (self.decisions[1]["board"], self.decisions[2]["board"]),
            (onroll_frame(BAR_PAIR), flip_frame(onroll_frame(BAR_PAIR))),
        )

    def test_cube_decision_keeps_the_following_roll(self):
        self.assertEqual([self.decisions[i]["dice"] for i in (0, 3, 5)], [[3, 1], [4, 4], None])

    def test_score_and_match_context(self):
        d = self.decisions[0]
        self.assertEqual(
            (d["game_no"], d["score1"], d["score2"], d["match_length"], d["crawford_game"], d["position_id"]),
            (1, 2, 3, 7, False, "P1"),
        )

    def test_games_summary(self):
        self.assertEqual(
            self.result["games"],
            [
                {"game_no": 1, "score1": 2, "score2": 3, "crawford": False, "winner": 2, "points": 2},
                {"game_no": 2, "score1": 2, "score2": 5, "crawford": True, "winner": 1, "points": 1},
            ],
        )


class WalkMoneyGame(unittest.TestCase):
    def test_money_equities_are_not_converted(self):
        helpers = FakeHelpers()
        money = {"match-info": {"match-length": 0, "X": {"name": "a"}, "O": {"name": "b"}},
                 "games": [{"info": {"score-X": 0, "score-O": 0}, "game": GAME[4:6]}]}
        decisions = walk_match(money, helpers)["decisions"]
        self.assertEqual((helpers.conversions, decisions[0]["cube"]["nd"]), ([], 0.70))


if __name__ == "__main__":
    unittest.main()


class WalkLegalMoves(unittest.TestCase):
    def setUp(self):
        self.decisions = walk_match(MATCH, FakeHelpers())["decisions"]

    def test_every_legal_move_is_kept_with_steps_and_depth(self):
        self.assertEqual(
            self.decisions[1]["legal"],
            [
                {"steps": [[24, 21], [24, 23]], "text": "24/21 24/23", "equity": 0.5, "full": False},
                {"steps": [[13, 10], [24, 23]], "text": "13/10 24/23", "equity": 0.2, "full": True},
                {"steps": [[8, 5], [6, 5]], "text": "8/5 6/5", "equity": 0.15, "full": True},
            ],
        )

    def test_candidates_carry_steps_for_arrows(self):
        self.assertEqual([c["steps"] for c in self.decisions[1]["candidates"]], [[[13, 10], [24, 23]], [[8, 5], [6, 5]]])

    def test_cube_decisions_have_no_legal_list(self):
        self.assertEqual({d["kind"] for d in self.decisions if d.get("legal") is None}, {"cube", "take"})

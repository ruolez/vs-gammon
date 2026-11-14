import os
import unittest

from app.live.transcript import parse_mat, render_mat
from app.matfile import match_fingerprint

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "galaxy_3pt.mat")
HEADER = {"match_length": 5, "player1": "You", "player2": "Opponent"}


def read_fixture():
    with open(FIXTURE) as f:
        return f.read()


class ParseMat(unittest.TestCase):
    def test_reads_games_scores_moves_cube_actions_and_results(self):
        header, games = parse_mat(read_fixture())
        first = games[0]
        self.assertEqual(
            (header["match_length"], len(games), first["score"], first["actions"][0], first["actions"][1],
             first["result"], [a["kind"] for a in first["actions"] if a["kind"] != "move"]),
            (3, 2, (0, 0), {"player": 1, "kind": "move", "dice": (3, 1), "steps": ((8, 5), (6, 5))},
             {"player": 2, "kind": "move", "dice": (6, 4), "steps": ((24, 18), (18, 14))},
             {"winner": 1, "points": 2}, ["double", "take"]),
        )

    def test_a_dance_is_a_move_without_steps(self):
        _, games = parse_mat(read_fixture())
        self.assertIn({"player": 1, "kind": "move", "dice": (4, 4), "steps": ()}, games[0]["actions"])


class RenderMat(unittest.TestCase):
    def test_round_trip_keeps_the_match_fingerprint(self):
        text = read_fixture()
        header, games = parse_mat(text)
        self.assertEqual(match_fingerprint(render_mat(header, games)), match_fingerprint(text))

    def test_parse_after_render_gives_the_same_games(self):
        header, games = parse_mat(read_fixture())
        again = parse_mat(render_mat(header, games))
        self.assertEqual((again[0]["match_length"], again[1]), (header["match_length"], games))

    def test_a_game_in_progress_ends_after_its_last_action(self):
        games = [{"score": (0, 0), "result": None, "actions": [
            {"player": 2, "kind": "move", "dice": (5, 2), "steps": ((13, 8), (13, 11))},
            {"player": 1, "kind": "move", "dice": (6, 1), "steps": ((13, 7), (8, 7))},
            {"player": 2, "kind": "move", "dice": (4, 4), "steps": ()},
        ]}]
        lines = render_mat(HEADER, games).rstrip("\n").splitlines()
        self.assertEqual(lines[-3:], [
            " You : 0                         Opponent : 0",
            "  1)                             52: 13/11 13/8",
            "  2) 61: 13/7 8/7                44:",
        ])

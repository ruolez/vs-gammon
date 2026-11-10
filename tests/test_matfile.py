import os
import unittest

from app.matfile import parse_mat_header

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class ParseMatHeader(unittest.TestCase):
    def test_galaxy_header(self):
        with open(os.path.join(FIXTURES, "galaxy_3pt.mat"), encoding="utf-8") as f:
            header = parse_mat_header(f.read())
        self.assertEqual(
            header,
            {"site": "BackgammonGalaxy", "external_id": "50469849", "player1": "chessgamm0n", "player2": "fishsoup",
             "elo1": "2246.97", "elo2": "1838.26", "event_date": "2026-11-09", "event_time": "18:53", "match_length": 3},
        )

    def test_plain_jellyfish_file_uses_first_game_score_line(self):
        text = " 7 point match\n\n Game 1\n Alice : 0                    Bob : 0\n  1)                             31: 8/5 6/5\n"
        self.assertEqual(
            parse_mat_header(text),
            {"site": None, "external_id": None, "player1": "Alice", "player2": "Bob", "elo1": None, "elo2": None,
             "event_date": None, "event_time": None, "match_length": 7},
        )

    def test_money_session(self):
        self.assertEqual(parse_mat_header(" 0 point match\n")["match_length"], 0)

    def test_not_a_match_file(self):
        with self.assertRaises(ValueError):
            parse_mat_header("hello world\n")


if __name__ == "__main__":
    unittest.main()

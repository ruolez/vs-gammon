import os
import unittest

from app.matfile import match_fingerprint, parse_mat_header

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


LEFT_FIRST = """ 3 point match

 Game 1
 Alice : 0                       Bob : 0
  1) 31: 8/5 6/5                 64: 24/18 18/14
  2) 66: 24/18(2) 13/7*(2)       Doubles => 2
  3)  Takes                      52: 13/8 13/11
      Wins 1 point
"""
RIGHT_FIRST = """ 3 point match

 Game 1
 Bob : 0                         Alice : 0
  1)                             31: 6/5 8/5
  2) 64: 24/18 18/14             66: 24/18 24/18 13/7 13/7
  3)  Doubles => 2                Takes
  4) 52: 13/8 13/11
                                  Wins 1 point
"""


class MatchFingerprint(unittest.TestCase):
    def fixture(self):
        with open(os.path.join(FIXTURES, "galaxy_3pt.mat"), encoding="utf-8") as f:
            return f.read()

    def test_headers_do_not_matter(self):
        text = self.fixture()
        changed = text.replace('Elo "2246,97/0"', 'Elo "2250,01/0"').replace('EventTime "18.53"', 'EventTime "19.02"')
        self.assertEqual(match_fingerprint(changed), match_fingerprint(text))

    def test_same_match_with_the_columns_swapped(self):
        self.assertEqual(match_fingerprint(RIGHT_FIRST), match_fingerprint(LEFT_FIRST))

    def test_different_play_is_a_different_match(self):
        text = self.fixture()
        self.assertNotEqual(match_fingerprint(text.replace("31: 6/5 8/5", "31: 24/21 24/23", 1)), match_fingerprint(text))

    def test_different_player_is_a_different_match(self):
        text = self.fixture()
        self.assertNotEqual(match_fingerprint(text.replace("fishsoup", "fishsoup2")), match_fingerprint(text))

    def test_file_without_games_has_no_fingerprint(self):
        self.assertIsNone(match_fingerprint(" 3 point match\n"))


if __name__ == "__main__":
    unittest.main()

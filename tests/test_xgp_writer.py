import datetime
import unittest

from app.xgp.archive import read_xg_file
from app.xgp.records import CUBE, HEADER_GAME, HEADER_MATCH, MOVE, NOT_ANALYSED, get_field, record_type, split_records

UNUSED = [-1] * 8
from app.xgp.writer import build_xgp
from app.position import flip_frame

BOARD = [-1, 0, 0, 2, 2, 0, 4, 0, 2, 1, 0, 0, -6, 2, 0, 0, 0, 0, 0, -3, 0, 2, -2, -1, -2, 0]
SAVED_AT = datetime.datetime(2026, 11, 9, 18, 53)


def spot(**overrides):
    base = {
        "player1": "chessgamm0n",
        "player2": "fishsoup",
        "match_length": 7,
        "score1": 2,
        "score2": 4,
        "crawford_game": False,
        "on_roll": 1,
        "board": BOARD,
        "cube_value": 2,
        "cube_owner": 1,
        "decision": "checker",
        "dice": (6, 3),
        "action": "9/3 8/5",
        "played_steps": [[9, 3], [8, 5]],
        "comment": "",
        "guid": b"0123456789abcdef",
        "saved_at": SAVED_AT,
        "thumbnail": b"\xff\xd8thumb\xff\xd9",
    }
    base.update(overrides)
    return base


def board(own, opponent=None, own_bar=0, opponent_bar=0):
    """Frame of the player on roll: 1-24 points, 25 = own bar, 0 = the opponent's bar (negative)."""
    frame = [0] * 26
    for point, n in own.items():
        frame[point] = n
    for point, n in (opponent or {}).items():
        frame[point] = -n
    frame[25], frame[0] = own_bar, -opponent_bar
    return frame


def records_of(data):
    files = dict(read_xg_file(data)["files"])
    return split_records(files["temp.xg"]), split_records(files["temp.xgi"])


def fields(record, *names):
    return tuple(get_field(record, n) for n in names)


class BuildXgpCheckerPlay(unittest.TestCase):
    def setUp(self):
        self.data = build_xgp(spot())
        self.game, self.index = records_of(self.data)

    def test_record_sequence(self):
        self.assertEqual(
            ([record_type(r) for r in self.game], [record_type(r) for r in self.index]),
            ([HEADER_MATCH, HEADER_GAME, CUBE, MOVE], [HEADER_MATCH, MOVE]),
        )

    def test_header_carries_names_save_name_and_thumbnail(self):
        header = read_xg_file(self.data)
        self.assertEqual(
            (header["save_name"], header["thumbnail"], header["guid"])
            + fields(self.game[0], "s_player1", "s_player2", "player1", "player2", "match_length", "crawford", "version"),
            ("Position: 7 point match 2-4", b"\xff\xd8thumb\xff\xd9", b"0123456789abcdef",
             "chessgamm0n", "fishsoup", "chessgamm0n", "fishsoup", 7, True, 30),
        )

    def test_match_date_is_delphi_days(self):
        self.assertAlmostEqual(get_field(self.game[0], "date"), 46335 + (18 * 60 + 53) / 1440, places=6)

    def test_game_header_scores(self):
        self.assertEqual(
            fields(self.game[1], "score1", "score2", "crawford_apply", "game_number", "in_progress"),
            (2, 4, False, 1, True),
        )

    def test_cube_record_is_context_without_double(self):
        self.assertEqual(
            fields(self.game[2], "active", "double", "take", "cube_b", "position", "dice_rolled",
                   "err_cube", "err_take", "an_flag_double", "an_equ_no_double", "analyze_c"),
            (1, 0, -1, 1, BOARD, "63", NOT_ANALYSED, NOT_ANALYSED, -100, 0.0, -1),
        )

    def test_move_record_holds_the_played_move_unanalysed(self):
        end = BOARD.copy()
        end[9], end[3], end[8], end[5] = 0, 3, 1, 1
        self.assertEqual(
            fields(self.game[3], "active", "position_i", "dice", "cube_a", "played", "moves", "position_end",
                   "err_move", "comment_move") + (self.game[3] == self.index[1],),
            (1, BOARD, [6, 3], 1, True, [8, 2, 7, 4, -1, -1, -1, -1], end, NOT_ANALYSED, -1, True),
        )

    def test_no_comment_file_without_a_comment(self):
        self.assertEqual([name for name, _ in read_xg_file(self.data)["files"]], ["temp.xg", "temp.xgi"])


class BuildXgpPlayedMove(unittest.TestCase):
    def played(self, start, steps, dice, **overrides):
        game, _ = records_of(build_xgp(spot(board=start, played_steps=steps, dice=dice, **overrides)))
        return fields(game[3], "moves", "position_end")

    def test_entering_from_the_bar_and_hitting_on_the_way(self):
        start = board({6: 14}, {22: 1, 1: 14}, own_bar=1)
        end = board({6: 14, 21: 1}, {1: 14}, opponent_bar=1)
        self.assertEqual(self.played(start, [[25, 22], [22, 21]], (3, 1)),
                         ([24, 21, 21, 20, -1, -1, -1, -1], end))

    def test_bearing_off(self):
        start = board({6: 1, 2: 14}, {24: 15})
        end = board({2: 13}, {24: 15})
        self.assertEqual(self.played(start, [[6, 0], [2, 0]], (6, 2)), ([5, -1, 1, -1, -1, -1, -1, -1], end))

    def test_doubles_use_all_four_pairs(self):
        start = board({13: 4, 6: 11}, {24: 15})
        end = board({13: 2, 6: 11, 7: 2}, {24: 15})
        self.assertEqual(self.played(start, [[13, 10], [13, 10], [10, 7], [10, 7]], (3, 3)),
                         ([12, 9, 12, 9, 9, 6, 9, 6], end))

    def test_end_position_is_seen_from_the_player_who_moved(self):
        mover = board({9: 1, 8: 2, 6: 12}, {24: 15})
        end = board({3: 1, 8: 1, 5: 1, 6: 12}, {24: 15})
        self.assertEqual(self.played(flip_frame(mover), [[9, 3], [8, 5]], (6, 3), on_roll=2, cube_owner=2),
                         ([8, 2, 7, 4, -1, -1, -1, -1], end))

    def test_cube_record_says_whether_the_cube_could_be_turned(self):
        cases = [dict(cube_owner=0, cube_value=1), dict(cube_owner=1), dict(cube_owner=2),
                 dict(cube_owner=0, cube_value=1, crawford_game=True)]
        self.assertEqual([get_field(records_of(build_xgp(spot(**c)))[0][2], "double") for c in cases], [0, 0, -2, -2])


class BuildXgpComment(unittest.TestCase):
    TEXT = "Played: 9/3 8/5 (-0.107, bad). Best: 13/7 13/10."

    def test_comment_goes_to_temp_xgc_as_xg_rtf(self):
        files = dict(read_xg_file(build_xgp(spot(comment=self.TEXT)))["files"])
        self.assertEqual(
            files["temp.xgc"],
            b"{\\rtf1\\ansi\\ansicpg1252\\uc1\\deff0\\deflang1033\\deflangfe1033{\\fonttbl{\\f0\\fcharset0 Arial;}}"
            b"\x01\x02{\\colortbl;}\x01\x02\\pard\\sl-240\\slmult1 \\lang1033\\fs20\\f0 "
            + self.TEXT.encode() + b"\\par\x01\x02}\r\n",
        )

    def test_rtf_specials_and_accents_are_escaped(self):
        files = dict(read_xg_file(build_xgp(spot(comment="{Ølav} \\ win")))["files"])
        self.assertIn(b"\\f0 \\{\\'d8lav\\} \\\\ win\\par", files["temp.xgc"])

    def test_the_decision_record_points_at_the_comment(self):
        checker, _ = records_of(build_xgp(spot(comment=self.TEXT)))
        double, _ = records_of(build_xgp(spot(decision="double", dice=None, action="Double", comment=self.TEXT)))
        self.assertEqual((get_field(checker[3], "comment_move"), get_field(checker[2], "comment_cube"),
                          get_field(double[2], "comment_cube")), (0, -1, 0))


class BuildXgpCubeDecisions(unittest.TestCase):
    def test_double_decision_has_no_move_record(self):
        game, index = records_of(build_xgp(spot(decision="double", dice=None, action="Double")))
        self.assertEqual([record_type(r) for r in game], [HEADER_MATCH, HEADER_GAME, CUBE])

    def test_cube_record_holds_the_action_taken(self):
        cases = [("double", "Double"), ("double", "No double"), ("take", "Take"), ("take", "Pass")]
        self.assertEqual(
            [fields(records_of(build_xgp(spot(decision=k, dice=None, action=a)))[0][2], "double", "take")
             for k, a in cases],
            [(1, -1), (0, -1), (1, 1), (1, 0)],
        )

    def test_pending_roll_in_index_matches_dice_rolled(self):
        game, index = records_of(build_xgp(spot(decision="double", dice=(4, 2), action="No double")))
        self.assertEqual(
            (get_field(game[2], "dice_rolled"),) + fields(index[1], "dice", "position_i"),
            ("42", [4, 2], BOARD),
        )


class BuildXgpPerspective(unittest.TestCase):
    def test_player2_on_roll(self):
        game, _ = records_of(build_xgp(spot(on_roll=2, cube_owner=2, cube_value=4)))
        self.assertEqual(
            fields(game[2], "active", "cube_b", "position", "an_pos", "an_score", "an_cube", "an_cube_pos")
            + fields(game[3], "active", "cube_a", "position_i"),
            (-1, -2, BOARD, flip_frame(BOARD), [3, 5], 4, 1, -1, -2, BOARD),
        )

    def test_player1_analysis_block_view(self):
        game, _ = records_of(build_xgp(spot(cube_owner=2)))
        self.assertEqual(
            fields(game[2], "an_pos", "an_score", "an_cube_pos", "cube_b"),
            (BOARD, [5, 3], -1, -1),
        )

    def test_centered_cube(self):
        game, _ = records_of(build_xgp(spot(cube_value=1, cube_owner=0)))
        self.assertEqual(fields(game[2], "cube_b", "an_cube", "an_cube_pos"), (0, 1, 0))

    def test_crawford_game_flags(self):
        game, _ = records_of(build_xgp(spot(match_length=3, score1=2, score2=0, crawford_game=True, cube_value=1, cube_owner=0)))
        self.assertEqual(
            fields(game[1], "crawford_apply") + fields(game[2], "an_crawford"),
            (True, 1),
        )


class BuildXgpNames(unittest.TestCase):
    def test_long_and_unicode_names(self):
        long_name = "x" * 60
        game, _ = records_of(build_xgp(spot(player1=long_name, player2="Ølav")))
        self.assertEqual(
            fields(game[0], "s_player1", "player1", "player2"),
            ("x" * 40, "x" * 60, "Ølav"),
        )


if __name__ == "__main__":
    unittest.main()

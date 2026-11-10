import datetime
import unittest

from app.xgp.archive import read_xg_file
from app.xgp.records import CUBE, HEADER_GAME, HEADER_MATCH, MOVE, NOT_ANALYSED, get_field, record_type, split_records
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
        "guid": b"0123456789abcdef",
        "saved_at": SAVED_AT,
        "thumbnail": b"\xff\xd8thumb\xff\xd9",
    }
    base.update(overrides)
    return base


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

    def test_move_record_holds_the_roll_unanalysed(self):
        self.assertEqual(
            fields(self.game[3], "active", "position_i", "dice", "cube_a", "played", "err_move")
            + (self.game[3] == self.index[1],),
            (1, BOARD, [6, 3], 1, False, NOT_ANALYSED, True),
        )


class BuildXgpCubeDecisions(unittest.TestCase):
    def test_double_decision_has_no_move_record(self):
        game, index = records_of(build_xgp(spot(decision="double", dice=None)))
        self.assertEqual(
            ([record_type(r) for r in game],) + fields(game[2], "double", "take"),
            ([HEADER_MATCH, HEADER_GAME, CUBE], -1, -1),
        )

    def test_take_decision_marks_the_double_as_offered(self):
        game, _ = records_of(build_xgp(spot(decision="take", dice=None)))
        self.assertEqual(fields(game[2], "double", "take"), (1, -1))

    def test_pending_roll_in_index_matches_dice_rolled(self):
        game, index = records_of(build_xgp(spot(decision="double", dice=(4, 2))))
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

import csv
import datetime
import io
import unittest
import zipfile

from app.export import build_export_zip, export_filename, spot_from_decision
from app.xgp.archive import read_xg_file
from app.xgp.records import get_field, record_type, split_records
from tests.test_position import START_FRAME

SAVED_AT = datetime.datetime(2026, 11, 10, 12, 0)
THRESHOLDS = {"doubtful": 0.03, "bad": 0.06, "very_bad": 0.12}


def decision(**overrides):
    base = {
        "id": 7, "player1": "chess gamm0n", "player2": "fish/soup", "event_date": "2026-11-09",
        "match_length": 3, "score1": 0, "score2": 0, "crawford_game": False, "game_no": 1, "move_no": 16,
        "player": 2, "on_roll": 2, "kind": "checker", "board": START_FRAME, "cube_value": 2, "cube_owner": 2,
        "dice": [6, 6], "action": "22/16 21/15(2) 16/10", "best": "22/10 13/7(2)", "error": 0.107,
        "xgid": "XGID=test",
    }
    base.update(overrides)
    return base


class ExportFilename(unittest.TestCase):
    def test_names_are_safe_and_descriptive(self):
        self.assertEqual(
            export_filename(decision(), "bad"),
            "chess_gamm0n-vs-fish_soup_2026-11-09_g1_m16_fish_soup_checker_bad.xgp",
        )

    def test_unclassified_decision(self):
        self.assertTrue(export_filename(decision(kind="take", player=1), None).endswith("_g1_m16_chess_gamm0n_take_ok.xgp"))


class SpotFromDecision(unittest.TestCase):
    def test_maps_decision_fields(self):
        spot = spot_from_decision(decision(), SAVED_AT, b"g" * 16, b"jpeg")
        self.assertEqual(
            spot,
            {"player1": "chess gamm0n", "player2": "fish/soup", "match_length": 3, "score1": 0, "score2": 0,
             "crawford_game": False, "on_roll": 2, "board": START_FRAME, "cube_value": 2, "cube_owner": 2,
             "decision": "checker", "dice": (6, 6), "guid": b"g" * 16, "saved_at": SAVED_AT, "thumbnail": b"jpeg"},
        )

    def test_cube_kinds(self):
        self.assertEqual(
            [spot_from_decision(decision(kind=k, dice=None), SAVED_AT, b"g" * 16, b"")["decision"] for k in ("cube", "take")],
            ["double", "take"],
        )


class BuildExportZip(unittest.TestCase):
    def test_zip_holds_one_xgp_per_decision_and_an_index(self):
        decisions = [decision(), decision(id=8, kind="cube", player=1, on_roll=1, move_no=15, dice=None, error=0.0,
                                          action="Double", best="Double, take")]
        archive = zipfile.ZipFile(io.BytesIO(build_export_zip(decisions, THRESHOLDS, SAVED_AT)))
        names = sorted(archive.namelist())
        xgp_names = [n for n in names if n.endswith(".xgp")]
        kinds = [[record_type(r) for r in split_records(dict(read_xg_file(archive.read(n))["files"])["temp.xg"])]
                 for n in xgp_names]
        rows = list(csv.DictReader(io.StringIO(archive.read("index.csv").decode("utf-8"))))
        self.assertEqual(
            (names, kinds, [(r["move"], r["class"], r["error"]) for r in rows]),
            (
                ["chess_gamm0n-vs-fish_soup_2026-11-09_g1_m15_chess_gamm0n_cube_ok.xgp",
                 "chess_gamm0n-vs-fish_soup_2026-11-09_g1_m16_fish_soup_checker_bad.xgp", "index.csv"],
                [[0, 1, 2], [0, 1, 2, 3]],
                [("16", "bad", "0.107"), ("15", "", "0.000")],
            ),
        )

    def test_duplicate_names_get_a_suffix(self):
        archive = zipfile.ZipFile(io.BytesIO(build_export_zip([decision(), decision(id=9)], THRESHOLDS, SAVED_AT)))
        self.assertEqual(
            sorted(n for n in archive.namelist() if n.endswith(".xgp")),
            ["chess_gamm0n-vs-fish_soup_2026-11-09_g1_m16_fish_soup_checker_bad-2.xgp",
             "chess_gamm0n-vs-fish_soup_2026-11-09_g1_m16_fish_soup_checker_bad.xgp"],
        )

    def test_players_on_roll_in_xgp(self):
        archive = zipfile.ZipFile(io.BytesIO(build_export_zip([decision()], THRESHOLDS, SAVED_AT)))
        name = next(n for n in archive.namelist() if n.endswith(".xgp"))
        records = split_records(dict(read_xg_file(archive.read(name))["files"])["temp.xg"])
        self.assertEqual((get_field(records[3], "active"), get_field(records[3], "dice")), (-1, [6, 6]))


if __name__ == "__main__":
    unittest.main()

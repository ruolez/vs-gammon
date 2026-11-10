import io
import os
import shutil
import tempfile
import unittest
import zipfile

try:
    import flask  # noqa: F401
except ImportError:
    raise unittest.SkipTest("Flask is only installed in the container")

from app import db, jobs  # noqa: E402
from app.importer import upload_path  # noqa: E402
from app.engine.runner import EngineError  # noqa: E402
from app.engine.walk import walk_match  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_walk import MATCH, FakeHelpers

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fake_analyse(path, plies, threads):
    result = walk_match(MATCH, FakeHelpers())
    result["engine"] = {"plies": plies, "threads": threads, "seconds": 0.5}
    return result


def failing_analyse(path, plies, threads):
    raise EngineError("gnubg could not import any games from this file")


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, "data")
        self.host_root = os.path.join(self.tmp, "host")
        os.makedirs(os.path.join(self.host_root, "Downloads", "Galaxy"))
        self.app = create_app({"DATA_DIR": self.data_dir, "EXPORT_DIR": os.path.join(self.tmp, "exports"),
                               "START_WORKER": False, "TESTING": True,
                               "HOST_HOME": "/Users/tester", "HOST_ROOT": self.host_root})
        self.client = self.app.test_client()
        self.conn = db.connect(os.path.join(self.data_dir, "app.db"))

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp)

    def upload(self, name="galaxy_3pt.mat", content=None):
        if content is None:
            with open(os.path.join(FIXTURES, "galaxy_3pt.mat"), "rb") as f:
                content = f.read()
        return self.client.post("/api/matches", data={"files": (io.BytesIO(content), name)},
                                content_type="multipart/form-data").get_json()["results"]

    def analysed_match(self, analyse=fake_analyse):
        match_id = self.upload()[0]["id"]
        jobs.process_next(self.conn, self.data_dir, analyse=analyse)
        return match_id


class UploadMatches(ApiTestCase):
    def test_upload_queues_the_match_with_header_details(self):
        result = self.upload()
        match = self.client.get(f"/api/matches/{result[0]['id']}").get_json()["match"]
        self.assertEqual(
            (result[0]["duplicate"], match["status"], match["player1"], match["player2"], match["match_length"],
             match["event_date"], match["external_id"]),
            (False, "queued", "chessgamm0n", "fishsoup", 3, "2026-11-09", "50469849"),
        )

    def test_same_file_is_not_imported_twice(self):
        first = self.upload()[0]
        second = self.upload(name="copy.mat")[0]
        self.assertEqual((second["id"], second["duplicate"]), (first["id"], True))

    def test_non_match_file_is_rejected(self):
        self.assertEqual(self.upload(name="notes.txt", content=b"hello"),
                         [{"filename": "notes.txt", "error": "not a match file: no 'N point match' line"}])


class AnalyseMatches(ApiTestCase):
    def test_analysed_match_has_games_and_summary(self):
        match_id = self.analysed_match()
        match = self.client.get(f"/api/matches/{match_id}").get_json()["match"]
        self.assertEqual(
            (match["status"], match["plies"], len(match["games"]), sorted(match["summary"])),
            ("done", 2, 2, ["1", "2"]),
        )

    def test_failed_analysis_is_reported(self):
        match_id = self.analysed_match(analyse=failing_analyse)
        match = self.client.get(f"/api/matches/{match_id}").get_json()["match"]
        self.assertEqual((match["status"], match["error"]),
                         ("error", "gnubg could not import any games from this file"))

    def test_reanalyze_requeues(self):
        match_id = self.analysed_match()
        self.client.post(f"/api/matches/{match_id}/reanalyze")
        self.assertEqual(self.client.get(f"/api/matches/{match_id}").get_json()["match"]["status"], "queued")

    def test_delete_removes_match_and_upload(self):
        match_id = self.analysed_match()
        sha = self.conn.execute("SELECT sha256 FROM matches WHERE id = ?", (match_id,)).fetchone()["sha256"]
        self.client.delete(f"/api/matches/{match_id}")
        self.assertEqual(
            (self.client.get(f"/api/matches/{match_id}").status_code,
             os.path.exists(upload_path(self.data_dir, sha)),
             self.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]),
            (404, False, 0),
        )


class FilterDecisions(ApiTestCase):
    def decisions(self, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(f"/api/decisions?{query}").get_json()["decisions"]

    def test_min_error_filter(self):
        match_id = self.analysed_match()
        self.assertEqual(
            [(d["kind"], d["player"], d["move_no"], round(d["error"], 3), d["class"])
             for d in self.decisions(match_id=match_id, min_error=0.03)],
            [("checker", 1, 1, 0.05, "doubtful"), ("cube", 1, 2, 0.1, "bad"), ("take", 1, 5, 0.6, "very_bad")],
        )

    def test_kind_and_player_filters(self):
        match_id = self.analysed_match()
        self.assertEqual(
            [(d["kind"], d["action"]) for d in self.decisions(match_id=match_id, kind="cube", player=2)],
            [("take", "Take"), ("cube", "Double")],
        )

    def test_forced_moves_hidden_unless_asked(self):
        match_id = self.analysed_match()
        self.assertEqual(
            (len(self.decisions(match_id=match_id, kind="checker")),
             len(self.decisions(match_id=match_id, kind="checker", include_forced=1))),
            (3, 4),
        )

    def test_player_name_filter_across_matches(self):
        self.analysed_match()
        self.assertEqual({d["player"] for d in self.decisions(player_name="fishsoup")}, {2})

    def test_decision_detail_includes_xgid_and_candidates(self):
        match_id = self.analysed_match()
        first = self.decisions(match_id=match_id, kind="checker")[0]
        detail = self.client.get(f"/api/decisions/{first['id']}").get_json()["decision"]
        self.assertEqual(
            (detail["xgid"].startswith("XGID="), [c["move"] for c in detail["candidates"]], detail["played_index"]),
            (True, ["13/10 24/23", "8/5 6/5"], 1),
        )


class ExportPositions(ApiTestCase):
    def test_export_returns_zip_and_keeps_a_copy(self):
        match_id = self.analysed_match()
        ids = [d["id"] for d in self.client.get(f"/api/decisions?match_id={match_id}&min_error=0.03").get_json()["decisions"]]
        response = self.client.post("/api/export", json={"decision_ids": ids})
        names = zipfile.ZipFile(io.BytesIO(response.data)).namelist()
        self.assertEqual(
            (response.mimetype, len([n for n in names if n.endswith(".xgp")]), "index.csv" in names,
             len(os.listdir(os.path.join(self.tmp, "exports")))),
            ("application/zip", 3, True, 1),
        )

    def test_empty_selection_is_rejected(self):
        response = self.client.post("/api/export", json={"decision_ids": []})
        self.assertEqual((response.status_code, response.get_json()["error"]),
                         (400, "select at least one position to export"))


class Settings(ApiTestCase):
    def test_xg_preset_sets_thresholds(self):
        settings = self.client.put("/api/settings", json={"preset": "xg"}).get_json()["settings"]
        self.assertEqual((settings["preset"], settings["thresholds"]),
                         ("xg", {"doubtful": 0.02, "bad": 0.04, "very_bad": 0.08}))

    def test_thresholds_reclassify_without_reanalysis(self):
        match_id = self.analysed_match()
        self.client.put("/api/settings", json={"preset": "custom",
                                               "thresholds": {"doubtful": 0.01, "bad": 0.04, "very_bad": 0.5}})
        classes = [d["class"] for d in self.client.get(f"/api/decisions?match_id={match_id}&min_error=0.03")
                   .get_json()["decisions"]]
        self.assertEqual(classes, ["bad", "bad", "very_bad"])

    def test_invalid_thresholds_rejected(self):
        response = self.client.put("/api/settings", json={"thresholds": {"doubtful": 0.1, "bad": 0.05, "very_bad": 0.2}})
        self.assertEqual(response.status_code, 400)

    def test_depth_is_validated(self):
        self.assertEqual(
            (self.client.put("/api/settings", json={"plies": 3}).status_code,
             self.client.put("/api/settings", json={"plies": 5}).status_code),
            (200, 400),
        )



class WorkerRobustness(ApiTestCase):
    def test_unexpected_crash_marks_match_failed(self):
        def crashing(path, plies, threads):
            raise RuntimeError("boom")

        match_id = self.analysed_match(analyse=crashing)
        match = self.client.get(f"/api/matches/{match_id}").get_json()["match"]
        self.assertEqual((match["status"], match["error"]), ("error", "RuntimeError: boom"))



class History(ApiTestCase):
    def test_import_analysis_and_export_are_logged_newest_first(self):
        match_id = self.analysed_match()
        ids = [d["id"] for d in self.client.get(f"/api/decisions?match_id={match_id}&min_error=0.1").get_json()["decisions"]]
        self.client.post("/api/export", json={"decision_ids": ids})
        events = self.client.get("/api/history").get_json()["events"]
        self.assertEqual(
            [(e["kind"], e["match_id"]) for e in events],
            [("exported", None), ("analysed", match_id), ("imported", match_id)],
        )

    def test_analysis_message_summarises_both_players(self):
        match_id = self.analysed_match()
        analysed = self.client.get("/api/history?kind=analysed").get_json()["events"][0]["message"]
        self.assertEqual(
            analysed,
            "Analysed chessgamm0n vs fishsoup (7-point, 2026-11-09) at 2-ply in 0.5 s, 10 decisions. "
            "chessgamm0n: PR 62.5, 3 errors (1 very bad); fishsoup: PR 0.0, 0 errors (0 very bad)",
        )

    def test_history_paging(self):
        self.analysed_match()
        first = self.client.get("/api/history?limit=1").get_json()
        older = self.client.get(f"/api/history?limit=1&before={first['events'][0]['id']}").get_json()
        self.assertEqual(([e["kind"] for e in first["events"]], first["more"], [e["kind"] for e in older["events"]]),
                         (["analysed"], True, ["imported"]))


class Reanalysis(ApiTestCase):
    def test_decision_ids_and_practice_survive_reanalysis(self):
        match_id = self.analysed_match()
        decisions = self.client.get(f"/api/decisions?match_id={match_id}").get_json()["decisions"]
        before = [d["id"] for d in decisions]
        checker = next(d["id"] for d in decisions if d["kind"] == "checker")
        self.client.post(f"/api/practice/{checker}/answer", json={"legal_index": 1})
        self.client.post(f"/api/matches/{match_id}/reanalyze")
        jobs.process_next(self.conn, self.data_dir, analyse=fake_analyse)
        after = [d["id"] for d in self.client.get(f"/api/decisions?match_id={match_id}").get_json()["decisions"]]
        attempts = self.client.get(f"/api/decisions/{checker}").get_json()["decision"]["practice"]
        self.assertEqual((after, len(attempts)), (before, 1))


class Folders(ApiTestCase):
    def test_browse_home_and_subfolders(self):
        self.assertEqual(
            self.client.get("/api/fs?path=/Users/tester/Downloads").get_json(),
            {"path": "/Users/tester/Downloads", "parent": "/Users/tester", "match_files": 0,
             "dirs": [{"name": "Galaxy", "path": "/Users/tester/Downloads/Galaxy"}]},
        )

    def test_browsing_outside_home_is_refused(self):
        response = self.client.get("/api/fs?path=/etc")
        self.assertEqual((response.status_code, response.get_json()["error"]),
                         (400, "only folders inside /Users/tester can be used"))

    def test_add_toggle_and_remove_a_folder(self):
        added = self.client.post("/api/folders", json={"path": "/Users/tester/Downloads", "recursive": True}).get_json()
        toggled = self.client.patch(f"/api/folders/{added['id']}", json={"enabled": False}).get_json()["folders"]
        removed = self.client.delete(f"/api/folders/{added['id']}").get_json()["folders"]
        self.assertEqual(
            ([(f["path"], f["recursive"], f["enabled"]) for f in added["folders"]],
             [f["enabled"] for f in toggled], removed,
             [e["kind"] for e in self.client.get("/api/history").get_json()["events"]]),
            ([("/Users/tester/Downloads", 1, 1)], [0], [], ["folder_removed", "folder_added"]),
        )

    def test_missing_folder_cannot_be_added(self):
        response = self.client.post("/api/folders", json={"path": "/Users/tester/Nope"})
        self.assertEqual((response.status_code, response.get_json()["error"]),
                         (400, "/Users/tester/Nope is not a folder"))


class FoldersUnavailable(unittest.TestCase):
    def test_folder_routes_explain_how_to_enable(self):
        tmp = tempfile.mkdtemp()
        try:
            app = create_app({"DATA_DIR": os.path.join(tmp, "d"), "EXPORT_DIR": os.path.join(tmp, "e"),
                              "START_WORKER": False, "HOST_HOME": None})
            client = app.test_client()
            self.assertEqual(
                (client.get("/api/folders").get_json()["available"], client.get("/api/fs").status_code),
                (False, 400),
            )
        finally:
            shutil.rmtree(tmp)


class Practice(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.match_id = self.analysed_match()
        self.decisions = self.client.get(f"/api/decisions?match_id={self.match_id}").get_json()["decisions"]

    def first(self, kind, player=None):
        return next(d for d in self.decisions if d["kind"] == kind and (player is None or d["player"] == player))

    def queue(self, query=""):
        return self.client.get(f"/api/practice/queue?match_id={self.match_id}{query}").get_json()

    def test_checker_answer_is_graded_by_final_position_index(self):
        decision = self.first("checker", 1)
        best = self.client.post(f"/api/practice/{decision['id']}/answer", json={"legal_index": 1}).get_json()
        worse = self.client.post(f"/api/practice/{decision['id']}/answer", json={"legal_index": 2}).get_json()
        self.assertEqual(
            [(r["answer"], r["correct"], round(r["error"], 3), r["class"], r["approx"]) for r in (best, worse)],
            [("13/10 24/23", True, 0.0, None, False), ("8/5 6/5", False, 0.05, "doubtful", False)],
        )

    def test_cube_answers(self):
        double = self.first("cube", 1)
        take = self.first("take")
        results = [
            self.client.post(f"/api/practice/{double['id']}/answer", json={"action": "no_double"}).get_json(),
            self.client.post(f"/api/practice/{take['id']}/answer", json={"action": "pass"}).get_json(),
        ]
        self.assertEqual([(r["answer"], r["correct"]) for r in results], [("No double", True), ("Pass", False)])

    def test_wrong_kind_of_answer_is_rejected(self):
        response = self.client.post(f"/api/practice/{self.first('take')['id']}/answer", json={"action": "double"})
        self.assertEqual(response.status_code, 400)

    def test_queue_puts_misses_first_then_new_and_hides_mastered(self):
        checkers = [d for d in self.decisions if d["kind"] == "checker"]
        self.client.post(f"/api/practice/{checkers[0]['id']}/answer", json={"legal_index": 1})
        self.client.post(f"/api/practice/{checkers[1]['id']}/reveal")
        due = [i["id"] for i in self.queue("&kind=checker")["items"]]
        everything = [i["id"] for i in self.queue("&kind=checker&mode=all")["items"]]
        self.assertEqual(
            (due[0], checkers[0]["id"] in due, len(due), everything[-1]),
            (checkers[1]["id"], False, len(checkers) - 1, checkers[0]["id"]),
        )

    def test_stats_count_positions_and_attempts(self):
        checkers = [d for d in self.decisions if d["kind"] == "checker"]
        self.client.post(f"/api/practice/{checkers[0]['id']}/answer", json={"legal_index": 2})
        self.client.post(f"/api/practice/{checkers[0]['id']}/answer", json={"legal_index": 1})
        stats = self.queue("&kind=checker")["stats"]
        self.assertEqual(
            {k: stats[k] for k in ("positions", "new", "missed", "mastered", "attempts", "correct")},
            {"positions": len(checkers), "new": len(checkers) - 1, "missed": 0, "mastered": 1, "attempts": 2,
             "correct": 1},
        )

    def test_unknown_mode_is_rejected(self):
        self.assertEqual(self.client.get("/api/practice/queue?mode=weird").status_code, 400)



class Dashboard(ApiTestCase):
    def test_dashboard_for_the_most_frequent_player(self):
        self.analysed_match()
        data = self.client.get("/api/dashboard").get_json()
        self.assertEqual(
            (data["player"], [(m["opponent"], m["my_score"], m["their_score"], m["won"], m["lost"], m["pr"], m["errors"])
                              for m in data["matches"]],
             data["summary"]["last_pr"], [round(m["error"], 6) for m in data["mistakes"]][:2]),
            ("chessgamm0n", [("fishsoup", 1, 2, False, False, 62.5, 3)], 62.5, [0.6, 0.1]),
        )

    def test_phase_breakdown_covers_every_phase(self):
        self.analysed_match()
        phases = self.client.get("/api/dashboard?player_name=chessgamm0n").get_json()["phases"]
        self.assertEqual([p["phase"] for p in phases], ["opening", "middle", "race", "bearoff", "cube"])

    def test_chosen_player_wins_over_most_frequent(self):
        self.analysed_match()
        self.client.put("/api/settings", json={"me": "fishsoup"})
        self.assertEqual(self.client.get("/api/dashboard").get_json()["player"], "fishsoup")

    def test_practice_block_counts_due_and_streak(self):
        self.analysed_match()
        decisions = self.client.get("/api/decisions?kind=checker&player=1").get_json()["decisions"]
        self.client.post(f"/api/practice/{decisions[0]['id']}/answer", json={"legal_index": 1})
        practice = self.client.get("/api/dashboard").get_json()["practice"]
        self.assertEqual((practice["streak"], practice["mastered"], practice["attempts"]), (1, 1, 1))

    def test_shell_reports_due_count_and_player(self):
        self.analysed_match()
        shell = self.client.get("/api/shell").get_json()
        self.assertEqual((shell["me"], shell["due"], shell["watching"]), ("chessgamm0n", 3, []))

    def test_empty_app(self):
        self.assertEqual(self.client.get("/api/dashboard").get_json(), {"player": None, "matches": [], "empty": True})


if __name__ == "__main__":
    unittest.main()

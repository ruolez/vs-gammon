import hashlib
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

from app import db, deep_jobs, jobs  # noqa: E402
from app.importer import fill_missing_keys, upload_path  # noqa: E402
from app.matfile import parse_mat_header  # noqa: E402
from app.engine.runner import Cancelled, EngineError  # noqa: E402
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

    def fixture_bytes(self):
        with open(os.path.join(FIXTURES, "galaxy_3pt.mat"), "rb") as f:
            return f.read()

    def other_match_bytes(self):
        return self.fixture_bytes().replace(b"fishsoup", b"seaweed")

    def analysed_match(self, analyse=fake_analyse, content=None):
        match_id = self.upload(content=content)[0]["id"]
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

    def test_same_match_in_a_different_file_is_not_imported_twice(self):
        first = self.upload()[0]
        later = self.fixture_bytes().replace(b'Elo "2246,97/0"', b'Elo "2251,40/0"').replace(b"\n", b"\r\n")
        second = self.upload(name="downloaded-again.mat", content=later)[0]
        events = self.client.get("/api/history").get_json()["events"]
        self.assertEqual(
            ((second["id"], second["duplicate"]), events[0]["kind"],
             len(self.client.get("/api/matches").get_json()["matches"])),
            ((first["id"], True), "duplicate", 1),
        )

    def test_another_match_of_the_same_players_is_imported(self):
        first = self.upload()[0]
        second = self.upload(name="rematch.mat", content=self.other_match_bytes())[0]
        self.assertEqual((second["duplicate"], second["id"] != first["id"]), (False, True))

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


class ReviewProgress(ApiTestCase):
    def mistakes(self, match_id):
        return self.client.get(f"/api/decisions?match_id={match_id}&min_error=0.03").get_json()["decisions"]

    def review(self, match_id):
        return self.client.get(f"/api/matches/{match_id}").get_json()["match"]["review"]

    def mark(self, match_id, reviewed):
        return self.client.put(f"/api/matches/{match_id}/reviewed", json={"reviewed": reviewed}).get_json()["review"]

    def test_new_match_has_its_mistakes_unseen(self):
        match_id = self.analysed_match()
        self.assertEqual(self.review(match_id), {"mistakes": 3, "seen": 0, "auto": False, "reviewed": False, "mark": None})

    def test_opening_every_mistake_marks_the_match_reviewed(self):
        match_id = self.analysed_match()
        answers = [self.client.post(f"/api/decisions/{d['id']}/seen").get_json() for d in self.mistakes(match_id)]
        self.assertEqual(
            ([a["review"]["seen"] for a in answers], answers[-1]["match_id"], self.review(match_id)["reviewed"]),
            ([1, 2, 3], match_id, True),
        )

    def test_my_player_setting_limits_the_mistakes_counted(self):
        match_id = self.analysed_match()
        self.client.put("/api/settings", json={"me": "fishsoup"})
        self.assertEqual(self.review(match_id)["mistakes"], 0)

    def test_manual_mark_is_kept_only_while_it_differs_from_the_automatic_state(self):
        match_id = self.analysed_match()
        marked, unmarked = self.mark(match_id, True), self.mark(match_id, False)
        for d in self.mistakes(match_id):
            self.client.post(f"/api/decisions/{d['id']}/seen")
        reopened = self.mark(match_id, False)
        self.assertEqual(
            [(r["mark"], r["reviewed"]) for r in (marked, unmarked, reopened)],
            [(1, True), (None, False), (0, False)],
        )

    def test_seen_decisions_survive_reanalysis(self):
        match_id = self.analysed_match()
        first = self.mistakes(match_id)[0]
        self.client.post(f"/api/decisions/{first['id']}/seen")
        self.client.post(f"/api/matches/{match_id}/reanalyze")
        jobs.process_next(self.conn, self.data_dir, analyse=fake_analyse)
        self.assertEqual(self.review(match_id)["seen"], 1)

    def test_unknown_decision_or_match_is_404(self):
        self.assertEqual(
            (self.client.post("/api/decisions/999/seen").status_code,
             self.client.put("/api/matches/999/reviewed", json={"reviewed": True}).status_code),
            (404, 404),
        )

    def test_decisions_of_several_matches(self):
        first = self.analysed_match()
        second = self.upload(name="rematch.mat", content=self.other_match_bytes())[0]["id"]
        jobs.process_next(self.conn, self.data_dir, analyse=fake_analyse)
        query = lambda ids: {d["match_id"] for d in self.client.get(
            f"/api/decisions?match_id={ids}&min_error=0.03").get_json()["decisions"]}
        self.assertEqual((query(f"{first},{second}"), query(str(second))), ({first, second}, {second}))

    def test_xgid_puts_the_decider_at_the_bottom(self):
        match_id = self.analysed_match()
        decisions = self.client.get(f"/api/decisions?match_id={match_id}&include_forced=1").get_json()["decisions"]
        fields = [d["xgid"].split(":") for d in decisions]
        self.assertEqual(
            [(f[3], f[5]) for f in fields],
            [("-1" if d["kind"] == "take" else "1", str(d["score1"] if d["player"] == 1 else d["score2"]))
             for d in decisions],
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


class Tags(ApiTestCase):
    def create(self, name, color="blue"):
        return self.client.post("/api/tags", json={"name": name, "color": color})

    def tags(self):
        return [(t["name"], t["color"], t["count"]) for t in self.client.get("/api/tags").get_json()["tags"]]

    def decision_ids(self, **params):
        query = "&".join(f"{k}={v}" for k, v in {"include_forced": 1, "group": "position", **params}.items())
        return [d["id"] for d in self.client.get(f"/api/decisions?{query}").get_json()["decisions"]]

    def positions(self, ids):
        keys = {d["id"]: d["position_key"] for d in
                self.client.get("/api/decisions?include_forced=1").get_json()["decisions"]}
        return sorted(keys[i] for i in ids)

    def tag(self, tag_id, add=(), remove=()):
        return self.client.post(f"/api/tags/{tag_id}/decisions", json={"add": list(add), "remove": list(remove)})

    def test_create_lists_tags_by_name_with_counts(self):
        self.create("Prime vs prime", "green")
        self.create("bear-in", "red")
        self.assertEqual(self.tags(), [("bear-in", "red", 0), ("Prime vs prime", "green", 0)])

    def test_tag_names_are_unique_ignoring_case_and_validated(self):
        self.create("Blitz")
        self.assertEqual(
            [(r.status_code, r.get_json()["error"]) for r in
             (self.create("blitz"), self.create("   "), self.create("x" * 41), self.create("Ok", "neon"))],
            [(400, "a tag named 'blitz' already exists"), (400, "a tag needs a name"),
             (400, "tag names are at most 40 characters"), (400, "unknown tag colour")],
        )

    def test_tagging_shows_on_decisions_and_filters_them(self):
        self.analysed_match()
        ids = self.decision_ids()
        blitz = self.create("Blitz").get_json()["tag"]["id"]
        prime = self.create("Prime").get_json()["tag"]["id"]
        self.tag(blitz, add=ids[:3])
        self.tag(prime, add=ids[2:4])
        self.tag(blitz, remove=[ids[0]])
        tagged = {d["id"]: d["tags"] for d in self.client.get("/api/decisions?include_forced=1&group=position").get_json()["decisions"]}
        self.assertEqual(
            ([tagged[i] for i in ids[:5]], self.decision_ids(tag=blitz), self.decision_ids(tag=f"{blitz},{prime}"),
             self.decision_ids(tag="none"), self.tags()),
            ([[], [blitz], [blitz, prime], [prime], []], ids[1:3], ids[1:4], [ids[0]] + ids[4:],
             [("Blitz", "blue", 2), ("Prime", "blue", 2)]),
        )

    def test_several_tags_match_any_or_all(self):
        self.analysed_match()
        ids = self.decision_ids()
        blitz = self.create("Blitz").get_json()["tag"]["id"]
        prime = self.create("Prime").get_json()["tag"]["id"]
        self.tag(blitz, add=ids[0:3])
        self.tag(prime, add=ids[2:5])
        both = f"{blitz},{prime}"
        self.assertEqual(
            (self.decision_ids(tag=both), self.decision_ids(tag=both, tag_match="all"),
             self.decision_ids(tag=blitz, tag_match="all")),
            (ids[0:5], [ids[2]], ids[0:3]),
        )

    def test_practice_queue_matches_all_tags(self):
        self.analysed_match()
        ids = self.decision_ids(min_error=0, include_forced=0)
        blitz = self.create("Blitz").get_json()["tag"]["id"]
        prime = self.create("Prime").get_json()["tag"]["id"]
        self.tag(blitz, add=ids[0:2])
        self.tag(prime, add=ids[1:3])
        items = self.client.get(f"/api/practice/queue?tag={blitz},{prime}&tag_match=all&mode=all").get_json()["items"]
        self.assertEqual(self.positions(i["id"] for i in items), self.positions([ids[1]]))

    def test_rename_and_recolour(self):
        tag_id = self.create("Blitz").get_json()["tag"]["id"]
        response = self.client.patch(f"/api/tags/{tag_id}", json={"name": "Blitzes", "color": "purple"})
        self.assertEqual((response.status_code, self.tags()), (200, [("Blitzes", "purple", 0)]))

    def test_delete_removes_the_tag_but_keeps_positions(self):
        self.analysed_match()
        ids = self.decision_ids()
        tag_id = self.create("Blitz").get_json()["tag"]["id"]
        self.tag(tag_id, add=ids)
        self.client.delete(f"/api/tags/{tag_id}")
        self.assertEqual((self.tags(), self.decision_ids()), ([], ids))

    def test_merge_moves_positions_into_the_target_without_duplicates(self):
        self.analysed_match()
        ids = self.decision_ids()
        source = self.create("Blitz").get_json()["tag"]["id"]
        target = self.create("Attack").get_json()["tag"]["id"]
        self.tag(source, add=ids[:3])
        self.tag(target, add=ids[2:5])
        response = self.client.post(f"/api/tags/{source}/merge", json={"into": target})
        self.assertEqual((response.status_code, self.tags(), self.decision_ids(tag=target)),
                         (200, [("Attack", "blue", 5)], ids[:5]))

    def test_merging_a_tag_into_itself_is_refused(self):
        tag_id = self.create("Blitz").get_json()["tag"]["id"]
        response = self.client.post(f"/api/tags/{tag_id}/merge", json={"into": tag_id})
        self.assertEqual((response.status_code, response.get_json()["error"]), (400, "choose another tag to merge into"))

    def test_unknown_tag_or_decision_is_404(self):
        self.analysed_match()
        tag_id = self.create("Blitz").get_json()["tag"]["id"]
        self.assertEqual(
            [r.status_code for r in (self.client.patch("/api/tags/99", json={"name": "x"}), self.client.delete("/api/tags/99"),
                                     self.tag(99, add=self.decision_ids()[:1]), self.tag(tag_id, add=[9999]))],
            [404, 404, 404, 404],
        )

    def test_tags_survive_reanalysis_and_go_with_a_deleted_match(self):
        match_id = self.analysed_match()
        tag_id = self.create("Blitz").get_json()["tag"]["id"]
        self.tag(tag_id, add=self.decision_ids()[:2])
        self.client.post(f"/api/matches/{match_id}/reanalyze")
        jobs.process_next(self.conn, self.data_dir, analyse=fake_analyse)
        kept = self.tags()
        self.client.delete(f"/api/matches/{match_id}")
        self.assertEqual((kept, self.tags()), ([("Blitz", "blue", 2)], [("Blitz", "blue", 0)]))

    def test_practice_queue_by_tag_includes_good_moves(self):
        self.analysed_match()
        good = [d["id"] for d in self.client.get("/api/decisions?min_error=0&group=position").get_json()["decisions"]
                if d["error"] == 0]
        tag_id = self.create("Quiz").get_json()["tag"]["id"]
        self.tag(tag_id, add=good[:2])
        items = self.client.get(f"/api/practice/queue?tag={tag_id}&mode=all").get_json()["items"]
        self.assertEqual(self.positions(i["id"] for i in items), self.positions(good[:2]))


class DuplicatesInTheLibrary(ApiTestCase):
    """Duplicates imported before they were detected: the second copy is inserted the way old versions did."""

    def old_style_copy(self):
        raw = self.fixture_bytes().replace(b'Elo "2246,97/0"', b'Elo "2251,40/0"')
        sha = hashlib.sha256(raw).hexdigest()
        with open(upload_path(self.data_dir, sha), "wb") as f:
            f.write(raw)
        match_id = db.insert_match(self.conn, "old-copy.mat", sha, parse_mat_header(raw.decode()))
        jobs.process_next(self.conn, self.data_dir, analyse=fake_analyse)
        with self.conn:
            self.conn.execute("UPDATE matches SET content_key = NULL")
        fill_missing_keys(self.conn, self.data_dir)
        return match_id, sha

    def test_matches_list_points_duplicates_at_the_kept_copy(self):
        kept = self.analysed_match()
        copy, _ = self.old_style_copy()
        listed = {m["id"]: m["duplicate_of"] for m in self.client.get("/api/matches").get_json()["matches"]}
        self.assertEqual(listed, {kept: None, copy: kept})

    def test_removing_duplicates_keeps_practice_and_deletes_the_file(self):
        kept = self.analysed_match()
        copy, sha = self.old_style_copy()
        answered = self.client.get(f"/api/decisions?match_id={copy}&kind=cube").get_json()["decisions"][0]
        self.client.post(f"/api/practice/{answered['id']}/reveal")
        removed = self.client.post("/api/matches/remove-duplicates").get_json()["removed"]
        history = self.client.get(f"/api/decisions/{answered['id']}")
        kept_twin = next(d for d in self.client.get(f"/api/decisions?match_id={kept}&include_forced=1")
                         .get_json()["decisions"] if d["position_key"] == answered["position_key"])
        self.assertEqual(
            (removed, history.status_code, os.path.exists(upload_path(self.data_dir, sha)),
             len(self.client.get(f"/api/decisions/{kept_twin['id']}").get_json()["decision"]["practice"]),
             [m["id"] for m in self.client.get("/api/matches").get_json()["matches"]]),
            ([copy], 404, False, 1, [kept]),
        )


class SamePositionInSeveralMatches(ApiTestCase):
    def two_matches(self):
        return self.analysed_match(), self.analysed_match(content=self.other_match_bytes())

    def grouped(self, query=""):
        return self.client.get(f"/api/decisions?include_forced=1&group=position{query}").get_json()["decisions"]

    def test_listed_once_with_every_copy(self):
        first, second = self.two_matches()
        every = self.client.get("/api/decisions?include_forced=1").get_json()["decisions"]
        grouped = self.grouped()
        self.assertEqual(
            (len(grouped), sum(len(d["copies"]) for d in grouped), {c["match_id"] for c in grouped[0]["copies"]}),
            (len({d["position_key"] for d in every}), len(every), {first, second}),
        )

    def test_a_tag_covers_every_copy(self):
        first, second = self.two_matches()
        tag_id = self.client.post("/api/tags", json={"name": "Opening", "color": "green"}).get_json()["tag"]["id"]
        target = self.grouped(f"&match_id={first}&kind=checker")[0]
        self.client.post(f"/api/tags/{tag_id}/decisions", json={"add": [target["id"]]})
        tagged = {d["match_id"] for d in self.client.get(f"/api/decisions?tag={tag_id}").get_json()["decisions"]}
        self.assertEqual((tagged, self.client.get("/api/tags").get_json()["tags"][0]["count"]), ({first, second}, 1))

    def test_practice_asks_a_position_once_and_remembers_it_for_every_copy(self):
        first, second = self.two_matches()
        queue = lambda: self.client.get("/api/practice/queue?mode=due&min_error=0").get_json()
        before = queue()
        self.client.post(f"/api/practice/{before['items'][0]['id']}/reveal")
        positions = {d["position_key"] for d in self.client.get("/api/decisions?min_error=0").get_json()["decisions"]}
        after = queue()
        self.assertEqual(
            (len(before["items"]), before["stats"]["positions"], after["stats"]["new"], after["stats"]["missed"]),
            (len(positions), len(positions), len(positions) - 1, 1),
        )

    def test_copies_cover_the_whole_library_when_one_match_is_shown(self):
        first, second = self.two_matches()
        rows = self.grouped(f"&match_id={first}")
        self.assertEqual(({r["match_id"] for r in rows}, {c["match_id"] for c in rows[0]["copies"]}),
                         ({first}, {first, second}))

    def test_opening_a_position_marks_it_seen_in_every_match(self):
        first, second = self.two_matches()
        target = self.grouped(f"&match_id={first}&min_error=0.03")[0]
        self.client.post(f"/api/decisions/{target['id']}/seen")
        seen = {d["match_id"] for d in self.client.get("/api/decisions?include_forced=1").get_json()["decisions"]
                if d["seen_at"] and d["position_key"] == target["position_key"]}
        self.assertEqual(seen, {first, second})


class TagsFromOlderVersions(ApiTestCase):
    def test_decision_tags_become_position_tags(self):
        match_id = self.analysed_match()
        tag_id = self.client.post("/api/tags", json={"name": "Old", "color": "red"}).get_json()["tag"]["id"]
        decision = self.client.get(f"/api/decisions?match_id={match_id}&kind=checker").get_json()["decisions"][0]
        with self.conn:
            self.conn.execute("CREATE TABLE decision_tags (decision_id INTEGER, tag_id INTEGER, added_at TEXT)")
            self.conn.execute("INSERT INTO decision_tags VALUES (?, ?, '2026-11-01T10:00:00')", (decision["id"], tag_id))
            self.conn.execute("UPDATE decisions SET position_key = NULL")
        fill_missing_keys(self.conn, self.data_dir)
        tagged = self.client.get(f"/api/decisions?tag={tag_id}").get_json()["decisions"]
        table_left = self.conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'decision_tags'").fetchone()
        self.assertEqual(([d["id"] for d in tagged], table_left), ([decision["id"]], None))


class OldPageAddresses(ApiTestCase):
    def test_review_and_positions_redirect_to_moves(self):
        responses = [self.client.get("/review?match=4&focus=9"), self.client.get("/positions")]
        self.assertEqual([(r.status_code, r.headers["Location"]) for r in responses],
                         [(302, "/moves?match=4&focus=9"), (302, "/moves")])


def fake_deep(path, job, on_line=None, cancelled=lambda: False):
    on_line("VSG-PROGRESS 648 1296\n")
    if cancelled():
        raise Cancelled()
    decision = next(d for d in walk_match(MATCH, FakeHelpers())["decisions"]
                    if all(d[k] == job["decision"][k] for k in ("game_no", "move_no", "kind", "player")))
    if decision["kind"] == "checker":
        for row in decision["candidates"]:
            row["rollout"] = {"trials": 1296, "std": 0.01}
    return {"decision": {**decision, "error": 0.0123, "best": "rolled best"}, "seconds": 1.5}


class DeepAnalysis(ApiTestCase):
    def checker(self, match_id):
        return next(d for d in self.client.get(f"/api/decisions?match_id={match_id}&include_forced=1").get_json()["decisions"]
                    if d["kind"] == "checker" and len(d["candidates"]) > 1)

    def start(self, decision_id, **payload):
        return self.client.post(f"/api/decisions/{decision_id}/deep", json={"mode": "rollout", **payload})

    def detail(self, decision_id):
        return self.client.get(f"/api/decisions/{decision_id}").get_json()["decision"]

    def test_rollout_job_runs_and_its_result_replaces_the_analysis(self):
        target = self.checker(self.analysed_match())
        job = self.start(target["id"], settings={"trials": 1296}).get_json()["job"]
        ranked = sorted(target["candidates"], key=lambda c: -c["equity"])
        played = target["candidates"][target["played_index"]]
        expected = [c["steps"] for c in ranked[:3]] + ([played["steps"]] if played not in ranked[:3] else [])
        deep_jobs.process_next(self.conn, self.data_dir, run=fake_deep)
        after = self.detail(target["id"])
        finished = self.client.get(f"/api/deep/jobs/{job['id']}").get_json()["job"]
        listed = next(d for d in self.client.get("/api/decisions?include_forced=1").get_json()["decisions"]
                      if d["id"] == target["id"])
        self.assertEqual(
            (job["status"], job["moves"] == expected,
             finished["status"], (finished["done"], finished["total"]), after["error"], after["best"],
             after["deep"]["mode"], after["deep"]["settings"]["trials"], after["deep_job"], listed["deep_mode"]),
            ("queued", True, "done", (1296, 1296), 0.0123, "rolled best", "rollout", 1296, None, "rollout"),
        )

    def test_cube_decision_rollout(self):
        match_id = self.analysed_match()
        cube = next(d for d in self.client.get(f"/api/decisions?match_id={match_id}&kind=cube").get_json()["decisions"]
                    if d["kind"] == "cube")
        job = self.start(cube["id"]).get_json()["job"]
        deep_jobs.process_next(self.conn, self.data_dir, run=fake_deep)
        after = self.detail(cube["id"])
        self.assertEqual((job["moves"], self.client.get(f"/api/deep/jobs/{job['id']}").get_json()["job"]["status"],
                          after["error"], after["candidates"]), (None, "done", 0.0123, None))

    def test_going_back_restores_the_original_analysis(self):
        target = self.checker(self.analysed_match())
        self.start(target["id"])
        deep_jobs.process_next(self.conn, self.data_dir, run=fake_deep)
        cleared = self.client.delete(f"/api/decisions/{target['id']}/deep")
        after = self.detail(target["id"])
        self.assertEqual((cleared.status_code, after["error"], after["best"], after["deep"]),
                         (200, target["error"], target["best"], None))

    def test_reanalysing_the_match_keeps_the_deeper_result(self):
        match_id = self.analysed_match()
        target = self.checker(match_id)
        self.start(target["id"], mode="eval", settings={"checker": {"plies": 4}})
        deep_jobs.process_next(self.conn, self.data_dir, run=fake_deep)
        self.client.post(f"/api/matches/{match_id}/reanalyze")
        jobs.process_next(self.conn, self.data_dir, analyse=fake_analyse)
        self.client.delete(f"/api/decisions/{target['id']}/deep")
        self.assertEqual(self.detail(target["id"])["error"], target["error"])

    def test_reanalysis_result_sits_on_the_fresh_analysis(self):
        match_id = self.analysed_match()
        target = self.checker(match_id)
        self.start(target["id"], mode="eval")
        deep_jobs.process_next(self.conn, self.data_dir, run=fake_deep)
        self.client.post(f"/api/matches/{match_id}/reanalyze")
        jobs.process_next(self.conn, self.data_dir, analyse=fake_analyse)
        self.assertEqual((self.detail(target["id"])["error"], self.detail(target["id"])["deep"]["mode"]), (0.0123, "eval"))

    def test_cancelling_a_queued_job_and_a_running_one(self):
        target = self.checker(self.analysed_match())
        queued = self.start(target["id"]).get_json()["job"]
        first = self.client.post(f"/api/deep/jobs/{queued['id']}/cancel").get_json()["job"]["status"]
        running = self.start(target["id"]).get_json()["job"]
        with self.conn:
            self.conn.execute("UPDATE deep_jobs SET status = 'running' WHERE id = ?", (running["id"],))
        self.client.post(f"/api/deep/jobs/{running['id']}/cancel")
        with self.conn:
            self.conn.execute("UPDATE deep_jobs SET status = 'queued' WHERE id = ?", (running["id"],))
        cancelling = lambda path, job, on_line=None, cancelled=lambda: False: (
            self.client.post(f"/api/deep/jobs/{running['id']}/cancel"), fake_deep(path, job, on_line, cancelled))[1]
        deep_jobs.process_next(self.conn, self.data_dir, run=cancelling)
        self.assertEqual((first, self.client.get(f"/api/deep/jobs/{running['id']}").get_json()["job"]["status"],
                          self.detail(target["id"])["error"]), ("cancelled", "cancelled", target["error"]))

    def test_engine_failure_is_reported_on_the_job(self):
        target = self.checker(self.analysed_match())
        job = self.start(target["id"]).get_json()["job"]

        def broken(*args, **kwargs):
            raise EngineError("gnubg exited with code 1 without a result: boom")

        deep_jobs.process_next(self.conn, self.data_dir, run=broken)
        failed = self.client.get(f"/api/deep/jobs/{job['id']}").get_json()["job"]
        self.assertEqual((failed["status"], failed["error"], self.detail(target["id"])["deep"]),
                         ("error", "gnubg exited with code 1 without a result: boom", None))

    def test_requests_are_validated(self):
        target = self.checker(self.analysed_match())
        responses = [self.start(target["id"], mode="magic"), self.start(target["id"], settings={"trials": 0}),
                     self.start(target["id"], moves=[[[1, 0]]]), self.start(999)]
        self.start(target["id"])
        responses.append(self.start(target["id"]))
        self.assertEqual(
            [(r.status_code, (r.get_json() or {}).get("error")) for r in responses],
            [(400, "choose a deeper evaluation or a rollout"), (400, "games must be between 1 and 1000000"),
             (400, "choose at least one move to roll out"), (404, None), (400, "this position is already being analysed")],
        )

    def test_options_list_defaults_and_presets(self):
        options = self.client.get("/api/deep/options").get_json()
        self.assertEqual((sorted(options["presets"]), options["rollout"]["trials"], options["eval"]["checker"]["plies"],
                          options["max_plies"]), (["quick", "standard", "strong"], 1296, 3, 4))


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




class ImportDocker(ApiTestCase):
    def test_shell_offers_nothing_without_a_docker_install(self):
        self.assertEqual(self.client.get("/api/shell").get_json()["docker_data"], False)

    def test_import_is_refused_when_there_is_nothing_to_bring_over(self):
        response = self.client.post("/api/import-docker")
        self.assertEqual((response.status_code, response.get_json()["error"]), (400, "there is nothing to bring over"))


if __name__ == "__main__":
    unittest.main()

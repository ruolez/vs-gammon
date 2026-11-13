import datetime
import logging
import os
import threading

from flask import Flask, abort, g, jsonify, redirect, request, send_file, send_from_directory

from app import db, jobs, migrate_docker, watcher
from app.dashboard import build_dashboard
from app.analysis import classify, grade_checker, grade_cube, is_correct, review_state, summarize
from app.engine.runner import gnubg_version
from app.export import build_export_zip
from app.importer import (MAX_UPLOAD_BYTES, describe, fill_missing_keys, import_match_bytes, remove_duplicates,
                          upload_path)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
MAX_EXPORT = 500
PAGES = {"/": "index.html", "/matches": "matches.html", "/moves": "moves.html", "/practice": "practice.html",
         "/history": "history.html", "/settings": "settings.html"}
MOVED_PAGES = {"/review": "/moves", "/positions": "/moves"}
CUBE_ANSWER_TEXT = {"double": "Double", "no_double": "No double", "take": "Take", "pass": "Pass"}


def _int_arg(name):
    value = request.args.get(name, "")
    return int(value) if value.lstrip("-").isdigit() else None


def _float_arg(name, default=0.0):
    try:
        return float(request.args.get(name, default))
    except ValueError:
        return default


def _id_list_arg(name):
    return [int(v) for v in request.args.get(name, "").split(",") if v.strip().isdigit()] or None


def _filter_args():
    return {
        "match_ids": _id_list_arg("match_id"),
        "tag_ids": _id_list_arg("tag"),
        "untagged": request.args.get("tag") == "none",
        "all_tags": request.args.get("tag_match") == "all",
        "player": _int_arg("player"),
        "player_name": request.args.get("player_name") or None,
        "kind": request.args.get("kind") or None,
        "min_error": max(0.0, _float_arg("min_error")),
        "game_no": _int_arg("game"),
    }


def _validate_settings(payload):
    changes = {}
    if "preset" in payload:
        if payload["preset"] not in (*db.PRESETS, "custom"):
            raise ValueError("unknown preset")
        changes["preset"] = payload["preset"]
    if "thresholds" in payload:
        t = payload["thresholds"]
        values = {k: float(t[k]) for k in ("doubtful", "bad", "very_bad")}
        if not 0 < values["doubtful"] < values["bad"] < values["very_bad"] <= 2:
            raise ValueError("thresholds must increase: 0 < doubtful < bad < very bad ≤ 2")
        changes["thresholds"] = values
    elif changes.get("preset") in db.PRESETS:
        changes["thresholds"] = db.PRESETS[changes["preset"]]
    if "plies" in payload:
        plies = int(payload["plies"])
        if plies not in (0, 1, 2, 3):
            raise ValueError("analysis depth must be 0, 1, 2 or 3 ply")
        changes["plies"] = plies
    if "threads" in payload:
        threads = int(payload["threads"])
        if not 1 <= threads <= 64:
            raise ValueError("threads must be between 1 and 64")
        changes["threads"] = threads
    if "me" in payload:
        me = str(payload["me"] or "").strip()
        if len(me) > 80:
            raise ValueError("player name is too long")
        changes["me"] = me
    if "watch_interval" in payload:
        interval = int(payload["watch_interval"])
        if not 5 <= interval <= 3600:
            raise ValueError("folder scan interval must be between 5 and 3600 seconds")
        changes["watch_interval"] = interval
    return changes


def _match_json(row, thresholds, conn, me):
    match = dict(row)
    if match["status"] == "done":
        decisions = db.all_decisions_for_match(conn, match["id"], thresholds)
        match["summary"] = summarize(decisions, thresholds)
        side = {match["player1"]: 1, match["player2"]: 2}.get(me) if me else None
        match["review"] = review_state(decisions, thresholds, side, match["review_mark"])
        match["games"] = [dict(r) for r in conn.execute(
            "SELECT game_no, score1, score2, crawford, winner, points FROM games WHERE match_id = ? ORDER BY game_no",
            (match["id"],))]
    return match


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(
        DATA_DIR=os.environ.get("DATA_DIR", "/srv/data"),
        EXPORT_DIR=os.environ.get("EXPORT_DIR", "/srv/exports"),
        HOST_HOME=os.environ.get("HOST_HOME") or None,
        HOST_ROOT=os.environ.get("HOST_ROOT", "/host"),
        DOCKER_SOURCE=os.environ.get("VSG_DOCKER_SOURCE") or None,
        START_WORKER=True,
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES * 20,
    )
    app.config.update(config or {})
    data_dir = app.config["DATA_DIR"]
    host_home, host_root = app.config["HOST_HOME"], app.config["HOST_ROOT"]
    folders_available = bool(host_home and host_root and os.path.isdir(host_root))
    os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)
    os.makedirs(app.config["EXPORT_DIR"], exist_ok=True)
    db_path = os.path.join(data_dir, "app.db")
    setup = db.connect(db_path)
    db.migrate(setup)
    fill_missing_keys(setup, data_dir)
    setup.close()
    wake = threading.Event()
    wake_scan = threading.Event()
    app.extensions["wake_worker"] = wake
    if app.config["START_WORKER"]:
        logging.basicConfig(level=logging.INFO)
        jobs.start_worker(db_path, data_dir, wake)
        if folders_available:
            watcher.start_watcher(db_path, data_dir, host_home, host_root, wake_scan, wake)

    def conn():
        if "db" not in g:
            g.db = db.connect(db_path)
        return g.db

    def thresholds():
        return db.get_settings(conn())["thresholds"]

    def match_json(row):
        settings = db.get_settings(conn())
        return _match_json(row, settings["thresholds"], conn(), settings["me"])

    def match_row(match_id):
        row = conn().execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not row:
            abort(404)
        return row

    def require_folders():
        if not folders_available:
            raise watcher.FolderAccessError("folder access is not set up; run ./install.sh update to enable it")

    @app.teardown_appcontext
    def close_db(_exc):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.errorhandler(ValueError)
    def bad_request(exc):
        return jsonify(error=str(exc)), 400

    for route, page in PAGES.items():
        app.add_url_rule(route, f"page_{page}", (lambda p=page: send_from_directory(STATIC_DIR, p)))

    for old, new in MOVED_PAGES.items():
        app.add_url_rule(old, f"moved_{old}", (lambda target=new: redirect(
            f"{target}?{request.query_string.decode()}" if request.query_string else target)))

    @app.get("/static/<path:path>")
    def static_files(path):
        return send_from_directory(STATIC_DIR, path)

    @app.get("/health")
    def health():
        return jsonify(status="ok", engine=gnubg_version(), folders=folders_available)

    @app.post("/api/matches")
    def upload_matches():
        files = request.files.getlist("files")
        if not files:
            raise ValueError("no files uploaded")
        results = []
        for upload in files:
            raw = upload.read(MAX_UPLOAD_BYTES + 1)
            name = os.path.basename(upload.filename or "match.mat")
            results.append(import_match_bytes(conn(), data_dir, raw, name))
        wake.set()
        return jsonify(results=results)

    @app.get("/api/matches")
    def list_matches():
        rows = conn().execute("SELECT * FROM matches ORDER BY COALESCE(event_date, '') DESC, id DESC").fetchall()
        duplicates = db.duplicate_matches(conn())
        return jsonify(matches=[{**match_json(r), "duplicate_of": duplicates.get(r["id"])} for r in rows])

    @app.post("/api/matches/remove-duplicates")
    def remove_duplicate_matches():
        return jsonify(removed=remove_duplicates(conn(), data_dir))

    @app.get("/api/matches/<int:match_id>")
    def get_match(match_id):
        match = match_json(match_row(match_id))
        match["history"] = [dict(r) for r in conn().execute(
            "SELECT at, kind, message FROM events WHERE match_id = ? ORDER BY id DESC LIMIT 50", (match_id,))]
        return jsonify(match=match)

    @app.delete("/api/matches/<int:match_id>")
    def delete_match(match_id):
        row = conn().execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not row:
            abort(404)
        with conn():
            conn().execute("DELETE FROM matches WHERE id = ?", (match_id,))
        try:
            os.remove(upload_path(data_dir, row["sha256"]))
        except FileNotFoundError:
            pass
        db.log_event(conn(), "deleted", f"Deleted {describe(row)}")
        return jsonify(deleted=match_id)

    @app.put("/api/matches/<int:match_id>/reviewed")
    def mark_reviewed(match_id):
        reviewed = bool((request.get_json(silent=True) or {}).get("reviewed"))
        auto = match_json(match_row(match_id))["review"]["auto"]
        db.set_review_mark(conn(), match_id, None if reviewed == auto else int(reviewed))
        return jsonify(review=match_json(match_row(match_id))["review"])

    @app.post("/api/matches/<int:match_id>/reanalyze")
    def reanalyze(match_id):
        row = conn().execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not row:
            abort(404)
        if row["status"] != "analyzing":
            db.set_match_status(conn(), match_id, "queued")
            db.log_event(conn(), "reanalysis", f"Re-analysis requested for {describe(row)}", match_id)
        wake.set()
        return jsonify(queued=match_id)

    @app.get("/api/players")
    def players():
        rows = conn().execute(
            """SELECT name, COUNT(*) AS matches FROM (SELECT player1 AS name FROM matches UNION ALL
                   SELECT player2 FROM matches) WHERE name IS NOT NULL GROUP BY name ORDER BY matches DESC, name"""
        ).fetchall()
        return jsonify(players=[dict(r) for r in rows])

    def default_player():
        me = db.get_settings(conn()).get("me")
        if me:
            return me
        row = conn().execute(
            """SELECT name, COUNT(*) AS n FROM (SELECT player1 AS name FROM matches UNION ALL
                   SELECT player2 FROM matches) WHERE name IS NOT NULL GROUP BY name ORDER BY n DESC, name LIMIT 1"""
        ).fetchone()
        return row["name"] if row else None

    @app.get("/api/shell")
    def shell():
        me = default_player()
        t = thresholds()
        due = 0
        if me:
            stats = db.practice_stats(conn(), player_name=me, min_error=t["doubtful"])
            due = stats["new"] + stats["missed"]
        watching = [f["path"] for f in db.list_folders(conn()) if f["enabled"]]
        return jsonify(me=me, due=due, watching=watching, folders=folders_available, engine=gnubg_version(),
                       docker_data=migrate_docker.available(app.config["DOCKER_SOURCE"], conn()))

    @app.post("/api/import-docker")
    def import_docker():
        if not migrate_docker.available(app.config["DOCKER_SOURCE"], conn()):
            raise ValueError("there is nothing to bring over")
        count = migrate_docker.import_docker_data(app.config["DOCKER_SOURCE"], conn(), data_dir, app.config["EXPORT_DIR"])
        wake.set()
        wake_scan.set()
        return jsonify(matches=count)

    @app.get("/api/dashboard")
    def dashboard():
        player = request.args.get("player_name") or default_player()
        if not player:
            return jsonify(player=None, matches=[], empty=True)
        today = db.local_now(db.LOCAL_TZ).date().isoformat()
        return jsonify(build_dashboard(conn(), thresholds(), player, today))

    @app.get("/api/decisions")
    def list_decisions():
        t = thresholds()
        decisions = db.query_decisions(conn(), t, include_forced=request.args.get("include_forced") == "1",
                                       **_filter_args())
        if request.args.get("group") == "position":
            decisions = db.group_positions(conn(), decisions, t)
        return jsonify(decisions=decisions, thresholds=t)

    @app.get("/api/decisions/<int:decision_id>")
    def get_decision(decision_id):
        found = db.decisions_by_ids(conn(), [decision_id], thresholds(), with_legal=True)
        if not found:
            abort(404)
        decision = found[0]
        decision["practice"] = db.decision_practice_history(conn(), decision_id)
        return jsonify(decision=decision)

    @app.post("/api/decisions/<int:decision_id>/seen")
    def decision_seen(decision_id):
        row = conn().execute("SELECT match_id FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        if not row:
            abort(404)
        db.mark_seen(conn(), decision_id)
        return jsonify(match_id=row["match_id"], review=match_json(match_row(row["match_id"]))["review"])

    def tag_or_404(tag_id):
        tag = db.get_tag(conn(), tag_id)
        if not tag:
            abort(404)
        return tag

    @app.get("/api/tags")
    def list_tags():
        return jsonify(tags=db.list_tags(conn()))

    @app.post("/api/tags")
    def create_tag():
        payload = request.get_json(silent=True) or {}
        tag_id = db.create_tag(conn(), payload.get("name", ""), payload.get("color", "blue"))
        return jsonify(tag=db.get_tag(conn(), tag_id), tags=db.list_tags(conn()))

    @app.patch("/api/tags/<int:tag_id>")
    def update_tag(tag_id):
        tag_or_404(tag_id)
        payload = request.get_json(silent=True) or {}
        db.update_tag(conn(), tag_id, name=payload.get("name"), color=payload.get("color"))
        return jsonify(tag=db.get_tag(conn(), tag_id), tags=db.list_tags(conn()))

    @app.delete("/api/tags/<int:tag_id>")
    def delete_tag(tag_id):
        tag_or_404(tag_id)
        db.delete_tag(conn(), tag_id)
        return jsonify(tags=db.list_tags(conn()))

    @app.post("/api/tags/<int:tag_id>/merge")
    def merge_tag(tag_id):
        tag_or_404(tag_id)
        target = (request.get_json(silent=True) or {}).get("into")
        if target == tag_id:
            raise ValueError("choose another tag to merge into")
        tag_or_404(target)
        db.merge_tag(conn(), tag_id, target)
        return jsonify(tags=db.list_tags(conn()))

    @app.post("/api/tags/<int:tag_id>/decisions")
    def tag_decisions(tag_id):
        tag_or_404(tag_id)
        payload = request.get_json(silent=True) or {}
        add = [int(i) for i in payload.get("add", []) if str(i).isdigit()]
        remove = [int(i) for i in payload.get("remove", []) if str(i).isdigit()]
        if len(db.existing_decisions(conn(), add)) != len(set(add)):
            abort(404)
        db.set_decision_tag(conn(), tag_id, add=add, remove=remove)
        return jsonify(tags=db.list_tags(conn()))

    @app.post("/api/export")
    def export():
        payload = request.get_json(silent=True) or {}
        ids = [int(i) for i in payload.get("decision_ids", []) if str(i).isdigit()]
        if not ids:
            raise ValueError("select at least one position to export")
        if len(ids) > MAX_EXPORT:
            raise ValueError(f"export at most {MAX_EXPORT} positions at a time")
        t = thresholds()
        decisions = db.decisions_by_ids(conn(), ids, t)
        if not decisions:
            abort(404)
        stamp = datetime.datetime.now()
        data = build_export_zip(decisions, t, stamp)
        filename = f"gammon-positions-{stamp:%Y%m%d-%H%M%S}.zip"
        path = os.path.join(app.config["EXPORT_DIR"], filename)
        with open(path, "wb") as f:
            f.write(data)
        db.record_export(conn(), len(decisions), filename)
        db.log_event(conn(), "exported", f"Exported {len(decisions)} positions to {filename}")
        return send_file(path, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/api/settings")
    def get_settings():
        return jsonify(settings=db.get_settings(conn()), presets=db.PRESETS)

    @app.put("/api/settings")
    def put_settings():
        changes = _validate_settings(request.get_json(silent=True) or {})
        db.save_settings(conn(), changes)
        return jsonify(settings=db.get_settings(conn()))

    @app.get("/api/history")
    def history():
        limit = min(500, max(1, _int_arg("limit") or 100))
        events = db.list_events(conn(), limit=limit, before_id=_int_arg("before"), kind=request.args.get("kind") or None)
        return jsonify(events=events, more=len(events) == limit)

    @app.get("/api/folders")
    def folders():
        return jsonify(available=folders_available, home=host_home, folders=db.list_folders(conn()))

    @app.post("/api/folders")
    def add_folder():
        require_folders()
        payload = request.get_json(silent=True) or {}
        listing = watcher.list_directory(payload.get("path"), host_home, host_root)
        folder_id = db.add_folder(conn(), listing["path"], bool(payload.get("recursive")))
        db.log_event(conn(), "folder_added", f"Watching {listing['path']} for new match files")
        wake_scan.set()
        return jsonify(id=folder_id, folders=db.list_folders(conn()))

    @app.patch("/api/folders/<int:folder_id>")
    def patch_folder(folder_id):
        payload = request.get_json(silent=True) or {}
        db.update_folder(conn(), folder_id, **{k: bool(v) for k, v in payload.items()})
        wake_scan.set()
        return jsonify(folders=db.list_folders(conn()))

    @app.delete("/api/folders/<int:folder_id>")
    def delete_folder(folder_id):
        row = conn().execute("SELECT path FROM watched_folders WHERE id = ?", (folder_id,)).fetchone()
        if not row:
            abort(404)
        db.remove_folder(conn(), folder_id)
        db.log_event(conn(), "folder_removed", f"Stopped watching {row['path']}")
        return jsonify(folders=db.list_folders(conn()))

    @app.post("/api/folders/scan")
    def scan_now():
        require_folders()
        wake_scan.set()
        return jsonify(scanning=True)

    @app.get("/api/fs")
    def browse():
        require_folders()
        return jsonify(watcher.list_directory(request.args.get("path") or host_home, host_home, host_root))

    @app.get("/api/practice/queue")
    def practice_queue():
        filters = _filter_args()
        items = db.practice_queue(conn(), mode=request.args.get("mode", "due"), **filters)
        return jsonify(items=items, stats=db.practice_stats(conn(), **filters))

    @app.get("/api/practice/stats")
    def practice_stats():
        return jsonify(stats=db.practice_stats(conn(), **_filter_args()))

    def practice_decision(decision_id):
        found = db.decisions_by_ids(conn(), [decision_id], thresholds(), with_legal=True)
        if not found:
            abort(404)
        return found[0]

    @app.post("/api/practice/<int:decision_id>/answer")
    def practice_answer(decision_id):
        decision = practice_decision(decision_id)
        payload = request.get_json(silent=True) or {}
        t = thresholds()
        if decision["kind"] == "checker":
            if not decision.get("legal"):
                raise ValueError("this position has no stored move list; re-analyse the match")
            index = int(payload.get("legal_index", -1))
            graded = grade_checker(decision["legal"], index)
            answer = decision["legal"][index]["text"]
        else:
            action = payload.get("action", "")
            graded = {"error": grade_cube(decision["kind"], decision["cube"], action), "approx": False}
            answer = CUBE_ANSWER_TEXT[action]
        correct = is_correct(graded["error"], t)
        db.record_attempt(conn(), decision_id, answer, graded["error"], correct)
        return jsonify(correct=correct, error=graded["error"], approx=graded["approx"],
                       **{"class": classify(graded["error"], t)}, answer=answer,
                       history=db.decision_practice_history(conn(), decision_id))

    @app.post("/api/practice/<int:decision_id>/reveal")
    def practice_reveal(decision_id):
        practice_decision(decision_id)
        db.record_attempt(conn(), decision_id, "revealed", None, False, revealed=True)
        return jsonify(history=db.decision_practice_history(conn(), decision_id))

    return app

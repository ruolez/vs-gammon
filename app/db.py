import datetime
import json
import os
import sqlite3
from zoneinfo import ZoneInfo

from app.analysis import classify
from app.position import build_xgid, seat_decider

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")
LOCAL_TZ = ZoneInfo(os.environ.get("TZ") or "UTC")

PRESETS = {
    "gnubg": {"doubtful": 0.03, "bad": 0.06, "very_bad": 0.12},
    "xg": {"doubtful": 0.02, "bad": 0.04, "very_bad": 0.08},
}
DEFAULT_SETTINGS = {
    "preset": "gnubg",
    "thresholds": PRESETS["gnubg"],
    "plies": 2,
    "threads": max(1, min(8, os.cpu_count() or 2)),
    "watch_interval": 30,
    "me": "",
}
JSON_COLUMNS = ("dice", "board", "candidates", "cube", "legal")
DECISION_FIELDS = (
    "game_no", "move_no", "player", "on_roll", "kind", "dice", "position_id", "xgid", "board", "cube_value",
    "cube_owner", "score1", "score2", "match_length", "crawford_game", "action", "best", "error", "forced",
    "candidates", "played_index", "cube", "gnubg_skill", "legal",
)
DECISION_IDENTITY = ("game_no", "move_no", "kind", "player")
LIST_COLUMNS = ", ".join(f"d.{f}" for f in DECISION_FIELDS if f != "legal")


def now_local():
    return datetime.datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
    for name in sorted(os.listdir(MIGRATIONS_DIR)):
        if name.endswith(".sql") and name not in applied:
            with open(os.path.join(MIGRATIONS_DIR, name)) as f:
                conn.executescript(f.read())
            conn.execute("INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)", (name, now_local()))
            conn.commit()


def get_settings(conn):
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    for row in conn.execute("SELECT key, value FROM settings"):
        settings[row["key"]] = json.loads(row["value"])
    return settings


def save_settings(conn, changes):
    with conn:
        for key, value in changes.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )


def log_event(conn, kind, message, match_id=None):
    with conn:
        conn.execute("INSERT INTO events (at, kind, match_id, message) VALUES (?, ?, ?, ?)",
                     (now_local(), kind, match_id, message))


def list_events(conn, limit=100, before_id=None, kind=None):
    where, params = [], []
    if before_id:
        where.append("e.id < ?")
        params.append(before_id)
    if kind:
        where.append("e.kind = ?")
        params.append(kind)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(
        f"""SELECT e.*, m.player1, m.player2, m.event_date, m.status AS match_status
            FROM events e LEFT JOIN matches m ON m.id = e.match_id
            {clause} ORDER BY e.id DESC LIMIT ?""",
        params + [limit],
    )
    return [dict(r) for r in rows]


def insert_match(conn, filename, sha256, header, source="upload", source_path=None):
    with conn:
        cur = conn.execute(
            """INSERT INTO matches (filename, sha256, site, external_id, player1, player2, elo1, elo2, match_length,
                                    event_date, event_time, status, created_at, source, source_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)""",
            (filename, sha256, header["site"], header["external_id"], header["player1"], header["player2"],
             header["elo1"], header["elo2"], header["match_length"], header["event_date"], header["event_time"],
             now_local(), source, source_path),
        )
    return cur.lastrowid


def match_by_sha(conn, sha256):
    return conn.execute("SELECT * FROM matches WHERE sha256 = ?", (sha256,)).fetchone()


def set_match_status(conn, match_id, status, error=None):
    with conn:
        conn.execute("UPDATE matches SET status = ?, error = ? WHERE id = ?", (status, error, match_id))


def claim_next_match(conn):
    with conn:
        row = conn.execute("SELECT id FROM matches WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        conn.execute("UPDATE matches SET status = 'analyzing', error = NULL WHERE id = ?", (row["id"],))
    return conn.execute("SELECT * FROM matches WHERE id = ?", (row["id"],)).fetchone()


def requeue_interrupted(conn):
    with conn:
        conn.execute("UPDATE matches SET status = 'queued' WHERE status = 'analyzing'")


def _xgid(d):
    dice = d["dice"] if d["kind"] == "checker" else None
    s = seat_decider(d)
    return build_xgid(s["board"], s["on_roll"], dice, s["cube_value"], s["cube_owner"], s["score1"], s["score2"],
                      s["match_length"], s["crawford_game"])


def _decision_values(d):
    values = {
        **{f: d.get(f) for f in DECISION_FIELDS},
        "xgid": _xgid(d),
        "crawford_game": int(d["crawford_game"]),
        "forced": int(d["forced"]),
    }
    for column in JSON_COLUMNS:
        values[column] = json.dumps(d.get(column))
    return [values[f] for f in DECISION_FIELDS]


def store_analysis(conn, match_id, result):
    match = result["match"]
    columns = ", ".join(DECISION_FIELDS)
    marks = ", ".join("?" * (len(DECISION_FIELDS) + 1))
    updates = ", ".join(f"{f} = excluded.{f}" for f in DECISION_FIELDS if f not in DECISION_IDENTITY)
    with conn:
        conn.execute("DELETE FROM games WHERE match_id = ?", (match_id,))
        conn.executemany(
            "INSERT INTO games (match_id, game_no, score1, score2, crawford, winner, points) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(match_id, g["game_no"], g["score1"], g["score2"], int(g["crawford"]), g["winner"], g["points"])
             for g in result["games"]],
        )
        conn.executemany(
            f"""INSERT INTO decisions (match_id, {columns}) VALUES ({marks})
                ON CONFLICT(match_id, game_no, move_no, kind, player) DO UPDATE SET {updates}""",
            [[match_id] + _decision_values(d) for d in result["decisions"]],
        )
        keep = {tuple(d[f] for f in DECISION_IDENTITY) for d in result["decisions"]}
        stale = [row["id"] for row in conn.execute(
            "SELECT id, game_no, move_no, kind, player FROM decisions WHERE match_id = ?", (match_id,))
            if (row["game_no"], row["move_no"], row["kind"], row["player"]) not in keep]
        conn.executemany("DELETE FROM decisions WHERE id = ?", [(i,) for i in stale])
        conn.execute(
            """UPDATE matches SET status = 'done', error = NULL, plies = ?, analysis_seconds = ?, analyzed_at = ?,
                   player1 = COALESCE(player1, ?), player2 = COALESCE(player2, ?), match_length = ?
               WHERE id = ?""",
            (result["engine"]["plies"], result["engine"]["seconds"], now_local(), match["player1"], match["player2"],
             match["match_length"], match_id),
        )


def decision_from_row(row, thresholds):
    d = dict(row)
    for column in JSON_COLUMNS:
        if column in d and d[column] is not None:
            d[column] = json.loads(d[column])
    d["forced"] = bool(d["forced"])
    d["crawford_game"] = bool(d["crawford_game"])
    d["class"] = classify(d["error"], thresholds)
    d["xgid"] = _xgid(d)
    return d


MATCH_COLUMNS = "m.player1, m.player2, m.event_date, m.filename"
FULL_SELECT = f"SELECT d.id, d.match_id, d.seen_at, {', '.join('d.' + f for f in DECISION_FIELDS)}, {MATCH_COLUMNS} " \
              "FROM decisions d JOIN matches m ON m.id = d.match_id"
LIST_SELECT = f"SELECT d.id, d.match_id, d.seen_at, {LIST_COLUMNS}, {MATCH_COLUMNS} " \
              "FROM decisions d JOIN matches m ON m.id = d.match_id"


def decision_filters(match_ids=None, player=None, player_name=None, kind=None, min_error=0.0, game_no=None,
                     include_forced=False):
    where, params = ["d.error >= ?"], [min_error]
    if match_ids:
        where.append(f"d.match_id IN ({','.join('?' * len(match_ids))})")
        params += list(match_ids)
    if player in (1, 2):
        where.append("d.player = ?")
        params.append(player)
    if player_name:
        where.append("((d.player = 1 AND m.player1 = ?) OR (d.player = 2 AND m.player2 = ?))")
        params += [player_name, player_name]
    if kind == "checker":
        where.append("d.kind = 'checker'")
    elif kind == "cube":
        where.append("d.kind IN ('cube', 'take')")
    if game_no is not None:
        where.append("d.game_no = ?")
        params.append(game_no)
    if not include_forced:
        where.append("d.forced = 0")
    return where, params


def query_decisions(conn, thresholds, limit=5000, **filters):
    where, params = decision_filters(**filters)
    sql = f"{LIST_SELECT} WHERE {' AND '.join(where)} ORDER BY d.match_id DESC, d.game_no, d.move_no, d.id LIMIT ?"
    return [decision_from_row(r, thresholds) for r in conn.execute(sql, params + [limit])]


def decisions_by_ids(conn, ids, thresholds, with_legal=False):
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    select = FULL_SELECT if with_legal else LIST_SELECT
    sql = f"{select} WHERE d.id IN ({marks}) ORDER BY d.match_id, d.game_no, d.move_no, d.id"
    return [decision_from_row(r, thresholds) for r in conn.execute(sql, list(ids))]


def all_decisions_for_match(conn, match_id, thresholds):
    sql = f"{LIST_SELECT} WHERE d.match_id = ? ORDER BY d.game_no, d.move_no, d.id"
    return [decision_from_row(r, thresholds) for r in conn.execute(sql, (match_id,))]


def mark_seen(conn, decision_id):
    with conn:
        conn.execute("UPDATE decisions SET seen_at = COALESCE(seen_at, ?) WHERE id = ?", (now_local(), decision_id))


def set_review_mark(conn, match_id, mark):
    with conn:
        conn.execute("UPDATE matches SET review_mark = ? WHERE id = ?", (mark, match_id))


def record_export(conn, count, filename):
    with conn:
        conn.execute("INSERT INTO exports (created_at, decision_count, filename) VALUES (?, ?, ?)",
                     (now_local(), count, filename))


def list_folders(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM watched_folders ORDER BY path")]


def add_folder(conn, path, recursive):
    with conn:
        conn.execute(
            "INSERT INTO watched_folders (path, recursive, enabled, added_at) VALUES (?, ?, 1, ?) "
            "ON CONFLICT(path) DO UPDATE SET enabled = 1, recursive = excluded.recursive",
            (path, int(recursive), now_local()),
        )
    return conn.execute("SELECT id FROM watched_folders WHERE path = ?", (path,)).fetchone()["id"]


def update_folder(conn, folder_id, **changes):
    allowed = {k: int(v) for k, v in changes.items() if k in ("recursive", "enabled")}
    if not allowed:
        return
    sets = ", ".join(f"{k} = ?" for k in allowed)
    with conn:
        conn.execute(f"UPDATE watched_folders SET {sets} WHERE id = ?", list(allowed.values()) + [folder_id])


def remove_folder(conn, folder_id):
    with conn:
        conn.execute("DELETE FROM watched_folders WHERE id = ?", (folder_id,))


def record_attempt(conn, decision_id, answer, error, correct, revealed=False):
    with conn:
        conn.execute(
            "INSERT INTO practice_attempts (decision_id, at, answer, error, correct, revealed) VALUES (?, ?, ?, ?, ?, ?)",
            (decision_id, now_local(), answer, error, int(correct), int(revealed)),
        )


PRACTICE_STATE = """
    LEFT JOIN (
        SELECT decision_id, correct AS last_correct, at AS last_at,
               ROW_NUMBER() OVER (PARTITION BY decision_id ORDER BY id DESC) AS rn
        FROM practice_attempts
    ) last ON last.decision_id = d.id AND last.rn = 1
    LEFT JOIN (
        SELECT decision_id, COUNT(*) AS attempts, SUM(correct) AS correct_attempts
        FROM practice_attempts GROUP BY decision_id
    ) totals ON totals.decision_id = d.id
"""
PRACTICE_MODES = {
    "due": "(last.last_correct IS NULL OR last.last_correct = 0)",
    "misses": "last.last_correct = 0",
    "new": "last.last_correct IS NULL",
    "all": "1 = 1",
}


def practice_queue(conn, mode="due", limit=500, **filters):
    if mode not in PRACTICE_MODES:
        raise ValueError(f"unknown practice mode '{mode}'")
    where, params = decision_filters(include_forced=False, **filters)
    where.append(PRACTICE_MODES[mode])
    rows = conn.execute(
        f"""SELECT d.id, d.error, last.last_correct, last.last_at, COALESCE(totals.attempts, 0) AS attempts
            FROM decisions d JOIN matches m ON m.id = d.match_id {PRACTICE_STATE}
            WHERE {' AND '.join(where)}
            ORDER BY CASE WHEN last.last_correct = 0 THEN 0 WHEN last.last_correct IS NULL THEN 1 ELSE 2 END,
                     last.last_at, d.error DESC, d.id
            LIMIT ?""",
        params + [limit],
    )
    return [dict(r) for r in rows]


def practice_stats(conn, **filters):
    where, params = decision_filters(include_forced=False, **filters)
    row = conn.execute(
        f"""SELECT COUNT(*) AS positions,
                   SUM(CASE WHEN last.last_correct IS NULL THEN 1 ELSE 0 END) AS new,
                   SUM(CASE WHEN last.last_correct = 0 THEN 1 ELSE 0 END) AS missed,
                   SUM(CASE WHEN last.last_correct = 1 THEN 1 ELSE 0 END) AS mastered,
                   COALESCE(SUM(totals.attempts), 0) AS attempts,
                   COALESCE(SUM(totals.correct_attempts), 0) AS correct
            FROM decisions d JOIN matches m ON m.id = d.match_id {PRACTICE_STATE}
            WHERE {' AND '.join(where)}""",
        params,
    ).fetchone()
    stats = {k: row[k] or 0 for k in row.keys()}
    days = conn.execute(
        f"""SELECT substr(a.at, 1, 10) AS day, COUNT(*) AS attempts, SUM(a.correct) AS correct
            FROM practice_attempts a JOIN decisions d ON d.id = a.decision_id JOIN matches m ON m.id = d.match_id
            WHERE {' AND '.join(where)}
            GROUP BY day ORDER BY day DESC LIMIT 14""",
        params,
    )
    stats["days"] = [dict(r) for r in days]
    return stats


def decision_practice_history(conn, decision_id):
    return [dict(r) for r in conn.execute(
        "SELECT at, answer, error, correct, revealed FROM practice_attempts WHERE decision_id = ? ORDER BY id DESC LIMIT 20",
        (decision_id,))]

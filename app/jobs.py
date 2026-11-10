import logging
import threading

from app import db
from app.analysis import summarize
from app.engine.runner import EngineError, run_analysis
from app.importer import describe, upload_path

log = logging.getLogger(__name__)
POLL_SECONDS = 5


def analysis_message(match, decisions, thresholds, engine):
    summary = summarize(decisions, thresholds)
    parts = []
    for player, name in ((1, match["player1"]), (2, match["player2"])):
        s = summary.get(player)
        if not s:
            continue
        errors = sum(s[k][sev] for k in ("checker", "cube") for sev in ("doubtful", "bad", "very_bad"))
        blunders = s["checker"]["very_bad"] + s["cube"]["very_bad"]
        pr = "–" if s["pr"] is None else f"{s['pr']:.1f}"
        parts.append(f"{name}: PR {pr}, {errors} errors ({blunders} very bad)")
    return (f"Analysed {describe(match)} at {engine['plies']}-ply in {engine['seconds']} s, "
            f"{len(decisions)} decisions. " + "; ".join(parts))


def process_next(conn, data_dir, analyse=run_analysis):
    match = db.claim_next_match(conn)
    if match is None:
        return False
    settings = db.get_settings(conn)
    try:
        result = analyse(upload_path(data_dir, match["sha256"]), plies=settings["plies"], threads=settings["threads"])
        db.store_analysis(conn, match["id"], result)
        stored = conn.execute("SELECT * FROM matches WHERE id = ?", (match["id"],)).fetchone()
        decisions = db.all_decisions_for_match(conn, match["id"], settings["thresholds"])
        db.log_event(conn, "analysed", analysis_message(stored, decisions, settings["thresholds"], result["engine"]),
                     match["id"])
        log.info("analysed match %s in %ss", match["id"], result["engine"]["seconds"])
    except EngineError as exc:
        log.warning("analysis of match %s failed: %s", match["id"], exc)
        db.set_match_status(conn, match["id"], "error", str(exc)[:2000])
        db.log_event(conn, "analysis_failed", f"Analysis of {describe(match)} failed: {exc}"[:2000], match["id"])
    except Exception as exc:
        log.exception("analysis of match %s crashed", match["id"])
        message = f"{type(exc).__name__}: {exc}"[:2000]
        db.set_match_status(conn, match["id"], "error", message)
        db.log_event(conn, "analysis_failed", f"Analysis of {describe(match)} crashed: {message}"[:2000], match["id"])
    return True


def start_worker(db_path, data_dir, wake):
    def loop():
        conn = db.connect(db_path)
        db.requeue_interrupted(conn)
        while True:
            try:
                while process_next(conn, data_dir):
                    pass
            except Exception:
                log.exception("analysis worker error")
            wake.wait(POLL_SECONDS)
            wake.clear()

    thread = threading.Thread(target=loop, name="analysis-worker", daemon=True)
    thread.start()
    return thread

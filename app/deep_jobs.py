"""Background worker for deeper analysis of single decisions (deeper evaluation or rollout), one job at a time."""
import logging
import threading
import time

from app import db
from app.engine import deep
from app.engine.runner import Cancelled, EngineError, run_deep
from app.importer import upload_path

log = logging.getLogger(__name__)
POLL_SECONDS = 5
IDENTITY = ("game_no", "move_no", "kind", "player")


def job_payload(job, decision, match, threads):
    return {
        "mode": job["mode"],
        "settings": job["settings"],
        "moves": job["moves"],
        "decision": {k: decision[k] for k in IDENTITY},
        "threads": threads,
        "base_plies": match["plies"] if match["plies"] is not None else 2,
    }


def process_next(conn, data_dir, run=run_deep):
    job = db.claim_deep_job(conn)
    if not job:
        return False
    started = time.time()
    try:
        decision = conn.execute("SELECT * FROM decisions WHERE id = ?", (job["decision_id"],)).fetchone()
        match = conn.execute("SELECT * FROM matches WHERE id = ?", (decision["match_id"],)).fetchone() if decision else None
        if not match:
            raise EngineError("this position no longer exists")
        progress = {"latest": None, "written": None}

        def on_line(line):
            found = deep.parse_progress(line)
            if found:
                progress["latest"] = found

        def cancelled():
            latest = progress["latest"]
            if latest and latest != progress["written"]:
                db.deep_job_progress(conn, job["id"], latest["done"], latest["total"])
                progress["written"] = latest
            return db.deep_job_cancelling(conn, job["id"])

        threads = db.get_settings(conn)["threads"]
        result = run(upload_path(data_dir, match["sha256"]), job_payload(job, decision, match, threads),
                     on_line=on_line, cancelled=cancelled)
        if job["mode"] == "rollout":
            db.deep_job_progress(conn, job["id"], job["settings"]["trials"], job["settings"]["trials"])
        db.apply_deep_result(conn, job["decision_id"], job, result["decision"], result["seconds"])
        db.finish_deep_job(conn, job["id"], "done", seconds=round(time.time() - started, 2))
    except Cancelled:
        db.finish_deep_job(conn, job["id"], "cancelled", seconds=round(time.time() - started, 2))
    except (EngineError, OSError, ValueError, KeyError) as exc:
        db.finish_deep_job(conn, job["id"], "error", error=str(exc), seconds=round(time.time() - started, 2))
    except Exception as exc:
        log.exception("deep analysis crashed")
        db.finish_deep_job(conn, job["id"], "error", error=f"{type(exc).__name__}: {exc}")
    return True


def start_worker(db_path, data_dir, wake):
    def loop():
        conn = db.connect(db_path)
        db.interrupt_deep_jobs(conn)
        while True:
            try:
                while process_next(conn, data_dir):
                    pass
            except Exception:
                log.exception("deep analysis worker error")
            wake.wait(POLL_SECONDS)
            wake.clear()

    thread = threading.Thread(target=loop, name="deep-analysis-worker", daemon=True)
    thread.start()
    return thread

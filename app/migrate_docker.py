"""One-time copy of an existing Docker install's data into the macOS app. The source is only ever read."""
import os
import shutil
import sqlite3
from urllib.parse import quote

from app import db
from app.importer import fill_missing_keys


def _source_db(source):
    return os.path.join(source, "data", "app.db")


def _open_read_only(path):
    return sqlite3.connect(f"file:{quote(path)}?mode=ro", uri=True)


def _has_matches(conn):
    return conn.execute("SELECT EXISTS (SELECT 1 FROM matches)").fetchone()[0] == 1


def available(source, conn):
    if not source or not os.path.exists(_source_db(source)) or _has_matches(conn):
        return False
    src = _open_read_only(_source_db(source))
    try:
        return _has_matches(src)
    except sqlite3.OperationalError:
        return False
    finally:
        src.close()


def import_docker_data(source, conn, data_dir, export_dir):
    if _has_matches(conn):
        raise ValueError("this app already has matches")
    for folder, target in ((os.path.join(source, "data", "uploads"), os.path.join(data_dir, "uploads")),
                           (os.path.join(source, "exports"), export_dir)):
        if os.path.isdir(folder):
            shutil.copytree(folder, target, dirs_exist_ok=True)
    src = _open_read_only(_source_db(source))
    try:
        src.backup(conn)
    finally:
        src.close()
    db.migrate(conn)
    fill_missing_keys(conn, data_dir)
    db.requeue_interrupted(conn)
    return conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

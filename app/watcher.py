import logging
import os
import threading
import time

from app import db
from app.importer import import_match_bytes

log = logging.getLogger(__name__)
SETTLE_SECONDS = 5
MATCH_SUFFIXES = (".mat",)


class FolderAccessError(ValueError):
    pass


def to_container_path(host_path, host_home, host_root):
    if not host_home or not host_root:
        raise FolderAccessError("folder access is not set up; run ./install.sh update")
    host_path = os.path.normpath(host_path or host_home)
    home = os.path.normpath(host_home)
    if host_path != home and not host_path.startswith(home + os.sep):
        raise FolderAccessError(f"only folders inside {home} can be used")
    relative = os.path.relpath(host_path, home)
    container = os.path.normpath(os.path.join(host_root, relative))
    real_root = os.path.realpath(host_root)
    real = os.path.realpath(container)
    if real != real_root and not real.startswith(real_root + os.sep):
        raise FolderAccessError("that folder points outside your home folder")
    return container


def _is_match_file(name):
    return name.lower().endswith(MATCH_SUFFIXES) and not name.startswith(".")


def list_directory(host_path, host_home, host_root):
    container = to_container_path(host_path, host_home, host_root)
    if not os.path.isdir(container):
        raise FolderAccessError(f"{host_path} is not a folder")
    host_path = os.path.normpath(host_path or host_home)
    dirs, matches = [], 0
    try:
        entries = sorted(os.scandir(container), key=lambda e: e.name.lower())
    except PermissionError as exc:
        raise FolderAccessError(f"no permission to read {host_path}") from exc
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": os.path.join(host_path, entry.name)})
            elif entry.is_file() and _is_match_file(entry.name):
                matches += 1
        except OSError:
            continue
    parent = os.path.dirname(host_path) if os.path.normpath(host_path) != os.path.normpath(host_home) else None
    return {"path": host_path, "parent": parent, "dirs": dirs, "match_files": matches}


def _match_files(container_dir, recursive):
    if not recursive:
        for entry in os.scandir(container_dir):
            if entry.is_file() and _is_match_file(entry.name):
                yield entry.path
        return
    for root, dirnames, filenames in os.walk(container_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if _is_match_file(name):
                yield os.path.join(root, name)


def scan_folder(conn, data_dir, folder, host_home, host_root, now=None):
    now = time.time() if now is None else now
    container_dir = to_container_path(folder["path"], host_home, host_root)
    if not os.path.isdir(container_dir):
        raise FolderAccessError(f"{folder['path']} no longer exists")
    results = []
    for container_file in sorted(_match_files(container_dir, folder["recursive"])):
        try:
            stat = os.stat(container_file)
        except OSError:
            continue
        if stat.st_mtime > now - SETTLE_SECONDS:
            continue
        host_file = os.path.join(folder["path"], os.path.relpath(container_file, container_dir))
        seen = conn.execute("SELECT size, mtime FROM folder_files WHERE path = ?", (host_file,)).fetchone()
        if seen and seen["size"] == stat.st_size and seen["mtime"] == stat.st_mtime:
            continue
        with open(container_file, "rb") as f:
            raw = f.read()
        result = import_match_bytes(conn, data_dir, raw, os.path.basename(host_file), source="folder",
                                    source_path=host_file)
        with conn:
            conn.execute(
                """INSERT INTO folder_files (path, size, mtime, match_id, error, seen_at) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(path) DO UPDATE SET size = excluded.size, mtime = excluded.mtime,
                       match_id = excluded.match_id, error = excluded.error, seen_at = excluded.seen_at""",
                (host_file, stat.st_size, stat.st_mtime, result.get("id"), result.get("error"), db.now_local()),
            )
        results.append(result)
    return results


def scan_all(conn, data_dir, host_home, host_root, now=None):
    imported = []
    for folder in conn.execute("SELECT * FROM watched_folders WHERE enabled = 1").fetchall():
        error = None
        try:
            imported += scan_folder(conn, data_dir, folder, host_home, host_root, now)
        except (FolderAccessError, OSError) as exc:
            error = str(exc)
        with conn:
            conn.execute("UPDATE watched_folders SET last_scan_at = ?, last_error = ? WHERE id = ?",
                         (db.now_local(), error, folder["id"]))
    return imported


def start_watcher(db_path, data_dir, host_home, host_root, wake_scan, wake_analysis):
    def loop():
        conn = db.connect(db_path)
        while True:
            try:
                results = scan_all(conn, data_dir, host_home, host_root)
                if any(r.get("id") and not r.get("duplicate") for r in results):
                    wake_analysis.set()
            except Exception:
                log.exception("folder watcher error")
            interval = db.get_settings(conn).get("watch_interval", 30)
            wake_scan.wait(max(5, int(interval)))
            wake_scan.clear()

    thread = threading.Thread(target=loop, name="folder-watcher", daemon=True)
    thread.start()
    return thread

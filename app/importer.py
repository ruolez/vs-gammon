import hashlib
import os

from app import db
from app.matfile import match_fingerprint, parse_mat_header

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def upload_path(data_dir, sha256):
    return os.path.join(data_dir, "uploads", f"{sha256}.mat")


def describe(header):
    header = dict(header)
    length = f"{header['match_length']}-point" if header["match_length"] else "money"
    date = f", {header['event_date']}" if header.get("event_date") else ""
    return f"{header['player1']} vs {header['player2']} ({length}{date})"


def import_match_bytes(conn, data_dir, raw, filename, source="upload", source_path=None):
    origin = source_path or filename
    if len(raw) > MAX_UPLOAD_BYTES:
        db.log_event(conn, "import_failed", f"{origin}: file is larger than 5 MB")
        return {"filename": filename, "error": "file is larger than 5 MB"}
    try:
        header = parse_mat_header(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        db.log_event(conn, "import_failed", f"{origin}: {exc}")
        return {"filename": filename, "error": str(exc)}
    sha = hashlib.sha256(raw).hexdigest()
    content_key = match_fingerprint(raw.decode("utf-8", errors="replace"))
    existing = db.match_by_sha(conn, sha) or db.match_by_content(conn, content_key)
    if existing:
        db.log_event(conn, "duplicate", f"{origin} is already imported as {describe(existing)}", existing["id"])
        return {"filename": filename, "id": existing["id"], "duplicate": True}
    with open(upload_path(data_dir, sha), "wb") as f:
        f.write(raw)
    match_id = db.insert_match(conn, filename, sha, header, source=source, source_path=source_path,
                               content_key=content_key)
    where = f"from {source_path}" if source == "folder" else f"by upload ({filename})"
    db.log_event(conn, "imported", f"Imported {describe(header)} {where}", match_id)
    return {"filename": filename, "id": match_id, "duplicate": False}


def fill_missing_keys(conn, data_dir):
    """Fingerprints for matches imported before duplicates were detected, and position keys for their decisions."""
    rows = conn.execute("SELECT id, sha256 FROM matches WHERE content_key IS NULL").fetchall()
    keys = []
    for row in rows:
        try:
            with open(upload_path(data_dir, row["sha256"]), "rb") as f:
                keys.append((match_fingerprint(f.read().decode("utf-8", errors="replace")), row["id"]))
        except OSError:
            continue
    with conn:
        conn.executemany("UPDATE matches SET content_key = ? WHERE id = ?", keys)
    db.fill_position_keys(conn)


def remove_duplicates(conn, data_dir):
    removed = []
    for duplicate_id, keep_id in db.duplicate_matches(conn).items():
        row = conn.execute("SELECT * FROM matches WHERE id = ?", (duplicate_id,)).fetchone()
        db.fold_duplicate(conn, duplicate_id, keep_id)
        try:
            os.remove(upload_path(data_dir, row["sha256"]))
        except FileNotFoundError:
            pass
        db.log_event(conn, "deleted", f"Removed a duplicate of {describe(row)}", keep_id)
        removed.append(duplicate_id)
    return removed

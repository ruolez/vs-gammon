import hashlib
import os

from app import db
from app.matfile import parse_mat_header

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
    existing = db.match_by_sha(conn, sha)
    if existing:
        db.log_event(conn, "duplicate", f"{origin} is already imported as {describe(header)}", existing["id"])
        return {"filename": filename, "id": existing["id"], "duplicate": True}
    with open(upload_path(data_dir, sha), "wb") as f:
        f.write(raw)
    match_id = db.insert_match(conn, filename, sha, header, source=source, source_path=source_path)
    where = f"from {source_path}" if source == "folder" else f"by upload ({filename})"
    db.log_event(conn, "imported", f"Imported {describe(header)} {where}", match_id)
    return {"filename": filename, "id": match_id, "duplicate": False}

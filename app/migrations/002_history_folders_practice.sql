ALTER TABLE matches ADD COLUMN source TEXT NOT NULL DEFAULT 'upload';
ALTER TABLE matches ADD COLUMN source_path TEXT;

ALTER TABLE decisions ADD COLUMN legal TEXT;
CREATE UNIQUE INDEX decisions_identity ON decisions(match_id, game_no, move_no, kind, player);

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    match_id INTEGER,
    message TEXT NOT NULL
);
CREATE INDEX events_at ON events(id DESC);
CREATE INDEX events_match ON events(match_id);

CREATE TABLE watched_folders (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    recursive INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    added_at TEXT NOT NULL,
    last_scan_at TEXT,
    last_error TEXT
);

CREATE TABLE folder_files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    match_id INTEGER REFERENCES matches(id) ON DELETE SET NULL,
    error TEXT,
    seen_at TEXT NOT NULL
);

CREATE TABLE practice_attempts (
    id INTEGER PRIMARY KEY,
    decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    answer TEXT NOT NULL,
    error REAL,
    correct INTEGER NOT NULL,
    revealed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX practice_decision ON practice_attempts(decision_id, id);

UPDATE matches SET status = 'queued' WHERE status = 'done';

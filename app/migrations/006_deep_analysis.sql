CREATE TABLE deep_jobs (
    id INTEGER PRIMARY KEY,
    decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    settings TEXT NOT NULL,
    moves TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    done INTEGER,
    total INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    seconds REAL
);
CREATE INDEX deep_jobs_decision ON deep_jobs(decision_id, id);
CREATE INDEX deep_jobs_status ON deep_jobs(status);

CREATE TABLE deep_results (
    decision_id INTEGER PRIMARY KEY REFERENCES decisions(id) ON DELETE CASCADE,
    job_id INTEGER,
    mode TEXT NOT NULL,
    settings TEXT NOT NULL,
    result TEXT NOT NULL,
    original TEXT NOT NULL,
    seconds REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE decision_tags (
    decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (decision_id, tag_id)
);

CREATE INDEX decision_tags_tag ON decision_tags(tag_id);

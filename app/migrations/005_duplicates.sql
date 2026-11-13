ALTER TABLE matches ADD COLUMN content_key TEXT;
CREATE INDEX matches_content ON matches(content_key);

ALTER TABLE decisions ADD COLUMN position_key TEXT;
CREATE INDEX decisions_position ON decisions(position_key);

CREATE TABLE position_tags (
    position_key TEXT NOT NULL,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (position_key, tag_id)
);
CREATE INDEX position_tags_tag ON position_tags(tag_id);

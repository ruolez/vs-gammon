CREATE TABLE matches (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    site TEXT,
    external_id TEXT,
    player1 TEXT,
    player2 TEXT,
    elo1 TEXT,
    elo2 TEXT,
    match_length INTEGER,
    event_date TEXT,
    event_time TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    plies INTEGER,
    analysis_seconds REAL,
    created_at TEXT NOT NULL,
    analyzed_at TEXT
);

CREATE TABLE games (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    game_no INTEGER NOT NULL,
    score1 INTEGER NOT NULL,
    score2 INTEGER NOT NULL,
    crawford INTEGER NOT NULL,
    winner INTEGER,
    points INTEGER
);

CREATE TABLE decisions (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    game_no INTEGER NOT NULL,
    move_no INTEGER NOT NULL,
    player INTEGER NOT NULL,
    on_roll INTEGER NOT NULL,
    kind TEXT NOT NULL,
    dice TEXT,
    position_id TEXT,
    xgid TEXT,
    board TEXT NOT NULL,
    cube_value INTEGER NOT NULL,
    cube_owner INTEGER NOT NULL,
    score1 INTEGER NOT NULL,
    score2 INTEGER NOT NULL,
    match_length INTEGER NOT NULL,
    crawford_game INTEGER NOT NULL,
    action TEXT,
    best TEXT,
    error REAL NOT NULL,
    forced INTEGER NOT NULL,
    candidates TEXT,
    played_index INTEGER,
    cube TEXT,
    gnubg_skill TEXT
);

CREATE INDEX decisions_match ON decisions(match_id, game_no, move_no);
CREATE INDEX decisions_error ON decisions(error);
CREATE INDEX games_match ON games(match_id);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE exports (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    decision_count INTEGER NOT NULL,
    filename TEXT NOT NULL
);

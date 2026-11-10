import datetime

from app.position import flip_frame

OPENING_MOVES = 3
HOME = 6
PHASES = ("opening", "middle", "race", "bearoff", "cube")


def game_phase(decision):
    if decision["kind"] != "checker":
        return "cube"
    if decision["move_no"] <= OPENING_MOVES:
        return "opening"
    frame = decision["board"] if decision["on_roll"] == 1 else flip_frame(decision["board"])
    my_back = max(p for p in range(1, 26) if frame[p] > 0)
    opponent_back = min((p for p in range(0, 25) if frame[p] < 0), default=0)
    if my_back <= HOME:
        return "bearoff"
    if my_back < opponent_back or not any(frame[p] < 0 for p in range(25)):
        return "race"
    return "middle"


def streak_days(days, today):
    practiced = set(days)
    day = datetime.date.fromisoformat(today)
    if day.isoformat() not in practiced:
        day -= datetime.timedelta(days=1)
    count = 0
    while day.isoformat() in practiced:
        count += 1
        day -= datetime.timedelta(days=1)
    return count


def _player_number(match, name):
    if match["player1"] == name:
        return 1
    if match["player2"] == name:
        return 2
    return None


def _match_result(conn, match_id, me):
    points = {1: 0, 2: 0}
    for game in conn.execute("SELECT winner, points FROM games WHERE match_id = ?", (match_id,)):
        if game["winner"] in points and game["points"]:
            points[game["winner"]] += game["points"]
    return points[me], points[3 - me]


def build_dashboard(conn, thresholds, player, today, recent=10):
    from app import db
    from app.analysis import classify, summarize

    rows = conn.execute(
        """SELECT * FROM matches WHERE status = 'done' AND (player1 = ? OR player2 = ?)
           ORDER BY COALESCE(event_date, substr(created_at, 1, 10)) DESC, COALESCE(event_time, '') DESC, id DESC""",
        (player, player),
    ).fetchall()
    matches, mistakes = [], []
    phases = {p: {"phase": p, "error": 0.0, "errors": 0, "decisions": 0} for p in PHASES}
    for index, match in enumerate(rows):
        me = _player_number(match, player)
        decisions = db.all_decisions_for_match(conn, match["id"], thresholds)
        mine = [d for d in decisions if d["player"] == me]
        both = summarize(decisions, thresholds)
        summary = both.get(me)
        theirs = both.get(3 - me)
        my_score, their_score = _match_result(conn, match["id"], me)
        errors = [d for d in mine if classify(d["error"], thresholds)]
        matches.append({
            "id": match["id"], "date": match["event_date"] or match["created_at"][:10],
            "opponent": match["player2"] if me == 1 else match["player1"],
            "match_length": match["match_length"], "my_score": my_score, "their_score": their_score,
            "won": bool(match["match_length"]) and my_score >= match["match_length"],
            "lost": bool(match["match_length"]) and their_score >= match["match_length"],
            "pr": summary["pr"] if summary else None,
            "their_pr": theirs["pr"] if theirs else None,
            "errors": len(errors),
            "blunders": sum(1 for d in errors if d["class"] == "very_bad"),
        })
        if index < recent:
            for d in mine:
                if d["kind"] == "checker" and d["forced"]:
                    continue
                bucket = phases[game_phase(d)]
                bucket["decisions"] += 1
                if d["class"]:
                    bucket["errors"] += 1
                    bucket["error"] = round(bucket["error"] + d["error"], 6)
            mistakes += [{**d, "opponent": matches[-1]["opponent"]} for d in errors]
    mistakes.sort(key=lambda d: -d["error"])
    rated = [m["pr"] for m in matches if m["pr"] is not None]
    last10, previous10 = rated[:recent], rated[recent:2 * recent]
    attempt_days = [r["day"] for r in conn.execute(
        """SELECT DISTINCT substr(a.at, 1, 10) AS day FROM practice_attempts a
           JOIN decisions d ON d.id = a.decision_id JOIN matches m ON m.id = d.match_id
           WHERE (d.player = 1 AND m.player1 = ?) OR (d.player = 2 AND m.player2 = ?)""", (player, player))]
    practice = db.practice_stats(conn, player_name=player, min_error=thresholds["doubtful"])
    return {
        "player": player,
        "matches": matches[:30],
        "summary": {
            "matches": len(matches),
            "last_pr": rated[0] if rated else None,
            "avg_pr": round(sum(last10) / len(last10), 2) if last10 else None,
            "prev_avg_pr": round(sum(previous10) / len(previous10), 2) if previous10 else None,
            "errors_per_match": round(sum(m["errors"] for m in matches[:recent]) / min(len(matches), recent), 1) if matches else None,
            "blunders_per_match": round(sum(m["blunders"] for m in matches[:recent]) / min(len(matches), recent), 1) if matches else None,
        },
        "phases": [phases[p] for p in PHASES],
        "mistakes": mistakes[:6],
        "practice": {**practice, "streak": streak_days(attempt_days, today), "due": practice["new"] + practice["missed"]},
    }

SEVERITIES = ("very_bad", "bad", "doubtful")


def checker_error(candidates, played_index):
    best = max(c["equity"] for c in candidates)
    return max(0.0, best - candidates[played_index]["equity"])


def double_error(nd, dt, dp, doubled):
    double_equity = min(dt, dp)
    if doubled:
        return max(0.0, nd - double_equity)
    return max(0.0, double_equity - nd)


def take_error(dt, dp, took):
    if took:
        return max(0.0, dt - dp)
    return max(0.0, dp - dt)


def classify(error, thresholds):
    for severity in SEVERITIES:
        if error >= thresholds[severity] - 1e-12:
            return severity
    return None


CLOSE_CUBE_MARGIN = 0.16
CUBE_ACTIONS_TAKEN = ("Double", "Take", "Pass")


def counts_for_rating(decision):
    if decision["kind"] == "checker":
        return not decision["forced"]
    if decision["action"] in CUBE_ACTIONS_TAKEN or decision["error"] > 0:
        return True
    cube = decision["cube"]
    return min(cube["dt"], cube["dp"]) - cube["nd"] > -CLOSE_CUBE_MARGIN


def summarize(decisions, thresholds):
    summary = {}
    for decision in decisions:
        player = summary.setdefault(decision["player"], {
            "checker": {"decisions": 0, "doubtful": 0, "bad": 0, "very_bad": 0, "error": 0.0},
            "cube": {"decisions": 0, "doubtful": 0, "bad": 0, "very_bad": 0, "error": 0.0},
        })
        if not counts_for_rating(decision):
            continue
        bucket = player["checker" if decision["kind"] == "checker" else "cube"]
        bucket["decisions"] += 1
        bucket["error"] = round(bucket["error"] + decision["error"], 6)
        severity = classify(decision["error"], thresholds)
        if severity:
            bucket[severity] += 1
    for player in summary.values():
        counted = player["checker"]["decisions"] + player["cube"]["decisions"]
        total = player["checker"]["error"] + player["cube"]["error"]
        player["pr"] = round(500 * total / counted, 2) if counted else None
    return summary


def review_state(decisions, thresholds, side, mark):
    mistakes = [d for d in decisions if classify(d["error"], thresholds) and side in (None, d["player"])]
    seen = sum(1 for d in mistakes if d["seen_at"])
    auto = bool(mistakes) and seen == len(mistakes)
    return {"mistakes": len(mistakes), "seen": seen, "auto": auto,
            "reviewed": auto if mark is None else bool(mark), "mark": mark}


def grade_checker(legal, index):
    if not 0 <= index < len(legal):
        raise ValueError("that move is not legal in this position")
    full = [m["equity"] for m in legal if m["full"]] or [m["equity"] for m in legal]
    chosen = legal[index]
    return {"error": max(0.0, max(full) - chosen["equity"]), "approx": not chosen["full"]}


CUBE_ANSWERS = {"cube": ("double", "no_double"), "take": ("take", "pass")}


def grade_cube(kind, cube, action):
    if action not in CUBE_ANSWERS.get(kind, ()):
        raise ValueError(f"'{action}' is not an answer to this cube decision")
    if kind == "cube":
        return double_error(cube["nd"], cube["dt"], cube["dp"], doubled=action == "double")
    return take_error(cube["dt"], cube["dp"], took=action == "take")


def is_correct(error, thresholds):
    return error < thresholds["doubtful"] - 1e-12

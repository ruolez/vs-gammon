"""Settings for analysing one decision more deeply: a deeper evaluation, or a rollout with every gnubg option.
Pure functions: validate what the page sends, turn it into gnubg commands, read gnubg's progress lines."""
import copy

MAX_PLIES = 4
MAX_TRIALS = 1_000_000
MAX_SEED = 2**31 - 1

EVAL_DEFAULTS = {"checker": {"plies": 3, "prune": True}, "cube": {"plies": 3, "prune": True},
                 "moves": {"count": 5, "within": 0.16}}

ROLLOUT_DEFAULTS = {
    "trials": 1296,
    "cubeful": True,
    "variance_reduction": True,
    "quasi_random": True,
    "seed": None,
    "checker": {"plies": 1, "prune": True},
    "cube": {"plies": 1, "prune": True},
    "later": {"enabled": False, "after": 7, "checker": {"plies": 0, "prune": True}, "cube": {"plies": 0, "prune": True}},
    "truncation": {"enabled": False, "after": 11, "checker": {"plies": 1, "prune": True},
                   "cube": {"plies": 1, "prune": True}},
    "bearoff": {"exact": True, "one_sided": True},
    "stop_on_error": {"enabled": False, "min_games": 324, "max_error": 0.005},
    "stop_on_jsd": {"enabled": False, "min_games": 324, "limit": 2.33},
}


def _merge(base, changes):
    merged = copy.deepcopy(base)
    for key, value in (changes or {}).items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge(merged[key], value)
        elif key in merged:
            merged[key] = value
    return merged


ROLLOUT_PRESETS = {
    "quick": _merge(ROLLOUT_DEFAULTS, {"checker": {"plies": 0}, "cube": {"plies": 0}}),
    "standard": copy.deepcopy(ROLLOUT_DEFAULTS),
    "strong": _merge(ROLLOUT_DEFAULTS, {
        "checker": {"plies": 2}, "cube": {"plies": 2},
        "truncation": {"enabled": True, "after": 11, "checker": {"plies": 2}, "cube": {"plies": 2}},
    }),
}


def _int(value, low, high, name):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number") from None
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return number


def _float(value, low, high, name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return number


def _evaluation(value, name):
    return {"plies": _int(value["plies"], 0, MAX_PLIES, f"{name} plies"), "prune": bool(value["prune"])}


def eval_settings(changes):
    merged = _merge(EVAL_DEFAULTS, changes)
    return {"checker": _evaluation(merged["checker"], "checker play"), "cube": _evaluation(merged["cube"], "cube"),
            "moves": {"count": _int(merged["moves"]["count"], 1, 32, "moves"),
                      "within": _float(merged["moves"]["within"], 0.01, 2, "equity window")}}


def rollout_settings(changes):
    s = _merge(ROLLOUT_DEFAULTS, changes)
    seed = s["seed"]
    return {
        "trials": _int(s["trials"], 1, MAX_TRIALS, "games"),
        "cubeful": bool(s["cubeful"]),
        "variance_reduction": bool(s["variance_reduction"]),
        "quasi_random": bool(s["quasi_random"]),
        "seed": None if seed in (None, "") else _int(seed, 0, MAX_SEED, "seed"),
        "checker": _evaluation(s["checker"], "checker play"),
        "cube": _evaluation(s["cube"], "cube"),
        "later": {"enabled": bool(s["later"]["enabled"]), "after": _int(s["later"]["after"], 1, 1000, "later plies"),
                  "checker": _evaluation(s["later"]["checker"], "later checker play"),
                  "cube": _evaluation(s["later"]["cube"], "later cube")},
        "truncation": {"enabled": bool(s["truncation"]["enabled"]),
                       "after": _int(s["truncation"]["after"], 1, 1000, "truncation plies"),
                       "checker": _evaluation(s["truncation"]["checker"], "truncation checker play"),
                       "cube": _evaluation(s["truncation"]["cube"], "truncation cube")},
        "bearoff": {"exact": bool(s["bearoff"]["exact"]), "one_sided": bool(s["bearoff"]["one_sided"])},
        "stop_on_error": {"enabled": bool(s["stop_on_error"]["enabled"]),
                          "min_games": _int(s["stop_on_error"]["min_games"], 1, MAX_TRIALS, "minimum games"),
                          "max_error": _float(s["stop_on_error"]["max_error"], 0.0001, 1, "standard error")},
        "stop_on_jsd": {"enabled": bool(s["stop_on_jsd"]["enabled"]),
                        "min_games": _int(s["stop_on_jsd"]["min_games"], 1, MAX_TRIALS, "minimum games"),
                        "limit": _float(s["stop_on_jsd"]["limit"], 0.01, 100, "JSD limit")},
    }


def _on(flag):
    return "on" if flag else "off"


def _evaluation_commands(prefix, value, cubeful):
    return [f"{prefix} plies {value['plies']}", f"{prefix} prune {_on(value['prune'])}", f"{prefix} cubeful {_on(cubeful)}"]


def _final_filter_level(plies):
    return 0 if plies <= 2 else 2


def evaluation_commands(settings):
    """Deeper evaluation of one decision. The move filter's last stage keeps the chosen number of moves (within an
    equity window) for the full depth; earlier stages keep gnubg's defaults."""
    plies, moves = settings["checker"]["plies"], settings["moves"]
    commands = (_evaluation_commands("set analysis chequerplay evaluation", settings["checker"], True)
                + _evaluation_commands("set analysis cubedecision evaluation", settings["cube"], True))
    if plies >= 1:
        level = _final_filter_level(plies)
        commands.append(f"set analysis movefilter {plies} {level} 0 {moves['count']} {moves['within']}")
        if plies >= 3:
            commands.append(f"set analysis movefilter {plies} 0 0 {max(8, moves['count'])} {max(0.16, moves['within'])}")
        if plies == 4:
            commands.append("set analysis movefilter 4 3 -1 0 0")
    return commands


def rollout_commands(s):
    later, truncation = s["later"], s["truncation"]
    commands = [
        "set rollout players-are-same on",
        "set rollout cube-equal-chequer off",
        "set rollout truncate-equal-player0 on",
        "set rollout initial off",
        f"set rollout trials {s['trials']}",
        f"set rollout cubeful {_on(s['cubeful'])}",
        f"set rollout varredn {_on(s['variance_reduction'])}",
        f"set rollout quasirandom {_on(s['quasi_random'])}",
        *_evaluation_commands("set rollout chequerplay", s["checker"], s["cubeful"]),
        *_evaluation_commands("set rollout cubedecision", s["cube"], s["cubeful"]),
        f"set rollout later enable {_on(later['enabled'])}",
        f"set rollout later plies {later['after']}",
        *_evaluation_commands("set rollout later chequerplay", later["checker"], s["cubeful"]),
        *_evaluation_commands("set rollout later cubedecision", later["cube"], s["cubeful"]),
        f"set rollout truncation enable {_on(truncation['enabled'])}",
        f"set rollout truncation plies {truncation['after']}",
        *_evaluation_commands("set rollout truncation chequerplay", truncation["checker"], s["cubeful"]),
        *_evaluation_commands("set rollout truncation cubedecision", truncation["cube"], s["cubeful"]),
        f"set rollout bearofftruncation exact {_on(s['bearoff']['exact'])}",
        f"set rollout bearofftruncation onesided {_on(s['bearoff']['one_sided'])}",
        f"set rollout limit enable {_on(s['stop_on_error']['enabled'])}",
        f"set rollout limit minimumgames {s['stop_on_error']['min_games']}",
        f"set rollout limit maxerror {s['stop_on_error']['max_error']}",
        f"set rollout jsd stop {_on(s['stop_on_jsd']['enabled'])}",
        f"set rollout jsd minimumgames {s['stop_on_jsd']['min_games']}",
        f"set rollout jsd limit {s['stop_on_jsd']['limit']}",
    ]
    if s["seed"] is not None:
        commands.append(f"set rollout seed {s['seed']}")
    return commands


PROGRESS_MARK = "VSG-PROGRESS"
QUASI_RANDOM_BLOCK = 36


def rollout_steps(trials, steps=10):
    """Totals to roll out in turn, each extending the last, so progress can be reported between them. Kept to
    multiples of 36 games so quasi-random dice stay balanced."""
    if trials <= QUASI_RANDOM_BLOCK:
        return [trials]
    totals = []
    for i in range(1, steps + 1):
        total = min(trials, -(-trials * i // steps // QUASI_RANDOM_BLOCK) * QUASI_RANDOM_BLOCK)
        if not totals or total > totals[-1]:
            totals.append(total)
    if totals[-1] != trials:
        totals.append(trials)
    return totals


def stops_early(settings):
    return settings["stop_on_error"]["enabled"] or settings["stop_on_jsd"]["enabled"]


def progress_line(done, total):
    return f"{PROGRESS_MARK} {done} {total}"


def parse_progress(line):
    parts = line.split()
    if len(parts) == 3 and parts[0] == PROGRESS_MARK and parts[1].isdigit() and parts[2].isdigit():
        return {"done": int(parts[1]), "total": int(parts[2])}
    return None

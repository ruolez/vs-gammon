import functools
import json
import os
import subprocess
import tempfile

GNUBG = os.environ.get("GNUBG_BIN", "/usr/games/gnubg")
DRIVER = os.path.join(os.path.dirname(__file__), "analyse_gnubg.py")
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TIMEOUT = 3600


class EngineError(Exception):
    pass


def gnubg_available():
    return os.path.exists(GNUBG)


@functools.lru_cache(maxsize=1)
def gnubg_version():
    try:
        out = subprocess.run([GNUBG, "--version"], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        return out.stdout.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def run_analysis(mat_path, plies=2, threads=4, timeout=DEFAULT_TIMEOUT):
    with tempfile.TemporaryDirectory(prefix="gnubg-") as work:
        output = os.path.join(work, "result.json")
        env = {
            **os.environ,
            "HOME": work,
            "GA_INPUT": os.path.abspath(mat_path),
            "GA_OUTPUT": output,
            "GA_PLIES": str(plies),
            "GA_THREADS": str(threads),
            "GA_APP_ROOT": APP_ROOT,
        }
        try:
            proc = subprocess.run(
                [GNUBG, "-t", "-q", "-r", "-s", work, "-p", DRIVER],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, env=env, cwd=work,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"analysis timed out after {timeout} s") from exc
        if not os.path.exists(output):
            tail = (proc.stderr or proc.stdout or "")[-2000:]
            raise EngineError(f"gnubg exited with code {proc.returncode} without a result: {tail}")
        with open(output) as f:
            result = json.load(f)
    if "error" in result:
        raise EngineError(result["error"])
    return result

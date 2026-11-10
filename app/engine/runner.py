import functools
import json
import os
import subprocess
import tempfile
import threading

GNUBG = os.environ.get("GNUBG_BIN", "/usr/games/gnubg")
DRIVER = os.path.join(os.path.dirname(__file__), "analyse_gnubg.py")
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TIMEOUT = 3600

_running = set()
_stopping = threading.Event()


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


def engine_command(binary, work, env):
    command = [binary, "-t", "-q", "-r", "-s", work]
    if env.get("GNUBG_DATADIR"):
        command += ["-D", env["GNUBG_DATADIR"]]
    if env.get("GNUBG_PKGDATADIR"):
        command += ["-P", env["GNUBG_PKGDATADIR"]]
    return command + ["-p", DRIVER]


def stop_running():
    _stopping.set()
    for proc in list(_running):
        proc.kill()


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
        proc = subprocess.Popen(
            engine_command(GNUBG, work, env),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=work,
        )
        _running.add(proc)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.communicate()
            raise EngineError(f"analysis timed out after {timeout} s") from exc
        finally:
            _running.discard(proc)
        if _stopping.is_set():
            # The app is quitting: leave the match marked as analysing so it is requeued on next launch.
            threading.Event().wait()
        if not os.path.exists(output):
            tail = (stderr or stdout or "")[-2000:]
            raise EngineError(f"gnubg exited with code {proc.returncode} without a result: {tail}")
        with open(output) as f:
            result = json.load(f)
    if "error" in result:
        raise EngineError(result["error"])
    return result

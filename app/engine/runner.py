import functools
import json
import os
import subprocess
import tempfile
import threading

GNUBG = os.environ.get("GNUBG_BIN", "/usr/games/gnubg")
DRIVER = os.path.join(os.path.dirname(__file__), "analyse_gnubg.py")
DEEP_DRIVER = os.path.join(os.path.dirname(__file__), "deep_gnubg.py")
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TIMEOUT = 3600

_running = set()
_stopping = threading.Event()


class EngineError(Exception):
    pass


class Cancelled(Exception):
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


def engine_command(binary, work, env, driver=DRIVER):
    command = [binary, "-t", "-q", "-r", "-s", work]
    if env.get("GNUBG_DATADIR"):
        command += ["-D", env["GNUBG_DATADIR"]]
    if env.get("GNUBG_PKGDATADIR"):
        command += ["-P", env["GNUBG_PKGDATADIR"]]
    return command + ["-p", driver]


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


def run_deep(mat_path, job, on_line=None, cancelled=lambda: False, timeout=24 * 3600):
    """Runs deep_gnubg.py for one decision. on_line gets each line gnubg prints (rollout progress); cancelled is
    polled and stops gnubg when it returns True."""
    with tempfile.TemporaryDirectory(prefix="gnubg-deep-") as work:
        output = os.path.join(work, "result.json")
        job_path = os.path.join(work, "job.json")
        with open(job_path, "w") as f:
            json.dump({**job, "mat": os.path.abspath(mat_path)}, f)
        env = {**os.environ, "HOME": work, "GA_JOB": job_path, "GA_OUTPUT": output, "GA_APP_ROOT": APP_ROOT}
        proc = subprocess.Popen(
            engine_command(GNUBG, work, env, DEEP_DRIVER),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, cwd=work,
            errors="replace",
        )
        _running.add(proc)
        tail = []

        def read():
            for line in proc.stdout:
                tail.append(line)
                del tail[:-40]
                if on_line:
                    on_line(line)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        waited = 0.0
        try:
            while proc.poll() is None:
                if cancelled():
                    proc.kill()
                    proc.wait()
                    raise Cancelled()
                if waited > timeout:
                    proc.kill()
                    proc.wait()
                    raise EngineError(f"analysis timed out after {timeout} s")
                threading.Event().wait(0.3)
                waited += 0.3
        finally:
            _running.discard(proc)
            reader.join(timeout=5)
        if _stopping.is_set():
            threading.Event().wait()
        if not os.path.exists(output):
            raise EngineError(f"gnubg exited with code {proc.returncode} without a result: {''.join(tail)[-2000:]}")
        with open(output) as f:
            result = json.load(f)
    if "error" in result:
        error = EngineError(result["error"])
        error.trace = result.get("trace")
        raise error
    return result

"""One gnubg process kept running for live analysis (app/engine/live_gnubg.py), fed one transcript at a time."""
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading

from app.engine.runner import APP_ROOT, GNUBG, EngineError, engine_command

DRIVER = os.path.join(APP_ROOT, "app", "engine", "live_gnubg.py")
PREFIX = "VSG-LIVE "


class LiveEngine:
    def __init__(self, binary=None):
        self.binary = binary or GNUBG
        self.proc = None
        self.lines = None
        self.work = None
        self.lock = threading.Lock()

    def _start(self):
        self.work = tempfile.mkdtemp(prefix="gnubg-live-")
        env = {**os.environ, "HOME": self.work, "GA_APP_ROOT": APP_ROOT}
        self.proc = subprocess.Popen(
            engine_command(self.binary, self.work, env, DRIVER), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, env=env, cwd=self.work, bufsize=1, errors="replace",
        )
        self.lines = queue.Queue()
        tail = []

        def read(proc, lines):
            for line in proc.stdout:
                if line.startswith(PREFIX):
                    lines.put(line[len(PREFIX):])
                else:
                    tail.append(line)
                    del tail[:-30]
            lines.put(None)

        self.tail = tail
        threading.Thread(target=read, args=(self.proc, self.lines), daemon=True).start()

    def analyse(self, mat_text, from_record, plies=2, threads=2, timeout=120):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            path = os.path.join(self.work, "live.mat")
            with open(path, "w") as f:
                f.write(mat_text)
            request = {"mat": path, "from_record": from_record, "plies": plies, "threads": threads}
            try:
                self.proc.stdin.write(json.dumps(request) + "\n")
                self.proc.stdin.flush()
                line = self.lines.get(timeout=timeout)
            except (OSError, queue.Empty) as exc:
                self._kill()
                raise EngineError(f"live analysis did not answer: {exc}") from exc
            if line is None:
                tail = "".join(self.tail)[-1500:]
                self._kill()
                raise EngineError(f"gnubg stopped: {tail}")
            result = json.loads(line)
            if "error" in result:
                raise EngineError(result["error"])
            return result

    def _kill(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()
        self.proc = None
        if self.work:
            shutil.rmtree(self.work, ignore_errors=True)
            self.work = None

    def stop(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.stdin.close()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            self._kill()

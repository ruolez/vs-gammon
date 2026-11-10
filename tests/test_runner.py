import os
import stat
import tempfile
import threading
import time
import unittest
from unittest import mock

from app.engine import runner

WORK = "/tmp/work"
DRIVER = runner.DRIVER


class EngineCommand(unittest.TestCase):
    def test_without_data_dirs_is_the_container_command(self):
        self.assertEqual(
            runner.engine_command("/bin/gnubg", WORK, {}),
            ["/bin/gnubg", "-t", "-q", "-r", "-s", WORK, "-p", DRIVER],
        )

    def test_with_data_dirs_points_gnubg_inside_the_bundle(self):
        env = {"GNUBG_DATADIR": "/b/share", "GNUBG_PKGDATADIR": "/b/share/gnubg"}
        self.assertEqual(
            runner.engine_command("/bin/gnubg", WORK, env),
            ["/bin/gnubg", "-t", "-q", "-r", "-s", WORK, "-D", "/b/share", "-P", "/b/share/gnubg", "-p", DRIVER],
        )


class StopRunning(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.addCleanup(runner._stopping.clear)
        self.engine = os.path.join(self.dir.name, "engine")
        with open(self.engine, "w") as f:
            f.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(self.engine, os.stat(self.engine).st_mode | stat.S_IEXEC)

    def test_kills_the_engine_and_never_reports_a_failure(self):
        outcome = []

        def analyse():
            try:
                outcome.append(runner.run_analysis("/tmp/none.mat", timeout=30))
            except Exception as exc:
                outcome.append(exc)

        with mock.patch.object(runner, "GNUBG", self.engine):
            thread = threading.Thread(target=analyse, daemon=True)
            thread.start()
            deadline = time.time() + 5
            while not runner._running and time.time() < deadline:
                time.sleep(0.02)
            child = next(iter(runner._running))
            runner.stop_running()
            child.wait(5)
            thread.join(0.3)
        self.assertEqual((child.returncode, outcome, thread.is_alive()), (-9, [], True))

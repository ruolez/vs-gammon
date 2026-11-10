import io
import os
import threading
import unittest

from app import desktop

HOME = "/Users/someone"
ROOT = "/Applications/VS Gammon.app/Contents/Resources"
SUPPORT = f"{HOME}/Library/Application Support/VS Gammon"


class HostAllowed(unittest.TestCase):
    def test_accepts_loopback_names_with_or_without_port(self):
        hosts = ["127.0.0.1", "127.0.0.1:5565", "localhost", "localhost:5565", "LOCALHOST:5565"]
        self.assertEqual([desktop.host_allowed(h) for h in hosts], [True] * len(hosts))

    def test_rejects_every_other_name(self):
        hosts = ["", "evil.example", "evil.example:5565", "127.0.0.1.evil.example", "localhost.evil.example:5565", "0.0.0.0:5565"]
        self.assertEqual([desktop.host_allowed(h) for h in hosts], [False] * len(hosts))


class GuardHosts(unittest.TestCase):
    def call(self, host):
        status = []

        def inner(environ, start_response):
            start_response("200 OK", [])
            return [b"app"]

        body = desktop.guard_hosts(inner)({"HTTP_HOST": host}, lambda s, h: status.append(s))
        return status[0], b"".join(body)

    def test_passes_loopback_requests_to_the_app(self):
        self.assertEqual(self.call("127.0.0.1:5565"), ("200 OK", b"app"))

    def test_refuses_a_rebound_hostname_without_reaching_the_app(self):
        self.assertEqual(self.call("evil.example:5565"), ("403 Forbidden", b"forbidden host"))


class DesktopEnvironment(unittest.TestCase):
    def test_paths_live_in_application_support_and_the_bundle(self):
        self.assertEqual(
            desktop.desktop_environment(HOME, ROOT),
            {
                "DATA_DIR": f"{SUPPORT}/data",
                "EXPORT_DIR": f"{SUPPORT}/exports",
                "HOST_HOME": HOME,
                "HOST_ROOT": HOME,
                "GNUBG_BIN": f"{ROOT}/engine/bin/gnubg",
                "GNUBG_DATADIR": f"{ROOT}/engine/share",
                "GNUBG_PKGDATADIR": f"{ROOT}/engine/share/gnubg",
                "PYTHONHOME": f"{ROOT}/python",
                "VSG_DOCKER_SOURCE": f"{HOME}/vs-gammon",
            },
        )


class ExitWhenStdinCloses(unittest.TestCase):
    def test_calls_back_once_the_stream_ends(self):
        closed = threading.Event()
        desktop.exit_when_stdin_closes(io.BytesIO(b""), closed.set)
        self.assertTrue(closed.wait(2))

    def test_waits_while_the_stream_stays_open(self):
        read_end, write_end = os.pipe()
        closed = threading.Event()
        with os.fdopen(read_end, "rb") as stream:
            desktop.exit_when_stdin_closes(stream, closed.set)
            self.assertFalse(closed.wait(0.2))
            os.close(write_end)
            self.assertTrue(closed.wait(2))

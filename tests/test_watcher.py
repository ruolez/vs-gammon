import os
import shutil
import tempfile
import time
import unittest

from app import db
from app.watcher import FolderAccessError, list_directory, scan_all, to_container_path

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
HOST_HOME = "/Users/tester"
NOW = 2_000_000_000.0


def write(path, content, mtime=NOW - 60):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    os.utime(path, (mtime, mtime))


def sample():
    with open(os.path.join(FIXTURES, "galaxy_3pt.mat"), "rb") as f:
        return f.read()


class WatcherTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "host")
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(os.path.join(self.data_dir, "uploads"))
        os.makedirs(os.path.join(self.root, "Downloads"))
        self.conn = db.connect(os.path.join(self.data_dir, "app.db"))
        db.migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp)

    def scan(self, now=NOW):
        return scan_all(self.conn, self.data_dir, HOST_HOME, self.root, now=now)

    def matches(self):
        return [(r["source"], r["source_path"]) for r in self.conn.execute("SELECT * FROM matches ORDER BY id")]


class ContainerPaths(WatcherTestCase):
    def test_home_and_subfolders_map_into_the_mount(self):
        self.assertEqual(
            (to_container_path(HOST_HOME, HOST_HOME, self.root),
             to_container_path(f"{HOST_HOME}/Downloads", HOST_HOME, self.root)),
            (self.root, os.path.join(self.root, "Downloads")),
        )

    def test_paths_outside_home_are_refused(self):
        for path in ("/etc", f"{HOST_HOME}/../other", "/Users/testerX"):
            with self.subTest(path), self.assertRaises(FolderAccessError):
                to_container_path(path, HOST_HOME, self.root)

    def test_symlink_escaping_the_mount_is_refused(self):
        os.symlink("/", os.path.join(self.root, "escape"))
        with self.assertRaises(FolderAccessError):
            to_container_path(f"{HOST_HOME}/escape", HOST_HOME, self.root)

    def test_unconfigured_mount(self):
        with self.assertRaises(FolderAccessError):
            to_container_path(HOST_HOME, None, None)


class ListDirectory(WatcherTestCase):
    def test_lists_visible_subfolders_and_counts_match_files(self):
        write(os.path.join(self.root, "Downloads", "a.mat"), b"x")
        write(os.path.join(self.root, "Downloads", "b.MAT"), b"x")
        write(os.path.join(self.root, "Downloads", "notes.txt"), b"x")
        os.makedirs(os.path.join(self.root, "Downloads", "Galaxy"))
        os.makedirs(os.path.join(self.root, "Downloads", ".cache"))
        self.assertEqual(
            list_directory(f"{HOST_HOME}/Downloads", HOST_HOME, self.root),
            {"path": f"{HOST_HOME}/Downloads", "parent": HOST_HOME, "match_files": 2,
             "dirs": [{"name": "Galaxy", "path": f"{HOST_HOME}/Downloads/Galaxy"}]},
        )

    def test_home_has_no_parent(self):
        self.assertIsNone(list_directory(HOST_HOME, HOST_HOME, self.root)["parent"])


class ScanFolders(WatcherTestCase):
    def test_new_match_files_are_imported_once(self):
        db.add_folder(self.conn, f"{HOST_HOME}/Downloads", recursive=False)
        write(os.path.join(self.root, "Downloads", "m1.mat"), sample())
        first = self.scan()
        second = self.scan()
        self.assertEqual(
            ([(r["filename"], r["duplicate"]) for r in first], second, self.matches()),
            ([("m1.mat", False)], [], [("folder", f"{HOST_HOME}/Downloads/m1.mat")]),
        )

    def test_files_still_being_written_wait_for_the_next_scan(self):
        db.add_folder(self.conn, f"{HOST_HOME}/Downloads", recursive=False)
        write(os.path.join(self.root, "Downloads", "fresh.mat"), sample(), mtime=NOW - 1)
        self.assertEqual((self.scan(), len(self.scan(now=NOW + 10))), ([], 1))

    def test_subfolders_only_when_recursive(self):
        write(os.path.join(self.root, "Downloads", "Galaxy", "deep.mat"), sample())
        folder_id = db.add_folder(self.conn, f"{HOST_HOME}/Downloads", recursive=False)
        flat = self.scan()
        db.update_folder(self.conn, folder_id, recursive=True)
        deep = self.scan()
        self.assertEqual((flat, [r["filename"] for r in deep]), ([], ["deep.mat"]))

    def test_same_match_in_two_files_is_a_duplicate(self):
        db.add_folder(self.conn, f"{HOST_HOME}/Downloads", recursive=False)
        write(os.path.join(self.root, "Downloads", "a.mat"), sample())
        write(os.path.join(self.root, "Downloads", "b.mat"), sample())
        self.assertEqual([r["duplicate"] for r in self.scan()], [False, True])

    def test_bad_file_is_recorded_and_not_retried_until_it_changes(self):
        db.add_folder(self.conn, f"{HOST_HOME}/Downloads", recursive=False)
        path = os.path.join(self.root, "Downloads", "broken.mat")
        write(path, b"garbage")
        first = self.scan()
        again = self.scan()
        write(path, sample(), mtime=NOW - 30)
        fixed = self.scan()
        self.assertEqual(
            ([r.get("error") for r in first], again, [r["duplicate"] for r in fixed]),
            (["not a match file: no 'N point match' line"], [], [False]),
        )

    def test_missing_folder_is_reported_on_the_folder(self):
        db.add_folder(self.conn, f"{HOST_HOME}/Gone", recursive=False)
        self.scan()
        self.assertEqual(db.list_folders(self.conn)[0]["last_error"], f"{HOST_HOME}/Gone no longer exists")

    def test_disabled_folder_is_skipped(self):
        folder_id = db.add_folder(self.conn, f"{HOST_HOME}/Downloads", recursive=False)
        db.update_folder(self.conn, folder_id, enabled=False)
        write(os.path.join(self.root, "Downloads", "m1.mat"), sample())
        self.assertEqual(self.scan(), [])

    def test_imports_are_logged_in_history(self):
        db.add_folder(self.conn, f"{HOST_HOME}/Downloads", recursive=False)
        write(os.path.join(self.root, "Downloads", "m1.mat"), sample())
        self.scan()
        self.assertEqual(
            [(e["kind"], e["message"]) for e in db.list_events(self.conn)],
            [("imported", f"Imported chessgamm0n vs fishsoup (3-point, 2026-11-09) from {HOST_HOME}/Downloads/m1.mat")],
        )


if __name__ == "__main__":
    unittest.main()

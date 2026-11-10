import os
import sqlite3
import tempfile
import unittest

from app import db, migrate_docker

SHA = "a" * 64
ZIP_NAME = "positions.zip"
UPLOAD_BYTES = b"3 point match"


def insert_match(conn, status="done"):
    conn.execute(
        "INSERT INTO matches (filename, sha256, source, status, created_at) VALUES ('m.mat', ?, 'upload', ?, '2026-11-09')",
        (SHA, status),
    )
    conn.commit()


class DockerImportCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = os.path.join(tmp.name, "vs-gammon")
        self.data = os.path.join(tmp.name, "support", "data")
        self.exports = os.path.join(tmp.name, "support", "exports")
        os.makedirs(os.path.join(self.source, "data", "uploads"))
        os.makedirs(os.path.join(self.source, "exports"))
        os.makedirs(self.data)
        os.makedirs(self.exports)
        self.source_db = os.path.join(self.source, "data", "app.db")
        self.conn = db.connect(os.path.join(self.data, "app.db"))
        db.migrate(self.conn)
        self.addCleanup(self.conn.close)

    def make_source(self, status="done"):
        conn = db.connect(self.source_db)
        db.migrate(conn)
        insert_match(conn, status)
        conn.close()
        with open(os.path.join(self.source, "data", "uploads", f"{SHA}.mat"), "wb") as f:
            f.write(UPLOAD_BYTES)
        with open(os.path.join(self.source, "exports", ZIP_NAME), "wb") as f:
            f.write(b"zip")

    def import_data(self):
        return migrate_docker.import_docker_data(self.source, self.conn, self.data, self.exports)


class Available(DockerImportCase):
    def test_false_without_a_docker_install(self):
        self.assertEqual(migrate_docker.available(self.source, self.conn), False)

    def test_false_when_the_docker_install_is_empty(self):
        db.migrate(db.connect(self.source_db))
        self.assertEqual(migrate_docker.available(self.source, self.conn), False)

    def test_true_when_docker_has_matches_and_the_app_has_none(self):
        self.make_source()
        self.assertEqual(migrate_docker.available(self.source, self.conn), True)

    def test_false_once_the_app_has_matches(self):
        self.make_source()
        insert_match(self.conn)
        self.assertEqual(migrate_docker.available(self.source, self.conn), False)

    def test_false_when_source_is_not_given(self):
        self.assertEqual(migrate_docker.available(None, self.conn), False)


class ImportDockerData(DockerImportCase):
    def test_brings_over_matches_uploads_and_exports(self):
        self.make_source()
        count = self.import_data()
        with open(os.path.join(self.data, "uploads", f"{SHA}.mat"), "rb") as f:
            upload = f.read()
        rows = [tuple(r) for r in self.conn.execute("SELECT sha256, status FROM matches")]
        self.assertEqual(
            (count, rows, upload, os.path.exists(os.path.join(self.exports, ZIP_NAME))),
            (1, [(SHA, "done")], UPLOAD_BYTES, True),
        )

    def test_leaves_the_docker_data_unchanged(self):
        self.make_source()
        with open(self.source_db, "rb") as f:
            before = f.read()
        self.import_data()
        with open(self.source_db, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_requeues_a_match_that_was_mid_analysis(self):
        self.make_source(status="analyzing")
        self.import_data()
        self.assertEqual(self.conn.execute("SELECT status FROM matches").fetchone()[0], "queued")

    def test_refuses_to_overwrite_existing_matches(self):
        self.make_source()
        insert_match(self.conn)
        with self.assertRaises(ValueError):
            self.import_data()

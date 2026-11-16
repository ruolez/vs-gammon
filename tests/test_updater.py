import base64
import json
import os
import shutil
import tempfile
import unittest

from app import ed25519, updater

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "fixtures")
UPDATE = os.path.join(FIXTURES, "update")
REPO = os.path.dirname(HERE)


def read(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def release(tag, *names, draft=False, prerelease=False):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
            "assets": [{"name": n, "browser_download_url": f"https://example.test/{n}"} for n in names]}


def windows_release(version, arch="arm64", **flags):
    zip_name = f"VS-Gammon-{version}-windows-{arch}.zip"
    return release(f"v{version}-windows", zip_name, zip_name + ".sig", **flags)


class Ed25519(unittest.TestCase):
    def setUp(self):
        self.vectors = json.loads(read(os.path.join(FIXTURES, "ed25519_cryptokit.json"), "r"))
        self.key = base64.b64decode(self.vectors["public_key"])

    def cases(self):
        return [(base64.b64decode(c["message"]), base64.b64decode(c["signature"])) for c in self.vectors["cases"]]

    def test_accepts_signatures_made_by_cryptokit(self):
        self.assertEqual([ed25519.verify(self.key, m, s) for m, s in self.cases()], [True] * len(self.cases()))

    def test_accepts_the_rfc_8032_test_vector(self):
        key = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        signature = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc"
                                  "61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertTrue(ed25519.verify(key, b"", signature))

    def test_rejects_a_changed_message_signature_or_key(self):
        message, signature = self.cases()[2]
        flipped = signature[:40] + bytes([signature[40] ^ 1]) + signature[41:]
        other_key = bytes([self.key[0] ^ 1]) + self.key[1:]
        self.assertEqual([ed25519.verify(self.key, message + b".", signature), ed25519.verify(self.key, message, flipped),
                          ed25519.verify(other_key, message, signature), ed25519.verify(self.key, message, signature[:63])],
                         [False, False, False, False])

    def test_rejects_a_signature_scalar_out_of_range(self):
        message, signature = self.cases()[0]
        s = int.from_bytes(signature[32:], "little") + ed25519.L
        self.assertFalse(ed25519.verify(self.key, message, signature[:32] + s.to_bytes(32, "little")))


class Versions(unittest.TestCase):
    def test_is_newer(self):
        cases = [("1.6.2", "1.6.1", True), ("1.10.0", "1.9.9", True), ("2.0", "1.99.99", True), ("1.6.1", "1.6.1", False),
                 ("1.6.0", "1.6.1", False), ("v1.7.0", "1.6.1", True), ("1.7.0-beta", "1.6.1", False), ("", "1.6.1", False)]
        self.assertEqual([updater.is_newer(a, b) for a, b, _ in cases], [expected for _, _, expected in cases])

    def test_the_built_in_key_is_the_release_key(self):
        self.assertEqual(base64.b64encode(updater.PUBLIC_KEY).decode(),
                         read(os.path.join(REPO, "packaging", "macos", "release-public-key.txt"), "r").strip())


class PickRelease(unittest.TestCase):
    def test_the_newest_signed_windows_release_for_the_arch(self):
        releases = [release("v1.9.0", "VS-Gammon-1.9.0.zip", "VS-Gammon-1.9.0.zip.sig"), windows_release("1.7.0"),
                    windows_release("1.10.0"), windows_release("1.8.0")]
        self.assertEqual(updater.pick_release(releases, "arm64"),
                         {"version": "1.10.0", "zip": "https://example.test/VS-Gammon-1.10.0-windows-arm64.zip",
                          "signature": "https://example.test/VS-Gammon-1.10.0-windows-arm64.zip.sig"})

    def test_skips_drafts_prereleases_unsigned_zips_and_other_arches(self):
        releases = [windows_release("2.0.0", draft=True), windows_release("1.9.0", prerelease=True),
                    release("v1.8.0-windows", "VS-Gammon-1.8.0-windows-arm64.zip"), windows_release("1.7.5", arch="x64"),
                    windows_release("1.7.0")]
        self.assertEqual(updater.pick_release(releases, "arm64")["version"], "1.7.0")

    def test_nothing_suitable(self):
        self.assertIsNone(updater.pick_release([windows_release("1.7.0", arch="x64")], "arm64"))


class WithAppFolder(unittest.TestCase):
    def setUp(self):
        self.parent = tempfile.mkdtemp()
        self.root = os.path.join(self.parent, "VS Gammon")
        os.makedirs(self.root)
        with open(os.path.join(self.root, "build-info.json"), "w") as f:
            json.dump({"version": "1.6.1", "arch": "arm64"}, f)
        self.public_key = base64.b64decode(read(os.path.join(UPDATE, "public-key.txt"), "r").strip())

    def tearDown(self):
        shutil.rmtree(self.parent, ignore_errors=True)

    @staticmethod
    def served(files):
        def get(url):
            if url not in files:
                raise updater.UpdateError("network")
            return files[url]
        return get


class Check(WithAppFolder):
    def test_a_newer_release_is_available(self):
        get = self.served({updater.FEED: json.dumps([windows_release("1.6.0"), windows_release("1.7.0")]).encode()})
        result = updater.check(self.root, get)
        self.assertEqual({k: result[k] for k in ("current", "latest", "available")},
                         {"current": "1.6.1", "latest": "1.7.0", "available": True})

    def test_up_to_date(self):
        get = self.served({updater.FEED: json.dumps([windows_release("1.6.1")]).encode()})
        self.assertEqual(updater.check(self.root, get),
                         {"current": "1.6.1", "latest": "1.6.1", "available": False, "release": None})

    def test_an_unreadable_feed_is_a_network_error(self):
        with self.assertRaises(updater.UpdateError) as caught:
            updater.check(self.root, self.served({updater.FEED: b"<html>rate limited</html>"}))
        self.assertEqual(caught.exception.reason, "network")

    def test_only_an_app_folder_with_build_info_has_updates(self):
        self.assertEqual((updater.build_info(self.root), updater.build_info(self.parent)),
                         ({"version": "1.6.1", "arch": "arm64"}, None))


class Stage(WithAppFolder):
    RELEASE = {"version": "9.9.9", "zip": "z", "signature": "s"}

    def stage(self, name, signature_of=None):
        files = {"z": read(os.path.join(UPDATE, name)), "s": read(os.path.join(UPDATE, (signature_of or name) + ".sig"))}
        return updater.stage(self.RELEASE, self.root, self.served(files), self.public_key)

    def test_a_signed_build_is_unpacked_next_to_the_app_folder(self):
        staged = self.stage("good.zip")
        self.assertEqual((staged, sorted(os.listdir(staged)), os.path.exists(os.path.join(self.root + ".update", "update.zip"))),
                         (os.path.join(self.parent, "VS Gammon.update", "VS Gammon"), ["VS Gammon.exe", "app", "build-info.json"], False))

    def test_a_bad_signature_is_refused_before_anything_is_written(self):
        with self.assertRaises(updater.UpdateError) as caught:
            self.stage("good.zip", signature_of="wrong-version.zip")
        self.assertEqual((caught.exception.reason, os.path.exists(self.root + ".update")), ("signature", False))

    def test_a_build_of_another_version_is_refused_and_removed(self):
        with self.assertRaises(updater.UpdateError) as caught:
            self.stage("wrong-version.zip")
        self.assertEqual((caught.exception.reason, os.path.exists(self.root + ".update")), ("bad", False))

    def test_a_zip_reaching_outside_the_staging_folder_is_refused(self):
        with self.assertRaises(updater.UpdateError) as caught:
            self.stage("slip.zip")
        self.assertEqual((caught.exception.reason, os.path.exists(os.path.join(self.parent, "escaped.txt")),
                          os.path.exists(self.root + ".update")), ("bad", False, False))

    def test_a_staging_folder_left_by_an_earlier_try_is_replaced(self):
        os.makedirs(os.path.join(self.root + ".update", "VS Gammon", "stale"))
        self.assertEqual(sorted(os.listdir(self.stage("good.zip"))), ["VS Gammon.exe", "app", "build-info.json"])


if __name__ == "__main__":
    unittest.main()

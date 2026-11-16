"""Updates for the Windows app (the macOS app updates itself in Swift, packaging/macos/shell/Updater.swift).

The newest GitHub release tagged v<version>-windows that has VS-Gammon-<version>-windows-<arch>.zip and its Ed25519
signature (.zip.sig) is the update. It is downloaded, checked against the release key and unpacked next to the app
folder, as "<app folder>.update/VS Gammon/". The launcher then swaps the folders once the app has quit
(packaging/windows/launcher.c, --apply-update). The app folder carries build-info.json {"version", "arch"}; without
it (Docker, a browser, a source checkout) there are no updates."""
import base64
import json
import os
import shutil
import urllib.request
import zipfile

from app import ed25519

FEED = "https://api.github.com/repos/ruolez/vs-gammon/releases?per_page=30"
PUBLIC_KEY = base64.b64decode("zyqN20IGoA8CUheVN1AKMi+WawNWZEQ3aU0GJU9H1pA=")
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = "VS Gammon.exe"
TIMEOUT = 30


class UpdateError(Exception):
    """reason: "network", "signature", "bad" (the download isn't a VS Gammon build) or "move" (folder not writable)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def parse_version(text):
    parts = str(text).strip().lstrip("v").split(".")
    return tuple(int(p) for p in parts) if parts and all(p.isdigit() for p in parts) else None


def is_newer(candidate, current):
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


def build_info(root=APP_ROOT):
    try:
        with open(os.path.join(root, "build-info.json"), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    return info if parse_version(info.get("version", "")) and info.get("arch") else None


def supported(root=APP_ROOT):
    return os.name == "nt" and build_info(root) is not None


def pick_release(releases, arch):
    """The newest published Windows release with a signed zip for arch: {"version", "zip", "signature"} or None."""
    best = None
    for release in releases:
        tag = release.get("tag_name") or ""
        if release.get("draft") or release.get("prerelease") or not tag.endswith("-windows"):
            continue
        version = tag[:-len("-windows")].lstrip("v")
        if not parse_version(version):
            continue
        assets = {a.get("name"): a.get("browser_download_url") for a in release.get("assets") or []}
        name = f"VS-Gammon-{version}-windows-{arch}.zip"
        if assets.get(name) and assets.get(name + ".sig") and (best is None or is_newer(version, best["version"])):
            best = {"version": version, "zip": assets[name], "signature": assets[name + ".sig"]}
    return best


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "VS-Gammon", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except OSError as exc:
        raise UpdateError("network") from exc


def feed_url():
    return os.environ.get("VSG_UPDATE_FEED") or FEED


def check(root=APP_ROOT, get=fetch):
    info = build_info(root)
    try:
        releases = json.loads(get(feed_url()))
    except ValueError as exc:
        raise UpdateError("network") from exc
    release = pick_release(releases if isinstance(releases, list) else [], info["arch"])
    available = bool(release and is_newer(release["version"], info["version"]))
    return {"current": info["version"], "latest": release["version"] if available else info["version"],
            "available": available, "release": release if available else None}


def staging_dir(root=APP_ROOT):
    return os.path.normpath(root) + ".update"


def unpack(archive, target):
    """Extracts a zip, refusing any member that would land outside target."""
    base = os.path.realpath(target)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            path = os.path.realpath(os.path.join(base, member.filename))
            if os.path.commonpath([base, path]) != base:
                raise UpdateError("bad")
        z.extractall(base)


def stage(release, root=APP_ROOT, get=fetch, public_key=PUBLIC_KEY):
    """Downloads, verifies and unpacks release next to the app folder. Returns the staged app folder."""
    data = get(release["zip"])
    signature = get(release["signature"])
    if not ed25519.verify(public_key, data, signature):
        raise UpdateError("signature")
    target = staging_dir(root)
    try:
        shutil.rmtree(target, ignore_errors=True)
        os.makedirs(target)
        archive = os.path.join(target, "update.zip")
        with open(archive, "wb") as f:
            f.write(data)
    except OSError as exc:
        raise UpdateError("move") from exc
    app = os.path.join(target, "VS Gammon")
    try:
        unpack(archive, target)
        os.remove(archive)
        staged = build_info(app)
        if not os.path.isfile(os.path.join(app, EXE)) or not staged or staged["version"] != release["version"]:
            raise UpdateError("bad")
    except (UpdateError, zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise exc if isinstance(exc, UpdateError) else UpdateError("bad") from exc
    return app

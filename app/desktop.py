"""Entry point of the macOS and Windows apps: serves the web app on loopback only, for as long as the shell lives."""
import ntpath
import os
import sys
import threading

PORT = 5565
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
WEB_THREADS = 8


def host_allowed(host):
    return host.rsplit(":", 1)[0].lower() in ALLOWED_HOSTS


def guard_hosts(wsgi_app):
    def guarded(environ, start_response):
        if host_allowed(environ.get("HTTP_HOST", "")):
            return wsgi_app(environ, start_response)
        start_response("403 Forbidden", [("Content-Type", "text/plain")])
        return [b"forbidden host"]

    return guarded


def desktop_environment(home, root):
    support = os.path.join(home, "Library", "Application Support", "VS Gammon")
    return {
        "DATA_DIR": os.path.join(support, "data"),
        "EXPORT_DIR": os.path.join(support, "exports"),
        "HOST_HOME": home,
        "HOST_ROOT": home,
        "GNUBG_BIN": os.path.join(root, "engine", "bin", "gnubg"),
        "GNUBG_DATADIR": os.path.join(root, "engine", "share"),
        "GNUBG_PKGDATADIR": os.path.join(root, "engine", "share", "gnubg"),
        "PYTHONHOME": os.path.join(root, "python"),
        "VSG_DOCKER_SOURCE": os.path.join(home, "vs-gammon"),
    }


def windows_environment(home, local_app_data, root):
    support = ntpath.join(local_app_data, "VS Gammon")
    return {
        "DATA_DIR": ntpath.join(support, "data"),
        "EXPORT_DIR": ntpath.join(support, "exports"),
        "HOST_HOME": home,
        "HOST_ROOT": home,
        "GNUBG_BIN": ntpath.join(root, "engine", "bin", "gnubg.exe"),
        "GNUBG_DATADIR": ntpath.join(root, "engine", "share"),
        "GNUBG_PKGDATADIR": ntpath.join(root, "engine", "share", "gnubg"),
        "PYTHONHOME": ntpath.join(root, "python"),
    }


def exit_when_stdin_closes(stream, on_close):
    def wait():
        stream.read()
        on_close()

    threading.Thread(target=wait, name="shell-watch", daemon=True).start()


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    home = os.path.expanduser("~")
    if os.name == "nt":
        environment = windows_environment(home, os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), root)
    else:
        environment = desktop_environment(home, root)
    for key, value in environment.items():
        os.environ.setdefault(key, value)

    from waitress import serve

    from app.engine import runner
    from app.main import create_app

    def quit_now():
        runner.stop_running()
        os._exit(0)

    exit_when_stdin_closes(sys.stdin.buffer, quit_now)
    serve(guard_hosts(create_app()), host="127.0.0.1", port=PORT, threads=WEB_THREADS, ident=None)


if __name__ == "__main__":
    main()

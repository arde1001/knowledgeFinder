"""Local web demo of the domain expert, in one shell:

    python -m kf.web --data testdata [--profile low] [--port 8765] [--no-browser] [--no-ollama]

One process does everything: it starts Ollama if nothing answers on its port (a child process, stopped again when this
process ends), serves the page on 127.0.0.1 only, and opens a browser window. Ctrl+C, closing the shell or killing the
process stops the server and the Ollama it started (an Ollama that was already running is left alone).
Test-user login has no password: this is a local demo of the permission model, never a deployment.
"""

import argparse
import atexit
import json
import mimetypes
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urlsplit

import requests

from kf import account, llm, profiles
from kf.expert import Expert, notice
from kf.finder import load_finder

STATIC = Path(__file__).parent / "static"
MAX_SESSIONS = 50
MAX_BODY = 20_000
MAX_QUESTION = 1000


def ollama_up():
    try:
        return requests.get(f"{llm.URL}/api/version", timeout=2).ok
    except requests.RequestException:
        return False


def start_ollama():
    """Return the Ollama child process we started, or None when one was already answering (or cannot be started)."""
    if ollama_up():
        return None
    exe = shutil.which("ollama")
    if not exe:
        print("Ollama is not running and was not found on this machine: install it from https://ollama.com/download", file=sys.stderr)
        return None
    print("Starting Ollama ...", flush=True)
    # the profile's server settings (one request at a time, both models resident, smaller KV cache) apply only to an Ollama we start
    env = {**os.environ, **profiles.current().ollama_env}
    proc = subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    atexit.register(stop, proc)
    for _ in range(60):
        if ollama_up():
            return proc
        time.sleep(0.5)
    print("Ollama did not start within 30 s; answers will fail until it does.", file=sys.stderr)
    return proc


def warm_up(app):
    """Load both models and the keyword index before the first question: a cold start costs 2-20 s on a laptop."""
    with app.lock:
        try:
            app.finder.warm_up()
            app.chat([{"role": "user", "content": "Say OK."}], max_tokens=1)
        except requests.RequestException:
            pass  # the first question reports it


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def missing_models():
    try:
        have = {m["name"] for m in requests.get(f"{llm.URL}/api/tags", timeout=5).json()["models"]}
    except (requests.RequestException, KeyError, ValueError):
        return []
    has = lambda name: name in have or f"{name}:latest" in have
    return [m for m in (llm.CHAT_MODEL, llm.EMBED_MODEL) if not has(m)]


def open_window(url):
    """A browser window without tabs and address bar where Chrome, Edge or Chromium exists (--app), else the default browser."""
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge", "chrome"]
    roots = [os.environ.get(v, "") for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    candidates = [shutil.which(n) for n in names] + [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium"] + [
        os.path.join(r, *p) for r in roots if r for p in (("Google", "Chrome", "Application", "chrome.exe"), ("Microsoft", "Edge", "Application", "msedge.exe"))]
    for exe in candidates:
        if exe and os.path.exists(exe):
            subprocess.Popen([exe, f"--app={url}", "--window-size=1200,820"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    webbrowser.open(url)


class App:
    """Shared state: the finder, one Expert (chat history) per browser session and user, and a lock that serialises model calls."""

    def __init__(self, finder, data, chat=llm.chat):
        self.finder, self.data, self.chat = finder, Path(data), chat
        self.sessions = OrderedDict()
        self.lock = threading.Lock()
        qa = self.data / "qa.jsonl"
        self.questions = [json.loads(l) for l in qa.read_text(encoding="utf-8").splitlines()] if qa.exists() else []

    def users(self):
        p = self.finder.policy
        return [{"id": u, "roles": p.roles_of(u), "drives": [p.drive_name(d) for d in sorted(p.drives_with_access(u))]} for u in p.users()]

    def me(self, user):
        info = account.build(self.finder, user, "")
        return {"user": user, "roles": info.roles, "drives": [{"name": n, "label": l} for _, n, l in info.drives], "shared": info.shared}

    def test_questions(self):
        """One fact question per drive, from the generated ground truth (empty for a fragment of real files)."""
        out, seen = [], set()
        for q in self.questions:
            if q["drive"] not in seen and q["aligned"]:
                seen.add(q["drive"])
                out.append({"question": q["question"], "drive": self.finder.policy.drive_name(q["drive"])})
        return out

    def expert(self, user, sid):
        key = (sid, user)
        if key not in self.sessions:
            self.sessions[key] = Expert(self.finder, chat=self.chat)
            while len(self.sessions) > MAX_SESSIONS:
                self.sessions.popitem(last=False)
        self.sessions.move_to_end(key)
        return self.sessions[key]

    def ask(self, user, sid, question):
        with self.lock:
            r = self.expert(user, sid).ask(user, question)
        return {"answer": r.answer, "query": r.query, "notice": notice(r.denial) if r.denial else None,
                "sources": [{"n": n, "path": path, "drive": drive, "created": created} for n, path, drive, created in r.sources]}

    def reset(self, user, sid):
        with self.lock:
            self.sessions.pop((sid, user), None)


def handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "kf-demo"

        def log_message(self, fmt, *args):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'")
            self.end_headers()
            self.wfile.write(data)

        def host_ok(self):  # DNS-rebinding guard: only requests addressed to this machine's own name are served
            port = self.server.server_port
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.host_ok():
                return self.send(403, {"error": "forbidden"})
            url = urlsplit(self.path)
            path, user = unquote_plus(url.path), parse_qs(url.query).get("user", [""])[0]
            if path == "/api/users":
                return self.send(200, {"users": app.users(), "questions": app.test_questions(), "model": llm.CHAT_MODEL})
            if path == "/api/me":
                if not app.finder.policy.knows(user):
                    return self.send(404, {"error": "unknown user"})
                return self.send(200, app.me(user))
            name = "index.html" if path == "/" else path.lstrip("/")
            file = (STATIC / name).resolve()
            if STATIC.resolve() in file.parents and file.is_file():
                return self.send(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "application/octet-stream"))
            self.send(404, {"error": "not found"})

        def do_POST(self):
            if not self.host_ok() or "application/json" not in self.headers.get("Content-Type", ""):
                return self.send(403, {"error": "forbidden"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self.send(413, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                user, sid = str(body.get("user", "")), str(body.get("session", ""))[:64]
            except (ValueError, AttributeError):
                return self.send(400, {"error": "bad request"})
            if not app.finder.policy.knows(user):
                return self.send(404, {"error": "unknown user"})
            if self.path == "/api/reset":
                app.reset(user, sid)
                return self.send(200, {"ok": True})
            if self.path == "/api/ask":
                question = str(body.get("question", "")).strip()[:MAX_QUESTION]
                if not question:
                    return self.send(400, {"error": "empty question"})
                try:
                    return self.send(200, app.ask(user, sid, question))
                except requests.RequestException:
                    return self.send(503, {"error": "The language model did not answer. Is Ollama running and are the models pulled?"})
            self.send(404, {"error": "not found"})

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Local web demo of the domain expert.")
    ap.add_argument("--data", default="testdata")
    ap.add_argument("--config", help="finder thresholds (default: the profile's)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="only print the address")
    ap.add_argument("--no-ollama", action="store_true", help="do not start Ollama (it must already be running)")
    profiles.add_argument(ap)
    a = ap.parse_args()
    profiles.activate(a.profile)
    data = Path(a.data)
    if not (data / "filemap.json").exists():
        raise SystemExit(f"{data / 'filemap.json'} is missing: run the labeler and the indexer first (see docs/tutorial.md)")
    try:
        finder = load_finder(data, a.config)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))
    try:  # bind first: a busy port should fail before Ollama is started
        app = App(finder, data)
        server = ThreadingHTTPServer(("127.0.0.1", a.port), handler(app))
    except OSError as exc:
        raise SystemExit(f"cannot listen on port {a.port} ({exc.strerror}): is another demo running? Try --port {a.port + 1}")
    for sig in (getattr(signal, n, None) for n in ("SIGTERM", "SIGHUP", "SIGBREAK")):  # the shell closing must end the child too
        if sig:
            signal.signal(sig, lambda *_: sys.exit(0))
    proc = None if a.no_ollama else start_ollama()
    url = f"http://127.0.0.1:{a.port}/"
    gone = missing_models()
    if gone:
        print("Missing models (answers will fail): " + ", ".join(f"ollama pull {m}" for m in gone), file=sys.stderr)
    else:
        threading.Thread(target=warm_up, args=(app,), daemon=True).start()
    print(f"Domain expert demo on {url}  (Ctrl+C to stop)", flush=True)
    if not a.no_browser:
        threading.Timer(0.5, open_window, [url]).start()
    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.server_close()
        if proc:
            stop(proc)


if __name__ == "__main__":
    main()

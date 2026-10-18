import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from test_retriever import env, make  # noqa: F401  (env is a pytest fixture)

from kf.web.server import App, handler


class FakeChat:
    def __init__(self):
        self.calls = 0

    def __call__(self, messages, **kw):
        self.calls += 1
        return "The gala is at Harbour Hall [1]."


@pytest.fixture
def server(env):
    finder, _ = make(env)
    chat = FakeChat()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler(App(finder, env[0], chat=chat)))
    httpd.chat = chat
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def call(server, method, path, body=None, headers=None, host=None):
    port = server.server_port
    conn = http.client.HTTPConnection("127.0.0.1", port)
    h = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    conn.request(method, path, json.dumps(body) if body is not None else None, h)
    r = conn.getresponse()
    data = r.read()
    return r.status, (json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data)


def test_page_and_assets_are_served(server):
    status, page = call(server, "GET", "/")
    assert status == 200 and b"Domain Expert" in page and b"ESTIEM" not in page.upper()
    assert call(server, "GET", "/app.js")[0] == 200 and call(server, "GET", "/fonts/open-sans-latin-wght-normal.woff2")[0] == 200


def test_no_file_outside_the_static_folder_is_served(server):
    for path in ("/../server.py", "/%2e%2e/server.py", "/fonts/../../server.py", "/..%2fserver.py"):
        assert call(server, "GET", path)[0] in (403, 404), path


def test_requests_for_another_host_name_are_refused(server):
    assert call(server, "GET", "/api/users", host="evil.example:80")[0] == 403
    assert call(server, "POST", "/api/ask", {"user": "bob", "question": "x"}, host="evil.example:80")[0] == 403


def test_post_needs_json_content_type(server):
    assert call(server, "POST", "/api/ask", {"user": "bob", "question": "x"}, headers={"Content-Type": "text/plain"})[0] == 403


def test_users_and_account_lists_only_what_that_user_may_open(server):
    status, data = call(server, "GET", "/api/users")
    assert status == 200 and {u["id"] for u in data["users"]} >= {"bob", "dave"}
    status, me = call(server, "GET", "/api/me?user=dave")
    assert status == 200 and [d["name"] for d in me["drives"]] == ["General"]
    assert call(server, "GET", "/api/me?user=nobody")[0] == 404


def test_ask_returns_the_answer_sources_and_no_prompt(server):
    status, r = call(server, "POST", "/api/ask", {"user": "bob", "session": "s1", "question": "gala venue Harbour Hall"})
    assert status == 200 and set(r) == {"answer", "query", "notice", "sources"}
    assert r["sources"][0]["path"] == "events/gala.md"


def test_ask_rejects_unknown_users_and_empty_questions(server):
    assert call(server, "POST", "/api/ask", {"user": "nobody", "question": "x"})[0] == 404
    assert call(server, "POST", "/api/ask", {"user": "bob", "question": "   "})[0] == 400
    assert call(server, "POST", "/api/ask", [1, 2])[0] == 400


def test_each_session_has_its_own_history_and_reset_clears_it(server):
    ask = lambda sid: call(server, "POST", "/api/ask", {"user": "bob", "session": sid, "question": "gala venue Harbour Hall"})
    ask("a")
    assert server.chat.calls == 1  # first question of a session: just the answer
    ask("a")
    assert server.chat.calls == 3  # a follow-up is rewritten first
    ask("b")
    assert server.chat.calls == 4  # another session starts without history
    assert call(server, "POST", "/api/reset", {"user": "bob", "session": "a"})[0] == 200
    ask("a")
    assert server.chat.calls == 5

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest
import requests

from test_retriever import env, make  # noqa: F401  (env is a pytest fixture)

from kf.expert import NOTHING
from kf.web.server import App, handler


class FakeChat:
    def __init__(self):
        self.calls = 0

    def __call__(self, messages, **kw):
        self.calls += 1
        return "The gala is at Harbour Hall [1]."


class FakeStream:
    """Stands in for llm.chat_stream: yields `reply` in small pieces."""

    def __init__(self, reply="The gala is at Harbour Hall [1]."):
        self.reply, self.calls, self.fail = reply, [], False

    def __call__(self, messages, **kw):
        self.calls.append(messages)
        if self.fail:
            raise requests.ConnectionError("down")
        for i in range(0, len(self.reply), 7):
            yield self.reply[i : i + 7]


@pytest.fixture
def server(env):
    finder, _ = make(env)
    chat, stream = FakeChat(), FakeStream()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler(App(finder, env[0], chat=chat, chat_stream=stream)))
    httpd.chat, httpd.stream = chat, stream
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


def stream(server, body):
    """POST /api/ask_stream and return [(event, data)]."""
    port = server.server_port
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("POST", "/api/ask_stream", json.dumps(body), {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    r = conn.getresponse()
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    events = []
    for block in r.read().decode().strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def test_stream_sends_deltas_then_one_final_with_sources(server):
    events = stream(server, {"user": "bob", "session": "s1", "question": "gala venue Harbour Hall"})
    names = [n for n, _ in events]
    assert names[-1] == "final" and names.count("final") == 1 and set(names[:-1]) == {"delta"} and len(names) > 2
    assert "".join(d["text"] for n, d in events if n == "delta") == server.stream.reply
    final = events[-1][1]
    assert set(final) == {"answer", "query", "notice", "sources"} and final["sources"][0]["path"] == "events/gala.md"
    assert server.chat.calls == 0  # the answer call streamed; no second, non-streamed call


def test_stream_not_found_is_replaced_by_the_standard_reply_without_sources(server):
    server.stream.reply = "NOT_FOUND"
    events = stream(server, {"user": "bob", "session": "s1", "question": "gala venue Harbour Hall"})
    assert "".join(d["text"] for n, d in events if n == "delta") == "NOT_FOUND"
    final = events[-1][1]
    assert final["answer"].startswith(NOTHING) and final["sources"] == []


def test_stream_never_carries_prompts_excerpts_or_the_notice_before_the_final_event(server):
    events = stream(server, {"user": "dave", "session": "s1", "question": "hackathon budget board approved"})
    deltas = json.dumps([d for n, d in events if n == "delta"])
    assert all(n == "delta" for n, _ in events[:-1])
    for secret in ("Harbour Hall", "+358", "anna.virtanen", "hackathon budget of 9000", "Drive Board", "you do not have permission"):
        assert secret not in deltas and secret not in json.dumps(events[-1][1].get("sources")), secret
    assert "prompt" not in json.dumps(events) and "Excerpts" not in json.dumps(events)


def test_stream_notice_arrives_only_in_the_final_event(server):
    server.stream.reply = "Nothing to add."
    events = stream(server, {"user": "dave", "session": "s1", "question": "hackathon budget of 9000 euros board approved"})
    assert events[-1][1]["notice"] and all("notice" not in d for n, d in events[:-1])


def test_stream_keeps_the_same_protections_as_ask(server):
    body = {"user": "bob", "question": "x"}
    assert call(server, "POST", "/api/ask_stream", body, host="evil.example:80")[0] == 403
    assert call(server, "POST", "/api/ask_stream", body, headers={"Content-Type": "text/plain"})[0] == 403
    assert call(server, "POST", "/api/ask_stream", {"user": "nobody", "question": "x"})[0] == 404
    assert call(server, "POST", "/api/ask_stream", {"user": "bob", "question": " "})[0] == 400


def test_stream_reports_a_model_failure_as_an_error_event(server):
    server.stream.fail = True
    events = stream(server, {"user": "bob", "session": "s1", "question": "gala venue Harbour Hall"})
    assert [n for n, _ in events] == ["error"] and "language model" in events[0][1]["error"]

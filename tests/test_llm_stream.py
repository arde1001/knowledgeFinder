import json

import pytest
import requests

from kf import llm


class Response:
    def __init__(self, *lines):
        self.lines = [json.dumps(l).encode() if isinstance(l, dict) else l for l in lines]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self.lines)


def test_chat_stream_yields_the_deltas_and_asks_for_a_stream(monkeypatch):
    sent = {}

    def post(url, json=None, **kw):
        sent.update(json, stream=kw.get("stream"))
        return Response({"message": {"content": "Hel"}}, b"", {"message": {"content": "lo"}}, {"message": {"content": ""}, "done": True})

    monkeypatch.setattr(llm.requests, "post", post)
    assert list(llm.chat_stream([{"role": "user", "content": "hi"}], model="m")) == ["Hel", "lo"]
    assert sent["stream"] is True and sent["model"] == "m" and sent["think"] is False and "num_ctx" in sent["options"]


def test_chat_stream_raises_on_an_error_line(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **kw: Response({"message": {"content": "x"}}, {"error": "out of memory"}))
    with pytest.raises(requests.RequestException):
        list(llm.chat_stream([]))

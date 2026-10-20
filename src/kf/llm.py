"""Minimal Ollama client. Models and context size come from the active profile (kf.profiles), so they can be swapped
without code changes."""

import json
import os

import requests

from kf import profiles

URL = os.environ.get("KF_OLLAMA_URL", "http://localhost:11434")


def __getattr__(name):  # llm.CHAT_MODEL / llm.EMBED_MODEL always follow the active profile
    if name == "CHAT_MODEL":
        return profiles.current().chat_model
    if name == "EMBED_MODEL":
        return profiles.current().embed_model
    raise AttributeError(name)


def _chat_request(messages, model, temperature, seed, max_tokens, stream):
    # one num_ctx per process: Ollama reloads the model whenever it changes
    options = {"temperature": temperature, "num_ctx": profiles.current().num_ctx}
    if seed is not None:
        options["seed"] = seed
    if max_tokens:
        options["num_predict"] = max_tokens
    return {"model": model or profiles.current().chat_model, "messages": messages, "stream": stream, "think": False, "options": options}


def chat(messages, model=None, temperature=0.7, seed=None, max_tokens=None, timeout=300):
    """Return the reply text. Thinking is off: these tasks want short direct answers."""
    r = requests.post(f"{URL}/api/chat", json=_chat_request(messages, model, temperature, seed, max_tokens, False), timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def chat_stream(messages, model=None, temperature=0.7, seed=None, max_tokens=None, timeout=300):
    """Yield the reply text piece by piece as Ollama generates it (one JSON object per line)."""
    with requests.post(f"{URL}/api/chat", json=_chat_request(messages, model, temperature, seed, max_tokens, True), timeout=timeout, stream=True) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            part = json.loads(line)
            if "error" in part:  # Ollama reports a failure mid-stream as a line of its own
                raise requests.RequestException(part["error"])
            if text := part.get("message", {}).get("content"):
                yield text
            if part.get("done"):
                break


# (document prefix, query prefix) for embedding models that expect one
PREFIXES = {
    "nomic-embed-text": ("search_document: ", "search_query: "),
    "qwen3-embedding": ("", "Instruct: Given a question, retrieve the passage that answers it\nQuery: "),
    "snowflake-arctic-embed": ("", "Represent this sentence for searching relevant passages: "),
}


def _prefixes(model):
    return PREFIXES.get((model or profiles.current().embed_model).split(":")[0], ("", ""))


def embed(texts, model=None, timeout=300):
    """Return one vector per text, as given (no prefixes)."""
    r = requests.post(f"{URL}/api/embed", json={"model": model or profiles.current().embed_model, "input": list(texts)}, timeout=timeout)
    r.raise_for_status()
    return r.json()["embeddings"]


def embed_documents(texts, model=None, batch=32):
    prefix = _prefixes(model)[0]
    out = []
    for i in range(0, len(texts), batch):
        out += embed([prefix + t for t in texts[i : i + batch]], model)
    return out


def embed_query(text, model=None):
    return embed([_prefixes(model)[1] + text], model)[0]

"""Minimal Ollama client. Models come from the environment so they can be swapped without code changes."""

import os

import requests

URL = os.environ.get("KF_OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.environ.get("KF_CHAT_MODEL", "qwen3:8b")
EMBED_MODEL = os.environ.get("KF_EMBED_MODEL", "nomic-embed-text")


def chat(messages, model=None, temperature=0.7, seed=None, max_tokens=None, timeout=300):
    """Return the reply text. Thinking is off: these tasks want short direct answers."""
    options = {"temperature": temperature, "num_ctx": 8192}
    if seed is not None:
        options["seed"] = seed
    if max_tokens:
        options["num_predict"] = max_tokens
    r = requests.post(
        f"{URL}/api/chat",
        json={"model": model or CHAT_MODEL, "messages": messages, "stream": False, "think": False, "options": options},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# (document prefix, query prefix) for embedding models that expect one
PREFIXES = {
    "nomic-embed-text": ("search_document: ", "search_query: "),
    "qwen3-embedding": ("", "Instruct: Given a question, retrieve the passage that answers it\nQuery: "),
}


def _prefixes(model):
    return PREFIXES.get((model or EMBED_MODEL).split(":")[0], ("", ""))


def embed(texts, model=None, timeout=300):
    """Return one vector per text, as given (no prefixes)."""
    r = requests.post(f"{URL}/api/embed", json={"model": model or EMBED_MODEL, "input": list(texts)}, timeout=timeout)
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

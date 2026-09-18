"""Drive retrieval-agent to ingest manifests via the official qdrant MCP
toolset (qdrant-store), one at a time -- large system prompt + slow CPU
model means batching them into one message blows the 8192-token context,
so each manifest is its own turn. See ADR-0004.
"""

import json
import pathlib
import sys
import time
import uuid

import requests

AGENT_URL = "http://localhost:8180/"
MANIFESTS_DIR = pathlib.Path(__file__).parent / "manifests"


def send(text: str, timeout: int = 300) -> dict:
    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }
    resp = requests.post(AGENT_URL, json=msg, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    files = sorted(MANIFESTS_DIR.glob("*.yaml"))
    for i, path in enumerate(files, 1):
        text = path.read_text(encoding="utf-8")
        kind, name = path.stem.split("-", 1)
        prompt = (
            f"Use qdrant-store (the official qdrant MCP / second toolset) to store "
            f"the following Kubernetes manifest. information = the raw YAML below. "
            f"metadata = {{\"name\": \"{name}\", \"kind\": \"{kind}\", \"namespace\": \"kagent\"}}. "
            f"Do not use vector_store or write-cypher for this. Just call qdrant-store once "
            f"and confirm.\n\n{text}"
        )
        print(f"[{i}/{len(files)}] {path.name} ...", flush=True)
        t0 = time.time()
        try:
            result = send(prompt)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            continue
        dt = time.time() - t0
        try:
            reply_text = result["result"]["status"]["message"]["parts"][0]["text"]
        except Exception:
            reply_text = json.dumps(result)[:300]
        print(f"  ({dt:.1f}s) {reply_text[:200]}", flush=True)


if __name__ == "__main__":
    main()

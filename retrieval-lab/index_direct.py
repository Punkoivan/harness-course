"""Direct (non-agentic) indexing baseline for the retrieval comparison.

Embeds the k8s manifests with sentence-transformers/all-MiniLM-L6-v2
directly -- no agent, no MCP tool call -- and writes straight to Qdrant.
Same model, same source manifests, same target Qdrant instance as the
agentic path in index_via_agent.py; only collection name differs, so the
two are comparable on identical inputs. See ADR-0004.

Usage:
    uv run index_direct.py
"""

import hashlib
import pathlib

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

MANIFESTS_DIR = pathlib.Path(__file__).parent / "manifests"
QDRANT_URL = "http://localhost:6333"
COLLECTION = "k8s_manifests_direct"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def stable_id(path: pathlib.Path) -> str:
    return hashlib.sha256(path.name.encode()).hexdigest()[:32]


def main() -> None:
    model = SentenceTransformer(MODEL_NAME)
    client = QdrantClient(url=QDRANT_URL)

    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=model.get_sentence_embedding_dimension(),
                distance=Distance.COSINE,
            ),
        )
        print(f"Created collection '{COLLECTION}'")

    files = sorted(MANIFESTS_DIR.glob("*.yaml"))
    points = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        vector = model.encode(text).tolist()
        kind, name = path.stem.split("-", 1)
        points.append(
            PointStruct(
                id=stable_id(path),
                vector=vector,
                payload={"name": name, "kind": kind, "text": text},
            )
        )
        print(f"embedded: {path.name}")

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"\nIndexed {len(points)} manifests into '{COLLECTION}' (direct)")


if __name__ == "__main__":
    main()

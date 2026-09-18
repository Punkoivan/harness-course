"""Compare direct vs agentic indexing: same manifests, same embedding
model (all-MiniLM-L6-v2), same queries, two different collections
(k8s_manifests_direct vs k8s_manifests_mcp). See ADR-0004 "Results".

Usage:
    uv run compare.py
"""

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

QDRANT_URL = "http://localhost:6333"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# The official mcp-server-qdrant (FastEmbed) creates a *named* vector,
# keyed by its own model-id convention -- not the anonymous default vector
# our own index_direct.py collection uses. Found via GET
# /collections/k8s_manifests_mcp: {"vectors": {"fast-all-minilm-l6-v2": ...}}
MCP_VECTOR_NAME = "fast-all-minilm-l6-v2"

QUERIES = [
    "which agent talks to a graph database",
    "model configuration for a local llama.cpp server",
    "remote MCP server using SSE transport",
    "agent that manages Grafana dashboards",
    "which object has qdrant-store and qdrant-find tools",
]


def main() -> None:
    model = SentenceTransformer(MODEL_NAME)
    client = QdrantClient(url=QDRANT_URL)

    for collection in ["k8s_manifests_direct", "k8s_manifests_mcp"]:
        print(f"\n{'=' * 60}\n{collection}\n{'=' * 60}")
        if not client.collection_exists(collection):
            print("  (collection does not exist)")
            continue
        count = client.count(collection).count
        print(f"  points: {count}")
        for q in QUERIES:
            vector = model.encode(q).tolist()
            using = MCP_VECTOR_NAME if collection == "k8s_manifests_mcp" else None
            results = client.query_points(
                collection_name=collection,
                query=vector,
                using=using,
                limit=3,
                with_payload=True,
            ).points
            print(f"\n  Q: {q}")
            for r in results:
                payload = r.payload or {}
                # our own collection: {"name", "kind", "text"}.
                # official server's: {"document", "metadata": {"name", ...} | None}.
                name = payload.get("name")
                if name is None:
                    meta = payload.get("metadata") or {}
                    name = meta.get("name") or (payload.get("document", "")[:60] + "...")
                print(f"    {r.score:.3f}  {name}")


if __name__ == "__main__":
    main()

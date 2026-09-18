# retrieval-lab

Course task 6-8 (see [ADR-0004](../docs/adr/0004-official-qdrant-mcp.md)):
compare direct indexing against agentic indexing (via `retrieval-agent`
and the official qdrant MCP), same manifests, same embedding model
(`sentence-transformers/all-MiniLM-L6-v2`).

```bash
uv sync
# Qdrant reachable at localhost:6333 (port-forward into abox's qdrant.qdrant)
# retrieval-agent reachable at localhost:8180 (port-forward into kagent/retrieval-agent svc:8080)

uv run index_direct.py       # -> k8s_manifests_direct
uv run ingest_via_agent.py   # -> k8s_manifests_mcp, via the agent
uv run compare.py            # side-by-side retrieval quality
```

`manifests/` is a snapshot of this cluster's own kagent custom resources
(`Agent`/`ModelConfig`/`MCPServer`/`RemoteMCPServer`) — the same objects
`retrieval-agent`'s own system prompt treats as canonical ingest targets.

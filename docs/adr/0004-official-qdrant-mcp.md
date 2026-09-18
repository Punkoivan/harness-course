# ADR-0004: Official qdrant MCP server, as a second toolset alongside the custom one

- **Status**: accepted, implemented 2026-09-18/19
- **Date**: 2026-09-19

## Context

Course tasks 4-8: add the official `qdrant/mcp-server-qdrant` MCP server's
tools, wire it into `retrieval-agent`'s system prompt, then use it to
compare **agentic retrieval** (the agent deciding how to call
store/find tools) against **direct indexing** (a script computing
embeddings and writing to Qdrant itself) on the same data, on the same
embedding model — isolating the "agent in the loop or not" variable,
which is what task 8 actually asks to evaluate.

The cluster already runs a **custom** Go qdrant-mcp server
(`ghcr.io/den-vasyliev/abox/qdrant-mcp`, tools `vector_store`/
`vector_find`, embeds via the in-cluster `llama-cpp-embeddings` route,
`nomic-embed-text-v1.5`). This ADR adds the **official** one alongside
it, not in place of it — both stay available so `retrieval-agent` can be
told which to use per exercise.

## Decision

**Image**: no official prebuilt image exists on Docker Hub or GHCR for
`qdrant/mcp-server-qdrant` (checked both directly). Built it from the
project's own, actual `Dockerfile` — `git clone` +
`docker build`, unmodified — rather than writing a from-scratch
`pip install mcp-server-qdrant` wrapper (which is what was tried first;
see log entry below for why that got redone). The real Dockerfile
already defaults `EMBEDDING_MODEL` to
`sentence-transformers/all-MiniLM-L6-v2`, exactly what task 6 asks for —
no override needed.

**Deployment shape**: plain `Deployment` + `Service` (`kubectl apply`,
same as ADR-0003's chat model — not through `releases/` + Flux, same
reasoning), registered as a **`RemoteMCPServer`**, not kagent's own
`MCPServer` CRD. The custom qdrant-mcp uses `MCPServer` because it's a
stdio process kagent wraps and manages itself; the official image runs
its **own** SSE HTTP server (`CMD uvx mcp-server-qdrant --transport sse`,
port 8000) — it's already a remote server from kagent's point of view,
so `RemoteMCPServer` (`protocol: SSE`, pointed at the Service's `/sse`
path) is the correct fit, matching how `kagent-tool-server` and
`kagent-grafana-mcp` are already registered in this cluster.

**Qdrant target**: the same in-cluster `qdrant.qdrant:6333` the custom
server uses, but a **separate collection**, `k8s_manifests_mcp` — keeps
the official server's `all-MiniLM-L6-v2` vectors from ever mixing with
the custom server's `nomic-embed-text-v1.5` ones in the same collection
(different, incompatible vector spaces).

**System prompt**: added a "Second toolset" section to `retrieval-agent`
rather than replacing the existing vector-store instructions. States the
official tools' names, their collection, their embedding model, and — the
important part — that they're used **only when explicitly asked for**
("the official qdrant MCP" / "the second toolset"), so the existing
graph-RAG ingest/retrieve behavior (well-specified already, see the rest
of the prompt) doesn't silently change for every other question.

## What actually broke (worth keeping)

First pass built a from-scratch image (`pip install mcp-server-qdrant`
on plain `python:3.12-slim`) instead of checking whether the project
ships its own Dockerfile — it does, at the repo root, and it's more
correct than an improvised one (pinned deps via `uv`, exact `CMD` for
SSE transport, documented env var defaults). Caught by the user pointing
directly at the README's "Using Docker" section. Rebuilt from the actual
source. Lesson, stated plainly: for "official X," check upstream's own
packaging story before writing one — the answer is usually already there.

## Alternatives considered

- **Replace the custom qdrant-mcp tools instead of adding alongside** —
  would make step 8's comparison impossible; the whole point is having
  both toolsets live at once so the agent (and the prompt) can be told
  which one a given exercise means.
- **kagent's `MCPServer` CRD instead of `RemoteMCPServer`** — would work
  only if the official image ran as a stdio process; it doesn't, it's an
  HTTP/SSE server by design. Forcing it through `MCPServer`'s stdio
  wrapping would fight the image rather than use it as built.

## Results (task 8 — added after steps 6-7)

See the ingest/comparison run below once complete.

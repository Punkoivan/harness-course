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

## Results (task 8)

**Setup**: 14 manifests (this cluster's own `Agent`/`ModelConfig`/
`MCPServer`/`RemoteMCPServer` custom resources — the same objects
`retrieval-agent`'s own prompt treats as canonical ingest targets),
embedded with the same model both ways
(`sentence-transformers/all-MiniLM-L6-v2`), into two collections:

- `k8s_manifests_direct` — `retrieval-lab/index_direct.py`, a plain script
  calling `sentence-transformers` directly and writing to Qdrant. No
  agent, no LLM, no tool call.
- `k8s_manifests_mcp` — `retrieval-lab/ingest_via_agent.py`, driving
  `retrieval-agent` (Qwen2.5-3B, CPU) via A2A `message/send`, one manifest
  per turn, instructed to call the official server's `qdrant-store` tool.

**Direct indexing: 14/14 succeeded**, correctly, in well under a minute
total (embedding 14 short YAML docs on CPU is fast; no LLM in the loop).

**Agentic indexing: 2/14 completed within a 300s-per-turn budget, and
neither of those 2 was fully correct.** The other 12 were killed by the
client timeout mid-generation and never called the tool at all — llama.cpp
server logs show the model still generating at the 300s mark, past 3500-
7000 tokens of output at ~2.4 tokens/second, for what should be a single
tool call plus a short confirmation. The generation was cleanly cancelled
server-side each time (`W srv stop: cancel task`), not stuck or crashed —
just far too slow and far too verbose for the turn budget.

Of the 2 that did complete:
- `argo-rollouts-conversion-agent`: metadata correct
  (`{"kind": "Agent", "name": "argo-rollouts-conversion-agent",
  "namespace": "kagent"}`), but the stored `document` field is the
  **literal string `"the raw YAML provided"`** — the model referred to
  the content instead of passing it, so nothing about that manifest is
  actually retrievable from what got stored.
- `helm-agent`: `document` correctly holds the full raw YAML, but
  `metadata` is `null` — the second tool argument was dropped.

So across 14 attempts: 0 fully-correct agentic stores, 2 partially-correct,
12 that never completed in a realistic turn.

**Retrieval quality**, 5 representative queries against each collection
(`retrieval-lab/compare.py`, same embedding model both sides, note
`k8s_manifests_mcp` uses a FastEmbed-named vector
`fast-all-minilm-l6-v2`, not the default anonymous one
`index_direct.py`'s collection uses — had to look that up via
`GET /collections/k8s_manifests_mcp` to query it at all):

| Query | Direct (top score, top hit) | Agentic (top score, top hit) |
|---|---|---|
| which agent talks to a graph database | 0.361, `retrieval-agent` (correct — it's the Neo4j agent) | 0.219, helm-agent's raw YAML (wrong) |
| model config for a local llama.cpp server | 0.304, `kagent-grafana-mcp` (topically close) | 0.120, `argo-rollouts-conversion-agent` (wrong) |
| remote MCP server using SSE transport | 0.355, `official-qdrant-mcp` (exactly correct — it IS the SSE server) | 0.096, `argo-rollouts-conversion-agent` (wrong) |
| agent that manages Grafana dashboards | 0.432, `observability-agent` (correct) | 0.211, helm-agent's YAML (wrong) |
| object with qdrant-store/qdrant-find tools | 0.391, `retrieval-agent` (exactly correct) | 0.210, `argo-rollouts-conversion-agent` (wrong) |

Direct indexing's scores (0.2-0.43) and top hits are semantically right
for every query. Agentic indexing's scores are uniformly lower (0.05-0.22,
one query even scored a *negative* -0.100 on its second hit) and every
single top hit is wrong — unsurprising with only 2 points in the
collection, one of which carries no real content at all. This isn't
"agentic retrieval is somewhat worse" — with this model, on this
hardware, under a realistic turn budget, it produced a collection that
cannot answer the questions it was populated to answer.

**Conclusion**: the bottleneck was never the official MCP server, the
tool schema, or the embedding model — all three worked correctly on the
2 turns that finished. It was the **chat model's generation speed and
verbosity** (see ADR-0003: 3B, Q4_K_M, CPU-only, chosen under a ~6.7GB
RAM ceiling) colliding with a per-turn budget realistic for interactive
use. A bigger/faster model, or a task-specific fine-tune, or simply more
patience per turn (uncapped timeout, minutes instead of seconds) would
likely close most of this gap — this result is a statement about *this*
model on *this* hardware under *these* constraints, not a general verdict
on agentic vs. direct indexing.

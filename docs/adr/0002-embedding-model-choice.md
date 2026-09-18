# ADR-0002: Text embedding model — bge-m3, served via llama.cpp

- **Status**: accepted (already implemented — see Consequences)
- **Date**: 2026-09-18

## Context

Course task: choose a text embedding model and a local serving method
(llama.cpp, recommended, or Ollama), and produce a runnable ToDo so the
model is actually callable, not just chosen on paper.

This decision was already made and implemented in practice while building
the `velesha` pet project (semantic search over Obsidian recipes and Home
Assistant history) — this ADR restates that decision for the course
record and adds the llama.cpp-vs-Ollama comparison the task specifically
asks for, which the original `velesha` ADR didn't need to make explicit.

Requirements driving the choice:
- Runs fully locally (no cloud API, no per-call cost, no home/life data
  leaving the machine — same reasoning as ADR-0001's sidecar-over-llm-d
  call: this is laptop-scale, not datacenter-scale).
- Content to embed is mixed-language but **mostly Ukrainian** (recipes,
  notes, HA event descriptions) — rules out English-only models.
- Needs a stable HTTP endpoint other processes can call (ingestion
  scripts, later: agents) — not just a Python-import-time embedding call.

## Decision

**Model**: `bge-m3` (BAAI), GGUF, `Q4_K_M` quantization (~440MB). Multilingual
(100+ languages, handles Ukrainian well), 1024-dim output, up to 8192-token
context — see `velesha` ADR-0002 for the original write-up.

**Serving**: `llama.cpp`'s `llama-server` in `--embedding` mode, over
Ollama. Comparison, since the task asks for one explicitly:

| | llama.cpp (`llama-server`) | Ollama |
|---|---|---|
| Engine | Direct — this *is* the engine | Wraps llama.cpp internally |
| Embedding API | `POST /embedding` | `POST /api/embed` |
| Batch/context control | Direct CLI flags (`-c`, `-b`, `-ub`) — needed here, see gotcha below | Abstracted away, less direct control |
| Extra layer | None | Daemon + its own model-registry/pull mechanism on top of llama.cpp |
| Model source | Any GGUF, from anywhere (HF, local build) | Ollama's own model library/format wrapper, or manual GGUF import (extra steps) |

Chose **llama.cpp directly**: one less moving part (no Ollama daemon to
also keep running/updated), direct control over batch size — which turned
out to matter (see gotcha), and GGUF files from HuggingFace load with zero
conversion. Ollama's model-management convenience (pull-by-name, registry)
isn't worth the indirection for a single pinned model on one machine.

**Known gotcha** (hit for real, see `velesha` ADR-0002): the server's
default `n_ubatch` (512) rejects any input over ~512 tokens with a 500
error — easy to trip on a full recipe or a long HA history batch. Fix:
`-b 8192 -ub 8192` to match context size.

## Alternatives considered

- **Ollama** — see comparison table above; rejected for the extra
  indirection layer with no corresponding benefit at this scale.
- **`nomic-embed-text-v1.5`** — has attractive Matryoshka (truncatable)
  embeddings, but is English-only; ruled out given the Ukrainian-heavy
  corpus. See `velesha` ADR-0002's alternatives section.
- **Cloud embedding API** (OpenAI, Cohere, Voyage) — simplest to start,
  but sends home/life data off-machine per call and adds cost for
  something re-run constantly during development. Flagged in `velesha`
  ADR-0002 as the likely answer *if/when* this needs to scale beyond
  current hardware — not needed now.

## Consequences

- Already implemented in `velesha`: `tools/llama.cpp` (local build) +
  `tools/models/bge-m3-Q4_K_M.gguf`, server started via the command in the
  ToDo below. Both `sources/obsidian/` and `sources/home_assistant/` in
  `velesha` call this same running server at `localhost:8081`.
- One embedding model for the whole project, regardless of source — see
  `velesha` ADR-0004 for why a second (e.g. numeric/time-series) model
  wasn't needed either.
- See `docs/todo/0002-run-embedding-model-locally.md` for the actual
  startup instructions and a verification step confirming the model is
  callable.

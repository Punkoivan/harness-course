# harness-course

Notes, proofs, and everything done during the harness instrumentation course
(memory, Skills, tools, protocols, external interfaces — Agent = Model + Harness).

## Structure

- `notes/` — course notes
- `proofs/` — evidence that a task/lab was completed (recordings, screenshots, logs)
- `docs/adr/` — architecture decisions made during the course
- `docs/todo/` — implementation checklists that follow from an ADR

## Log

- **2026-09-16** — set up `abox` locally (KinD cluster: agentgateway, kagent, Qdrant,
  Arize Phoenix, Flux CD). Recorded proof with VHS: [`proofs/abox-proof.gif`](proofs/abox-proof.gif).
- **2026-09-18** — prototyped a local embeddings + Qdrant search pipeline here
  (llama.cpp + bge-m3, indexed Obsidian recipes). It grew past "course
  exercise" into a real pet project and moved out to its own repo:
  [**velesha**](https://github.com/Punkoivan/velesha) — a personal assistant
  with memory over home/life data (HA, Jellyfin, notes), voice + avatar
  planned. Further work on that idea happens there, with ADRs.
- **2026-09-18** — course task: ADR + ToDo for running a model in `abox` as
  a sidecar vs. via **llm-d**. Researched llm-d's actual requirements
  first: it's a distributed-inference control plane over vLLM, with GPU
  (NVIDIA/AMD-datacenter/TPU) and CPU accelerator paths — the CPU path
  needs 64+ cores and 64GB+ RAM **per replica**, which the entire laptop
  host (16 cores/30GB) doesn't clear, let alone a single pod's share of
  it. Decision: sidecar (llama.cpp) now, llm-d revisited only if/when
  hardware actually clears one of its documented minimums — see
  [ADR-0001](docs/adr/0001-model-serving-sidecar-vs-llmd.md) and the
  [implementation checklist](docs/todo/0001-sidecar-model-serving.md)
  (not yet implemented). Correction 2026-09-18: an earlier pass of this
  ADR cited a stale v0.7 doc snapshot that missed llm-d's CPU support
  entirely — fixed after being challenged on it; the actual per-replica
  CPU floor still rules it out here, but for the right reason now.
  Notable side-finding: llm-d has a documented
  integration with `agentgateway` (already in `abox`) via the Gateway API
  Inference Extension, so that's the on-ramp when it's time to revisit.

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
- **2026-09-18** — course task: ADR + ToDo for the text embedding model
  choice. Already implemented in practice while building `velesha`:
  `bge-m3` (multilingual, handles Ukrainian) served via `llama.cpp`'s
  `llama-server` in `--embedding` mode, chosen over Ollama for one fewer
  moving part and direct batch-size control. See
  [ADR-0002](docs/adr/0002-embedding-model-choice.md) (includes the
  llama.cpp-vs-Ollama comparison table) and the
  [run-it instructions](docs/todo/0002-run-embedding-model-locally.md),
  verified callable (`dim: 1024` on a test query).
- **2026-09-18** — implemented ADR-0001's sidecar plan for real: a
  standalone `Deployment` (`sidecar/`) in `abox` with `bge-m3` served by
  `llama-server` as a second container next to a demo `app` container.
  Built a multi-stage Docker image (llama.cpp CPU build + model baked in,
  ~1GB), loaded into all 3 KinD nodes with `kind load docker-image`, no
  registry needed. First attempt crash-looped —
  `libllama-common.so.0: cannot open shared object file` — because the
  runtime stage only copied `.so`s matching `libggml*`/`libllama*` by
  glob, missing several llama.cpp produces (`libmtmd.so`,
  `libllama-server-impl.so`, etc.); fixed by copying the whole
  `build/bin/*.so*` glob instead of guessing. After the fix: pod `2/2
  Running`, `kubectl exec`'d into the `app` container and called
  `POST localhost:8081/embedding` — got back a real 1024-dim vector,
  confirming the sidecar pattern end-to-end inside the cluster. See
  [ToDo-0001](docs/todo/0001-sidecar-model-serving.md) for the full
  writeup, including what broke.

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
- **2026-09-19** — course tasks 3-8, all in `abox`: local chat model
  (Qwen2.5-3B) wired to `retrieval-agent`/`k8s-agent`
  ([ADR-0003](docs/adr/0003-chat-model-for-kagent-agents.md)); official
  qdrant MCP added as a second toolset
  ([ADR-0004](docs/adr/0004-official-qdrant-mcp.md)); then the actual
  point of task 8 — compared **direct** indexing (a script,
  `sentence-transformers` straight to Qdrant) against **agentic**
  indexing (the same manifests, via `retrieval-agent` calling the
  official MCP's `qdrant-store`). Direct: 14/14 correct. Agentic: 2/14
  completed inside a realistic turn budget, and neither of those 2 was
  fully correct (one stored the literal string `"the raw YAML provided"`
  instead of real content, the other dropped its metadata) — the other 12
  never finished, the 3B CPU model needed thousands of tokens and multiple
  minutes per turn for what should be one tool call. Retrieval quality
  followed directly: direct indexing's top hits were semantically correct
  for all 5 test queries (scores 0.2-0.43); agentic indexing's were wrong
  for all 5 (scores 0.05-0.22, one negative). Full writeup and the actual
  numbers in ADR-0004's Results section.
  
  Also had to redo the deployment approach partway through: patching
  Flux-managed resources with `kubectl` kept getting silently reverted by
  the 2-minute reconciliation loop (traced to `retrieval-agent` losing
  its model-config patch mid-run and reverting live A2A calls to the
  broken default). Fixed properly — pointed this fork's own CI at its own
  `ghcr.io` package (hit and fixed a real bug along the way: `github.com`
  repo paths preserve case, `ghcr.io` requires lowercase, so
  `Punkoivan/abox` broke the OCI push until the workflow lowercased it
  explicitly) and repointed the cluster's `ResourceSetInputProvider` at
  that fork via `oci_registry` in `bootstrap/variables.tf` — instead of
  continuing to fight the upstream-tracking GitOps loop by hand.
- **2026-09-22** — task 1 (own agentic-memory corpus) and task 5 (voice →
  A2A delegation), on `feat/xray-memory`. Built `xray-memory` from private
  source (repo access confirmed) after the public server image turned out
  to be a CGO-disabled build that can only serve pre-built snapshots, never
  build new ones — indexed `velesha` (own repo) with a self-generated age
  key, deployed alongside `den-vasyliev`'s still-undecryptable maps without
  disturbing them. Along the way: fixed a directory-walker gap (vendored
  `tools/llama.cpp` got parsed as 33k extra nodes until stashed aside — no
  `.gitignore` awareness, only a hardcoded skip-list), a hardcoded 30s
  embedding timeout that needed more embedder CPU (Flux reverted the first
  attempt — suspended `releases` again), a port collision with an unrelated
  session's process on the "default" port, and an `RWO`-PVC chicken-and-egg
  (crash-looping pod can't be `kubectl cp`'d into — worked around with a
  disposable `busybox` pod mounting the same claim). See
  [ADR-0005](docs/adr/0005-own-agentic-memory-corpus.md).

  Task 5: `voice-agent/` — push-to-talk client (Google Cloud
  Speech-to-Text → A2A `message/send` → Google Cloud Text-to-Speech) talking
  to a new `voice-router` kagent Agent that has no MCP tools of its own,
  only three other Agents as tools (`k8s-agent`, `retrieval-agent`,
  `xray-agent`) — kagent's Agent-as-tool mechanism *is* A2A delegation, so
  this is real delegation, not a mock of it.
- **2026-09-25** — o11y lab: `abox` from `feat/otel-demo` (OpenTelemetry
  Demo + MLflow/Phoenix), moved from the ThinkPad to the MacBook (arm64).
  Forked to `Punkoivan/abox@feat/otel-demo`; the cluster reconciles from the
  fork's own `ghcr.io/punkoivan/abox/releases-otel-demo` artifact. Getting it
  up took: iptables kube-proxy (rootless Docker in lima), inotify limits,
  multi-arch rebuilds of amd64-only images in fork CI, SOPS for secrets,
  dropping ngrok/triage/xray, and a local Qwen3-4B behind agentgateway-llm
  instead of Gemini. Main findings: on a fresh cluster **every** trace was
  dropped (MLflow 404 on hardcoded experiment ids, Phoenix auth rejecting
  all OTLP) with nothing alerting; a 50% payment failure showed 0 error
  traces (root span is Locust's, never marked error); metrics/logs have no
  backend at all. Task 3: kagent + gateway traces in Phoenix exposed a wrong
  agent answer (tool returned 27 pods, model said 30) and put 92% of a 171s
  turn on one LLM prefill. Full notes: [`o11y-lab/README.md`](o11y-lab/README.md).

# ADR-0003: Local chat model for retrieval-agent and k8s-agent

- **Status**: accepted, implemented 2026-09-18
- **Date**: 2026-09-18

## Context

Course task 3: configure a model for `retrieval-agent` and `k8s-agent`.
Both were already pointed at `default-model-config` (OpenAI `gpt-4.1-mini`),
but its `apiKeySecret` (`kagent-openai`) holds a 14-character placeholder
from the kagent Helm chart's defaults, not a real key — the model was
never actually configured, just referenced.

Checked what's already running in-cluster (`releases/llmd.yaml`,
`releases/llama-cpp-embeddings.yaml`) before adding anything new: both
existing llama.cpp/llm-d routes serve `nomic-embed-text-v1.5` —
**embeddings only**, no chat/completion capability. Nothing chat-capable
existed in the cluster.

## Decision

Add a chat-capable model **using the same in-cluster pattern already
established** for embeddings — llama.cpp, GGUF baked into a Docker image,
no external dependency — rather than introducing a new technology
(Ollama, despite `ModelConfig` having a native `ollama` provider field)
or paying for a real OpenAI key.

Model: **Qwen2.5-3B-Instruct**, GGUF, `Q4_K_M` (~2GB). Sized down from an
initial 7B plan after checking host memory: only ~6.7GB was available
(`free -h`) with the rest legitimately held by the user's desktop
session (Firefox foremost) — not something to fight for a course
exercise. 3B still has working tool-calling (verified below).

Serving: `llama-server --jinja` (the `--jinja` flag matters — without it,
the model's tool-call chat template isn't applied and function calling
silently doesn't work), port 8082, in the existing `llama-cpp` namespace
as a second Deployment (`llama-cpp-chat`) next to `llama-cpp-embeddings`.

Wiring: new `ModelConfig` (`local-chat-model`, provider `OpenAI`,
`openAI.baseUrl: http://llama-cpp-chat.llama-cpp.svc.cluster.local:8082/v1`)
— llama-server doesn't check the API key, but `ModelConfig` requires
`apiKeySecret` to be set regardless, so it points at the same
already-existing `kagent-openai` placeholder (never actually read).
`retrieval-agent` and `k8s-agent` patched (`kubectl patch`) to use it.

**Applied via `kubectl` directly, not through `releases/` + Flux.** The
cluster's `ResourceSetInputProvider` polls
`oci://ghcr.io/den-vasyliev/abox/releases-llmd-embeddings` — the
**upstream** repo's artifact, not this fork's. Getting a change into that
loop properly means overriding `bootstrap/variables.tf`'s
`releases_artifact` to point at this fork, enabling Actions here, tagging
a release, and waiting on the 5-minute `ResourceSetInputProvider` poll.
That's real plumbing, out of scope for a course lab — direct `kubectl`
gets a working cluster state without touching the GitOps loop's declared
inventory (Flux only reconciles/prunes objects it already owns by name;
a new `Deployment`/`Service`/`ModelConfig` it never declared is left
alone).

## Verification

- Chat completion: `POST /v1/chat/completions` from inside the cluster →
  coherent response.
- Tool calling: same endpoint with a `tools` array → correctly returned
  `finish_reason: "tool_calls"` with well-formed JSON arguments
  (`{"city": "Kyiv"}` for a `get_weather(city)` tool).
- Both agents: `READY: True`, `ACCEPTED: True` after the `ModelConfig`
  patch; new pods came up clean; the A2A endpoint on each responds with
  valid JSON-RPC (not a real invocation yet — that comes with the MCP
  tool wiring in the next steps).

## What actually broke (worth keeping)

First image build raced the model download: `docker build` started while
`curl` was still writing the GGUF to disk, and Docker's build-context
tarball snapshot only captured 701MB of what should have been a ~2GB
file. The build **succeeded** (no error — Docker doesn't know the file
was supposed to be bigger), and the resulting container crash-looped with
`tensor 'blk.13.ffn_gate.weight' data is not within the file bounds,
model is corrupted or incomplete` — a misleading error that reads like a
bad download or a corrupt upstream file, not "you built before the copy
finished." Lesson: don't fire `docker build` off a file a background
download task is still writing, even if an early size check looked
plausible — wait for the actual completion signal, then re-verify size on
disk immediately before building.

## Alternatives considered

- **Ollama, native `ModelConfig.spec.ollama` provider** — genuinely
  tempting given first-class support and (reportedly) more battle-tested
  tool-calling. Not chosen for *this* task specifically because it would
  introduce a second serving technology into a cluster that already has a
  working, proven llama.cpp pattern — reusing it was more in the spirit
  of "configure a model," not "evaluate serving stacks" (that was task 1
  / ADR-0001's job, and it went the other way there for different
  reasons). Worth a real side-by-side someday, not folded into this task.
- **7B model** — reverted after checking actual host memory headroom;
  3B was the size that didn't risk OOM-ing the host's normal desktop
  usage.
- **Real OpenAI key** — simplest on paper, but reintroduces the thing the
  whole `abox`/Velesha effort has been moving away from: a cloud
  dependency and per-call cost for something that now runs fully locally.

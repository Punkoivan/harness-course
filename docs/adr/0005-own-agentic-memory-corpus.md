# ADR-0005: Own agentic-memory corpus, built from xray-memory source, own key

- **Status**: accepted, implemented 2026-09-21/22
- **Date**: 2026-09-22

## Context

Course task 1: build your own corpus for agentic memory, hands-on --
"на базі xray, власного рішення або будь-якого існуючого (qdrant/n4j)".

Switched to the `feat/xray-memory` branch of `abox` (this repo's other
half) to try `den-vasyliev/abox`'s `xray-memory` release. Hit a real wall
first: the published server image
(`ghcr.io/den-vasyliev/abox/xray-memory:v1.23.66-61e4eaa`) is a
`CGO_ENABLED=0` build -- `snapshot`/`serve`/`dump <repo>` all refuse with
"this build has no Tree-sitter parser: rebuild with CGO_ENABLED=1" -- and
the shipped maps (`harness.graph.gob.gz`, `xray.graph.gob.gz`) are
age-encrypted for a key we don't have. The public image can only *serve*
pre-built snapshots, never build new ones, and we can't read the existing
ones either. That would have been a dead end, except the user has actual
push access to `den-vasyliev/xray-memory` (private source repo) -- so
this ADR is "build it from source with a key we control," not "work
around a closed system."

## Decision

1. `gh repo clone den-vasyliev/xray-memory` (private, access confirmed),
   `make build` (CGO, needs Go 1.27+ and a C compiler -- both already on
   this machine from earlier llama.cpp builds).
2. Generated our own age identity (`age-keygen`, same tool/pattern as
   `velesha`'s SOPS setup) at `~/.config/xray-memory/snapshot.key` --
   deliberately not den-vasyliev's, so this corpus is ours end to end.
3. Indexed **`velesha`** (our own project, not `abox`/`harness` or
   `xray-memory` itself) via `xray-memory snapshot`, embedding through the
   in-cluster `llama-cpp-embeddings` service (port-forwarded), encrypted
   to our own public key.
4. Deployed the result as a second, independent map next to (not
   replacing) `den-vasyliev`'s encrypted ones on the same PVC: they still
   fail to decrypt and get skipped with a warning, ours loads and serves.
   `xray-agent` (new kagent Agent) + a `RemoteMCPServer` wire it in.

## What actually broke (worth keeping)

- **Third-party code polluting the graph**: `xray-memory`'s directory
  walker (`skipDir()`) only recognizes a hardcoded list
  (`.git, node_modules, vendor, third_party, dist, build, .next, out,
  bin, .venv, __pycache__`) -- no `.gitignore` awareness. `velesha/tools/
  llama.cpp` (a vendored clone, gitignored *in velesha*) doesn't match
  any of those names, so the first snapshot attempt parsed 33,468 nodes
  including 14,642 C++ and 9,244 C nodes that were llama.cpp's own
  source, not ours. Fixed by moving `tools/llama.cpp` and `tools/models`
  out of the tree for the duration of the build (`mv` to `/tmp`, build,
  `mv` back) -- not a flag, there isn't one.
- **30s hard embedding timeout, no override**: `internal/embedder`'s
  HTTP client timeout is hardcoded to 30 seconds, and `EmbedBatch` sends
  every uncached node's text in one request. Embedding 531 nodes on the
  in-cluster embedder's default resources (`requests: 500m`) blew the
  budget every time (`context deadline exceeded`, then `EOF` after a
  resource bump that Flux immediately reverted -- see below). Fixed by
  suspending the `releases` Kustomization (same fix as ADR-0003/0004's
  chat-model saga -- Flux reverts unmanaged resource edits on its 2-minute
  reconcile) and bumping `llama-cpp-embeddings` to `4`/`8` CPU for the
  duration of the build.
- **Port collision with a totally unrelated process**: forwarded the
  embedder to `localhost:8090` on the host, the default `xray-memory`
  expects -- except `velesha`'s own FastAPI dev server (a parallel,
  unrelated session) was already listening there. Fixed by using a
  non-default local port (`18090`) and passing `-embedding-endpoint`
  explicitly; the lesson generalizes past this one tool: never assume a
  "default" local port is free when another long-running session shares
  the host.
- **PVC is `RWO`, can't just `kubectl cp` into a crash-looping pod**: the
  chart's own two maps are undecryptable with our key, so the pod
  crash-loops before it can be `exec`'d into. `kubectl cp` needs a live
  target container, and a `CrashLoopBackOff` pod rarely holds one open
  long enough to connect. Fixed by scaling the Deployment to 0 (releasing
  the `ReadWriteOnce` claim) and running a disposable `busybox` pod that
  mounts the same PVC, copying the snapshot in there instead -- no
  dependency on the real container ever running successfully.

## Alternatives considered

- **Index `abox` (this repo) instead of `velesha`** — also viable (own
  ADRs, own YAML), passed over only because `velesha` has more varied,
  genuinely interesting code (three different ingestion sources) to ask
  real questions about for task 2's evaluation.
- **Qdrant + Neo4j, hand-rolled, skipping `xray-memory` entirely** — the
  fallback plan when it looked like the CGO wall was unbreakable (no repo
  access assumed). Once access turned out to be real, `xray-memory` won:
  purpose-built code-graph tooling (call resolution, blast-radius,
  risk triage) beats reinventing a subset of it on generic Qdrant/Neo4j.

## Consequences

- The corpus (`maps/velesha.graph.gob.gz`) is safe to commit: it's
  age-encrypted, opens only with a key that lives outside this repo.
- `den-vasyliev`'s two original maps stay on the cluster's PVC,
  permanently unreadable without his key — harmless (skipped with a
  warning), not deleted, not worth cleaning up.
- Rebuilding requires repo access to `den-vasyliev/xray-memory` (private)
  — anyone without it is back to the CGO wall this ADR describes hitting
  first. `maps/velesha.graph.gob.gz` itself doesn't require rebuilding to
  use; only to regenerate after `velesha` changes.

## Task 5 note

`voice-agent/` (separate from this corpus work, same session) builds a
push-to-talk voice client that delegates over A2A to a new `voice-router`
kagent Agent, which has no MCP tools of its own -- every "tool" is
`k8s-agent`, `retrieval-agent` or `xray-agent` as an `Agent`-type tool
entry, i.e. kagent's own Agent-as-tool mechanism, which *is* A2A
delegation, not a wrapper around it. See `voice-agent/README.md`.

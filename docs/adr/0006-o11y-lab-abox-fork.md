# ADR-0006: o11y lab on an own `abox` fork — arm64, local LLM, agent traces to Phoenix

- **Status**: accepted, implemented 2026-09-25
- **Date**: 2026-09-25

## Context

o11y lab: deploy `abox` from `den-vasyliev/abox@feat/otel-demo`, exercise the
OpenTelemetry Demo from an observability point of view, and (optionally) put
our own agents and kagent into the o11y system. Findings and measurements are
in [`o11y-lab/README.md`](../../o11y-lab/README.md); this records the
decisions behind the setup.

What the branch assumed vs. what was available:

- **Hardware**: the branch targets x86 (Codespaces). This time it ran on the
  MacBook — arm64, with Docker in a lima VM that is **rootless** and was sized
  at 4 CPU / 4GB. Four images the branch pulls exist only as amd64
  (`nomic-embed`, `epp`, `agentregistry-inventory`, `xray-memory`).
- **Credentials**: the branch expects out-of-band Secrets for a Gemini key,
  an ngrok account (`triageagent.ngrok.dev`), a ghcr pull token for private
  `triage-*` packages, and xray-memory's snapshot identity. No Gemini key was
  available; the triage packages returned 403 to this account; the ngrok
  domain belongs to someone else.
- **GitOps shape**: the cluster reconciles from an OCI artifact published by
  CI. On upstream's artifact the only way to change anything is patching
  Flux-managed objects by hand — which ADR-0004 already showed gets reverted
  by the reconcile loop.

## Decision

**1. Fork, and reconcile from the fork's own artifact.**
`Punkoivan/abox@feat/otel-demo`, CI publishes
`oci://ghcr.io/punkoivan/abox/releases-otel-demo`, `bootstrap/variables.tf`
defaults to that registry. Every change is a commit + `v0.12.x` tag; the
cluster holds no hand patches. (Early on, before the fork, the stack was
unblocked with `spec.patches` on the Kustomizations and the ResourceSet's
reconcile disabled — removed when the cluster was rebuilt from the fork.)

**2. arm64: rebuild multi-arch in fork CI, not emulate.**
`nomic-embed` (f16), `epp` v1.5.0 (upstream Dockerfile pins
`ENV GOARCH=amd64`; CI swaps it for `TARGETARCH`), `agentregistry-inventory`
v0.5.18 (ko), all under `ghcr.io/punkoivan/abox`. Packages inherit the public
repo's visibility, so kind nodes pull them anonymously. Plus
`kubeProxyMode: iptables` (rootless Docker denies IPVS) and higher inotify
limits in the VM.

**3. Secrets: SOPS + age, key off-repo.**
`.sops.yaml` encrypts only `data`/`stringData` under `releases/secrets/`;
`scripts/seal-secrets.sh` renders each Secret with `kubectl --dry-run` and
pipes it straight into `sops -e`, so plaintext never lands on disk and
generated values (bearer tokens, the LLM virtual key) are never seen by
anyone. The age identity lives at `~/.config/sops/age/abox.agekey`;
bootstrap copies it into `flux-system/sops-age` and enables decryption on
both Kustomizations.

**4. LLM: local Qwen3-4B-Instruct-2507, behind agentgateway-llm.**
Stock multi-arch `llama.cpp` server, weights as a separate `FROM scratch`
image mounted as an image volume (`images/qwen3-4b`). kagent's
`default-model-config` points at `agentgateway-llm` with a `kagent` virtual
key, and the gateway forwards to `llama-cpp-chat` — so every agent LLM call
crosses the gateway, gets its guardrails, and is traced there. 4B over
ADR-0003's 3B because the 3B's tool calling was the bottleneck in ADR-0004.
Sized to fit after a first-boot OOMKill: q8_0 KV cache with flash attention,
24k context over 2 slots.

**5. Agent traces go to Phoenix, with Phoenix auth off.**
kagent `otel.tracing` → `phoenix-svc:4317`, next to agentgateway-llm's
existing `frontendPolicies.tracing`. The Phoenix chart enables auth by
default and then rejects every unauthenticated OTLP export (0 spans stored
while both exporters looked configured); ingestion only accepts API keys
minted in the running instance, so there is no declarative credential to
hand the exporters. `auth.enableAuth: false` matches how the branch's
exporters were already written (plaintext, in-cluster).

**6. MLflow experiments created by a Job, not by hand.**
The bridge collector routes by hardcoded experiment id (`2`, `3`); a fresh
MLflow only has `0`, so every export 404'd and was dropped. A Flux-managed
Job creates the experiments by name in a fixed order and fails if an
existing one holds a different id.

**7. Scope: drop what can't run here.**
ngrok-operator (its missing credentials also blocked `releases-crds`' health
check, and with it every app release), triage-core/agent + pages-triage +
graph-otel-demo (private packages), xray-memory (amd64-only server, private
source; already exercised in ADR-0005).

## Alternatives considered

- **Keep patching upstream's artifact in-cluster** — worked to get unblocked,
  but it's exactly the drift ADR-0004 fought; nothing is reproducible from
  git. Rejected once the fork existed.
- **Rosetta in lima for the amd64 images** — one VM switch instead of three
  CI builds. Rejected in favour of native images: no emulation in the
  measurements, and the fork's images work on any arm64 host.
- **Plain `kubectl create secret` out of band** (the branch's convention) —
  simpler, but the cluster can't be rebuilt from git alone; with SOPS the
  rebuild on 2026-09-25 needed no manual secret step.
- **Gemini / a hosted model** — no key; also the local model keeps the
  lab's latency numbers comparable with ADR-0003/0005.
- **kagent → llama.cpp directly** — one hop fewer, but the LLM calls would be
  invisible outside kagent's own spans.
- **Phoenix with auth, API key via a bootstrap Job** (log in as admin, mint
  a system key, write it to a Secret) — possible, but imperative and needs
  the default admin password in the loop. Deferred; noted in the manifest.
- **Agent traces to MLflow** instead of Phoenix — the gateway already pointed
  at Phoenix, and MLflow's id-routing was already the fragile part.

## Consequences

- The cluster is reproducible from the fork: `tofu apply` + the age key.
  Verified by deleting and rebuilding it; all 13 HelmReleases went Ready
  with no manual steps beyond the host-side VM tweaks (size, inotify).
- Phoenix accepts and serves traces to anything in the cluster — fine
  behind port-forward, not if it's ever exposed. Traces also carry full
  tool output (O11 in the lab notes), which makes that trade-off heavier.
- The fork diverges from upstream (ngrok/triage/xray removed, Gemini gone).
  Some fixes are upstream-worthy on their own (iptables for rootless,
  lowercase ghcr paths, the MLflow experiments Job, `USER root` in the
  nomic-embed fetch stage) — no PR for now, by choice.
- Every HelmRelease gets `timeout: 15m` and 3 install retries via one
  kustomize patch; first boot on a laptop pulls everything at once and four
  installs missed helm's 5m default.
- Open follow-ups (lab notes, "Next"): one collector in front of Phoenix and
  MLflow for redaction and fan-out; tracing on `kagent-controller`; find out
  why agent and gateway spans don't share a trace.

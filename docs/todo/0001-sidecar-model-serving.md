# ToDo: llama.cpp as a sidecar in `abox`

Follows ADR-0001. **Implemented and verified 2026-09-18** — see
`harness-course/sidecar/` for the Dockerfile and manifest, and the log
entry in the repo root README.

## Steps

- [x] **Build a sidecar image.** Multi-stage `Dockerfile`
      (`sidecar/Dockerfile`): `debian:bookworm-slim` build stage compiles
      llama.cpp (`-DGGML_NATIVE=ON` — fine since KinD nodes are containers
      on the same physical host, not separate hardware), runtime stage
      copies just `llama-server` + its `.so`s + the `bge-m3` GGUF baked
      in directly. No registry needed — loaded straight into KinD with
      `kind load docker-image velesha-embed-sidecar:bge-m3 --name abox`.
      Image size: ~1GB (mostly the 440MB model + llama.cpp shared libs).
- [x] **Pick the target pod.** Standalone `Deployment`
      (`sidecar/deployment.yaml`, `embed-sidecar-demo` in the `default`
      namespace) — not wired into any existing kagent workload or Flux
      release. Scoped as a course exercise, not a production integration.
- [x] **Write the sidecar container spec**: two containers —
      `app` (`busybox:1.36`, `sleep infinity`, stand-in for a real
      caller) and `llama-embed` (the model server, `--host 0.0.0.0` on
      `:8081` — container-internal, never exposed via a Service, reached
      only from `app` over `localhost` inside the shared pod network
      namespace). Resources: `requests: 2 cpu / 2Gi`, `limits: 4 cpu /
      4Gi` on the sidecar — untested under load, but sufficient to load
      `bge-m3` and serve single requests.
- [x] **Readiness/liveness probes** on `llama-embed`: `GET /health` on
      `:8081`, `initialDelaySeconds: 3`, generous `failureThreshold: 20`
      to cover model load time.
- [x] **Model file delivery**: baked into the image (chosen over an
      init-container fetch — simpler, and sidesteps re-testing the
      nested-Docker egress issue from `fix-egress.sh` for a one-off demo).
- [x] **Flux**: explicitly skipped — manual `kubectl apply`, scope
      decision recorded above.
- [x] **Verify**: `kubectl exec` into the `app` container, POST to
      `http://localhost:8081/embedding` — returned a 1024-dim vector,
      confirming the sidecar pattern works end-to-end inside the cluster.

## What actually broke (worth keeping)

First build's runtime image was missing shared libraries: only copied
`libggml*.so`/`libllama*.so` by glob, which missed `libllama-common.so`,
`libllama-server-impl.so`, `libmtmd.so`, etc. — llama.cpp produces far
more `.so` files than the binary's own name suggests (one per CLI tool it
builds, `--target llama-server` still links against all of them). Fix:
copy the whole `build/bin/*.so*` glob instead of guessing which ones
matter. Container was `CrashLoopBackOff` with
`error while loading shared libraries: libllama-common.so.0: cannot open
shared object file` until fixed.

`metrics-server` isn't installed in `abox`, so no hard CPU/RAM numbers
from this run — `kubectl top pod` isn't available. Worth adding if actual
resource tuning is ever needed.

## Explicitly out of scope (per ADR-0001)

- llm-d — no discrete/datacenter accelerator available; revisit only when
  real GPU hardware is in play. Don't attempt a "toy" llm-d install just
  to check the box — it wouldn't demonstrate anything real.

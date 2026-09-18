# ToDo: llama.cpp as a sidecar in `abox`

Follows ADR-0001. Not yet implemented — this is the checklist for doing it.

## Steps

- [ ] **Build a sidecar image.** `llama.cpp` CPU build (matches the
      `abox` nodes' arch) + the `bge-m3` GGUF baked in, or mounted —
      decide based on image size tolerance (baked-in ≈ 450MB+ layer vs.
      a PVC/init-container fetch step). Push to a registry the KinD nodes
      can pull from (local registry, or reuse `ghcr.io/den-vasyliev/abox`
      pattern already used by `releases/`).
- [ ] **Pick the target pod.** Which existing workload gets the sidecar —
      a kagent agent that needs local embeddings, or a standalone
      `Deployment` for the course exercise? Decide before writing the
      manifest; changes the Helm chart / `releases/` structure to touch.
- [ ] **Write the sidecar container spec**: second container in the pod,
      `--host 127.0.0.1` (no need to expose beyond the pod — main
      container talks over `localhost`), resource `requests`/`limits`
      sized for CPU inference on a 2-worker cluster (start conservative,
      e.g. `requests: 2 cpu / 2Gi`, `limits: 4 cpu / 4Gi` — measure and
      adjust).
- [ ] **Readiness probe** on the sidecar (`GET /health`) so the pod isn't
      marked ready before the model finishes loading — llama-server takes
      a couple seconds to load `bge-m3`, longer for bigger models.
- [ ] **Decide model file delivery**: baked into the image (simple,
      reproducible, bigger image) vs. `initContainer` that fetches the
      GGUF into an `emptyDir`/PVC (smaller image, extra moving part, needs
      egress to wherever the model is hosted — check this doesn't hit the
      same nested-Docker egress issue `abox`'s `fix-egress.sh` works
      around, see `harness-course` proof from 2026-09-16).
- [ ] **Wire up Flux** if this should be GitOps-managed like the rest of
      `abox` (`releases/`), or keep it a manual `kubectl apply` for the
      course exercise — decide scope before building.
- [ ] **Verify**: exec into the main container, curl the sidecar's
      `/embedding` over `localhost`, confirm it responds — same smoke test
      already used for Velesha's host-level `llama-server`.
- [ ] Log the outcome (worked / didn't / resource numbers observed) in
      `harness-course/README.md`'s Log section.

## Explicitly out of scope (per ADR-0001)

- llm-d — no discrete/datacenter accelerator available; revisit only when
  real GPU hardware is in play. Don't attempt a "toy" llm-d install just
  to check the box — it wouldn't demonstrate anything real.

# harness-course

Notes, proofs, and everything done during the harness instrumentation course
(memory, Skills, tools, protocols, external interfaces — Agent = Model + Harness).

## Structure

- `notes/` — course notes
- `proofs/` — evidence that a task/lab was completed (recordings, screenshots, logs)

## Log

- **2026-09-16** — set up `abox` locally (KinD cluster: agentgateway, kagent, Qdrant,
  Arize Phoenix, Flux CD). Recorded proof with VHS: [`proofs/abox-proof.gif`](proofs/abox-proof.gif).
- **2026-09-18** — prototyped a local embeddings + Qdrant search pipeline here
  (llama.cpp + bge-m3, indexed Obsidian recipes). It grew past "course
  exercise" into a real pet project and moved out to its own repo:
  [**velesha**](https://github.com/Punkoivan/velesha) — a personal assistant
  with memory over home/life data (HA, Jellyfin, notes), voice + avatar
  planned. Further work on that idea happens there, with ADRs.

# harness-course

Notes, proofs, and everything done during the harness instrumentation course
(memory, Skills, tools, protocols, external interfaces — Agent = Model + Harness).

## Structure

- `notes/` — course notes
- `proofs/` — evidence that a task/lab was completed (recordings, screenshots, logs)
- `tools/llama.cpp/` — local build of llama.cpp (gitignored, not committed)
- `tools/models/` — GGUF models (gitignored, not committed)
- `indexer/` — personal semantic search project: index HA history, Jellyfin
  library, and Obsidian recipes into Qdrant

## Personal semantic index

Pipeline: local `llama-server` (embedding mode, `bge-m3`, multilingual) → Qdrant → search script.

Sources (in progress):
- [x] Obsidian recipes (`Домашнє/рецепти/`) — collection `obsidian_recipes`
- [ ] Home Assistant history
- [ ] Jellyfin library (watch stats)

### Running it

```bash
# 1. Start the embedding server
cd tools/llama.cpp
./build/bin/llama-server -m ../models/bge-m3-Q4_K_M.gguf --embedding --pooling cls \
  -c 8192 -b 8192 -ub 8192 --port 8081 --host 127.0.0.1

# 2. Qdrant must be reachable at localhost:6333 (port-forward to the abox cluster)

# 3. Index / search
cd indexer
uv run index_recipes.py
uv run search_recipes.py "щось із куркою на вечерю"
```

## Log

- **2026-09-16** — set up `abox` locally (KinD cluster: agentgateway, kagent, Qdrant,
  Arize Phoenix, Flux CD). Recorded proof with VHS: [`proofs/abox-proof.gif`](proofs/abox-proof.gif).
- **2026-09-18** — built `llama.cpp` locally, indexed 33 Obsidian recipes into Qdrant
  (`obsidian_recipes` collection) using `bge-m3` embeddings. Semantic search verified
  working end-to-end. Next: Home Assistant history, Jellyfin library.

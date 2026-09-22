# xray-memory-own

Course task 1 (build your own agentic-memory corpus). Uses `xray-memory`
(den-vasyliev/xray-memory, private -- not vendored here, see `.gitignore`)
built from source against a self-generated age key, indexing the `velesha`
repo (our own project, not den-vasyliev's harness/xray maps).

- `maps/velesha.graph.gob.gz` — the encrypted snapshot (531 nodes, 2294
  edges), safe to commit: age-encrypted, only openable with the key at
  `~/.config/xray-memory/snapshot.key` (not in this repo, backed up
  separately).
- `agent.yaml` — `xray-agent` (kagent Agent) + `RemoteMCPServer` wiring
  this snapshot into the cluster.

Build tool: clone `den-vasyliev/xray-memory` yourself (`gh repo clone`,
requires repo access), `make build`, then:

```bash
./bin/xray-memory snapshot \
  -repo velesha=/path/to/velesha \
  -snapshot-dir ./maps \
  -embedding-endpoint http://localhost:PORT \
  -snapshot-recipient <your age1... public key>
```

Exclude vendored/third-party dirs first if the repo has any the tool's
hardcoded `skipDir()` list doesn't catch (`.git`, `node_modules`, `vendor`,
`third_party`, `dist`, `build`, `.venv`, `__pycache__` only) — velesha's
`tools/llama.cpp` had to be moved aside during the build, or it gets parsed
as 33k extra nodes of someone else's C/C++.

See `docs/adr/0005-own-agentic-memory-corpus.md` for the full writeup.

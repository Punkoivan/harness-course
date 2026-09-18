# ToDo: run the embedding model locally (llama.cpp) so it's callable

Follows ADR-0002. Already done once for `velesha`; this is the repeatable
instruction — for a fresh machine, or for an agent that needs to bring the
model up itself before calling it.

## Prerequisites

- Build tools: `cmake`, `gcc`/`g++`, `make`, `git` (check with
  `which cmake gcc g++ make git`).
- ~1GB free disk (llama.cpp build + `bge-m3` GGUF, ~450MB model file).

## Steps

1. **Clone and build llama.cpp** (CPU build; add `-DGGML_VULKAN=ON` if an
   iGPU/discrete GPU should be used instead):
   ```bash
   git clone --depth 1 https://github.com/ggml-org/llama.cpp.git
   cd llama.cpp
   cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON
   cmake --build build --config Release -j"$(nproc)"
   ```
   Verify: `./build/bin/llama-server --help` runs without error.

2. **Download the model** — `bge-m3`, `Q4_K_M` quant (~440MB). The
   canonical HuggingFace repo (`ChristianAzinn/bge-m3-gguf`) returned
   `401` when this was actually done; the working public mirror used was:
   ```bash
   curl -fL -o bge-m3-Q4_K_M.gguf \
     "https://huggingface.co/gpustack/bge-m3-GGUF/resolve/main/bge-m3-Q4_K_M.gguf"
   ```
   Verify: file exists and is ~440MB (`ls -la bge-m3-Q4_K_M.gguf`).

3. **Start the server in embedding mode**, with batch size matched to
   context (see ADR-0002's gotcha — default batch rejects long inputs):
   ```bash
   ./build/bin/llama-server \
     -m bge-m3-Q4_K_M.gguf \
     --embedding --pooling cls \
     -c 8192 -b 8192 -ub 8192 \
     --port 8081 --host 127.0.0.1
   ```
   Run this in the background / as a long-lived process — it must stay up
   for anything else to call it.

4. **Verify the model is actually callable** (this is the point of the
   task — don't skip it):
   ```bash
   curl -sS -X POST http://localhost:8081/embedding \
     -H "Content-Type: application/json" \
     -d '{"content":"тестовий запит"}' \
     | python3 -c "
import json, sys
d = json.load(sys.stdin)
emb = d[0]['embedding']
if isinstance(emb[0], list):
    emb = emb[0]
print('dim:', len(emb))
"
   ```
   Expected: `dim: 1024`. If you get a 500 error mentioning batch size,
   the `-b`/`-ub` flags above were dropped — re-check step 3.

## Already done

This was carried out for real while building `velesha` — see that repo's
`tools/llama.cpp` (gitignored build) and `tools/models/` (gitignored
model), and `README.md` for the exact running instructions used there.
This ToDo exists so the same steps are reproducible independent of that
specific project.

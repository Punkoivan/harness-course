# Sidecar image: llama-server (llama.cpp) + bge-m3, CPU-only.
# See docs/adr/0001-model-serving-sidecar-vs-llmd.md and
# docs/todo/0001-sidecar-model-serving.md.

FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp.git .
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON \
    && cmake --build build --config Release -j"$(nproc)" --target llama-server

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/build/bin/llama-server /app/llama-server
COPY --from=build /src/build/bin/*.so* /usr/lib/
COPY bge-m3-Q4_K_M.gguf /app/model.gguf

EXPOSE 8081
ENTRYPOINT ["/app/llama-server", \
    "-m", "/app/model.gguf", \
    "--embedding", "--pooling", "cls", \
    "-c", "8192", "-b", "8192", "-ub", "8192", \
    "--port", "8081", "--host", "0.0.0.0"]

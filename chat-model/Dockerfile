# Chat-capable llama.cpp sidecar for retrieval-agent / k8s-agent.
# Same pattern as harness-course/sidecar/Dockerfile and the cluster's own
# releases/llama-cpp-embeddings.yaml -- llama.cpp with the GGUF baked in,
# just without --embedding and with --jinja for tool-call templating.
# See docs/adr/0003-chat-model-for-kagent-agents.md.

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
COPY qwen2.5-3b-instruct-q4_k_m.gguf /app/model.gguf

EXPOSE 8082
ENTRYPOINT ["/app/llama-server", \
    "-m", "/app/model.gguf", \
    "--jinja", \
    "-c", "8192", \
    "--port", "8082", "--host", "0.0.0.0"]

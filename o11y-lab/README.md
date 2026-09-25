# o11y lab: OpenTelemetry Demo on abox (`feat/otel-demo`)

Course task, 2026-09-25:

1. Deploy `abox` from the otel branch; read the
   [OTel Demo architecture](https://opentelemetry.io/docs/demo/architecture/).
2. Exercise the demo, write down questions and observations from an o11y
   point of view.
3. *(optional)* Add own agents and the kagent setup to the o11y system.

## 1. Setup

Upstream branch: `den-vasyliev/abox@feat/otel-demo` (bundle `0.11.36`),
forked to **`Punkoivan/abox@feat/otel-demo`**. The cluster reconciles from
the fork's own artifact, `oci://ghcr.io/punkoivan/abox/releases-otel-demo`
(`0.12.x`), bootstrapped with `tofu apply` from the fork — no hand patches
left in the cluster. Runs on the MacBook (arm64, 12 cores / 24GB) in the
lima `docker` VM; kubeconfig is `~/.kube/abox.yaml` only, the work
`~/.kube/config` is never touched.

What it took, in the order it bit:

| Problem | Symptom | Fix (in the fork unless noted) |
|---|---|---|
| lima VM 4 CPU / 4GB | nothing of this size fits | VM → 10 CPU / 18GB (host-side) |
| Docker in lima is **rootless** | kube-proxy CrashLoop: `can't use the IPVS proxier: operation not permitted` | `kubeProxyMode: iptables` |
| tofu providers configured from the cluster resource | any kind-config change → refresh dials `localhost:80` | delete kind cluster + prune state, fresh apply (what `setup.sh` does on Codespaces) |
| `ngrok-operator` in `releases/crds` needs credentials | `releases-crds` health check never passes → **no app release is ever applied** | removed (it only published someone else's `triageagent.ngrok.dev`) |
| inotify `max_user_instances=128` in the VM | `qdrant-mcp`, `neo4j-mcp`, `flagd`: `Failed to create file watcher: No file descriptors available` | `/etc/sysctl.d/99-kind-inotify.conf` in the VM (host-side) |
| amd64-only images | `exec format error` | multi-arch rebuilds in fork CI under `ghcr.io/punkoivan/abox`: `nomic-embed` (f16), `epp` v1.5.0 (upstream Dockerfile pins `GOARCH=amd64`), `agentregistry-inventory` v0.5.18 (ko) |
| CI paths from `github.repository` | ghcr rejects `Punkoivan/…` | workflows lowercase the path |
| out-of-band Secrets | `CreateContainerConfigError` | SOPS: `.sops.yaml`, `scripts/seal-secrets.sh`, age key → `flux-system/sops-age`, decryption on both Kustomizations |
| no Gemini key | agentgateway-llm / triage need one | local **Qwen3-4B-Instruct-2507** (`llama-cpp-chat`, weights as an image volume); kagent → agentgateway-llm (virtual key) → llama.cpp |
| triage-* are private packages (403) | can't pull charts or images | triage, pages-triage, graph-otel-demo left out |
| xray-memory server amd64-only, private source | — | left out of the bundle for this lab |
| `llama-cpp-chat` first boot | **OOMKilled** at 6Gi: f16 KV for 32k ctx ≈ 4.8GB + 2.5GB weights | q8_0 KV + flash attention, 24k ctx (2×12k slots) |
| first boot pulls everything at once | kagent/mlflow/phoenix/otel-demo miss helm's 5m install timeout, then sit until the 1h interval | kustomize patch on every HelmRelease: `timeout: 15m`, 3 install retries |
| agentgateway-llm seeds its PVC once | a changed seed ConfigMap never reaches an existing claim | re-seed when the seed's md5 changes |

## 2. Architecture as deployed (vs. the reference)

Reference ([docs](https://opentelemetry.io/docs/demo/architecture/)): ~18
services in ~12 languages (gRPC between most, HTTP for a few, Kafka between
checkout → accounting/fraud-detection), flagd for fault injection, Locust
load generator, and one OTel Collector exporting to **Jaeger** (traces),
**Prometheus** (metrics, including span-metrics RED from the
`span_metrics` connector), **OpenSearch** (logs), **Grafana** on top.

This branch changes the backend half:

```
services ──OTLP──> otel-collector-agent (DaemonSet, otel-demo)
                    ├─ traces  → jaeger ✗   debug   span_metrics   mlflow-bridge
                    ├─ metrics → prometheus ✗   debug
                    ├─ logs    → opensearch ✗   debug
                    └─ profiles→ firepit ✗   debug
mlflow-bridge = otel-collector (mlflow ns) ─routing─> MLflow experiment by header id
                    k8s.namespace.name == otel-demo → x-mlflow-experiment-id: "3"
                    service.name == triage-core     → x-mlflow-experiment-id: "2"
```

✗ = backend disabled in values (`jaeger/prometheus/grafana/opensearch:
enabled: false`, to save ~1.7Gi on KinD), exporter left wired on purpose
(nulling it out through the umbrella chart doesn't delete the key).

## 3. Observations

### O1. Only traces have a backend at all; metrics, logs, profiles go nowhere
Every non-trace signal ends in `debug` + an exporter to a Service that
doesn't exist. Over 10 minutes one collector pod logged **752 "Exporting
failed. Dropping data"** — opensearch 400, jaeger 181, prometheus 171 —
plus DNS failures for `firepit`. The `span_metrics` connector still turns
traces into RED metrics… and hands them to the dead Prometheus exporter.
So there is no way to answer "what's the error rate / p99 of checkout"
from anything but raw spans.

### O2. MLflow silently received nothing on a fresh cluster (fixed in fork)
The bridge addresses MLflow experiments by **hardcoded numeric id**
(`"2"`, `"3"`). Those ids existed on the cluster the branch was built on
because experiments were created there by hand; a fresh MLflow has only
`0 Default`. Result: every otel-demo batch got `404` from
`/v1/traces` (`get_experiment()` → `RESOURCE_DOES_NOT_EXIST`), the exporter
treats that as a **permanent error — dropped, no retry** (814 drops in
30 min, ~1/s). Nothing alerts on it; the demo "works" and the trace store
stays empty.

Verified by creating experiments `scratch`(1), `triage-core`(2),
`otel-demo`(3) through the MLflow API: 404s went to 0 within a minute,
traces started landing (`200` ×78 / 40s). Side-finding: sending a
*hand-made* span with a nonexistent experiment id returned **200 and stored
nothing** — the failure mode depends on the payload, not only the id.

Fixed in the fork: `releases/mlflow-experiments.yaml`, a Flux-managed Job
that creates the experiments by name in a fixed order and **fails** if an
existing one holds a different id than the collector routes to. On the
rebuilt cluster it completed on first boot and traces landed without any
manual step. (Id routing is still brittle — a single experiment with
tag-based separation would remove the coupling.)

### O3. Fault injection is visible on spans, invisible at trace level
Turned `paymentFailure` to `50%` via flagd-ui's API for ~4 minutes:

- span level — correct: about half of `PaymentService/Charge`,
  `CheckoutService/PlaceOrder`, `POST /api/checkout` spans are
  `STATUS_CODE_ERROR`, errors propagate up the call chain as they should;
- trace level — **0 ERROR out of 2097 traces**. MLflow derives a trace's
  `state` from its **root span**, and the root is the load generator's
  `user_checkout_single/multi` span, which Locust leaves `UNSET` even when
  the request 500s. So any trace-level "error rate" view reads 0% during a
  50% payment outage;
- `payment` pod logs had 32 error lines in the same window, but logs have
  no backend (O1), so that's only visible with `kubectl logs`.

In a Jaeger + span-metrics setup this would be caught by the RED metrics
(error rate per span name). Here the only way to see it was a span-name
query plus reading span statuses per trace.

### O4. MLflow is an LLM-trace store; distributed traces fit awkwardly
- A trace's tags carry the resource attributes of **one** service
  (apparently whichever batch created the trace): a trace touching 8
  services shows a single `service.name`, e.g. `frontend-proxy`.
- Traces whose root span hasn't arrived yet stay `IN_PROGRESS` (122 of
  2097 in one window) — fine for a single LLM call, odd for a microservice
  trace where the root arrives from another pod's batch.
- There's no service map / dependency graph (the branch compensates with a
  prebuilt one delivered as an OCI artifact, `graph-otel-demo.yaml`).

### O5. Noise
- `flagd` produces **~30% of all traces** (408 of 1399 in 3 min) — feature
  flag evaluations traced as top-level operations.
- The collector's own logs are exported via OTLP **back into itself**
  (`service.telemetry.logs` → `otel-collector:4318`) into the logs pipeline,
  whose OpenSearch exporter fails, which logs an error with a stack trace,
  which is exported again: **~79k log lines / 7.2MB per pod per 10 min**,
  mostly stack traces. A feedback loop that only exists because the backend
  was removed.
- `kubeletstats` receiver fails every scrape: kind's kubelet serving cert
  has no IP SANs (`x509: cannot validate certificate for 172.18.0.2`) —
  needs `insecure_skip_verify` or node-name addressing on KinD.

### O6. Upstream chart bug (opentelemetry-demo 0.41.2)
`transform/sanitize_spans` is defined but **not referenced**; the traces
pipeline lists `transform/sanitize_logs` instead (which only has
`log_statements`, i.e. a no-op on spans). So the `http.route`
normalization for `frontend` spans and `set_semconv_span_name` never run —
high-cardinality span names (`/api/products/<id>`) reach the backend.
Same in the chart's default values, not introduced by this branch.
Also: the `batch` processor is defined but used in no pipeline — batching
happens only in the exporters that carry `sending_queue.batch` (jaeger,
prometheus), not in the added `otlp_grpc/mlflow-bridge`; and
`memory_limiter` comes after `k8s_attributes` instead of first.

### O7. The agent tracing that was configured never worked
`agentgateway-llm` already had `frontendPolicies.tracing` → Phoenix. The
Phoenix chart (12.0.14) turns **auth on by default**, and with auth on
Phoenix rejects unauthenticated OTLP: agentgateway-llm logged
`BatchSpanProcessor.ExportError`, kagent (once enabled)
`rpc error: code = Unauthenticated` — and Phoenix held **0 spans** while
both looked configured. Ingestion accepts only API keys minted in the
running Phoenix (`PHOENIX_ADMIN_SECRET` as a bearer also got 401), so there
is no declarative way to hand exporters a credential. Fork: `auth.enableAuth:
false` (Phoenix is in-cluster/port-forward only — trade-off noted in the
manifest). Same class of failure as O2: exporter-side errors, collector-less
path, nothing alerting.

Side-finding: the Phoenix chart doesn't roll its pod on ConfigMap changes
(no checksum annotation) — `PHOENIX_ENABLE_AUTH=false` sat in the ConfigMap
while the old pod kept enforcing auth until a manual `rollout restart`.

## 4. Task 3 — kagent + agents in the o11y system

Wiring (fork):

```
A2A client ─► kagent-controller (A2A proxy, no tracing)
                 └─► k8s-agent pod ──OTLP──► Phoenix  (kagent otel.tracing)
                        └─► agentgateway-llm ──OTLP──► Phoenix  (frontendPolicies.tracing)
                               └─► llama-cpp-chat (Qwen3-4B, CPU)
```

One question needing a tool ("list the pods in otel-demo, how many, which
aren't Running"), 171s end to end. What Phoenix shows:

| span | start → end | detail |
|---|---|---|
| `invoke_agent k8s_agent` | 18:59:17 → 19:02:08 | |
| `generate_content qwen3-4b-instruct` | → 18:59:30 (13s) | 3886 prompt / 63 completion tokens — picks the tool |
| `execute_tool k8s_get_resources` | <1s | args `{"namespace":"otel-demo","resource_type":"pod","output":"wide"}`; full kubectl output in `gcp.vertex.agent.tool_response` |
| `generate_content qwen3-4b-instruct` | → 19:02:08 (**2m38s**) | 6005 prompt / 135 completion — ~2.1k tokens of tool output to prefill on CPU |
| `POST /*` → `POST llama-cpp-chat…` (gateway) | matches each LLM call | same token counts, `http.status=200` |

(For scale, not like-for-like: ADR-0005's voice → voice-router → k8s-agent
round-trip, one hop more, took ~16–17 min on the old ThinkPad with
Qwen2.5-3B.)

Observations:

- **O8. The answer was wrong, and only the trace proves why.** The agent
  said "30 pods, all Running". The tool response in the span has **27**
  Running rows. So it's not bad data or a failed tool — the 4B model
  miscounted what it was given. An earlier "how many pods" question without
  "use your tools" got `10` in 1.5s: 3 completion tokens, no tool span at
  all — answered from nothing. Correctness is invisible in RED metrics;
  it takes span attributes (tool args + output) to tell hallucination from
  bad input.
- **O9. Trace context breaks at every hop.** The agent's spans and the
  gateway's spans for the same LLM call are **separate traces**:
  agentgateway-llm starts a new root for each call — either kagent's LLM
  client doesn't send `traceparent` or the gateway doesn't honour it; not
  yet determined which. The agent's
  root `POST /` has a parent id that doesn't exist — it's the A2A proxy in
  `kagent-controller`, which has no tracing (the chart's `otel` values only
  land on agent pods). Correlating agent turn ↔ gateway hop means matching
  timestamps and token counts by hand.
- **O10. Layers disagree on usage.** For the same request kagent reports
  `cache_read_input_tokens=0`, the gateway `3873` (llama.cpp's prompt cache
  hit). Token/cost dashboards built from one layer won't match the other.
- **O11. Traces carry full tool output.** `tool_response` holds the entire
  kubectl output (4KB here). An agent that reads a Secret or a ConfigMap
  with credentials writes it into Phoenix — now with auth off (O7). Needs
  attribute redaction/truncation at the collector before this is anything
  but a lab.
- **O12. Where the time goes is now visible.** 92% of the 171s is one LLM
  call's prefill of tool output — the fix is fewer/shorter tool results or
  a faster model, not the tool or the gateway (both <1s).

## Questions

1. Why MLflow and not Jaeger/Tempo for the microservice traces? It's the
   right store for triage-core's LLM traces; for the demo it loses service
   views, error-by-span-name aggregation and RED metrics. Is the intent
   "one store for everything, accept the loss", or just RAM on KinD?
2. If metrics/logs are out on purpose, should the collector drop those
   pipelines (or route them to `nop`) instead of leaving exporters to dead
   endpoints? Right now "is the pipeline healthy" can't be answered from
   the collector's own error rate — it's always failing.
3. What watches the telemetry pipeline itself? O2 dropped 100% of traces
   with nothing noticing. `otelcol_exporter_send_failed_spans` exists — but
   the collector's own metrics go to the same dead Prometheus.
4. Should the load generator set span status on failed requests, so the
   trace root reflects the user-facing outcome? Otherwise synthetic traffic
   hides every injected fault at the trace level.
5. Phoenix vs MLflow: two LLM-trace UIs in one cluster — which is the
   target for kagent/agent traces? (Chose Phoenix here, because
   agentgateway-llm already pointed there.)
6. Should all of this go through one collector (the bridge in `mlflow`)
   instead of four direct exporters? That's where redaction (O11),
   fan-out to both stores, and one place to watch export failures (O2/O7)
   would live.
7. Does kagent's model client propagate `traceparent` to the LLM endpoint,
   and does agentgateway-llm continue an incoming trace (O9)?

## Next

- Route kagent + agentgateway-llm through a collector: redact
  `tool_response`/`gen_ai` content attributes, fan out to Phoenix + MLflow,
  export the collector's own failure metrics somewhere.
- Tracing on `kagent-controller` (A2A proxy) so agent traces have a real
  root; see whether traceparent reaches agentgateway-llm.
- Re-add xray-memory once its server image is built multi-arch.

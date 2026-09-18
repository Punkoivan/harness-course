# ADR-0001: Model serving in the `abox` cluster — sidecar (llama.cpp) now, llm-d later

- **Status**: accepted
- **Date**: 2026-09-18

## Context

Course task: prepare an ADR/ToDo for running a model in the cluster in
**sidecar** mode, and evaluate **llm-d** as an alternative, then log the
outcome in the changelog.

Environment: `abox`, a 3-node KinD cluster (1 control-plane + 2 workers) on
a single laptop — 16-core Ryzen 7 PRO 4750U, 30GB RAM, AMD Radeon Vega
integrated GPU, no discrete/datacenter accelerator.

Two candidate approaches:

1. **Sidecar**: a model-serving container (`llama-server`, llama.cpp) runs
   in the same pod as an application container, reachable over `localhost`.
2. **llm-d**: a Kubernetes-native distributed inference control plane —
   researched before writing this ADR, see findings below.

## llm-d — what it actually is and why it doesn't fit here

llm-d is not an inference engine; it's an orchestration layer **on top of**
vLLM (also SGLang), providing scheduling/routing across many vLLM
instances — Red Hat's own framing: "vLLM is Linux, llm-d is Kubernetes"
for inference. CNCF sandbox project, backed by Red Hat, Google Cloud, IBM
Research, CoreWeave, NVIDIA, and others. Core architecture: disaggregated
prefill/decode pods (scaled independently), KV-cache-aware routing,
hierarchical KV-cache offload, wide expert-parallelism for MoE models.

Documented hardware requirements (llm-d.ai infrastructure docs):
- Supported accelerators: NVIDIA L4/A100/H100/H200/B200+, AMD MI250X+,
  Google TPU v5e/v6e+ — **no CPU-only path, no integrated-GPU support
  documented anywhere**.
- Baseline per node: **80+ cores, 500GiB+ memory, PCIe 5+**, plus
  high-speed interconnect (NVLink/InfiniBand/RoCE) for multi-host setups.
- Quickstart's default example: 8 replicas of a 32B model across NVIDIA
  GPUs; minimum cited cloud instance is a `g6e.12xlarge` (4×L40S 48GB).
- Kubernetes 1.29+ (1.33+ recommended), cert-manager, Gateway API CRDs
  v1.3.0+, NVIDIA GPU Operator, cluster-admin — and explicitly **no
  service mesh** (Istio CRDs conflict).
- Latest release: v0.9 (2026-08-28), CNCF sandbox, pre-1.0, explicitly
  framed as proving production/datacenter scale — not lightweight/dev-scale
  maturity.

None of this matches a laptop KinD cluster with an integrated GPU. Every
documented requirement (accelerator class, per-node core/RAM floor, fast
interconnect, multi-pod disaggregated topology) assumes a multi-node
datacenter GPU cluster. Installing the Helm charts in KinD and pointing
them at a toy CPU vLLM pod would technically "run," but would exercise none
of llm-d's actual value (disaggregation, GPU-aware scheduling, KV-cache
routing) — not a real test of the technology, just theater.

One finding worth keeping for later: llm-d has a **documented, named
integration with agentgateway** (already running in `abox`) via the
Gateway API Inference Extension — `InferencePool` CRD + an Endpoint Picker
that agentgateway routes to. So the on-ramp when real accelerator hardware
becomes available is "point the existing agentgateway at llm-d's
InferencePool," not a new gateway or a rip-and-replace.

## Decision

- **Now**: model serving in `abox` uses the **sidecar pattern** —
  `llama-server` (llama.cpp) as a second container in the target pod,
  CPU-only (optionally Vulkan for the iGPU later), talking to the main
  container over `localhost`. This is the only one of the two approaches
  with any realistic viability on this hardware, and it's the same
  llama.cpp setup already proven to work for Velesha's embedding pipeline
  outside the cluster (see `velesha` repo, ADR-0002) — same binary, new
  deployment target.
- **Later**: llm-d stays a documented option, revisited specifically when
  (a) the target environment has real NVIDIA/AMD-datacenter/TPU
  accelerators, and (b) the workload actually needs disaggregated serving
  or multi-replica routing — not before. When that day comes, the
  agentgateway integration is the entry point, not a green-field setup.

## Alternatives considered

- **llm-d now, accept it's a toy deployment** — rejected: doesn't validate
  anything about llm-d's actual purpose, burns cluster-admin-level Helm
  installs and CRDs (InferencePool, EPP) for a demo with no signal.
- **No in-cluster model serving; keep using the host-level `llama-server`
  Velesha already runs** — valid short-term fallback, but doesn't satisfy
  the course task ("in the cluster, sidecar mode"), and doesn't let
  in-cluster agents (kagent) reach a local model without a network hop to
  the host.

## Consequences

- Sidecar container needs its own resource requests/limits sized for
  CPU-bound embedding/inference so it doesn't starve the pod's main
  container on a 2-worker KinD cluster with no other headroom to spare.
- The GGUF model file has to get into the cluster somehow — either baked
  into the sidecar image (simplest, but a multi-hundred-MB image) or
  mounted from a PVC/hostPath (see ToDo).
- Revisiting llm-d requires re-checking its docs at that time — v0.9 is
  pre-1.0 and moving fast; requirements captured here (2026-09-18) may
  already be stale by the time real hardware is available.

See `docs/todo/0001-sidecar-model-serving.md` for the implementation
checklist.

# voice-agent

Course task 5: a voice interface that delegates spoken commands to kagent
agents over A2A.

Architecture:
```
mic --(parecord)--> wav --(Google Cloud Speech-to-Text)--> text
    --(A2A message/send)--> voice-router agent
        (delegates to k8s-agent / retrieval-agent / xray-agent as needed,
         via kagent's own Agent-as-tool = A2A mechanism)
    --> short spoken-style reply
    --(Google Cloud Text-to-Speech + ffplay)--> speaker
```

`voice-router` (`router-agent.yaml`) has no MCP tools of its own -- every
"tool" is another kagent Agent, so answering *is* A2A delegation, not a
simulation of it.

## Running it

```bash
# 1. voice-router reachable
kubectl port-forward -n kagent svc/voice-router 8182:8080

# 2. Google Cloud service-account key with Speech-to-Text + Text-to-Speech
#    API access. Kept OUTSIDE this repo deliberately -- point at wherever
#    you keep it, never commit it.
export GOOGLE_APPLICATION_CREDENTIALS=~/Downloads/your-key.json

# 3. Talk
uv sync
uv run voice_client.py
```

Push-to-talk: Enter to start recording, Enter again to stop. First reply is
slow (CPU chat model, cold cache) — see harness-course ADR-0003.

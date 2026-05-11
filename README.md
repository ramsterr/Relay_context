# Context Handover

> Track and preserve context across LLM session handovers.

When LLM sessions end, critical context gets lost. This library extracts semantic atoms from conversations, measures context drift, and ensures important decisions survive session transitions.

## Install

```bash
pip install -r requirements.txt
```

## What it does

```
Session 1                    Session 2                    Session 3
┌──────────────┐            ┌──────────────┐            ┌──────────────┐
│ Use RS256 ✓  │     →      │ Use RS256 ✓  │     →      │ Use RS256 ✓  │
│ Tokens: 1hr  │            │ Tokens: 1hr  │            │ Tokens: 1hr  │
│ Auth: JWT    │            │ Auth: JWT    │            │ Auth: JWT    │
└──────────────┘            └──────────────┘            └──────────────┘
```

- **Extracts atoms**: Decisions, constraints, entities, tasks from messages
- **Measures drift**: KL divergence + Jaccard to detect lost context
- **Builds packages**: Budget-aware selection for next session
- **Tracks loss**: What wasn't included vs what model dropped

## Usage

```python
from context_handover import ContextManager

manager = ContextManager(max_tokens=8000)

# Add messages - atoms extracted automatically
manager.add_message("Decision: use RS256 for JWT signing")
manager.add_message("Constraint: tokens expire after 1 hour")
manager.add_message("Question: how to handle refresh tokens?")

# See what was extracted
summary = manager.get_context_summary()
print(f"Atoms: {summary['total_atoms']}")
# Atoms: 3

# Check if context drifted
drift = manager.compute_drift()
print(f"Drift: {drift['composite']:.3f}")  # 0.0-1.0, lower is better

# Build what to pass to next session
package = manager.build_handover_package()
print(package.to_context_string())

# Handover to new session
old_id, new_id = manager.handover_to_new_session()
```

## Configuration

```python
manager = ContextManager(
    max_tokens=8000,              # Token budget per session
    model_client=openai_client,   # For LLM-based extraction
    embedding_client=openai_client,
    langfuse_public_key="pk-...", # Optional: Langfuse observability
    langfuse_secret_key="sk-...",
)
```

## Environment

```bash
export OPENAI_API_KEY=sk-...      # Enable LLM extraction
export LANGFUSE_PUBLIC_KEY=...    # Enable observability
```

## Run Demo

```bash
python examples/run_demo.py
```

## Run Tests

```bash
pytest
```

## License

MIT
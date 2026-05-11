# Context Handover

Track and preserve context across LLM sessions. Extracts semantic atoms from conversations, measures context drift, and ensures critical decisions survive session handovers.

## Install

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from context_handover import ContextManager

manager = ContextManager(max_tokens=8000)

# Add messages - atoms extracted automatically
manager.add_message("Decision: use RS256 for JWT signing")
manager.add_message("Constraint: tokens expire after 1 hour")

# Get atoms
atoms = manager.get_context_summary()
print(f"Total atoms: {atoms['total_atoms']}")  # 2

# Check drift
drift = manager.compute_drift()
print(f"Drift: {drift['composite']:.3f}")  # 0.087

# Build handover package
package = manager.build_handover_package()
print(package.to_context_string())
```

## Environment

```bash
export OPENAI_API_KEY=sk-...      # for LLM extraction
export LANGFUSE_PUBLIC_KEY=...   # for observability
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
# Context Handover System

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Status-Alpha-orange.svg" alt="Status">
  <img src="https://img.shields.io/badge/Phase-4%2F4-brightgreen.svg" alt="Phase">
</p>

> A production-ready system for tracking, measuring, and preserving context across LLM session handovers. Tracks semantic atoms, measures drift, and ensures critical decisions survive session transitions.

## 🎯 Overview

When working with LLMs across multiple sessions, critical context gets lost during handovers. This system:

- **Extracts** semantic atoms (decisions, constraints, entities, tasks) from conversations
- **Measures** context drift using KL divergence, Jaccard similarity, and embedding-based analysis
- **Preserves** high-priority atoms across sessions via intelligent handover packages
- **Observes** everything via Langfuse and OpenTelemetry integration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONTEXT PLANE (persists across sessions)          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                   │
│  │  Session 1   │ → │  Session 2   │ → │  Session 3   │                   │
│  │  atoms: 12   │   │  atoms: 15   │   │  atoms: 18   │                   │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                   │
│         │                  │                   │                          │
│         └──────────────────┴───────────────────┘                          │
│                            │                                               │
│                   ┌────────▼────────┐                                      │
│                   │   Session DAG   │                                      │
│                   │  (lineage trace)│                                      │
│                   └────────┬────────┘                                      │
│                            │                                               │
│         ┌──────────────────┼──────────────────┐                           │
│         ▼                  ▼                  ▼                           │
│   Atom Registry      Loss Ledger        Tag Registry                     │
│   (all atoms)         (what dropped)      (consistent tags)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## ✨ Features

### Phase 1: Foundation
- **SemanticAtom** data model with paraphrase-resistant identity
- **Structured extraction** via LLM (GPT-4o) with regex fallback
- **Checkpoint triggers** at 50%, 75%, 85% token utilization
- **Langfuse integration** for observability

### Phase 2: Measurement
- **Dual KL Divergence** (structural + semantic via embeddings)
- **Jaccard Verification** against model's self-report
- **Loss Ledger** tracking `not_included` vs `sent_but_dropped`
- **Tiktoken-accurate** budget management

### Phase 3: Production
- **Async pipeline** with Redis queue support
- **W3C-style trace context** for full handover lineage
- **OpenTelemetry** instrumentation (Jaeger, Prometheus)
- **Non-blocking** chat loop integration

### Phase 4: Codebase-Specific
- **CodeAtom** subtype with file paths, symbols, AST hashes
- **Symbol normalizer** (auth → authentication, cfg → config)
- **File salience decay** (config files decay faster than logic)
- **Dependency resolver** for import tracking

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/ramsterr/context_handover.git
cd context_handover

# Install dependencies
pip install -r requirements.txt

# Optional: Install dev dependencies
pip install -r requirements.txt[dev]
```

### Environment Variables

```bash
# Required for LLM-based extraction
export OPENAI_API_KEY=sk-...

# Optional: Langfuse for observability
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...

# Optional: Redis for async pipeline
export REDIS_URL=redis://localhost:6379
```

## 🚀 Quick Start

```python
from context_handover import ContextManager
from context_handover.core.checkpoint import CheckpointLevel

# Initialize the context manager
manager = ContextManager(max_tokens=8000)

# Add messages (atoms extracted automatically)
messages = [
    "We need to implement JWT authentication.",
    "Decision: use RS256 for signing tokens.",
    "Constraint: tokens must expire after 1 hour.",
]

for msg in messages:
    checkpoint = manager.add_message(msg)
    if checkpoint:
        print(f"Checkpoint triggered: {checkpoint.value}")

# Get session summary
summary = manager.get_context_summary()
print(f"Total atoms: {summary['total_atoms']}")
print(f"By type: {summary['by_type']}")

# Compute drift
drift = manager.compute_drift()
print(f"Drift composite: {drift['composite']:.3f}")
print(f"Verdict: {drift['verdict']}")

# Build handover package
package = manager.build_handover_package()
print(package.to_context_string())

# Create checkpoint
checkpoint = manager.create_checkpoint(CheckpointLevel.STANDARD)

# Handover to new session
old_id, new_id = manager.handover_to_new_session()
print(f"Handover: {old_id} → {new_id}")
```

## 📊 Demo Output

```
==================================================
 Context Handover System Demo
==================================================

OpenAI API: ✗ not set (using fallback)
Langfuse:   ✗ not set

[1] Created session: 3dc3ae8b
    Trace ID: 2d958a3f3900

[2] Adding 7 messages...

==================================================
 Session State
==================================================
Session ID:  3dc3ae8b
Total Atoms: 6
By Type:    {
    "task": 1,
    "decision": 2,
    "constraint": 2,
    "question": 1
}
Token Count: 99 / 8000 (1.2%)

==================================================
 Drift Analysis
==================================================
KL Structural: 0.3689
Jaccard:       1.0000
Composite:     0.0876
Verdict:       EXCELLENT
```

## 🏗️ Architecture

```
                    ┌─────────────────────────────┐
                    │      ContextManager         │
                    │    (main entry point)       │
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────┴───────┐        ┌────────┴────────┐        ┌────────┴────────┐
│    Core       │        │   Measurement  │        │    Pipeline      │
├───────────────┤        ├─────────────────┤        ├──────────────────┤
│ atoms.py      │        │ drift.py       │        │ pipeline.py     │
│ registry.py   │        │ ledger.py      │        │ trace_context.py│
│ budget.py     │        │ verification.py│        │                 │
│ checkpoint.py │        │                │        │                 │
└───────────────┘        └─────────────────┘        └─────────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐        ┌─────────────────┐        ┌─────────────────┐
│ Extraction    │        │ Instrumentation │        │ Code Analysis   │
├───────────────┤        ├─────────────────┤        ├──────────────────┤
│ extraction.py │        │ otel_instrument │        │ code_utils.py   │
│               │        │ langfuse.py    │        │                 │
└───────────────┘        └─────────────────┘        └─────────────────┘
```

## 📈 Atom Types

| Type | Description | Example |
|------|-------------|---------|
| `decision` | A choice that was made | "use RS256 for JWT" |
| `constraint` | A hard rule | "tokens expire after 1 hour" |
| `entity` | A concrete thing | "JWT middleware" |
| `task` | An action to take | "write auth middleware" |
| `question` | Something unresolved | "how to handle refresh?" |
| `belief` | Model's understanding | May be wrong |
| `relation` | How things relate | "A depends on B" |

## 🔧 Configuration

```python
manager = ContextManager(
    model_client=openai_client,      # OpenAI client for LLM extraction
    embedding_client=openai_client,   # For embedding-based dedup
    langfuse_public_key="pk-...",     # Langfuse observability
    langfuse_secret_key="sk-...",     # Langfuse observability
    jaeger_endpoint="http://localhost:14268/api/traces",
    max_tokens=8000,                  # Token budget
)
```

## 📝 API Reference

### ContextManager

```python
manager = ContextManager(max_tokens=8000)

# Add a message (extracts atoms automatically)
checkpoint = manager.add_message("Decision: use RS256")

# Get session state
summary = manager.get_context_summary()

# Compute drift score
drift = manager.compute_drift()  # {kl_structural, jaccard, composite, verdict}

# Build handover package
package = manager.build_handover_package()
package.to_context_string()  # Markdown-formatted context

# Create checkpoint
checkpoint = manager.create_checkpoint(CheckpointLevel.DEEP)

# Handover to new session
old_id, new_id = manager.handover_to_new_session()

# Get loss summary
ledger = manager.ledger.summary()
```

### DriftMeasurementSuite

```python
suite = DriftMeasurementSuite()

# Structural KL (type distribution)
kl_struct = suite.kl_structural(atoms, model_dist)

# Semantic KL (embedding clusters)
kl_sem = suite.kl_semantic(gt_embeddings, handover_embeddings)

# Jaccard (specific atoms present/absent)
jaccard = suite.jaccard(ground_truth_ids, reported_ids)

# Composite score
composite = suite.composite(kl_struct, jaccard, kl_sem)

# Verdict
verdict = suite.verdict(composite)  # EXCELLENT, GOOD, WARNING, CRITICAL
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_core.py -v

# Run with coverage
pytest --cov=src --cov-report=html
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Built following the 4-phase architecture from the original design doc
- Inspired by Langfuse observability patterns
- Uses tiktoken for accurate token counting

---

<p align="center">Made with ❤️ for better LLM context management</p>
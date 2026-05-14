# Context Handover - Complete User Guide

> **Preserve Semantic Continuity Across LLM Session Boundaries** 🐱

This comprehensive guide walks you through everything you need to know about `context_handover` — from installation to advanced production deployment.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start (5 Minutes)](#quick-start-5-minutes)
3. [Core Concepts](#core-concepts)
4. [Installation](#installation)
5. [Basic Usage](#basic-usage)
6. [Advanced Features](#advanced-features)
7. [Visualization Dashboard](#visualization-dashboard)
8. [Configuration](#configuration)
9. [API Reference](#api-reference)
10. [Troubleshooting](#troubleshooting)
11. [Best Practices](#best-practices)

---

## Introduction

### The Problem

Large Language Models (LLMs) have a fundamental limitation: **they forget everything when a session ends**. When your chat context exceeds the token limit or when you need to start a new session, critical information is lost.

Traditional solutions fall short:
- **Linear buffers** fill up quickly and lose important early context
- **Vector databases** are expensive and don't track semantic relationships
- **Manual summarization** loses nuance and requires human intervention

### The Solution

`context_handover` treats context as a **Directed Acyclic Graph (DAG)** of semantic units called **Semantic Atoms**. It uses:

- **Atom Extraction**: Automatically identifies facts, decisions, constraints, and preferences
- **Context Drift Detection**: Measures how much your conversation topic has shifted
- **Bounded Knapsack Algorithm**: Mathematically optimizes which atoms fit within token limits
- **Session Handover**: Seamlessly transfers optimized context to new sessions

---

## Quick Start (5 Minutes)

### Step 1: Install

```bash
pip install context-handover
```

### Step 2: Create Your First Session

Create a file called `hello_handover.py`:

```python
from context_handover import SessionManager

# Initialize the session manager
manager = SessionManager(session_id="my_first_session")

# Add some messages
manager.add_message(
    role="user",
    content="I'm building a SaaS product for project management."
)

manager.add_message(
    role="assistant", 
    content="Great! What features are you prioritizing? Task tracking, team collaboration, or reporting?"
)

manager.add_message(
    role="user",
    content="Task tracking and team collaboration are must-haves. Reporting is secondary."
)

# Extract semantic atoms automatically
atoms = manager.extract_atoms()
print(f"✨ Extracted {len(atoms)} semantic atoms:")
for atom in atoms:
    print(f"  - {atom.atom_type}: {atom.content[:50]}...")

# Build a handover package for the next session
handover_pkg = manager.build_handover_package()
print(f"\n📦 Handover package ready: {handover_pkg.token_count} tokens")
```

Run it:

```bash
python hello_handover.py
```

### Step 3: Launch the Visualization Dashboard

See your context in action:

```bash
streamlit run context_observatory.py
```

Open your browser to `http://localhost:8501` to explore the interactive dashboard.

---

## Core Concepts

### Semantic Atoms

A **Semantic Atom** is the smallest unit of meaningful context. Think of it as a Lego brick — not the whole castle, but an essential building block.

| Atom Type | Description | Example |
|-----------|-------------|---------|
| **FACT** | Objective information | "Methane has a specific impulse of 350s" |
| **DECISION** | Choices made by user or system | "Selected PostgreSQL as the database" |
| **CONSTRAINT** | Limitations or requirements | "Must work offline", "Budget under $100" |
| **USER_PREF** | User preferences | "Prefers dark mode", "Likes concise answers" |
| **CONTEXT_REF** | Reference to external context | Links to documents, previous sessions |

### Session DAG

Unlike linear chat history, `context_handover` tracks conversations as a **Directed Acyclic Graph (DAG)**:

```
Session 1                    Session 2
┌─────────┐                  ┌─────────┐
│ Fact A  │ ────────────────▶│ Decision│
└────┬────┘   Handover       └────┬────┘
     │         Inheritance         │
     ▼                             ▼
┌─────────┐                  ┌─────────┐
│Decision │                  │ Fact B  │
└─────────┘                  └─────────┘
```

This allows:
- **Branching conversations** without losing context
- **Selective inheritance** of only relevant atoms
- **Dependency tracking** across session boundaries

### Context Drift

**Drift** measures how much your conversation topic has changed over time. High drift indicates the current context may no longer represent the original intent.

Metrics used:
- **KL Divergence**: Semantic distribution shift
- **Cosine Distance**: Embedding vector drift  
- **Jaccard Index**: Vocabulary overlap
- **Composite Score**: Weighted fusion of all metrics

### Token Budget & Knapsack Optimization

When you hit token limits, the **Bounded Knapsack Algorithm** selects the most valuable atoms:

```
Goal: Maximize Σ(Value) subject to Σ(Tokens) ≤ Budget

Example:
┌─────────────┬───────┬───────┬──────────┐
│ Atom        │ Tokens│ Value │ Selected │
├─────────────┼───────┼───────┼──────────┤
│ Decision #1 │ 50    │ 0.95  │ ✅ Yes   │
│ Fact #3     │ 80    │ 0.88  │ ✅ Yes   │
│ Fluff #7    │ 120   │ 0.30  │ ❌ No    │
└─────────────┴───────┴───────┴──────────┘
```

---

## Installation

### Basic Installation

```bash
pip install context-handover
```

### With Optional Dependencies

For full functionality including visualizations and vector backends:

```bash
# All features
pip install context-handover[all]

# Or select specific extras
pip install context-handover[viz]      # Visualizations (Streamlit, Plotly)
pip install context-handover[vector]   # Vector stores (ChromaDB, Qdrant)
pip install context-handover[langchain] # LangChain integration
```

### Development Installation

```bash
git clone https://github.com/your-org/context-handover.git
cd context-handover
poetry install
pre-commit install
```

### Verify Installation

```bash
python -c "from context_handover import SessionManager; print('✅ Installation successful')"
```

---

## Basic Usage

### Initializing a Session

```python
from context_handover import SessionManager, Config

# Simple initialization
manager = SessionManager(session_id="session_001")

# With custom configuration
config = Config(
    max_tokens=4096,
    drift_threshold=0.5,
    knapsack_strategy="value_density"
)
manager = SessionManager(session_id="session_001", config=config)
```

### Adding Messages

```python
# Add a user message
manager.add_message(
    role="user",
    content="I need help designing a REST API for user authentication."
)

# Add an assistant response
manager.add_message(
    role="assistant",
    content="Let's design a secure authentication API. We'll use JWT tokens..."
)

# Add with metadata
manager.add_message(
    role="user",
    content="Use OAuth2 for third-party logins",
    metadata={
        "priority": "high",
        "tags": ["security", "oauth"],
        "timestamp": "2024-01-15T10:30:00Z"
    }
)
```

### Extracting Atoms

```python
# Automatic extraction
atoms = manager.extract_atoms()

# Manual extraction with filters
atoms = manager.extract_atoms(
    min_confidence=0.7,           # Only high-confidence atoms
    atom_types=["FACT", "DECISION"],  # Specific types
    after_timestamp="2024-01-15"  # Time-based filtering
)

# Inspect extracted atoms
for atom in atoms:
    print(f"Type: {atom.atom_type}")
    print(f"Content: {atom.content}")
    print(f"Confidence: {atom.confidence_score}")
    print(f"Tokens: {atom.token_count}")
    print("---")
```

### Building Handover Packages

```python
# Build optimized handover package
package = manager.build_handover_package()

# Access package contents
print(f"Total tokens: {package.token_count}")
print(f"Atoms included: {len(package.atoms)}")
print(f"Compression ratio: {package.compression_ratio}")

# Export to different formats
package.to_json("handover.json")
package.to_yaml("handover.yaml")
serialized = package.serialize()  # For Redis/message queues
```

### Handing Over to New Sessions

```python
# Create new session with handover
new_manager = SessionManager(session_id="session_002")
new_manager.handover_from_package(package)

# Continue the conversation seamlessly
new_manager.add_message(
    role="user",
    content="Continuing from where we left off..."
)
```

---

## Advanced Features

### Drift Detection

Monitor context drift in real-time:

```python
from context_handover import DriftDetector

detector = DriftDetector(manager)

# Get current drift metrics
metrics = detector.compute_drift()
print(f"KL Divergence: {metrics.kl_divergence}")
print(f"Cosine Similarity: {metrics.cosine_similarity}")
print(f"Composite Drift: {metrics.composite_score}")

# Set up drift alerts
if metrics.composite_score > 0.6:
    print("⚠️ High drift detected! Consider refreshing context.")
    manager.trigger_context_refresh()
```

### Custom Atom Extraction

Override default extraction logic:

```python
from context_handover import CustomAtomExtractor

class MyExtractor(CustomAtomExtractor):
    def extract_facts(self, text):
        # Custom fact extraction logic
        pass
    
    def extract_decisions(self, text):
        # Custom decision detection
        pass

manager.set_extractor(MyExtractor())
```

### Vector Store Integration

Use persistent vector storage:

```python
from context_handover.storage import ChromaBackend, QdrantBackend

# ChromaDB (local)
backend = ChromaBackend(persist_directory="./chroma_data")
manager.set_vector_backend(backend)

# Qdrant (production)
backend = QdrantBackend(
    url="http://localhost:6333",
    collection_name="context_atoms"
)
manager.set_vector_backend(backend)
```

### Dead Letter Queue (DLQ)

Handle failed processing:

```python
from context_handover.queue import DeadLetterQueue

dlq = DeadLetterQueue(storage_path="./dlq")

# Failed events are automatically queued
manager.set_dlq(dlq)

# Later, replay failed events
dlq.replay_all()
```

### Circuit Breaker Pattern

Prevent cascading failures:

```python
from context_handover.resilience import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30
)

manager.set_circuit_breaker(breaker)
```

---

## Visualization Dashboard

The **Context Observatory** provides real-time visibility into your context handover system.

### Launching the Dashboard

```bash
streamlit run context_observatory.py
```

Access at: `http://localhost:8501`

### Dashboard Views

#### 1. Session DAG Map

**What it shows**: Interactive graph of all atoms and their dependencies across sessions.

**Visual cues**:
- **Node colors**: Atom types (Orange=Decision, Blue=Fact, Red=Constraint, Green=User Pref)
- **Node size**: Status (Large=Missing/Error, Medium=Active, Small=Dropped)
- **Edge styles**: Dependencies (Solid=Sequential, Dashed=Handover inheritance)

**Use case**: Track how context flows between sessions, identify broken links.

#### 2. Drift & Health Dashboard

**What it shows**: Time-series of drift metrics plus current health gauge.

**Metrics tracked**:
- KL Divergence (semantic distribution shift)
- Cosine Distance (embedding drift)
- Jaccard Index (vocabulary overlap)
- Composite Score (weighted fusion)

**Color zones**: 
- 🟢 Green (<0.3): Healthy
- 🟡 Yellow (0.3-0.6): Moderate drift
- 🔴 Red (>0.6): High drift, refresh recommended

**Use case**: Monitor context decay over time, set alert thresholds.

#### 3. Token Budget & Knapsack View

**What it shows**: Optimization results of token selection.

**Visualizations**:
- Scatter plot: Value vs Cost (tokens) with selected/rejected coloring
- Pie chart: Token allocation (Used vs Remaining vs Rejected)
- Metrics: Efficiency %, Atoms Selected/Dropped

**Use case**: Understand why certain atoms were excluded, tune budget algorithm.

#### 4. Semantic Space Projection

**What it shows**: 2D clustering of atoms in vector space.

**Features**:
- Color-coded clusters (User Intent, System Constraints, Factual Context, Orphans)
- Symbol coding by status (Active/Archived/Dropped)
- Outlier detection

**Use case**: Identify semantic gaps, detect noisy atoms, validate clustering.

#### 5. Integrity Gaps Heatmap

**What it shows**: Topic × Time matrix of context coverage.

**Visual cues**: Red = Missing data, Green = Good coverage

**Auto-recommendations**: Suggests which topics need archival retrieval.

**Use case**: Proactive gap detection before handovers fail.

### Dashboard Architecture

```
context_observatory.py
├── Data Layer (replace with real DB calls)
│   ├── generate_mock_session_dag()
│   ├── generate_mock_drift_history()
│   ├── generate_mock_knapsack_data()
│   ├── generate_mock_vector_space()
│   └── generate_mock_gap_matrix()
│
├── Visualization Components
│   ├── render_session_dag() → Plotly Network Graph
│   ├── render_drift_dashboard() → Plotly Charts + Gauge
│   ├── render_knapsack_view() → Scatter + Pie + Metrics
│   ├── render_vector_space() → 2D Scatter Clustering
│   └── render_integrity_gaps() → Heatmap
│
└── Main App Layout (Sidebar navigation + State management)
```

### Connecting to Real Data

Replace mock functions with actual data sources:

```python
# Instead of mock data:
# data["dag"] = generate_mock_session_dag()

# Use real data:
from context_handover.storage.registry import AtomRegistry
registry = AtomRegistry()
data["dag"] = registry.build_session_graph(session_id="current")
```

### Customizing Visualizations

Add custom panels:

```python
def render_custom_view(df):
    fig = px.bar(df, x="category", y="count")
    st.plotly_chart(fig, use_container_width=True)

# Register in sidebar:
view_mode = st.sidebar.radio("Select View", 
    [..., "🆕 Custom View"])
    
if view_mode == "🆕 Custom View":
    render_custom_view(data["custom"])
```

---

## Configuration

### Configuration File

Create a `config.yaml` in your project root:

```yaml
pipeline:
  max_tokens: 4096
  drift_threshold: 0.5
  knapsack_strategy: "value_density"  # or 'greedy'
  extraction_model: "gpt-4"
  
storage:
  backend: "chromadb"  # or 'qdrant', 'memory', 'redis'
  path: "./data/atoms"
  connection_string: "localhost:6333"
  
resilience:
  enable_retries: true
  max_retries: 3
  retry_delay: 1.0
  circuit_breaker_threshold: 5
  
observability:
  tracing: true
  metrics_export: "otel"  # OpenTelemetry
  langfuse_enabled: true
  log_level: "INFO"
  
pii:
  enable_redaction: true
  redaction_patterns:
    - email
    - phone
    - credit_card
```

### Loading Configuration

```python
from context_handover import Config

# Load from file
config = Config.from_yaml("config.yaml")

# Or programmatically
config = Config(
    max_tokens=8192,
    drift_threshold=0.3,
    knapsack_strategy="value_density"
)

manager = SessionManager(session_id="session_001", config=config)
```

### Environment Variables

```bash
export CONTEXT_HANDOVER_MAX_TOKENS=4096
export CONTEXT_HANDOVER_DRIFT_THRESHOLD=0.5
export CONTEXT_HANDOVER_VECTOR_BACKEND=chromadb
export OPENAI_API_KEY="your-key-here"
```

---

## API Reference

### SessionManager

```python
class SessionManager:
    def __init__(self, session_id: str, config: Config = None)
    
    def add_message(self, role: str, content: str, metadata: dict = None)
    
    def extract_atoms(self, filters: dict = None) -> List[SemanticAtom]
    
    def build_handover_package(self) -> HandoverPackage
    
    def handover_to_new_session(self, new_session_id: str, package: HandoverPackage)
    
    def get_drift_metrics(self) -> DriftMetrics
    
    def get_token_usage(self) -> int
```

### SemanticAtom

```python
class SemanticAtom:
    atom_id: str
    atom_type: str  # FACT, DECISION, CONSTRAINT, USER_PREF, CONTEXT_REF
    content: str
    confidence_score: float
    token_count: int
    timestamp: datetime
    metadata: dict
    dependencies: List[str]
```

### HandoverPackage

```python
class HandoverPackage:
    atoms: List[SemanticAtom]
    token_count: int
    compression_ratio: float
    drift_score: float
    
    def to_json(self, filepath: str)
    def to_yaml(self, filepath: str)
    def serialize(self) -> bytes
```

---

## Troubleshooting

### Common Issues

#### Issue: "No atoms extracted"

**Cause**: Input text too short or unclear.

**Solution**: 
- Ensure messages have sufficient content (>20 words)
- Check extraction model connectivity
- Lower `min_confidence` threshold

#### Issue: "Token budget exceeded"

**Cause**: Too many atoms selected.

**Solution**:
- Increase `max_tokens` in config
- Adjust knapsack strategy to `"value_density"`
- Review atom value scores

#### Issue: "High drift detected"

**Cause**: Conversation topic changed significantly.

**Solution**:
- Trigger manual context refresh
- Archive old session and start fresh
- Adjust `drift_threshold` if appropriate

#### Issue: "Dashboard won't load"

**Cause**: Missing dependencies.

**Solution**:
```bash
pip install context-handover[viz]
streamlit run context_observatory.py
```

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

manager = SessionManager(session_id="debug_session", debug=True)
```

---

## Best Practices

### 1. Regular Handovers

Perform handovers every 10-15 messages or when drift exceeds 0.5:

```python
if len(manager.messages) % 15 == 0:
    package = manager.build_handover_package()
    # Transfer to new session
```

### 2. Monitor Drift Continuously

Set up automated drift monitoring:

```python
while conversation_active:
    metrics = manager.get_drift_metrics()
    if metrics.composite_score > 0.6:
        logger.warning("High drift! Refreshing context...")
        manager.refresh_context()
```

### 3. Optimize Token Usage

Prioritize high-value atoms:

```python
config = Config(knapsack_strategy="value_density")
# This maximizes semantic value per token
```

### 4. Archive Old Sessions

Don't delete old sessions immediately:

```python
manager.archive_session(reason="handover_complete")
# Keep for audit trail and potential rollback
```

### 5. Test with Real Workloads

Before production:

```bash
python examples/run_demo.py
pytest tests/ -v
```

### 6. Use PII Redaction

Always enable PII protection in production:

```yaml
pii:
  enable_redaction: true
```

---

## Examples

### Example 1: Multi-Session Conversation

```python
from context_handover import SessionManager

# Session 1: Initial discussion
s1 = SessionManager("session_001")
s1.add_message("user", "I want to build a mobile app for fitness tracking.")
s1.add_message("assistant", "Great! What platforms? iOS, Android, or both?")
s1.add_message("user", "Both, using React Native.")

atoms1 = s1.extract_atoms()
pkg1 = s1.build_handover_package()

# Session 2: Continuing with context
s2 = SessionManager("session_002")
s2.handover_from_package(pkg1)
s2.add_message("user", "Now let's design the database schema.")
# Previous context about React Native is preserved!
```

### Example 2: LangChain Integration

```python
from langchain.chat_models import ChatOpenAI
from context_handover.integrations.langchain import HandoverMemory

llm = ChatOpenAI(model="gpt-4")
memory = HandoverMemory(session_id="langchain_01")

chain = ConversationChain(llm=llm, memory=memory)
chain.run("Tell me about quantum computing")
chain.run("How does it relate to cryptography?")
```

### Example 3: Custom Visualization

```python
from context_observatory import render_custom_metrics
import streamlit as st

st.title("Custom Context Dashboard")
render_custom_metrics(manager.get_history())
```

---

## Contributing

We welcome contributions! See our [Contributing Guide](../CONTRIBUTING.md) for details.

### Quick Start for Contributors

```bash
git clone https://github.com/your-org/context-handover.git
cd context-handover
poetry install
pre-commit install
pytest tests/ -v
```

---

## License

MIT License - see [LICENSE](../LICENSE) for details.

---

<div align="center">

**Built with ❤️ for the future of agentic memory.** 🐱

[Report Bug](../../issues) · [Request Feature](../../issues) · [Join Discord](#)

</div>

# Context Observatory Dashboard 🎨

## ✅ Implementation Complete

I've created a comprehensive visualization dashboard for your `context_handover` system using **Streamlit** (pure Python, no web dev skills needed).

### 🚀 How to Run

```bash
streamlit run context_observatory.py
```

The dashboard is now running at: **http://localhost:8501**

---

## 📊 5 Interactive Views Included

### 1. 🗺️ Session DAG & Handover Map
- **What it shows**: Interactive graph of all atoms across sessions
- **Visual cues**:
  - Node colors = Atom types (Orange=Decision, Blue=Fact, Red=Constraint, Green=User Pref)
  - Node size = Status (Large=Missing/Error, Medium=Active, Small=Dropped)
  - Edges = Dependencies (Solid=Sequential, Dashed=Handover inheritance)
- **Use case**: Track how context flows between sessions, identify broken links

### 2. 📉 Drift & Health Dashboard
- **What it shows**: Time-series of drift metrics + current health gauge
- **Metrics tracked**:
  - KL Divergence (semantic distribution shift)
  - Cosine Distance (embedding drift)
  - Jaccard Index (vocabulary overlap)
  - Composite Score (weighted fusion)
- **Color zones**: Green (<0.3), Yellow (0.3-0.6), Red (>0.6)
- **Use case**: Monitor context decay over time, set alert thresholds

### 3. 💰 Token Budget & Knapsack View
- **What it shows**: Optimization results of token selection
- **Visualizations**:
  - Scatter plot: Value vs Cost (tokens) with selected/rejected coloring
  - Pie chart: Token allocation (Used vs Remaining vs Rejected)
  - Metrics: Efficiency %, Atoms Selected/Dropped
- **Use case**: Understand why certain atoms were excluded, tune budget algorithm

### 4. 🌌 Semantic Space Projection
- **What it shows**: 2D clustering of atoms in vector space
- **Features**:
  - Color-coded clusters (User Intent, System Constraints, Factual Context, Orphans)
  - Symbol coding by status (Active/Archived/Dropped)
  - Outlier detection
- **Use case**: Identify semantic gaps, detect noisy atoms, validate clustering

### 5. ⚠️ Integrity Gaps Heatmap
- **What it shows**: Topic × Time matrix of context coverage
- **Visual cues**: Red = Missing data, Green = Good coverage
- **Auto-recommendations**: Suggests which topics need archival retrieval
- **Use case**: Proactive gap detection before handovers fail

---

## 🔧 Architecture

```
context_observatory.py
├── Data Simulation Layer (replace with real DB calls)
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

---

## 🛠️ Customization Guide

### Connect to Real Data
Replace the mock functions with actual calls:

```python
# Instead of:
data["dag"] = generate_mock_session_dag()

# Use:
from context_handover.storage.registry import AtomRegistry
registry = AtomRegistry()
data["dag"] = registry.build_session_graph(session_id="current")
```

### Add New Visualizations
Add a new render function and register it in the sidebar:

```python
def render_new_view(df):
    fig = px.bar(df, x="category", y="count")
    st.plotly_chart(fig, use_container_width=True)

# In main():
view_mode = st.sidebar.radio("Select View", 
    [..., "🆕 New View"])
    
if view_mode == "🆕 New View":
    render_new_view(data["new"])
```

### Change Color Schemes
Modify the color dictionaries in `render_session_dag()`:

```python
type_colors = {
    "DECISION": "#YOUR_COLOR",
    "FACT": "#YOUR_COLOR",
    ...
}
```

---

## 📦 Dependencies

All installed automatically:
- `streamlit` - Web framework (Python-only)
- `plotly` - Interactive charts
- `networkx` - Graph algorithms
- `pandas` - Data manipulation
- `numpy` - Numerical operations

---

## 🎯 Next Steps

1. **Run locally**: `streamlit run context_observatory.py`
2. **Explore views**: Click through the 5 tabs in the sidebar
3. **Integrate real data**: Replace mock generators with your actual Registry/DB queries
4. **Deploy**: Share with team via `streamlit cloud` or internal server

---

## 💡 Pro Tips

- **Refresh button** regenerates mock data (useful for testing)
- **Hover over nodes/edges** to see detailed metadata
- **Resize browser** - dashboard is fully responsive
- **Export graphs**: Right-click on any Plotly chart → "Download plot as PNG"

Enjoy your new Context Observatory! 🔍
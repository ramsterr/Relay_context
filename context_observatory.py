"""
Context Observatory: Comprehensive Visualization Dashboard for context_handover
-------------------------------------------------------------------------------
This dashboard provides 5 key views:
1. Session DAG & Handover Map (Interactive Graph)
2. Drift & Decay Health (Time-series & Gauges)
3. Token Economy (Knapsack Visualization)
4. Semantic Space (Vector Clustering)
5. Integrity & Gaps (Missing Data Heatmap)

Usage:
    streamlit run context_observatory.py
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any
import random

# -----------------------------------------------------------------------------
# 1. DATA SIMULATION LAYER
# (In production, replace these functions with calls to your actual Registry/DB)
# -----------------------------------------------------------------------------

def generate_mock_session_dag() -> nx.DiGraph:
    """Generates a realistic Session DAG with atoms, dependencies, and handovers."""
    G = nx.DiGraph()
    
    # Session 1
    s1_atoms = [f"S1-A{i}" for i in range(1, 6)]
    for i, atom_id in enumerate(s1_atoms):
        atom_type = random.choice(["DECISION", "FACT", "CONSTRAINT", "USER_PREF"])
        G.add_node(atom_id, 
                   session="Session 1", 
                   type=atom_type, 
                   timestamp=datetime.now() - timedelta(hours=5-i),
                   status="active" if i < 4 else "dropped",
                   tokens=random.randint(20, 100),
                   value_score=random.uniform(0.5, 0.95))
    
    # Session 2 (Handover from S1)
    s2_atoms = [f"S2-A{i}" for i in range(1, 5)]
    for i, atom_id in enumerate(s2_atoms):
        atom_type = random.choice(["DECISION", "FACT", "CONTEXT_REF"])
        G.add_node(atom_id, 
                   session="Session 2", 
                   type=atom_type, 
                   timestamp=datetime.now() - timedelta(hours=2-i),
                   status="active",
                   tokens=random.randint(20, 80),
                   value_score=random.uniform(0.6, 0.98))
    
    # Dependencies (Edges)
    # Linear flow within sessions
    for i in range(len(s1_atoms)-1):
        G.add_edge(s1_atoms[i], s1_atoms[i+1], relation="sequential")
    
    # Handover dependency (S2 depends on specific S1 atoms)
    G.add_edge(s1_atoms[2], s2_atoms[0], relation="handover_inheritance", strength=0.9)
    G.add_edge(s1_atoms[3], s2_atoms[1], relation="handover_inheritance", strength=0.7)
    
    # Missing dependency (Broken link simulation)
    G.add_node("S2-MISSING-REF", session="Session 2", type="GHOST", status="missing", tokens=0, value_score=0)
    G.add_edge("S1-A99", "S2-MISSING-REF", relation="broken_link", strength=0.0) # S1-A99 doesn't exist
    
    return G

def generate_mock_drift_history() -> pd.DataFrame:
    """Generates historical drift metrics."""
    dates = [datetime.now() - timedelta(hours=i) for i in range(10, 0, -1)]
    data = {
        "timestamp": dates,
        "kl_divergence": np.random.uniform(0.1, 0.4, 10),
        "cosine_sim": np.random.uniform(0.7, 0.95, 10),
        "jaccard": np.random.uniform(0.2, 0.5, 10),
        "composite_drift": [] 
    }
    # Composite is weighted sum
    for i in range(10):
        score = (data["kl_divergence"][i] * 0.4 + 
                 (1 - data["cosine_sim"][i]) * 0.4 + 
                 (1 - data["jaccard"][i]) * 0.2)
        data["composite_drift"].append(score)
        
    return pd.DataFrame(data)

def generate_mock_knapsack_data() -> pd.DataFrame:
    """Simulates Knapsack Selection results."""
    items = []
    budget = 400
    current_load = 0
    
    for i in range(20):
        tokens = random.randint(30, 80)
        value = random.uniform(0.3, 0.99)
        atom_type = random.choice(["DECISION", "FACT", "FLUFF"])
        
        # Weight by type
        multiplier = 1.5 if atom_type == "DECISION" else (1.2 if atom_type == "FACT" else 0.8)
        adjusted_value = value * multiplier
        
        selected = False
        if current_load + tokens <= budget and adjusted_value > 0.5:
            selected = True
            current_load += tokens
            
        items.append({
            "atom_id": f"ATOM-{i}",
            "tokens": tokens,
            "value": adjusted_value,
            "type": atom_type,
            "selected": selected,
            "cumulative_tokens": current_load if selected else None
        })
    return pd.DataFrame(items)

def generate_mock_vector_space() -> pd.DataFrame:
    """Simulates 2D projection of semantic atoms."""
    n = 50
    df = pd.DataFrame({
        "x": np.random.randn(n),
        "y": np.random.randn(n),
        "cluster": np.random.choice(["User Intent", "System Constraints", "Factual Context", "Orphans"], n),
        "status": np.random.choice(["Active", "Archived", "Dropped"], n, p=[0.7, 0.2, 0.1])
    })
    # Make clusters slightly distinct
    df.loc[df['cluster'] == 'User Intent', 'x'] += 2
    df.loc[df['cluster'] == 'System Constraints', 'y'] += 2
    df.loc[df['cluster'] == 'Orphans', 'x'] -= 2
    df.loc[df['cluster'] == 'Orphans', 'y'] -= 2
    return df

def generate_mock_gap_matrix() -> pd.DataFrame:
    """Heatmap data for missing dependencies."""
    topics = ["Auth", "Billing", "API", "UX", "Security"]
    hours = [f"T-{i}h" for i in range(12, 0, -1)]
    
    data = np.random.uniform(0, 1, (12, 5))
    # Inject some "gaps" (very low scores)
    data[3, 1] = 0.1 # Billing gap at T-9h
    data[7, 4] = 0.05 # Security gap at T-5h
    data[9, 0] = 0.15 # Auth gap
    
    return pd.DataFrame(data, columns=topics, index=hours)

# -----------------------------------------------------------------------------
# 2. VISUALIZATION COMPONENTS
# -----------------------------------------------------------------------------

def render_session_dag(G: nx.DiGraph):
    """Renders an interactive NetworkX graph using Plotly."""
    pos = nx.spring_layout(G, k=1, iterations=50)
    
    node_traces = []
    edge_traces = []
    
    # Color mapping
    type_colors = {
        "DECISION": "#FF9900", "FACT": "#3399FF", 
        "CONSTRAINT": "#FF3333", "USER_PREF": "#33FF33",
        "CONTEXT_REF": "#9933FF", "GHOST": "#CCCCCC"
    }
    status_colors = {"active": "#00CC00", "dropped": "#FF6666", "missing": "#999999"}
    
    # Edges
    edge_x, edge_y, edge_text = [], [], []
    for u, v, data in G.edges(data=True):
        if u in pos and v in pos:
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            edge_text.append(f"{u} → {v}<br>{data.get('relation', 'link')}")
    
    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines', 
                            line=dict(width=0.5, color='#888'), hoverinfo='text',
                            text=edge_text)
    
    # Nodes
    node_x, node_y, node_text, node_colors, node_sizes = [], [], [], [], []
    for node in G.nodes():
        if node in pos:
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            
            info = G.nodes[node]
            label = f"{node}<br>Type: {info.get('type', 'Unknown')}<br>Status: {info.get('status', '?')}"
            node_text.append(label)
            
            # Color by status if missing/dropped, else by type
            if info.get('status') == 'missing':
                nc = "#FF0000"
                ns = 30
            elif info.get('status') == 'dropped':
                nc = "#CCCCCC"
                ns = 15
            else:
                nc = type_colors.get(info.get('type'), "#000000")
                ns = 25
                
            node_colors.append(nc)
            node_sizes.append(ns)
            
    node_trace = go.Scatter(x=node_x, y=node_y, mode='markers+text',
                            marker=dict(size=node_sizes, color=node_colors, line_width=2),
                            text=node_text, text_position="top center",
                            hoverinfo='text', hovertext=node_text)
    
    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(showlegend=False, hovermode='closest',
                                     margin=dict(b=20,l=5,r=5,t=40),
                                     title="Session DAG & Handover Flow",
                                     xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                     yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)))
    st.plotly_chart(fig, use_container_width=True)

def render_drift_dashboard(df: pd.DataFrame):
    """Renders drift metrics and health gauges."""
    col1, col2 = st.columns(2)
    
    with col1:
        # Time series
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['composite_drift'], name='Composite Drift', line=dict(color='red', width=3)))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['kl_divergence'], name='KL Divergence', line=dict(dash='dot')))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=1-df['cosine_sim'], name='Cosine Distance', line=dict(dash='dot')))
        
        fig.update_layout(title="Drift Metrics Over Time", yaxis_title="Score (0-1)", height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Current Status Gauge
        current_drift = df['composite_drift'].iloc[-1]
        gauge = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = current_drift,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Current Context Health", 'font': {'size': 24}},
            delta = {'reference': 0.3, 'increasing': {'color': "RebeccaPurple"}},
            gauge = {
                'axis': {'range': [None, 1]},
                'bar': {'color': "darkblue" if current_drift < 0.3 else "orange" if current_drift < 0.6 else "red"},
                'steps': [
                    {'range': [0, 0.3], 'color': "#e0ffe0"},
                    {'range': [0.3, 0.6], 'color': "#ffffe0"},
                    {'range': [0.6, 1], 'color': "#ffe0e0"}],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 0.8}}))
        st.plotly_chart(gauge, use_container_width=True)

def render_knapsack_view(df: pd.DataFrame):
    """Visualizes Token Budget and Selection."""
    selected = df[df['selected']]
    rejected = df[~df['selected']]
    
    total_tokens = df['tokens'].sum()
    used_tokens = selected['tokens'].sum()
    budget = 400
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Scatter: Value vs Cost
        fig = px.scatter(df, x="tokens", y="value", color="selected", 
                         hover_data=["atom_id", "type"],
                         title="Knapsack Optimization: Value vs Token Cost",
                         labels={"tokens": "Token Cost", "value": "Semantic Value"},
                         color_discrete_map={True: "#00CC00", False: "#FF6666"})
        
        # Add budget line approximation (visual aid)
        fig.add_shape(type="line", x0=budget, y0=0, x1=budget, y1=1, 
                      line=dict(color="Black", dash="dash"), name="Budget Limit")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Pie Chart
        fig = go.Figure(data=[go.Pie(labels=["Used Tokens", "Remaining Budget", "Rejected (Low Value)"],
                                     values=[used_tokens, budget-used_tokens, rejected['tokens'].sum()],
                                     hole=.3)])
        fig.update_layout(title="Token Allocation")
        st.plotly_chart(fig, use_container_width=True)
        
        st.metric("Efficiency", f"{used_tokens/budget:.1%}")
        st.metric("Atoms Selected", len(selected))
        st.metric("Atoms Dropped", len(rejected))

def render_vector_space(df: pd.DataFrame):
    """2D Projection of Semantic Atoms."""
    fig = px.scatter(df, x="x", y="y", color="cluster", symbol="status",
                     title="Semantic Space Projection (t-SNE/UMAP Simulation)",
                     hover_data=["status"],
                     color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_traces(marker=dict(size=12, line=dict(width=2, color='DarkSlateGrey')))
    st.plotly_chart(fig, use_container_width=True)

def render_integrity_gaps(df: pd.DataFrame):
    """Heatmap of context coverage."""
    fig = px.imshow(df, text_auto=".2f", aspect="auto",
                    title="Context Integrity Heatmap (Dark = Missing Data/Gaps)",
                    color_continuous_scale="RdYlGn_r") # Red is bad (low score)
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# 3. MAIN APP LAYOUT
# -----------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Context Observatory", layout="wide", page_icon="🔍")
    
    st.title("🔍 Context Observatory")
    st.markdown("""
    **Real-time visibility into semantic continuity, drift, and token optimization.**
    Select a view below to analyze different dimensions of your context handover system.
    """)
    
    # Sidebar Controls
    st.sidebar.header("Controls")
    view_mode = st.sidebar.radio("Select View", 
        ["🗺️ Session DAG", "📉 Drift & Health", "💰 Token Budget", "🌌 Semantic Space", "⚠️ Integrity Gaps"])
    
    refresh = st.sidebar.button("🔄 Refresh Data")
    
    # Load Data (Simulated)
    if refresh or 'data' not in st.session_state:
        st.session_state.data = {
            "dag": generate_mock_session_dag(),
            "drift": generate_mock_drift_history(),
            "knapsack": generate_mock_knapsack_data(),
            "vector": generate_mock_vector_space(),
            "gaps": generate_mock_gap_matrix()
        }
    
    data = st.session_state.data
    
    # Render Views
    if view_mode == "🗺️ Session DAG":
        st.header("Session Dependency Graph")
        st.info("Shows atom flow, handover inheritance, and broken links (Red nodes).")
        render_session_dag(data["dag"])
        
        st.subheader("Node Statistics")
        cols = st.columns(4)
        nodes = list(data["dag"].nodes(data=True))
        cols[0].metric("Total Atoms", len(nodes))
        cols[1].metric("Active", sum(1 for n,d in nodes if d.get('status')=='active'))
        cols[2].metric("Dropped", sum(1 for n,d in nodes if d.get('status')=='dropped'))
        cols[3].metric("Missing/Broken", sum(1 for n,d in nodes if d.get('status')=='missing'))
        
    elif view_mode == "📉 Drift & Health":
        st.header("Context Drift & Decay")
        st.warning("High drift indicates the current context may no longer represent the original intent.")
        render_drift_dashboard(data["drift"])
        
    elif view_mode == "💰 Token Budget":
        st.header("Token Economy & Knapsack Selection")
        st.success("Optimizing semantic value per token within the 4k window.")
        render_knapsack_view(data["knapsack"])
        
    elif view_mode == "🌌 Semantic Space":
        st.header("Vector Space Clustering")
        st.info("Visualizes how atoms group semantically. Outliers may indicate noise.")
        render_vector_space(data["vector"])
        
    elif view_mode == "⚠️ Integrity Gaps":
        st.header("Missing Data & Coverage Analysis")
        st.error("Dark red cells indicate topics/timeframes with missing context dependencies.")
        render_integrity_gaps(data["gaps"])
        
        st.subheader("Recommendations")
        st.write("- **Billing Topic**: Gap detected at T-9h. Consider retrieving archival memory.")
        st.write("- **Security Topic**: Gap detected at T-5h. Verify handover package completeness.")

if __name__ == "__main__":
    main()
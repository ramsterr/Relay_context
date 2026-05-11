#!/usr/bin/env python3
"""
Demo: Context Handover System
Run this to see the system in action.

Setup:
  pip install -r requirements.txt
  export OPENAI_API_KEY=sk-...
"""
from __future__ import annotations
import os
import sys
import json

sys.path.insert(0, "src")

from context_handover import ContextManager
from context_handover.core.checkpoint import CheckpointLevel
from context_handover.measurement.drift import DriftMeasurementSuite


def print_section(title):
    print(f"\n{'='*50}")
    print(f" {title}")
    print('='*50)


def main():
    print_section("Context Handover System Demo")

    api_key = os.environ.get("OPENAI_API_KEY")
    langfuse_pub = os.environ.get("LANGFUSE_PUBLIC_KEY")
    langfuse_sec = os.environ.get("LANGFUSE_SECRET_KEY")

    print(f"\nOpenAI API: {'✓ configured' if api_key else '✗ not set (using fallback)'}")
    print(f"Langfuse:   {'✓ configured' if langfuse_pub else '✗ not set'}")

    manager = ContextManager(
        langfuse_public_key=langfuse_pub,
        langfuse_secret_key=langfuse_sec,
        max_tokens=8000,
    )

    print(f"\n[1] Created session: {manager.current_session.session_id}")
    print(f"    Trace ID: {manager.current_session.trace_context.root_trace_id}")

    messages = [
        "We need to implement JWT authentication for our API.",
        "Decision: we'll use RS256 algorithm for signing tokens.",
        "Constraint: all tokens must expire after 1 hour.",
        "Question: how should we handle refresh tokens?",
        "Task: write middleware to validate JWT tokens.",
        "Decision: use asyncio for async operations.",
        "Constraint: must support both HS256 and RS256.",
    ]

    print(f"\n[2] Adding {len(messages)} messages...")
    for i, msg in enumerate(messages, 1):
        checkpoint = manager.add_message(msg)
        status = f" → checkpoint: {checkpoint.value}" if checkpoint else ""
        print(f"    {i}. {msg[:45]}...{status}")

    print_section("Session State")
    summary = manager.get_context_summary()
    print(f"Session ID:  {summary['session_id']}")
    print(f"Total Atoms: {summary['total_atoms']}")
    print(f"By Type:    {json.dumps(summary['by_type'], indent=4)}")
    print(f"Token Count: {summary['token_count']} / {summary['max_tokens']} ({summary['utilization']:.1%})")

    print_section("Drift Analysis")
    drift = manager.compute_drift()
    print(f"KL Structural: {drift.get('kl_structural', 0):.4f}")
    print(f"Jaccard:       {drift.get('jaccard', 1):.4f}")
    print(f"Composite:     {drift.get('composite', 0):.4f}")
    print(f"Verdict:       {drift.get('verdict', 'UNKNOWN')}")

    print_section("Handover Package")
    package = manager.build_handover_package()
    print(f"Selected Atoms: {len(package.selected_atoms)} / {len(manager.registry.get_active_atoms())}")
    print(f"Total Tokens:   {package.total_tokens}")
    print(f"\nContext to hand over:")
    print(package.to_context_string())

    print_section("Create Checkpoint")
    checkpoint = manager.create_checkpoint(CheckpointLevel.STANDARD)
    print(f"Created: {checkpoint.checkpoint_id}")
    print(f"Level:   {checkpoint.level.value}")
    print(f"Atoms:   {checkpoint.atom_count}")

    print_section("Session Handover")
    old_id, new_id = manager.handover_to_new_session()
    print(f"Handover: {old_id} → {new_id}")
    print(f"Parent sessions: {manager.current_session.trace_context.parent_sessions}")

    new_summary = manager.get_context_summary()
    print(f"\nNew session atoms: {new_summary['total_atoms']}")

    print_section("Loss Ledger")
    ledger_summary = manager.ledger.summary()
    print(f"Total Loss Events: {ledger_summary['total_loss_events']}")
    print(f"Avg Salience Lost: {ledger_summary.get('avg_salience_lost', 0)}")

    print_section("All Done!")
    print("""
Next steps:
  1. Set OPENAI_API_KEY to enable LLM-based atom extraction
  2. Set LANGFUSE_PUBLIC_KEY/SECRET for observability
  3. Try the async pipeline: from context_handover.pipeline import AsyncContextPipeline
  4. Add your own messages and see how atoms are extracted
""")


if __name__ == "__main__":
    main()
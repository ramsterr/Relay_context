from __future__ import annotations
import os
import sys
sys.path.insert(0, "src")

from context_handover.session import ContextManager
from context_handover.core.checkpoint import CheckpointLevel


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Warning: OPENAI_API_KEY not set - using mock mode")

    langfuse_pub = os.environ.get("LANGFUSE_PUBLIC_KEY")
    langfuse_sec = os.environ.get("LANGFUSE_SECRET_KEY")

    manager = ContextManager(
        langfuse_public_key=langfuse_pub,
        langfuse_secret_key=langfuse_sec,
        max_tokens=8000,
    )

    print(f"Created session: {manager.current_session.session_id}")

    messages = [
        "We need to implement JWT authentication for the API.",
        "Decision: we'll use RS256 for signing tokens.",
        "Constraint: tokens must expire after 1 hour.",
        "Question: how do we handle refresh tokens?",
        "Task: write the middleware to validate tokens.",
    ]

    for msg in messages:
        checkpoint_triggered = manager.add_message(msg)
        print(f"Added: {msg[:40]}...")
        if checkpoint_triggered:
            print(f"  → Checkpoint triggered: {checkpoint_triggered.value}")

    summary = manager.get_context_summary()
    print(f"\n--- Session Summary ---")
    print(f"Atoms: {summary['total_atoms']}")
    print(f"By type: {summary['by_type']}")
    print(f"Utilization: {summary['utilization']:.1%}")

    print("\n--- Drift Analysis ---")
    drift = manager.compute_drift()
    print(f"Composite: {drift['composite']:.3f}")
    print(f"Verdict: {drift['verdict']}")

    print("\n--- Handover Package ---")
    package = manager.build_handover_package()
    print(f"Selected atoms: {len(package.selected_atoms)}")
    print(f"Total tokens: {package.total_tokens}")
    print(package.to_context_string()[:200])

    print("\n--- Loss Ledger ---")
    print(manager.ledger.summary())

    print("\n--- New Session Handover ---")
    old_id, new_id = manager.handover_to_new_session()
    print(f"Handover: {old_id} → {new_id}")

    new_summary = manager.get_context_summary()
    print(f"New session atoms: {new_summary['total_atoms']}")


if __name__ == "__main__":
    main()
from __future__ import annotations
from typing import Optional, Any, List
import logging
from ..core.atoms import SemanticAtom
logger = logging.getLogger(__name__)

try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.warning("Langfuse not installed")


class ContextHandoverObserver:
    def __init__(self, public_key: Optional[str] = None, secret_key: Optional[str] = None):
        if not LANGFUSE_AVAILABLE:
            self.client = None
            return

        self.client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
        ) if public_key and secret_key else None

    def trace_handover(
        self,
        session_from: str,
        session_to: str,
        atoms: List[SemanticAtom],
        drift_score: Optional[float] = None,
    ):
        if not self.client:
            logger.debug("Langfuse not configured - skipping trace")
            return

        try:
            generation = self.client.generation(
                name="context_handover",
                metadata={
                    "session_from": session_from,
                    "session_to": session_to,
                    "atom_count": len(atoms),
                    "drift_score": drift_score,
                }
            )

            for atom in atoms:
                generation.update(
                    output=atom.content,
                    metadata={
                        "atom_type": atom.atom_type.value,
                        "atom_id": atom.atom_id,
                        "salience": atom.salience,
                        "propagation_score": atom.propagation_score,
                    }
                )

            generation.end()
            logger.info(f"Traced handover {session_from} → {session_to} with {len(atoms)} atoms")

        except Exception as e:
            logger.error(f"Failed to trace handover: {e}")

    def trace_extraction(
        self,
        session_id: str,
        atom_count: int,
        extraction_time_ms: float,
    ):
        if not self.client:
            return

        try:
            self.client.track(
                name="atom_extraction",
                metadata={
                    "session_id": session_id,
                    "atom_count": atom_count,
                    "extraction_time_ms": extraction_time_ms,
                }
            )
        except Exception as e:
            logger.error(f"Failed to trace extraction: {e}")

    def trace_checkpoint(
        self,
        checkpoint_id: str,
        session_id: str,
        level: str,
        atom_count: int,
        drift_score: Optional[float] = None,
    ):
        if not self.client:
            return

        try:
            self.client.generation(
                name=f"checkpoint_{level}",
                metadata={
                    "checkpoint_id": checkpoint_id,
                    "session_id": session_id,
                    "atom_count": atom_count,
                    "drift_score": drift_score,
                }
            ).end()
        except Exception as e:
            logger.error(f"Failed to trace checkpoint: {e}")
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
import uuid
from .core.atoms import SemanticAtom, AtomType, AtomStatus
from .core.registry import AtomRegistry
from .core.budget import TokenBudgetManager, HandoverPackage
from .core.checkpoint import CheckpointManager, Checkpoint, CheckpointLevel
from .measurement.drift import DriftMeasurementSuite
from .measurement.ledger import LossLedger
from .pipeline.trace_context import LLMTraceContext, SessionDAG
from .instrumentation.langfuse_integration import ContextHandoverObserver
from .instrumentation.otel_instrumentation import ContextInstrumentor
import logging
logger = logging.getLogger(__name__)


@dataclass
class Session:
    session_id: str
    trace_context: LLMTraceContext
    messages: List[dict] = field(default_factory=list)
    atom_ids: List[str] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    created_at: float = 0.0


class ContextManager:
    def __init__(
        self,
        model_client=None,
        embedding_client=None,
        langfuse_public_key: Optional[str] = None,
        langfuse_secret_key: Optional[str] = None,
        jaeger_endpoint: Optional[str] = None,
        max_tokens: int = 8000,
    ):
        self.session_id = str(uuid.uuid4())[:8]
        self.model_client = model_client
        self.embedding_client = embedding_client

        self.registry = AtomRegistry(embedding_client=embedding_client)
        self.budget_manager = TokenBudgetManager()
        self.drift_suite = DriftMeasurementSuite()
        self.ledger = LossLedger()
        self.checkpoint_manager = CheckpointManager(self.budget_manager)
        self.session_dag = SessionDAG()

        self.observer = ContextHandoverObserver(langfuse_public_key, langfuse_secret_key)
        self.instrumentor = ContextInstrumentor(jaeger_endpoint=jaeger_endpoint)

        self.current_session = self._create_session()
        self.max_tokens = max_tokens
        self.current_token_count = 0

    def _create_session(self, parent_ids: List[str] = None) -> Session:
        trace_ctx = self.session_dag.create_session(parent_ids)
        return Session(
            session_id=trace_ctx.session_id,
            trace_context=trace_ctx,
        )

    def add_message(self, content: str) -> Optional[CheckpointLevel]:
        self.current_session.messages.append({
            "role": "user",
            "content": content,
        })

        from .extraction import AtomExtractor
        if self.model_client:
            extractor = AtomExtractor(self.model_client)
            candidates = extractor.extract(content)
        else:
            extractor = AtomExtractor(None)
            candidates = extractor._regex_extract(content)

        for candidate in candidates:
            self.registry.insert_or_update(
                candidate,
                self.current_session.session_id,
                len(self.current_session.messages) - 1,
                len(self.current_session.messages),
            )

        self.current_token_count = self.budget_manager.count_messages(
            self.current_session.messages
        )

        return self.checkpoint_manager.evaluate(
            self.current_token_count,
            self.max_tokens
        )

    def create_checkpoint(self, level: CheckpointLevel) -> Checkpoint:
        checkpoint_id = str(uuid.uuid4())[:8]
        active_atoms = self.registry.get_active_atoms()
        atom_count = len(active_atoms)

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            session_id=self.current_session.session_id,
            level=level,
            atom_count=atom_count,
            token_count=self.current_token_count,
        )
        self.current_session.checkpoints.append(checkpoint)
        self.session_dag.add_checkpoint(
            self.current_session.session_id,
            {"checkpoint_id": checkpoint_id, "level": level.value, "atom_count": atom_count}
        )
        self.current_session.trace_context.set_checkpoint(checkpoint_id)
        return checkpoint

    def handover_to_new_session(self, parent_ids: List[str] = None) -> tuple[str, str]:
        old_session_id = self.current_session.session_id
        new_session = self._create_session(parent_ids or [old_session_id])

        self.current_session = new_session
        self.current_token_count = 0

        return old_session_id, new_session.session_id

    def compute_drift(self) -> dict:
        active_atoms = self.registry.get_active_atoms()
        if not active_atoms:
            return {"composite": 0.0, "verdict": "NO_ATOMS"}

        model_dist = {
            "entity": 0.3,
            "decision": 0.25,
            "constraint": 0.2,
            "task": 0.15,
            "question": 0.1,
        }

        kl_structural = self.drift_suite.kl_structural(active_atoms, model_dist)
        atom_ids = set(active_atoms.keys())
        jaccard = self.drift_suite.jaccard(atom_ids, atom_ids)

        composite = self.drift_suite.composite(kl_structural, jaccard)
        verdict = self.drift_suite.verdict(composite)

        return {
            "kl_structural": kl_structural,
            "jaccard": jaccard,
            "composite": composite,
            "verdict": verdict,
        }

    def build_handover_package(self) -> HandoverPackage:
        active_atoms = list(self.registry.get_active_atoms().values())
        package = HandoverPackage(active_atoms, self.budget_manager, self.max_tokens)
        package.build()
        return package

    def record_handover_loss(
        self,
        included_ids: set,
        retained_ids: set,
        session_from: str,
        session_to: str,
    ):
        all_atoms = self.registry.get_active_atoms()
        self.ledger.record_handover(
            all_atoms,
            included_ids,
            retained_ids,
            session_from,
            session_to,
        )

    def get_context_summary(self) -> dict:
        active_atoms = self.registry.get_active_atoms()
        by_type = {}
        for atom in active_atoms.values():
            t = atom.atom_type.value
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "session_id": self.current_session.session_id,
            "total_atoms": len(active_atoms),
            "by_type": by_type,
            "token_count": self.current_token_count,
            "max_tokens": self.max_tokens,
            "utilization": self.current_token_count / self.max_tokens if self.max_tokens > 0 else 0,
            "loss_summary": self.ledger.summary(),
        }
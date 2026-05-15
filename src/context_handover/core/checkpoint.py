from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import logging
logger = logging.getLogger(__name__)


class CheckpointLevel(Enum):
    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class CheckpointTrigger:
    level: CheckpointLevel
    utilization_threshold: float
    description: str


TRIGGERS = {
    CheckpointLevel.LIGHTWEIGHT: CheckpointTrigger(
        level=CheckpointLevel.LIGHTWEIGHT,
        utilization_threshold=0.50,
        description="50-75% utilization - lightweight checkpoint",
    ),
    CheckpointLevel.STANDARD: CheckpointTrigger(
        level=CheckpointLevel.STANDARD,
        utilization_threshold=0.75,
        description="75-85% utilization - standard checkpoint",
    ),
    CheckpointLevel.DEEP: CheckpointTrigger(
        level=CheckpointLevel.DEEP,
        utilization_threshold=0.85,
        description=">85% utilization - deep checkpoint with full drift analysis",
    ),
}


class CheckpointManager:
    def __init__(self, token_budget_manager):
        self.token_manager = token_budget_manager
        self.checkpoint_history: list = []

    def evaluate(
        self,
        current_tokens: int,
        max_tokens: int,
    ) -> Optional[CheckpointLevel]:
        if max_tokens <= 0:
            return None

        utilization = current_tokens / max_tokens

        if utilization < 0.50:
            return None
        elif utilization < 0.75:
            level = CheckpointLevel.LIGHTWEIGHT
        elif utilization < 0.85:
            level = CheckpointLevel.STANDARD
        else:
            level = CheckpointLevel.DEEP

        logger.info(f"Checkpoint triggered: {level.value} at {utilization:.1%} utilization")
        return level

    def should_handover(
        self,
        current_tokens: int,
        max_tokens: int,
        drift_score: Optional[float] = None,
    ) -> bool:
        utilization = current_tokens / max_tokens if max_tokens > 0 else 0

        if drift_score is not None and drift_score > 0.45:
            logger.warning(f"Critical drift detected ({drift_score:.2f}) - forcing handover")
            return True

        if utilization > 0.90:
            return True

        return False


class Checkpoint:
    def __init__(
        self,
        checkpoint_id: str,
        session_id: str,
        level: CheckpointLevel,
        atom_count: int,
        token_count: int,
        drift_score: Optional[float] = None,
    ):
        self.checkpoint_id = checkpoint_id
        self.session_id = session_id
        self.level = level
        self.atom_count = atom_count
        self.token_count = token_count
        self.drift_score = drift_score
        self.timestamp = None
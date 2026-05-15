from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import hashlib
import numpy as np


class AtomType(Enum):
    ENTITY = "entity"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    QUESTION = "question"
    TASK = "task"
    BELIEF = "belief"
    RELATION = "relation"


class AtomStatus(Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUSPENDED = "suspended"
    CONTESTED = "contested"


@dataclass
class SemanticAtom:
    atom_id: str
    atom_type: AtomType
    content: str
    canonical_form: str
    embedding: Optional[np.ndarray] = None
    salience: float = 0.5
    confidence: float = 0.5
    origin_session: str = ""
    origin_message: int = 0
    last_seen_session: str = ""
    last_seen_message: int = 0
    sessions_present: list[str] = field(default_factory=list)
    handover_count: int = 0
    loss_events: int = 0
    status: AtomStatus = AtomStatus.ACTIVE
    related_atoms: list[str] = field(default_factory=list)
    file_path: Optional[str] = None
    symbol_name: Optional[str] = None
    ast_hash: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)

    @staticmethod
    def make_id(canonical_form: str, atom_type: AtomType) -> str:
        raw = f"{atom_type.value}:{canonical_form.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def propagation_score(self) -> float:
        if self.handover_count == 0:
            return self.salience * 0.5
        survival_rate = 1.0 - (self.loss_events / max(self.handover_count, 1))
        return survival_rate * self.salience

    def update_salience(self, current_msg_idx: int, total_messages: int):
        mention_count = len(self.sessions_present) + 1
        recency = current_msg_idx / max(total_messages, 1)
        frequency_score = min(mention_count / 10.0, 1.0)
        self.salience = 0.6 * recency + 0.4 * frequency_score

    def apply_session_decay(self, sessions_since_seen: int):
        if self.atom_type in {AtomType.DECISION, AtomType.CONSTRAINT}:
            return
        self.salience *= (0.9 ** sessions_since_seen)


@dataclass
class CodeAtom(SemanticAtom):
    file_path: Optional[str] = None
    symbol_name: Optional[str] = None
    ast_hash: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.atom_type = AtomType.ENTITY
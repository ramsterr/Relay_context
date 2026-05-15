from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import logging
from ..core.atoms import SemanticAtom, AtomStatus
logger = logging.getLogger(__name__)


@dataclass
class LossEvent:
    atom_id: str
    content: str
    atom_type: str
    salience: float
    loss_type: str
    session_from: str
    session_to: str


class LossLedger:
    def __init__(self):
        self.events: list[LossEvent] = []

    def record_handover(
        self,
        all_atoms: dict[str, SemanticAtom],
        included_atom_ids: set,
        retained_atom_ids: set,
        session_from: str,
        session_to: str,
    ):
        all_ids = set(all_atoms.keys())
        dropped_ids = all_ids - included_atom_ids
        sent_not_retained = included_atom_ids - retained_atom_ids

        for atom_id in dropped_ids:
            atom = all_atoms.get(atom_id)
            if atom:
                atom.loss_events += 1
                atom.handover_count += 1
                self.events.append(LossEvent(
                    atom_id=atom_id,
                    content=atom.content,
                    atom_type=atom.atom_type.value,
                    salience=atom.salience,
                    loss_type="not_included",
                    session_from=session_from,
                    session_to=session_to,
                ))

        for atom_id in sent_not_retained:
            atom = all_atoms.get(atom_id)
            if atom:
                atom.loss_events += 1
                atom.handover_count += 1
                self.events.append(LossEvent(
                    atom_id=atom_id,
                    content=atom.content,
                    atom_type=atom.atom_type.value,
                    salience=atom.salience,
                    loss_type="sent_but_dropped",
                    session_from=session_from,
                    session_to=session_to,
                ))

        survived_ids = retained_atom_ids & included_atom_ids
        for atom_id in survived_ids:
            atom = all_atoms.get(atom_id)
            if atom:
                atom.handover_count += 1

        logger.info(
            f"Handover {session_from}→{session_to}: "
            f"{len(dropped_ids)} not included, "
            f"{len(sent_not_retained)} sent but dropped, "
            f"{len(survived_ids)} survived"
        )

    def summary(self) -> dict:
        total = len(self.events)
        if total == 0:
            return {"total_loss_events": 0, "avg_salience_lost": 0.0}

        by_loss: dict[str, int] = {}
        by_atom_type: dict[str, int] = {}

        for e in self.events:
            by_loss[e.loss_type] = by_loss.get(e.loss_type, 0) + 1
            by_atom_type[e.atom_type] = by_atom_type.get(e.atom_type, 0) + 1

        avg_salience = sum(e.salience for e in self.events) / total
        worst = sorted(self.events, key=lambda e: e.salience, reverse=True)[:5]

        return {
            "total_loss_events": total,
            "by_loss_type": by_loss,
            "by_atom_type": by_atom_type,
            "avg_salience_lost": round(avg_salience, 4),
            "highest_value_losses": [
                {"content": e.content, "salience": e.salience, "type": e.loss_type}
                for e in worst
            ],
        }

    def get_loss_rate(self) -> float:
        if not self.events:
            return 0.0
        total = len(self.events)
        not_included = sum(1 for e in self.events if e.loss_type == "not_included")
        return not_included / total
from __future__ import annotations
from typing import Optional, List
import logging
logger = logging.getLogger(__name__)

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed — falling back to word estimate")


class TokenBudgetManager:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name
        self.encoder = self._load_encoder(model_name) if TIKTOKEN_AVAILABLE else None

    def _load_encoder(self, model_name: str):
        try:
            try:
                return tiktoken.encoding_for_model(model_name)
            except KeyError:
                logger.warning(f"No encoder for {model_name}, using cl100k_base")
                return tiktoken.get_encoding("cl100k_base")
        except ImportError:
            return None

    def count(self, text: str) -> int:
        if self.encoder is None:
            return int(len(text.split()) * 1.4)
        return len(self.encoder.encode(text))

    def count_messages(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += self.count(msg.get("content", ""))
            total += 4
        total += 2
        return total

    def fit_atoms_to_budget(
        self,
        ranked_atoms: list,
        token_budget: int,
        overhead_per_atom: int = 15,
    ) -> list:
        from .atoms import AtomType, AtomStatus
        mandatory_types = {AtomType.DECISION, AtomType.CONSTRAINT}
        selected = []
        tokens_used = 0

        for atom in ranked_atoms:
            if atom.atom_type in mandatory_types and atom.status == AtomStatus.ACTIVE:
                cost = self.count(atom.content) + overhead_per_atom
                selected.append(atom)
                tokens_used += cost

        remaining = token_budget - tokens_used
        for atom in ranked_atoms:
            if atom in selected:
                continue
            if atom.status != AtomStatus.ACTIVE:
                continue
            cost = self.count(atom.content) + overhead_per_atom
            if cost <= remaining:
                selected.append(atom)
                remaining -= cost

        logger.debug(
            f"Budget fit: {len(selected)}/{len(ranked_atoms)} atoms "
            f"in {tokens_used + (token_budget - remaining)}/{token_budget} tokens"
        )
        return selected


class HandoverPackage:
    def __init__(
        self,
        atoms: list,
        budget_manager: TokenBudgetManager,
        max_tokens: int = 8000,
    ):
        self.atoms = atoms
        self.budget_manager = budget_manager
        self.max_tokens = max_tokens
        self.selected_atoms: list = []
        self.total_tokens: int = 0

    def build(self) -> list:
        ranked = sorted(self.atoms, key=lambda a: a.propagation_score, reverse=True)
        self.selected_atoms = self.budget_manager.fit_atoms_to_budget(
            ranked, self.max_tokens
        )
        self.total_tokens = sum(
            self.budget_manager.count(a.content) for a in self.selected_atoms
        )
        return self.selected_atoms

    def to_context_string(self) -> str:
        if not self.selected_atoms:
            return "No context atoms available."
        lines = ["## Context Atoms\n"]
        for atom in self.selected_atoms:
            lines.append(f"- [{atom.atom_type.value}] {atom.content}")
        return "\n".join(lines)
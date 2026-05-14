from __future__ import annotations
from typing import Optional, List, Tuple
import logging
logger = logging.getLogger(__name__)

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed — falling back to word estimate")


class TokenBudgetManager:
    """
    Manages token budgeting for context atoms using optimized selection algorithms.
    
    Supports both greedy selection (fast) and bounded knapsack optimization (optimal).
    """
    
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
        """Count tokens in text using tiktoken or word-based estimation."""
        if self.encoder is None:
            return int(len(text.split()) * 1.4)
        return len(self.encoder.encode(text))

    def count_messages(self, messages: list[dict]) -> int:
        """Count tokens for a list of message dictionaries."""
        total = 0
        for msg in messages:
            total += self.count(msg.get("content", ""))
            total += 4
        total += 2
        return total

    def _compute_atom_value(self, atom) -> float:
        """
        Compute semantic value score for an atom.
        Combines propagation_score with type-based priority weighting.
        """
        from .atoms import AtomType
        
        # Base value from propagation score (0-1 range)
        base_value = atom.propagation_score
        
        # Type-based multipliers for critical context types
        # Higher weights for more semantically important atom types
        type_weights = {
            AtomType.DECISION: 1.5,      # Critical decisions
            AtomType.CONSTRAINT: 1.4,    # Hard constraints
            AtomType.TASK: 1.3,          # Action items
            AtomType.QUESTION: 1.2,      # Open questions
            AtomType.BELIEF: 1.1,        # Beliefs/assumptions
            AtomType.ENTITY: 1.0,        # Entities/facts
            AtomType.RELATION: 1.0,      # Relationships
        }
        
        weight = type_weights.get(atom.atom_type, 1.0)
        return base_value * weight

    def fit_atoms_to_budget(
        self,
        ranked_atoms: list,
        token_budget: int,
        overhead_per_atom: int = 15,
        use_knapsack: bool = True,
    ) -> list:
        """
        Select atoms to maximize semantic value within token budget.
        
        Args:
            ranked_atoms: List of candidate atoms
            token_budget: Maximum token limit
            overhead_per_atom: Token overhead per atom for formatting
            use_knapsack: If True, use bounded knapsack optimization; else greedy
            
        Returns:
            List of selected atoms optimized for value/token ratio
        """
        from .atoms import AtomType, AtomStatus
        
        if not ranked_atoms:
            return []
        
        # Separate mandatory atoms (always included)
        mandatory_atoms = [
            atom for atom in ranked_atoms
            if atom.atom_type in {AtomType.DECISION, AtomType.CONSTRAINT}
            and atom.status == AtomStatus.ACTIVE
        ]
        
        # Calculate cost of mandatory atoms
        mandatory_tokens = sum(
            self.count(atom.content) + overhead_per_atom
            for atom in mandatory_atoms
        )
        
        if mandatory_tokens > token_budget:
            logger.warning(
                f"Mandatory atoms ({mandatory_tokens} tokens) exceed budget ({token_budget}). "
                "Truncating mandatory set."
            )
            # Fallback: select most critical mandatory atoms only
            mandatory_atoms = sorted(
                mandatory_atoms,
                key=lambda a: self._compute_atom_value(a),
                reverse=True
            )
            selected = []
            tokens_used = 0
            for atom in mandatory_atoms:
                cost = self.count(atom.content) + overhead_per_atom
                if tokens_used + cost <= token_budget:
                    selected.append(atom)
                    tokens_used += cost
            return selected
        
        remaining_budget = token_budget - mandatory_tokens
        
        # Get optional atoms
        optional_atoms = [
            atom for atom in ranked_atoms
            if atom not in mandatory_atoms
            and atom.status == AtomStatus.ACTIVE
        ]
        
        if not optional_atoms:
            return mandatory_atoms
        
        if use_knapsack:
            optional_selected = self._knapsack_select(
                optional_atoms, remaining_budget, overhead_per_atom
            )
        else:
            optional_selected = self._greedy_select(
                optional_atoms, remaining_budget, overhead_per_atom
            )
        
        selected = mandatory_atoms + optional_selected
        
        total_tokens = sum(
            self.count(atom.content) + overhead_per_atom
            for atom in selected
        )
        
        logger.info(
            f"Budget optimization: {len(selected)}/{len(ranked_atoms)} atoms "
            f"in {total_tokens}/{token_budget} tokens "
            f"(knapsack={use_knapsack}, value={sum(self._compute_atom_value(a) for a in selected):.2f})"
        )
        
        return selected

    def _greedy_select(
        self,
        atoms: list,
        budget: int,
        overhead: int,
    ) -> list:
        """Greedy selection by value-per-token ratio."""
        selected = []
        remaining = budget
        
        # Sort by value-per-token ratio (descending)
        atoms_with_ratio = []
        for atom in atoms:
            cost = self.count(atom.content) + overhead
            if cost > 0:
                value = self._compute_atom_value(atom)
                ratio = value / cost
                atoms_with_ratio.append((atom, ratio, cost))
        
        atoms_with_ratio.sort(key=lambda x: x[1], reverse=True)
        
        for atom, ratio, cost in atoms_with_ratio:
            if cost <= remaining:
                selected.append(atom)
                remaining -= cost
        
        return selected

    def _knapsack_select(
        self,
        atoms: list,
        budget: int,
        overhead: int,
    ) -> list:
        """
        Bounded knapsack optimization to maximize total semantic value.
        
        Uses dynamic programming for optimal selection under token constraint.
        Time complexity: O(n * W) where n=atoms, W=budget
        Space complexity: O(W) with space optimization
        """
        if not atoms:
            return []
        
        # Precompute costs and values
        items = []
        for atom in atoms:
            cost = self.count(atom.content) + overhead
            if cost <= budget:  # Filter out atoms that exceed budget alone
                value = self._compute_atom_value(atom)
                items.append((atom, cost, value))
        
        if not items:
            return []
        
        n = len(items)
        
        # For large budgets, use scaling approximation to avoid memory issues
        if budget > 10000:
            scale_factor = budget / 10000
            scaled_budget = 10000
            scaled_costs = [int(cost / scale_factor) for _, cost, _ in items]
            scaled_budget_int = int(scaled_budget)
            
            # DP with scaled costs
            dp = [0.0] * (scaled_budget_int + 1)
            parent = [-1] * (scaled_budget_int + 1)
            item_idx = [-1] * (scaled_budget_int + 1)
            
            for i, (atom, cost, value) in enumerate(items):
                scaled_cost = scaled_costs[i]
                if scaled_cost == 0:
                    scaled_cost = 1
                
                for w in range(scaled_budget_int, scaled_cost - 1, -1):
                    if dp[w - scaled_cost] + value > dp[w]:
                        dp[w] = dp[w - scaled_cost] + value
                        parent[w] = w - scaled_cost
                        item_idx[w] = i
            
            # Backtrack to find selected items
            selected_indices = set()
            w = scaled_budget_int
            while w > 0 and item_idx[w] != -1:
                idx = item_idx[w]
                selected_indices.add(idx)
                w = parent[w]
            
            return [items[i][0] for i in selected_indices]
        
        # Standard DP for smaller budgets
        dp = [0.0] * (budget + 1)
        parent = [-1] * (budget + 1)
        item_idx = [-1] * (budget + 1)
        
        for i, (atom, cost, value) in enumerate(items):
            for w in range(budget, cost - 1, -1):
                if dp[w - cost] + value > dp[w]:
                    dp[w] = dp[w - cost] + value
                    parent[w] = w - cost
                    item_idx[w] = i
        
        # Backtrack to find selected items
        selected_indices = set()
        w = budget
        while w > 0 and item_idx[w] != -1:
            idx = item_idx[w]
            selected_indices.add(idx)
            w = parent[w]
        
        return [items[i][0] for i in selected_indices]


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

    def build(self, use_knapsack: bool = True) -> list:
        """
        Build the handover package with optimized atom selection.
        
        Args:
            use_knapsack: If True (default), use bounded knapsack optimization.
                         If False, use faster greedy selection.
        """
        ranked = sorted(self.atoms, key=lambda a: a.propagation_score, reverse=True)
        self.selected_atoms = self.budget_manager.fit_atoms_to_budget(
            ranked, self.max_tokens, use_knapsack=use_knapsack
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
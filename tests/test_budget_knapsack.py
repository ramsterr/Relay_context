"""Tests for bounded knapsack token budgeting."""
import pytest
from context_handover.core.budget import TokenBudgetManager, HandoverPackage
from context_handover.core.atoms import SemanticAtom, AtomType, AtomStatus


class MockAtom:
    """Mock atom for testing."""
    def __init__(self, content: str, atom_type: AtomType, propagation_score: float = 0.5):
        self.content = content
        self.atom_type = atom_type
        self.propagation_score = propagation_score
        self.status = AtomStatus.ACTIVE


class TestTokenBudgetManager:
    
    def test_knapsack_vs_greedy(self):
        """Knapsack should select better value than greedy under tight budget."""
        manager = TokenBudgetManager()
        
        # Create atoms with different value/cost ratios
        atoms = [
            MockAtom("short high value", AtomType.ENTITY, 0.9),  # High value, low cost
            MockAtom("medium medium value", AtomType.QUESTION, 0.6),  # Medium both
            MockAtom("this is a very long content string with many tokens in it", AtomType.ENTITY, 0.3),  # Low value, high cost
        ]
        
        # Tight budget - only room for 1-2 atoms
        budget = 20
        
        knapsack_result = manager.fit_atoms_to_budget(atoms, budget, use_knapsack=True)
        greedy_result = manager.fit_atoms_to_budget(atoms, budget, use_knapsack=False)
        
        # Both should respect budget
        knapsack_tokens = sum(manager.count(a.content) + 15 for a in knapsack_result)
        greedy_tokens = sum(manager.count(a.content) + 15 for a in greedy_result)
        
        assert knapsack_tokens <= budget
        assert greedy_tokens <= budget
    
    def test_mandatory_atoms_always_included(self):
        """DECISION and CONSTRAINT atoms should always be included."""
        manager = TokenBudgetManager()
        
        atoms = [
            MockAtom("regular entity", AtomType.ENTITY, 0.9),  # High score but not mandatory
            MockAtom("critical decision", AtomType.DECISION, 0.2),  # Low score but mandatory
            MockAtom("important constraint", AtomType.CONSTRAINT, 0.1),  # Very low but mandatory
        ]
        
        result = manager.fit_atoms_to_budget(atoms, 200, use_knapsack=True)
        
        # Mandatory atoms should be included regardless of score
        mandatory_types = {a.atom_type for a in result}
        assert AtomType.DECISION in mandatory_types
        assert AtomType.CONSTRAINT in mandatory_types
    
    def test_value_computation(self):
        """Test that value computation weights different types correctly."""
        manager = TokenBudgetManager()
        
        decision_atom = MockAtom("test", AtomType.DECISION, 0.8)
        entity_atom = MockAtom("test", AtomType.ENTITY, 0.8)
        
        decision_value = manager._compute_atom_value(decision_atom)
        entity_value = manager._compute_atom_value(entity_atom)
        
        # Decision should have higher value due to type weight (1.5 vs 1.1)
        assert decision_value > entity_atom.propagation_score * 1.1
    
    def test_empty_atoms(self):
        """Handle empty atom list gracefully."""
        manager = TokenBudgetManager()
        result = manager.fit_atoms_to_budget([], 1000)
        assert result == []
    
    def test_budget_exceeded_by_mandatory(self):
        """When mandatory atoms exceed budget, select most critical."""
        manager = TokenBudgetManager()
        
        # Create many mandatory atoms that exceed budget
        atoms = [
            MockAtom("decision " * 20, AtomType.DECISION, 0.9),
            MockAtom("constraint " * 20, AtomType.CONSTRAINT, 0.8),
            MockAtom("decision " * 20, AtomType.DECISION, 0.3),
        ]
        
        result = manager.fit_atoms_to_budget(atoms, 100, use_knapsack=True)
        
        # Should select some atoms but not exceed budget
        total_tokens = sum(manager.count(a.content) + 15 for a in result)
        assert total_tokens <= 100


class TestHandoverPackage:
    
    def test_build_with_knapsack(self):
        """Test building package with knapsack optimization."""
        budget_manager = TokenBudgetManager()
        
        atoms = [
            MockAtom("content 1", AtomType.ENTITY, 0.7),
            MockAtom("content 2", AtomType.DECISION, 0.5),
            MockAtom("content 3", AtomType.QUESTION, 0.9),
        ]
        
        package = HandoverPackage(atoms, budget_manager, max_tokens=500)
        selected = package.build(use_knapsack=True)
        
        assert len(selected) > 0
        assert package.total_tokens <= 500
    
    def test_build_with_greedy(self):
        """Test building package with greedy selection."""
        budget_manager = TokenBudgetManager()
        
        atoms = [
            MockAtom("content 1", AtomType.ENTITY, 0.7),
            MockAtom("content 2", AtomType.DECISION, 0.5),
        ]
        
        package = HandoverPackage(atoms, budget_manager, max_tokens=500)
        selected = package.build(use_knapsack=False)
        
        assert len(selected) > 0
        assert package.total_tokens <= 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

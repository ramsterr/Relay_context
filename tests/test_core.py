"""Tests for core modules."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestAtomModel:
    """Test atom data model."""

    def test_make_id_deterministic(self):
        from context_handover.core.atoms import SemanticAtom, AtomType
        id1 = SemanticAtom.make_id("use rs256 for jwt", AtomType.DECISION)
        id2 = SemanticAtom.make_id("use rs256 for jwt", AtomType.DECISION)
        assert id1 == id2

    def test_different_content_different_id(self):
        from context_handover.core.atoms import SemanticAtom, AtomType
        id1 = SemanticAtom.make_id("use rs256", AtomType.DECISION)
        id2 = SemanticAtom.make_id("use hs256", AtomType.DECISION)
        assert id1 != id2

    def test_propagation_score(self):
        from context_handover.core.atoms import SemanticAtom, AtomType
        atom = SemanticAtom(
            atom_id="test123",
            atom_type=AtomType.DECISION,
            content="test content",
            canonical_form="test content",
            salience=0.8,
            handover_count=5,
            loss_events=1,
        )
        score = atom.propagation_score
        expected = 0.8 * (1 - 1/5)
        assert score == expected


class TestRegistry:
    """Test atom registry."""

    def test_insert_and_retrieve(self):
        from context_handover.core.registry import AtomRegistry
        from context_handover.extraction import AtomCandidate
        from context_handover.core.atoms import AtomType

        registry = AtomRegistry()
        candidate = AtomCandidate(
            type="decision",
            content="use rs256",
            canonical_form="use rs256",
            confidence=0.9,
        )
        atom = registry.insert_or_update(candidate, "session1", 0, 1)
        assert atom.atom_id is not None
        assert atom.atom_type == AtomType.DECISION


class TestBudget:
    """Test token budget manager."""

    def test_count_fallback(self):
        from context_handover.core.budget import TokenBudgetManager
        manager = TokenBudgetManager()
        count = manager.count("hello world test")
        assert count > 0

    def test_fit_atoms_to_budget(self):
        from context_handover.core.budget import TokenBudgetManager, HandoverPackage
        from context_handover.core.atoms import SemanticAtom, AtomType, AtomStatus

        manager = TokenBudgetManager()
        atoms = [
            SemanticAtom(
                atom_id=f"atom{i}",
                atom_type=AtomType.DECISION,
                content=f"decision {i}",
                canonical_form=f"decision {i}",
                salience=0.5,
                status=AtomStatus.ACTIVE,
            )
            for i in range(10)
        ]
        package = HandoverPackage(atoms, manager, max_tokens=500)
        selected = package.build()
        assert len(selected) > 0


class TestCheckpoint:
    """Test checkpoint triggers."""

    def test_evaluate_thresholds(self):
        from context_handover.core.budget import TokenBudgetManager
        from context_handover.core.checkpoint import CheckpointManager, CheckpointLevel

        manager = TokenBudgetManager()
        checkpoint_mgr = CheckpointManager(manager)

        assert checkpoint_mgr.evaluate(400, 1000) is None
        assert checkpoint_mgr.evaluate(600, 1000) == CheckpointLevel.LIGHTWEIGHT
        assert checkpoint_mgr.evaluate(800, 1000) == CheckpointLevel.STANDARD
        assert checkpoint_mgr.evaluate(950, 1000) == CheckpointLevel.DEEP


class TestDrift:
    """Test drift measurement."""

    def test_jaccard_identical(self):
        from context_handover.measurement.drift import DriftMeasurementSuite

        suite = DriftMeasurementSuite()
        ids1 = {"a", "b", "c"}
        ids2 = {"a", "b", "c"}
        assert suite.jaccard(ids1, ids2) == 1.0

    def test_jaccard_disjoint(self):
        from context_handover.measurement.drift import DriftMeasurementSuite

        suite = DriftMeasurementSuite()
        ids1 = {"a", "b"}
        ids2 = {"c", "d"}
        assert suite.jaccard(ids1, ids2) == 0.0

    def test_verdict_ranges(self):
        from context_handover.measurement.drift import DriftMeasurementSuite

        suite = DriftMeasurementSuite()
        assert suite.verdict(0.05) == "EXCELLENT"
        assert suite.verdict(0.20) == "GOOD"
        assert suite.verdict(0.40) == "WARNING — consider re-checkpoint"
        assert suite.verdict(0.60) == "CRITICAL — re-summarize before handover"


class TestTraceContext:
    """Test trace context."""

    def test_new_root(self):
        from context_handover.pipeline.trace_context import LLMTraceContext

        ctx = LLMTraceContext.new_root()
        assert ctx.root_trace_id is not None
        assert ctx.session_id is not None
        assert ctx.parent_sessions == []

    def test_inherit_single_parent(self):
        from context_handover.pipeline.trace_context import LLMTraceContext

        parent = LLMTraceContext.new_root()
        child = LLMTraceContext.inherit_from([parent])
        assert parent.session_id in child.parent_sessions
        assert child.root_trace_id == parent.root_trace_id

    def test_header_serialization(self):
        from context_handover.pipeline.trace_context import LLMTraceContext

        ctx = LLMTraceContext.new_root()
        header = ctx.to_header()
        assert "llm-trace:" in header

        parsed = LLMTraceContext.from_header(header)
        assert parsed.root_trace_id == ctx.root_trace_id


class TestCodeUtils:
    """Test code analysis utilities."""

    def test_symbol_normalizer_equivalence(self):
        from context_handover.code_analysis import SymbolNormalizer

        assert SymbolNormalizer.are_equivalent("auth", "authentication")
        assert SymbolNormalizer.are_equivalent("cfg", "config")
        assert not SymbolNormalizer.are_equivalent("auth", "db")

    def test_file_path_normalizer(self):
        from context_handover.code_analysis import FilePathNormalizer

        normalized = FilePathNormalizer.normalize("src/lib/utils.py")
        assert "lib/" in normalized

        ext = FilePathNormalizer.get_extension("test_file.spec.py")
        assert ext == "py"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
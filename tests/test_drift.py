"""Tests for drift measurement suite."""
import pytest
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestDriftInitialization:
    """Test drift suite initialization and configuration."""

    def test_default_weights(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        assert suite.weights == (0.35, 0.40, 0.25)
        assert suite.kl_epsilon == 1e-10

    def test_custom_weights(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite(weights=(0.5, 0.3, 0.2))
        assert suite.weights == (0.5, 0.3, 0.2)

    def test_weight_normalization(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        # Weights summing to 0.9 should be normalized
        suite = DriftMeasurementSuite(weights=(0.45, 0.27, 0.18))
        total = sum(suite.weights)
        assert abs(total - 1.0) < 0.01


class TestJaccard:
    """Test Jaccard similarity metric."""

    def test_identical_sets(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        ids1 = {"a", "b", "c"}
        ids2 = {"a", "b", "c"}
        assert suite.jaccard(ids1, ids2) == 1.0

    def test_disjoint_sets(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        ids1 = {"a", "b"}
        ids2 = {"c", "d"}
        assert suite.jaccard(ids1, ids2) == 0.0

    def test_partial_overlap(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        ids1 = {"a", "b", "c"}
        ids2 = {"b", "c", "d"}
        # intersection: {b, c} = 2, union: {a, b, c, d} = 4
        expected = 2 / 4
        assert suite.jaccard(ids1, ids2) == expected

    def test_empty_sets(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        assert suite.jaccard(set(), set()) == 1.0
        assert suite.jaccard({"a"}, set()) == 0.0
        assert suite.jaccard(set(), {"a"}) == 0.0


class TestCosineDrift:
    """Test cosine drift metric."""

    def test_identical_embeddings(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        emb = np.array([[1.0, 0.0], [0.0, 1.0]])
        drift = suite.cosine_drift(emb, emb)
        assert drift < 0.01  # Should be near zero

    def test_orthogonal_embeddings(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        gt = np.array([[1.0, 0.0], [1.0, 0.0]])
        ho = np.array([[0.0, 1.0], [0.0, 1.0]])
        drift = suite.cosine_drift(gt, ho)
        assert drift > 0.9  # Should be near 1.0

    def test_empty_embeddings(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        assert suite.cosine_drift(np.array([]).reshape(0, 2), np.array([]).reshape(0, 2)) == 0.0


class TestCompositeScore:
    """Test composite drift score computation."""

    def test_perfect_alignment(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        # KL=0 (identical distributions), Jaccard=1 (perfect overlap)
        composite = suite.composite(kl_structural=0.0, jaccard=1.0)
        assert composite == 0.0

    def test_high_drift(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        # High KL, low Jaccard
        composite = suite.composite(kl_structural=0.8, jaccard=0.2)
        assert composite > 0.5

    def test_with_semantic_kl(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        composite = suite.composite(
            kl_structural=0.3,
            jaccard=0.7,
            kl_semantic=0.4
        )
        # Should use all three metrics
        assert 0.0 <= composite <= 1.0

    def test_without_semantic_kl(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        composite_with = suite.composite(
            kl_structural=0.3,
            jaccard=0.7,
            kl_semantic=0.4
        )
        composite_without = suite.composite(
            kl_structural=0.3,
            jaccard=0.7,
            kl_semantic=None
        )
        # Both should be valid, but different
        assert composite_with != composite_without

    def test_custom_weights(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        # Override weights to heavily weight structural KL
        composite = suite.composite(
            kl_structural=0.5,
            jaccard=0.5,
            weights=(0.8, 0.2, 0.0)
        )
        # Should be closer to KL value
        assert composite > 0.35

    def test_input_clipping(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        # Out-of-range inputs should be clipped
        composite = suite.composite(kl_structural=1.5, jaccard=-0.2)
        assert 0.0 <= composite <= 1.0


class TestVerdict:
    """Test drift verdict classification."""

    def test_excellent_range(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        assert suite.verdict(0.05) == "EXCELLENT"
        assert suite.verdict(0.09) == "EXCELLENT"

    def test_good_range(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        assert suite.verdict(0.10) == "GOOD"
        assert suite.verdict(0.24) == "GOOD"

    def test_warning_range(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        assert suite.verdict(0.25) == "WARNING — consider re-checkpoint"
        assert suite.verdict(0.44) == "WARNING — consider re-checkpoint"

    def test_critical_range(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        assert suite.verdict(0.45) == "CRITICAL — re-summarize before handover"
        assert suite.verdict(0.90) == "CRITICAL — re-summarize before handover"


class TestKLStructural:
    """Test structural KL divergence computation."""

    def test_identical_distributions(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        from context_handover.core.atoms import SemanticAtom, AtomType
        
        suite = DriftMeasurementSuite()
        
        # Create atoms with uniform distribution
        atoms = {
            f"atom{i}": SemanticAtom(
                atom_id=f"atom{i}",
                atom_type=AtomType.DECISION,
                content=f"test {i}",
                canonical_form=f"test {i}",
                salience=1.0,
            )
            for i in range(5)
        }
        
        # Model belief matches ground truth (all decisions)
        model_dist = {"decision": 1.0}
        
        kl = suite.kl_structural(atoms, model_dist)
        assert 0.0 <= kl <= 0.2  # Should be very low

    def test_different_distributions(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        from context_handover.core.atoms import SemanticAtom, AtomType
        
        suite = DriftMeasurementSuite()
        
        # Mix of atom types
        atoms = {
            "a1": SemanticAtom(
                atom_id="a1",
                atom_type=AtomType.DECISION,
                content="dec1",
                canonical_form="dec1",
                salience=1.0,
            ),
            "a2": SemanticAtom(
                atom_id="a2",
                atom_type=AtomType.CONSTRAINT,
                content="con1",
                canonical_form="con1",
                salience=1.0,
            ),
        }
        
        # Model expects only decisions
        model_dist = {"decision": 1.0}
        
        kl = suite.kl_structural(atoms, model_dist)
        assert kl > 0.1  # Should detect mismatch

    def test_empty_atoms(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        suite = DriftMeasurementSuite()
        kl = suite.kl_structural({}, {"decision": 1.0})
        assert kl == 0.0

    def test_distribution_normalization(self):
        from context_handover.measurement.drift import DriftMeasurementSuite
        from context_handover.core.atoms import SemanticAtom, AtomType
        
        suite = DriftMeasurementSuite()
        atoms = {
            "a1": SemanticAtom(
                atom_id="a1",
                atom_type=AtomType.DECISION,
                content="dec1",
                canonical_form="dec1",
                salience=1.0,
            ),
        }
        
        # Model distribution doesn't sum to 1.0
        model_dist = {"decision": 0.5, "constraint": 0.3}  # sums to 0.8
        
        # Should still work (auto-normalizes)
        kl = suite.kl_structural(atoms, model_dist)
        assert 0.0 <= kl <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

from __future__ import annotations
import numpy as np
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

try:
    from scipy.stats import entropy
    from scipy.spatial.distance import cosine
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy not available - some drift metrics disabled")

try:
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available - semantic clustering disabled")


class DriftMeasurementSuite:
    """
    Multi-metric context drift measurement suite.
    
    Measures semantic and structural drift between ground truth context
    and model beliefs/handover packages using:
    - KL divergence (structural & semantic)
    - Jaccard similarity (atom overlap)
    - Cosine similarity (embedding drift)
    
    All metrics are normalized to [0, 1] range where 0 = no drift, 1 = maximum drift.
    """
    
    def __init__(
        self,
        weights: Tuple[float, float, float] = (0.35, 0.40, 0.25),
        kl_epsilon: float = 1e-10,
    ):
        """
        Initialize drift measurement suite.
        
        Args:
            weights: Tuple of (kl_structural_weight, jaccard_weight, kl_semantic_weight)
                    Weights should sum to 1.0. If semantic KL unavailable, 
                    weight redistributes to other metrics.
            kl_epsilon: Smoothing constant for KL divergence to avoid log(0)
        """
        self.weights = weights
        self.kl_epsilon = kl_epsilon
        self._validate_weights()
    
    def _validate_weights(self):
        """Validate that weights sum to approximately 1.0."""
        total = sum(self.weights)
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"Weights {self.weights} sum to {total}, normalizing..."
            )
            self.weights = tuple(w / total for w in self.weights)
    def kl_structural(
        self,
        ground_truth_atoms: dict,
        model_belief_dist: dict,
        epsilon: Optional[float] = None,
    ) -> float:
        """
        Compute KL divergence between atom type distributions.
        
        Measures structural drift by comparing the distribution of atom types
        in ground truth vs model beliefs. Uses salience-weighted type frequencies.
        
        Args:
            ground_truth_atoms: Dict of atom_id -> SemanticAtom
            model_belief_dist: Dict of atom_type -> probability (must sum to 1)
            epsilon: Smoothing constant (overrides instance default)
        
        Returns:
            KL divergence value normalized to [0, 1] range.
            0 = identical distributions, 1 = maximum divergence.
            Returns 0.0 if scipy unavailable or empty input.
        
        Mathematical basis:
            P(type) = Σ salience(atom) for atoms of that type / total_salience
            Q(type) = model_belief_dist[type]
            KL(P||Q) = Σ P(type) * log(P(type) / Q(type))
            
        Note: KL is asymmetric and unbounded. We normalize via:
            normalized = min(KL / max_expected_KL, 1.0)
            where max_expected_KL ≈ 2.0 for typical distributions
        """
        if not SCIPY_AVAILABLE:
            logger.warning("scipy not available - returning 0.0 for KL")
            return 0.0

        if not ground_truth_atoms:
            logger.debug("No ground truth atoms - KL undefined, returning 0.0")
            return 0.0

        truth_dist = self._build_type_distribution(ground_truth_atoms)
        eps = epsilon if epsilon is not None else self.kl_epsilon
        
        # Validate model belief distribution sums to ~1.0
        model_sum = sum(model_belief_dist.values())
        if abs(model_sum - 1.0) > 0.01:
            logger.warning(
                f"Model belief distribution sums to {model_sum}, normalizing..."
            )
            model_belief_dist = {k: v / model_sum for k, v in model_belief_dist.items()}
        
        raw_kl = self._kl(truth_dist, model_belief_dist, eps)
        
        # Normalize: KL typically ranges 0-2 for similar distributions,
        # but can be higher for very different distributions
        # Using soft clipping: normalized = 1 - exp(-KL/2)
        import math
        normalized = 1.0 - math.exp(-raw_kl / 2.0)
        
        logger.debug(
            f"KL structural: raw={raw_kl:.4f}, normalized={normalized:.4f}, "
            f"truth_dist={truth_dist}"
        )
        return normalized

    def _build_type_distribution(self, atoms: dict) -> dict[str, float]:
        type_weights: dict[str, float] = {}
        for atom in atoms.values():
            key = atom.atom_type.value
            type_weights[key] = type_weights.get(key, 0.0) + atom.salience
        total = sum(type_weights.values()) or 1.0
        return {k: v / total for k, v in type_weights.items()}

    def kl_semantic(
        self,
        ground_truth_embeddings: np.ndarray,
        handover_embeddings: np.ndarray,
        n_clusters: int = 8,
    ) -> Optional[float]:
        """
        Compute semantic KL divergence via clustering-based distribution mapping.
        
        Maps continuous embedding space to discrete probability distributions
        by clustering ground truth embeddings and measuring how handover
        embeddings distribute across those clusters.
        
        Args:
            ground_truth_embeddings: (N, D) array of ground truth embeddings
            handover_embeddings: (M, D) array of handover embeddings
            n_clusters: Number of clusters for K-means (auto-capped to data size)
        
        Returns:
            KL divergence normalized to [0, 1], or None if sklearn/scipy unavailable
            or insufficient data for clustering.
        
        Mathematical basis:
            1. Cluster ground truth embeddings: K-means → cluster centroids C
            2. P(cluster) = #ground_truth in cluster / total_ground_truth
            3. Q(cluster) = #handover assigned to cluster / total_handover
            4. KL(P||Q) computed with smoothing epsilon
            
        Why this works:
            - Clusters represent semantic regions in embedding space
            - Distribution shift indicates semantic drift
            - KL measures information loss when approximating P with Q
        """
        if not SKLEARN_AVAILABLE or not SCIPY_AVAILABLE:
            logger.warning("sklearn/scipy not available - skipping semantic KL")
            return None

        if len(ground_truth_embeddings) < 2 or len(handover_embeddings) < 2:
            logger.debug(
                f"Insufficient embeddings for clustering: "
                f"GT={len(ground_truth_embeddings)}, HO={len(handover_embeddings)}"
            )
            return 0.0

        # Auto-adjust clusters to data size
        n_clusters = min(n_clusters, len(ground_truth_embeddings))
        
        # Fit K-means on ground truth to define semantic regions
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        gt_cluster_labels = kmeans.fit_predict(ground_truth_embeddings)
        
        # Build ground truth distribution over clusters
        gt_counts = np.bincount(gt_cluster_labels, minlength=n_clusters)
        gt_dist = gt_counts / gt_counts.sum()
        
        # Assign handover embeddings to same clusters
        ho_cluster_labels = kmeans.predict(handover_embeddings)
        ho_counts = np.bincount(ho_cluster_labels, minlength=n_clusters)
        ho_dist = ho_counts / (ho_counts.sum() or 1)
        
        # Convert to dict format for KL computation
        gt_dict = {f"c{i}": float(v) for i, v in enumerate(gt_dist)}
        ho_dict = {f"c{i}": float(v) for i, v in enumerate(ho_dist)}
        
        raw_kl = self._kl(gt_dict, ho_dict, self.kl_epsilon)
        
        # Normalize using same soft-clipping as structural KL
        import math
        normalized = 1.0 - math.exp(-raw_kl / 2.0)
        
        logger.debug(
            f"KL semantic: raw={raw_kl:.4f}, normalized={normalized:.4f}, "
            f"n_clusters={n_clusters}"
        )
        return normalized

    def jaccard(
        self,
        ground_truth_ids: set,
        model_reported_ids: set,
    ) -> float:
        if not ground_truth_ids and not model_reported_ids:
            return 1.0
        if not ground_truth_ids or not model_reported_ids:
            return 0.0
        intersection = ground_truth_ids & model_reported_ids
        union = ground_truth_ids | model_reported_ids
        return len(intersection) / len(union)

    def cosine_drift(
        self,
        ground_truth_embeddings: np.ndarray,
        handover_embeddings: np.ndarray,
    ) -> float:
        if len(ground_truth_embeddings) == 0 or len(handover_embeddings) == 0:
            return 0.0

        gt_mean = np.mean(ground_truth_embeddings, axis=0)
        ho_mean = np.mean(handover_embeddings, axis=0)

        norm_a = np.linalg.norm(gt_mean)
        norm_b = np.linalg.norm(ho_mean)
        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = np.dot(gt_mean, ho_mean) / (norm_a * norm_b)
        return 1.0 - float(similarity)

    def composite(
        self,
        kl_structural: float,
        jaccard: float,
        kl_semantic: Optional[float] = None,
        weights: Optional[Tuple[float, float, float]] = None,
    ) -> float:
        """
        Compute weighted composite drift score from multiple metrics.
        
        Combines structural KL, Jaccard similarity, and semantic KL into
        a single normalized drift score in [0, 1] range.
        
        Args:
            kl_structural: Normalized structural KL divergence [0, 1]
            jaccard: Jaccard similarity coefficient [0, 1] (will be converted to loss)
            kl_semantic: Normalized semantic KL divergence [0, 1], or None
            weights: Override default weights (kl_struct, jaccard, kl_semantic).
                    If None, uses instance weights. If kl_semantic is None,
                    its weight redistributes proportionally.
        
        Returns:
            Composite drift score [0, 1] where:
            - 0.0-0.10: EXCELLENT (minimal drift)
            - 0.10-0.25: GOOD (acceptable drift)
            - 0.25-0.45: WARNING (consider re-checkpoint)
            - 0.45+: CRITICAL (re-summarize before handover)
        
        Fusion strategy:
            - All inputs normalized to [0, 1] with same semantics (higher = more drift)
            - Jaccard similarity converted to loss: jaccard_loss = 1 - jaccard
            - Weighted average with automatic redistribution if semantic KL unavailable
        """
        # Use provided weights or fall back to instance defaults
        if weights is None:
            weights = self.weights
        
        w_kl, w_jac, w_sem = weights
        
        # Ensure inputs are in valid range (defensive programming)
        kl_struct_norm = max(0.0, min(kl_structural, 1.0))
        jac_loss = max(0.0, min(1.0 - jaccard, 1.0))
        
        if kl_semantic is not None:
            sem_norm = max(0.0, min(kl_semantic, 1.0))
            composite = w_kl * kl_struct_norm + w_jac * jac_loss + w_sem * sem_norm
            logger.debug(
                f"Composite drift: struct={kl_struct_norm:.3f}, "
                f"jac_loss={jac_loss:.3f}, sem={sem_norm:.3f} → {composite:.3f}"
            )
        else:
            # Redistribute semantic weight proportionally to other metrics
            total_remaining = w_kl + w_jac
            if total_remaining > 0:
                adjusted_w_kl = w_kl / total_remaining
                adjusted_w_jac = w_jac / total_remaining
            else:
                # Edge case: all weights zero, use equal weighting
                adjusted_w_kl = 0.5
                adjusted_w_jac = 0.5
            
            composite = adjusted_w_kl * kl_struct_norm + adjusted_w_jac * jac_loss
            logger.debug(
                f"Composite drift (no semantic): struct={kl_struct_norm:.3f}, "
                f"jac_loss={jac_loss:.3f} → {composite:.3f}"
            )
        
        return composite

    def verdict(self, composite_score: float) -> str:
        if composite_score < 0.10:
            return "EXCELLENT"
        if composite_score < 0.25:
            return "GOOD"
        if composite_score < 0.45:
            return "WARNING — consider re-checkpoint"
        return "CRITICAL — re-summarize before handover"

    @staticmethod
    def _kl(P: dict, Q: dict, epsilon: float = 1e-10) -> float:
        if not SCIPY_AVAILABLE:
            return 0.0
        keys = set(P) | set(Q)
        p = np.array([P.get(k, epsilon) for k in keys])
        q = np.array([Q.get(k, epsilon) for k in keys])
        p = (p + epsilon) / (p + epsilon).sum()
        q = (q + epsilon) / (q + epsilon).sum()
        return float(entropy(p, q))
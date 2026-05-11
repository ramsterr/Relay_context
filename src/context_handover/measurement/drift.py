from __future__ import annotations
import numpy as np
from typing import Optional
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
    def kl_structural(
        self,
        ground_truth_atoms: dict,
        model_belief_dist: dict,
        epsilon: float = 1e-10,
    ) -> float:
        if not SCIPY_AVAILABLE:
            logger.warning("scipy not available - returning 0.0 for KL")
            return 0.0

        truth_dist = self._build_type_distribution(ground_truth_atoms)
        return self._kl(truth_dist, model_belief_dist, epsilon)

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
    ) -> float:
        if not SKLEARN_AVAILABLE or not SCIPY_AVAILABLE:
            logger.warning("sklearn/scipy not available - skipping semantic KL")
            return None

        if len(ground_truth_embeddings) < 2 or len(handover_embeddings) < 2:
            return 0.0

        n_clusters = min(n_clusters, len(ground_truth_embeddings))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        kmeans.fit(ground_truth_embeddings)

        gt_labels = kmeans.labels_
        gt_counts = np.bincount(gt_labels, minlength=n_clusters)
        gt_dist = gt_counts / gt_counts.sum()

        ho_labels = kmeans.predict(handover_embeddings)
        ho_counts = np.bincount(ho_labels, minlength=n_clusters)
        ho_dist = ho_counts / (ho_counts.sum() or 1)

        return self._kl(
            {f"c{i}": float(v) for i, v in enumerate(gt_dist)},
            {f"c{i}": float(v) for i, v in enumerate(ho_dist)},
        )

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
        weights: tuple = (0.35, 0.40, 0.25),
    ) -> float:
        w_kl, w_jac, w_sem = weights
        kl_norm = min(kl_structural / 2.0, 1.0)
        jac_loss = 1.0 - jaccard

        if kl_semantic is not None:
            sem_norm = min(kl_semantic / 2.0, 1.0)
            return w_kl * kl_norm + w_jac * jac_loss + w_sem * sem_norm
        else:
            adjusted_w_kl = w_kl + (w_sem * 0.5)
            adjusted_w_jac = w_jac + (w_sem * 0.5)
            return adjusted_w_kl * kl_norm + adjusted_w_jac * jac_loss

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
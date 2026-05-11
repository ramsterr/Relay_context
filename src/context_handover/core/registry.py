from __future__ import annotations
from typing import Optional, Any
import asyncio
import numpy as np
import logging
from .atoms import SemanticAtom, AtomType, AtomStatus
from ..extraction import AtomCandidate
logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.88


class AtomRegistry:
    def __init__(self, embedding_client: Optional[Any] = None):
        self.atoms: dict[str, SemanticAtom] = {}
        self.embeddings: dict[str, np.ndarray] = {}
        self.embedding_client = embedding_client

    def insert_or_update(
        self,
        candidate: AtomCandidate,
        session_id: str,
        msg_idx: int,
        total_msgs: int,
    ) -> SemanticAtom:
        atom_type = AtomType(candidate.type)
        exact_id = SemanticAtom.make_id(candidate.canonical_form, atom_type)

        if exact_id in self.atoms:
            return self._update_existing(exact_id, session_id, msg_idx, total_msgs)

        if self.embedding_client is not None:
            candidate_embedding = self._embed_blocking(candidate.canonical_form)
            similar_id = self._find_similar(candidate_embedding, atom_type)
            if similar_id is not None:
                logger.debug(f"Dedup: '{candidate.canonical_form}' → {similar_id}")
                return self._update_existing(similar_id, session_id, msg_idx, total_msgs)
            atom = self._create_atom(candidate, atom_type, session_id, msg_idx)
            self.atoms[atom.atom_id] = atom
            self.embeddings[atom.atom_id] = candidate_embedding
            return atom

        atom = self._create_atom(candidate, atom_type, session_id, msg_idx)
        self.atoms[atom.atom_id] = atom
        return atom

    async def insert_or_update_async(
        self,
        candidate: AtomCandidate,
        session_id: str,
        msg_idx: int,
        total_msgs: int,
    ) -> SemanticAtom:
        atom_type = AtomType(candidate.type)
        exact_id = SemanticAtom.make_id(candidate.canonical_form, atom_type)

        if exact_id in self.atoms:
            return self._update_existing(exact_id, session_id, msg_idx, total_msgs)

        if self.embedding_client is not None:
            candidate_embedding = await self._embed_async(candidate.canonical_form)
            similar_id = self._find_similar(candidate_embedding, atom_type)
            if similar_id is not None:
                logger.debug(f"Dedup: '{candidate.canonical_form}' → {similar_id}")
                return self._update_existing(similar_id, session_id, msg_idx, total_msgs)
            atom = self._create_atom(candidate, atom_type, session_id, msg_idx)
            self.atoms[atom.atom_id] = atom
            self.embeddings[atom.atom_id] = candidate_embedding
            return atom

        atom = self._create_atom(candidate, atom_type, session_id, msg_idx)
        self.atoms[atom.atom_id] = atom
        return atom

    def _find_similar(
        self,
        query_embedding: np.ndarray,
        atom_type: AtomType,
    ) -> Optional[str]:
        best_score = 0.0
        best_id = None
        for atom_id, atom in self.atoms.items():
            if atom.atom_type != atom_type:
                continue
            if atom_id not in self.embeddings:
                continue
            stored_emb = self.embeddings[atom_id]
            score = self._cosine_similarity(query_embedding, stored_emb)
            if score > best_score:
                best_score = score
                best_id = atom_id
        if best_score >= SIMILARITY_THRESHOLD:
            return best_id
        return None

    def _update_existing(
        self,
        atom_id: str,
        session_id: str,
        msg_idx: int,
        total_msgs: int,
    ) -> SemanticAtom:
        atom = self.atoms[atom_id]
        if session_id not in atom.sessions_present:
            atom.sessions_present.append(session_id)
        atom.last_seen_session = session_id
        atom.last_seen_message = msg_idx
        atom.update_salience(msg_idx, total_msgs)
        return atom

    def _create_atom(
        self,
        candidate: AtomCandidate,
        atom_type: AtomType,
        session_id: str,
        msg_idx: int,
    ) -> SemanticAtom:
        atom_id = SemanticAtom.make_id(candidate.canonical_form, atom_type)
        return SemanticAtom(
            atom_id=atom_id,
            atom_type=atom_type,
            content=candidate.content,
            canonical_form=candidate.canonical_form,
            embedding=None,
            salience=0.5,
            confidence=candidate.confidence,
            origin_session=session_id,
            origin_message=msg_idx,
            last_seen_session=session_id,
            last_seen_message=msg_idx,
            sessions_present=[session_id],
        )

    def _embed(self, text: str) -> np.ndarray:
        response = self.embedding_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return np.array(response.data[0].embedding)

    def _embed_blocking(self, text: str) -> np.ndarray:
        return self._embed(text)

    async def _embed_async(self, text: str) -> np.ndarray:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed, text)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def get_active_atoms(self) -> dict[str, SemanticAtom]:
        return {
            aid: a for aid, a in self.atoms.items()
            if a.status == AtomStatus.ACTIVE
        }

    def get_by_type(self, atom_type: AtomType) -> list[SemanticAtom]:
        return [a for a in self.atoms.values() if a.atom_type == atom_type]

    def get_ranked_atoms(self) -> list[SemanticAtom]:
        return sorted(
            self.get_active_atoms().values(),
            key=lambda a: a.propagation_score,
            reverse=True,
        )
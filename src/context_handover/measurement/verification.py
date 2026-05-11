from __future__ import annotations
from typing import Any, Optional
import json
import logging
from ..core.atoms import SemanticAtom, AtomType
from ..core.registry import AtomRegistry
logger = logging.getLogger(__name__)


SELF_REPORT_PROMPT = """
You are continuing a technical session.
Before proceeding, restate your current understanding as JSON.
Return ONLY this JSON structure, no other text:
{
  "decisions":   ["exact decision 1", "exact decision 2"],
  "constraints": ["constraint 1"],
  "questions":   ["open question 1"],
  "entities":    ["entity 1", "entity 2"],
  "tasks":       ["task 1"]
}
Be precise. Copy wording from earlier in the conversation where possible.
Do not invent. If unsure about something, omit it.
"""


class SelfReportVerifier:
    def __init__(self, model_client: Any, extractor, registry: AtomRegistry):
        self.model_client = model_client
        self.extractor = extractor
        self.registry = registry

    def verify(self, session_id: str, model_name: str = "gpt-4o-mini") -> dict:
        raw_report = self._get_self_report(model_name)
        if raw_report is None:
            return {"jaccard": None, "error": "self_report_failed"}

        report_text = self._flatten_report(raw_report)
        report_atoms = self.extractor.extract(report_text)

        reported_ids = set()
        for candidate in report_atoms:
            try:
                atype = AtomType(candidate.type)
                atom_id = SemanticAtom.make_id(candidate.canonical_form, atype)
                reported_ids.add(atom_id)
            except ValueError:
                continue

        ground_truth_ids = set(self.registry.get_active_atoms().keys())

        intersection = ground_truth_ids & reported_ids
        union = ground_truth_ids | reported_ids
        jaccard = len(intersection) / len(union) if union else 1.0

        dropped_ids = ground_truth_ids - reported_ids
        dropped_atoms = [
            self.registry.atoms[aid]
            for aid in dropped_ids
            if aid in self.registry.atoms
        ]

        return {
            "jaccard": jaccard,
            "ground_truth_count": len(ground_truth_ids),
            "reported_count": len(reported_ids),
            "intersection_count": len(intersection),
            "dropped_atoms": [a.content for a in dropped_atoms],
            "dropped_by_type": self._group_by_type(dropped_atoms),
        }

    def _get_self_report(self, model_name: str) -> Optional[dict]:
        try:
            response = self.model_client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": SELF_REPORT_PROMPT}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Self-report failed: {e}")
            return None

    def _flatten_report(self, report: dict) -> str:
        parts = []
        for key, items in report.items():
            if isinstance(items, list):
                parts.extend(items)
        return ". ".join(str(i) for i in parts)

    def _group_by_type(self, atoms: list) -> dict[str, int]:
        groups: dict[str, int] = {}
        for atom in atoms:
            key = atom.atom_type.value
            groups[key] = groups.get(key, 0) + 1
        return groups
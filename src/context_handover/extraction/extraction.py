from __future__ import annotations
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Any
import json
import re
import logging
logger = logging.getLogger(__name__)


class AtomCandidate(BaseModel):
    type: str
    content: str
    canonical_form: str
    confidence: float = Field(ge=0.0, le=1.0)

    @validator("type")
    def type_must_be_valid(cls, v):
        valid = {"entity", "decision", "constraint", "question", "task", "belief", "relation"}
        if v not in valid:
            raise ValueError(f"Invalid atom type: {v}")
        return v

    @validator("canonical_form")
    def canonical_must_be_short(cls, v):
        if len(v) > 200:
            return v[:200]
        return v


class ExtractionResponse(BaseModel):
    atoms: List[AtomCandidate]


EXTRACTION_PROMPT = """You are a semantic atom extractor for a context tracking system.
Extract semantic atoms from the conversation snippet below.
Atom types:
- entity:      a concrete thing (file, class, library, concept, person)
- decision:    a choice that was made ("we will use X", "X is the approach")
- constraint:  a hard rule that must be followed
- question:    something unresolved that needs answering
- task:        an action to be taken or in progress
- belief:      the speaker's understanding of something (may be wrong)
- relation:    how two things relate (A depends on B, A conflicts with B)
For EACH atom, produce:
- type: one of the types above
- content: the atom as stated in the text (preserve original wording)
- canonical_form: a normalized, concise restatement
  (e.g. "we should use RS256 for JWT" -> "use RS256 for JWT signing")
- confidence: 0.0-1.0, how certain you are this is a real atom
Rules:
- canonical_form must be unique and concise — this is used for deduplication
- Do not extract trivial entities (e.g. "the", "this")
- Prefer fewer high-confidence atoms over many low-confidence ones
- If the same concept appears twice, emit it ONCE with higher confidence
Return ONLY valid JSON:
{
  "atoms": [
    {"type": "...", "content": "...", "canonical_form": "...", "confidence": 0.0}
  ]
}
Text to extract from:
{text}"""

FALLBACK_PATTERNS = {
    "decision": [
        r"we (?:will|should|must|are going to) (.+)",
        r"(?:decided|agreed|confirmed) (?:to|that) (.+)",
        r"(?:use|using) (.+) (?:for|as|to) (.+)",
    ],
    "question": [
        r"(?:how|what|why|when|where|should) (?:do|we|is|are|can) (.+)\?",
        r"(?:not sure|unclear|need to figure out) (.+)",
    ],
    "constraint": [
        r"(?:must|cannot|should not|never|always) (.+)",
        r"(?:required|mandatory|forbidden) (?:that|to) (.+)",
    ],
    "task": [
        r"(?:todo|need to|will|going to) (?:implement|write|fix|add|remove|refactor) (.+)",
    ],
}


class AtomExtractor:
    def __init__(self, model_client: Any, model_name: str = "gpt-4o-mini"):
        self.model_client = model_client
        self.model_name = model_name

    def extract(self, text: str, max_chars: int = 3000) -> List[AtomCandidate]:
        if self.model_client is None:
            return self._regex_extract(text[:max_chars])
        truncated = text[:max_chars]
        try:
            return self._llm_extract(truncated)
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e} — falling back to regex")
            return self._regex_extract(truncated)

    def _llm_extract(self, text: str) -> List[AtomCandidate]:
        prompt = EXTRACTION_PROMPT.format(text=text)
        response = self.model_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return ExtractionResponse(**data).atoms

    def _regex_extract(self, text: str) -> List[AtomCandidate]:
        candidates = []
        for atom_type, patterns in FALLBACK_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text.lower())
                for match in matches:
                    content = match if isinstance(match, str) else " ".join(match)
                    if len(content.strip()) > 3:
                        candidates.append(AtomCandidate(
                            type=atom_type,
                            content=content.strip(),
                            canonical_form=content.strip().lower(),
                            confidence=0.4,
                        ))
        return candidates
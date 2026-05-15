from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid


@dataclass
class LLMTraceContext:
    root_trace_id: str
    session_id: str
    parent_sessions: list[str]
    checkpoint_id: str
    message_index: int
    flags: dict = field(default_factory=lambda: {
        "handover_in_progress": False,
        "context_verified": False,
        "drift_above_threshold": False,
        "loss_detected": False,
    })

    @classmethod
    def new_root(cls, problem_description: str = "") -> "LLMTraceContext":
        root_id = str(uuid.uuid4()).replace("-", "")[:12]
        return cls(
            root_trace_id=root_id,
            session_id=str(uuid.uuid4()).replace("-", "")[:8],
            parent_sessions=[],
            checkpoint_id="init",
            message_index=0,
        )

    @classmethod
    def inherit_from(cls, parents: list["LLMTraceContext"]) -> "LLMTraceContext":
        root_ids = set(p.root_trace_id for p in parents)
        root_id = root_ids.pop() if len(root_ids) == 1 else str(uuid.uuid4()).replace("-", "")[:12]
        return cls(
            root_trace_id=root_id,
            session_id=str(uuid.uuid4()).replace("-", "")[:8],
            parent_sessions=[p.session_id for p in parents],
            checkpoint_id="init",
            message_index=0,
        )

    def to_header(self) -> str:
        flag_str = "".join("1" if v else "0" for v in self.flags.values())
        return f"llm-trace: v1|{self.root_trace_id}|{self.session_id}|{self.checkpoint_id}|{flag_str}"

    @classmethod
    def from_header(cls, header: str) -> Optional["LLMTraceContext"]:
        try:
            _, rest = header.split(": ", 1)
            parts = rest.split("|")
            if len(parts) >= 5:
                version = parts[0]
                root = parts[1]
                session = parts[2]
                checkpoint = parts[3]
                flags = parts[4] if len(parts) > 4 else "0000"
            else:
                return None
            flag_keys = ["handover_in_progress", "context_verified",
                         "drift_above_threshold", "loss_detected"]
            flag_dict = {k: (flags[i] == "1") for i, k in enumerate(flag_keys)}
            return cls(
                root_trace_id=root,
                session_id=session,
                parent_sessions=[],
                checkpoint_id=checkpoint,
                message_index=0,
                flags=flag_dict,
            )
        except Exception:
            return None

    def advance_message(self):
        self.message_index += 1

    def set_checkpoint(self, checkpoint_id: str):
        self.checkpoint_id = checkpoint_id

    def mark_handover_start(self):
        self.flags["handover_in_progress"] = True

    def mark_handover_end(self, drift_detected: bool = False, loss_detected: bool = False):
        self.flags["handover_in_progress"] = False
        self.flags["context_verified"] = True
        self.flags["drift_above_threshold"] = drift_detected
        self.flags["loss_detected"] = loss_detected


class SessionDAG:
    def __init__(self):
        self.sessions: dict[str, LLMTraceContext] = {}
        self.checkpoints: dict[str, dict] = {}

    def create_session(self, parent_ids: list[str] = None) -> LLMTraceContext:
        if parent_ids and all(pid in self.sessions for pid in parent_ids):
            parents = [self.sessions[pid] for pid in parent_ids]
            ctx = LLMTraceContext.inherit_from(parents)
        else:
            ctx = LLMTraceContext.new_root()

        self.sessions[ctx.session_id] = ctx
        return ctx

    def get_session(self, session_id: str) -> Optional[LLMTraceContext]:
        return self.sessions.get(session_id)

    def add_checkpoint(self, session_id: str, checkpoint_data: dict):
        if session_id not in self.checkpoints:
            self.checkpoints[session_id] = {}
        self.checkpoints[session_id][checkpoint_data["checkpoint_id"]] = checkpoint_data

    def get_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[dict]:
        return self.checkpoints.get(session_id, {}).get(checkpoint_id)

    def get_lineage(self, session_id: str) -> list[str]:
        ctx = self.sessions.get(session_id)
        if not ctx:
            return []
        lineage = [session_id]
        for parent_id in ctx.parent_sessions:
            lineage.extend(self.get_lineage(parent_id))
        return lineage
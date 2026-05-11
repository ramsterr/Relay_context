from __future__ import annotations
import re
import hashlib
from typing import Optional, List
from dataclasses import dataclass


class SymbolNormalizer:
    ALIASES = {
        "auth": "authentication",
        "authz": "authorization",
        "cfg": "config",
        "conf": "config",
        "ctx": "context",
        "db": "database",
        "env": "environment",
        "err": "error",
        "fn": "function",
        "init": "initialize",
        "lib": "library",
        "msg": "message",
        "num": "number",
        "obj": "object",
        "pkg": "package",
        "prop": "property",
        "req": "request",
        "res": "response",
        "svc": "service",
        "util": "utility",
    }

    @classmethod
    def normalize(cls, symbol: str) -> str:
        normalized = symbol.lower()
        for short, long in cls.ALIASES.items():
            normalized = re.sub(rf"\b{short}\b", long, normalized)
        normalized = re.sub(r"[_-]", "", normalized)
        return normalized

    @classmethod
    def are_equivalent(cls, symbol1: str, symbol2: str) -> bool:
        return cls.normalize(symbol1) == cls.normalize(symbol2)


class FilePathNormalizer:
    COMMON_PATHS = {
        "src/": "",
        "lib/": "",
        "app/": "",
        "packages/": "",
    }

    @classmethod
    def normalize(cls, path: str) -> str:
        normalized = path
        for prefix, replacement in cls.COMMON_PATHS.items():
            if normalized.startswith(prefix):
                normalized = replacement + normalized[len(prefix):]
                break
        normalized = re.sub(r"/+", "/", normalized)
        return normalized.rstrip("/")

    @classmethod
    def extract_module(cls, path: str) -> str:
        parts = path.replace("\\", "/").split("/")
        if len(parts) >= 2:
            return parts[-2]
        return ""

    @classmethod
    def get_extension(cls, path: str) -> str:
        match = re.search(r"\.(\w+)$", path)
        return match.group(1) if match else ""


@dataclass
class CodeAtomMetadata:
    file_path: Optional[str] = None
    symbol_name: Optional[str] = None
    ast_hash: Optional[str] = None
    dependencies: List[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

    @classmethod
    def from_text(cls, text: str) -> "CodeAtomMetadata":
        file_paths = re.findall(r"(?:from|import)\s+([a-zA-Z0-9_.]+)", text)
        return cls(dependencies=file_paths)


def compute_ast_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()[:16]


class DependencyResolver:
    def __init__(self):
        self.dependency_graph: dict[str, set[str]] = {}

    def add_dependency(self, source: str, target: str):
        if source not in self.dependency_graph:
            self.dependency_graph[source] = set()
        self.dependency_graph[source].add(target)

    def get_dependencies(self, module: str) -> set[str]:
        return self.dependency_graph.get(module, set())

    def get_dependents(self, module: str) -> set[str]:
        dependents = set()
        for source, targets in self.dependency_graph.items():
            if module in targets:
                dependents.add(source)
        return dependents

    def topological_sort(self) -> List[str]:
        visited = set()
        result = []

        def visit(node: str):
            if node in visited:
                return
            visited.add(node)
            for dep in self.get_dependencies(node):
                visit(dep)
            result.append(node)

        for node in self.dependency_graph:
            visit(node)

        return result


class FileSalienceDecay:
    @staticmethod
    def calculate_decay(
        file_path: str,
        sessions_since_modified: int,
        atom_type: str,
    ) -> float:
        base_decay = 0.9 ** sessions_since_modified

        extension = FilePathNormalizer.get_extension(file_path)
        config_extensions = {"json", "yaml", "yml", "toml", "ini", "env"}
        test_extensions = {"test", "spec"}

        if extension in config_extensions:
            return base_decay * 0.8
        if extension in test_extensions:
            return base_decay * 0.7
        if atom_type == "decision" or atom_type == "constraint":
            return 1.0

        return base_decay
"""Source base + registry.

Each source implements fetch(city, region) -> FetchResult. The orchestrator
runs them with per-source timeout + error isolation and merges the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchResult:
    source: str
    posts: list = field(default_factory=list)     # RawPost[]
    status: str = "ok"        # ok | quiet | none | error | ambiguous
    note: str = ""
    detail: dict = field(default_factory=dict)


class Source:
    name = "source"
    label = "Source"
    priority = 100            # lower runs first

    def fetch(self, city: str, region: str | None = None) -> FetchResult:
        raise NotImplementedError

    def _ok(self, posts, note="", **detail):
        return FetchResult(self.name, posts, "ok", note, detail)

    def _empty(self, status="none", note="", **detail):
        return FetchResult(self.name, [], status, note, detail)


_REGISTRY: list[Source] = []


def register(source: Source) -> Source:
    # replace any existing source with the same name (idempotent imports)
    global _REGISTRY
    _REGISTRY = [s for s in _REGISTRY if s.name != source.name]
    _REGISTRY.append(source)
    _REGISTRY.sort(key=lambda s: s.priority)
    return source


def all_sources() -> list:
    return list(_REGISTRY)


def reset_registry() -> None:
    _REGISTRY.clear()

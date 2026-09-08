from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar


T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, *, kind: str):
        self.kind = kind
        self._items: dict[str, T] = {}

    def register(self, key: str, item: T) -> None:
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError(f"{self.kind} registry key cannot be empty.")
        self._items[normalized_key] = item

    def get(self, key: str) -> T:
        normalized_key = str(key).strip()
        if normalized_key not in self._items:
            raise KeyError(f"{self.kind} registry does not contain '{normalized_key}'.")
        return self._items[normalized_key]

    def contains(self, key: str) -> bool:
        return str(key).strip() in self._items

    def list_items(self) -> list[tuple[str, T]]:
        return sorted(self._items.items(), key=lambda item: item[0])


@dataclass(slots=True)
class ComponentDescriptor:
    id: str
    kind: str
    name: str
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class BackendRegistries:
    stage_registry: Registry[object]
    connector_registry: Registry[ComponentDescriptor]
    generation_registry: Registry[ComponentDescriptor]
    renderer_registry: Registry[ComponentDescriptor]

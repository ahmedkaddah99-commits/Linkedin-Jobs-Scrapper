from .base import LocalCLIProvider


class CodexCLIProvider(LocalCLIProvider):
    def __init__(self, command: tuple[str, ...] = (), *, model: str = "", timeout_seconds: int | None = None) -> None:
        super().__init__(
            "codex", command[0] if command else "codex", command, model=model, timeout_seconds=timeout_seconds
        )

from .base import LocalCLIProvider


class OpenCodeCLIProvider(LocalCLIProvider):
    def __init__(self, command: tuple[str, ...] = (), *, model: str = "", timeout_seconds: int | None = None) -> None:
        super().__init__(
            "opencode_subscription",
            command[0] if command else "opencode",
            command,
            model=model,
            timeout_seconds=timeout_seconds,
        )

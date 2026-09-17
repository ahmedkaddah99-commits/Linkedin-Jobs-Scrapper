from .base import LocalCLIProvider


class CodexCLIProvider(LocalCLIProvider):
    def __init__(self, command: tuple[str, ...] = ()) -> None:
        super().__init__("codex", "codex", command)

from .base import LocalCLIProvider


class OpenCodeCLIProvider(LocalCLIProvider):
    def __init__(self, command: tuple[str, ...] = ()) -> None:
        super().__init__("opencode", "opencode", command)

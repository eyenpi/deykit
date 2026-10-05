"""Portable internal component policy shared by the private filesystem adapters."""

from deykit.storage.errors import fail

Parts = tuple[str, ...]
_RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {
    f"{prefix}{suffix}" for prefix in ("com", "lpt") for suffix in "123456789¹²³"
}


def check_component(part: str) -> None:
    if (
        not part
        or part in {".", ".."}
        or part[-1:] in {".", " "}
        or any(ord(char) < 32 or char in '/\\:*?"<>|' for char in part)
        or part.split(".", 1)[0].casefold() in _RESERVED
    ):
        fail("unsafe_source_path")

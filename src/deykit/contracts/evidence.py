"""Exact hashes for ordered persisted evidence bodies."""

from deykit.contracts.json_value import bytes_hash


def evidence_hash(bodies: tuple[bytes, ...]) -> str:
    """Hash the ordered body hashes using the established evidence envelope."""
    return bytes_hash("\n".join(bytes_hash(body) for body in bodies).encode("ascii"))

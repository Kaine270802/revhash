"""Text helpers for revhash — str <-> bytes strict.

Provides explicit ``compress_text`` / ``decompress_text`` that wrap
``compress`` / ``decompress`` with UTF-8 strict handling. Imported at the
tail of ``revhash/__init__.py`` to avoid circular imports (like dict_builder).
"""

from __future__ import annotations

from . import compress as _compress, decompress as _decompress


def compress_text(
    text: str,
    codec: str = "zstd",
    level: int = 3,
    chunk_size: int = 4 * 1024 * 1024,
    dict_data: bytes | None = None,
    encoding: str = "utf-8",
) -> bytes:
    """Compress ``str`` → revhash blob (UTF-8 strict).

    Args:
        text: must be ``str``; ``bytes`` raises ``TypeError``.
        codec, level, chunk_size, dict_data: as in :func:`revhash.compress`.
        encoding: text encoding (default ``utf-8``) with ``errors="strict"``.

    Returns:
        revhash blob ``bytes``.

    Raises:
        TypeError: if ``text`` is not ``str``.
        UnicodeEncodeError: if ``text`` cannot be encoded with ``encoding`` strict.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    return _compress(
        text.encode(encoding, "strict"),
        codec=codec,
        level=level,
        chunk_size=chunk_size,
        dict_data=dict_data,
    )


def decompress_text(
    blob: bytes,
    dict_data: bytes | None = None,
    encoding: str = "utf-8",
) -> str:
    """Decompress revhash blob → ``str`` (UTF-8 strict).

    Args:
        blob: revhash blob ``bytes`` (or ``bytearray``/``memoryview``).
        dict_data: optional dictionary bytes.
        encoding: text encoding for ``bytes.decode`` strict.

    Returns:
        Decoded ``str``.

    Raises:
        TypeError: if ``blob`` is not bytes-like.
        UnicodeDecodeError: if decompressed bytes are not valid ``encoding``.
    """
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise TypeError("blob must be bytes")
    return _decompress(blob, dict_data=dict_data).decode(encoding, "strict")

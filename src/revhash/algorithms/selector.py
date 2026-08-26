"""Auto codec/level/chunk selector for revhash — Optimization Builder (M3b).

Implements ``research.md §6.5`` + ``api.md §6`` hybrid 3-tier logic.

Decision table (research §6.5):

| File size            | Content         | Codec suggestion     | Reason                     |
|----------------------|-----------------|----------------------|----------------------------|
| < 10 KB              | any             | zstd-3 + dict        | dict reduces 80%           |
| 10 KB-1 MB text      | text repeat     | zstd-3               | fast, ratio good           |
| 10 KB-1 MB realistic | natural text    | zstd-9 / brotli-6    | balanced ratio             |
| 1 MB-100 MB          | any             | zstd-3 streaming     | 0% overhead, 600+ MB/s     |
| >100 MB → GB        | any             | zstd-3 streaming 4MB | O(1) bounded               |
| archival             | any             | zstd-19 / lzma-6     | max ratio, offline         |
| random/binary        | —               | store / zstd-3(autodetect) | avoid inflation          |

Chunk tuning (research §5.2):

- <10 MB  → 1 MiB
- 10 MB-1 GiB → 4 MiB  (default)
- >1 GiB  → 8 MiB

Dictionary heuristic (research §5.4, api.md §2.3):

- Use dict if ``data_len <64 KiB`` and dict available, or for first chunk
  of large file (helps initial window).

This module is deliberately dependency-light; ``compress_auto`` lazily
imports ``revhash`` to avoid circular imports.
"""

from __future__ import annotations


__all__ = [
    "auto_select",
    "estimate_ratio",
    "choose_best_chunk",
    "should_use_dict",
    "compress_auto",
]

# ── constants (mirrors research) ────────────────────────────────────────────
CHUNK_1M: int = 1 * 1024 * 1024
CHUNK_4M: int = 4 * 1024 * 1024
CHUNK_8M: int = 8 * 1024 * 1024

THRESH_SMALL: int = 10 * 1024  # 10 KB
THRESH_MEDIUM: int = 1 * 1024 * 1024  # 1 MB
THRESH_LARGE: int = 100 * 1024 * 1024  # 100 MB
THRESH_DICT: int = 64 * 1024  # 64 KB
THRESH_CHUNK_1M: int = 10 * 1024 * 1024  # <10 MB →1M
THRESH_CHUNK_4M: int = 1 * 1024 * 1024 * 1024  # 10 MB-1 GB →4M, >1 GB→8M


def choose_best_chunk(data_len: int) -> int:
    """Choose optimal chunk size based on total data length.

    Args:
        data_len: total bytes of data (file size or len(data)).

    Returns:
        chunk_size bytes: 1 MiB if ``data_len <10 MB``, 4 MiB if
        ``10 MB ≤ data_len ≤1 GB``, 8 MiB if ``data_len >1 GB``.

    Raises:
        ValueError: if data_len is negative.

    Examples:
        >>> choose_best_chunk(5*1024*1024)
        1048576
        >>> choose_best_chunk(500*1024*1024)
        4194304
    """
    if not isinstance(data_len, int):
        raise TypeError(f"data_len must be int, got {type(data_len)}")
    if data_len < 0:
        raise ValueError(f"data_len must be >=0, got {data_len}")
    if data_len < THRESH_CHUNK_1M:
        return CHUNK_1M
    if data_len <= THRESH_CHUNK_4M:
        return CHUNK_4M
    return CHUNK_8M


def should_use_dict(data_len: int, dict_data: bytes | None) -> bool:
    """Decide whether to use dictionary for compression.

    Args:
        data_len: size of data to compress (total file size or chunk size).
        dict_data: dictionary bytes if available, else ``None``.

    Returns:
        True if ``dict_data`` exists and:
          - ``data_len <64 KiB`` (small file, 80% saving per research §5.4), OR
          - ``data_len`` is large (first chunk of large file benefits from dict).

    Logic:
        - If no dict → False.
        - If small (<64 KB) → True.
        - If large (≥10 MB) → True (first chunk of streaming file, helps
          initial window before data fills window).
        - Otherwise (64 KB-10 MB) → False (LZ window already helps).

    Note: For total-file context, ``data_len`` is file size. For
    per-chunk call, pass chunk size.
    """
    if dict_data is None:
        return False
    # Empty bytes is considered no dict
    try:
        if len(dict_data) == 0:  # type: ignore
            return False
    except Exception:
        return False

    if not isinstance(data_len, int):
        # Be lenient for None? Caller may pass None for unknown stream size
        return False
    if data_len < 0:
        return False

    # Small file → dict highly beneficial (research 80% saving)
    if data_len < THRESH_DICT:
        return True
    # Large file first chunk → dict helps initial window
    # Heuristic: files >=10 MB use dict for first chunk
    if data_len >= THRESH_CHUNK_1M:
        # For large files, dict helps first 1-4 MB chunk
        # We return True to suggest using dict for whole stream;
        # zstd will use it for first window.
        return True
    # Medium (64 KB -10 MB) → window sufficient, dict overhead not worth
    return False


def estimate_ratio(data: bytes, codec: str = "zstd", level: int = 3) -> float:
    """Estimate compression ratio for *data* with *codec*/*level*.

    Actually compresses the sample (or prefix) and returns
    ``len(compressed)/len(original)``. Ratio <1.0 means saving.
    Used for store-fallback heuristic and for Verifier benchmarks.

    Args:
        data: bytes to test (can be prefix sample, e.g. 64 KB).
        codec: codec name (``"zstd"``, ``"gzip"``, ``"lzma"``, ``"brotli"``, ``"store"``).
        level: codec level.

    Returns:
        Ratio float (0.0 for empty, >1.0 means inflation).

    Notes:
        - Imports ``revhash.codec.compress_raw`` lazily to avoid circular deps.
        - If backend missing, tries ``revhash.compress`` fallback.
        - Never raises on missing codec; returns ``1.0`` on error.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"data must be bytes, got {type(data)}")
    data_b = bytes(data)
    if len(data_b) == 0:
        return 0.0
    # For very large data, sample prefix to keep estimate fast
    # Use first 256 KB or up to 1 MB
    sample = data_b
    if len(sample) > 256 * 1024:
        # For huge data, estimate on prefix is representative for text_repeat/realistic
        # But for random, prefix vs whole similar.
        sample = sample[: 256 * 1024]

    try:
        from ..codec import compress_raw  # type: ignore

        comp = compress_raw(sample, codec=codec, level=level, allow_store_fallback=False)
        # If codec internally fell back to store (len(comp) == len(sample) for incompressible with allow fallback? But we disabled fallback)
        # compute ratio on sample
        return len(comp) / len(sample) if len(sample) else 0.0
    except Exception:
        # Fallback via revhash high-level (includes header) - still indicative
        try:
            # Lazy import to avoid circular
            import importlib

            rev = importlib.import_module("revhash")
            blob = rev.compress(sample, codec=codec, level=level, chunk_size=CHUNK_1M)  # type: ignore
            # Header overhead inflates ratio for small samples; subtract minimal overhead estimate 60B?
            # Use raw ratio as fallback; if blob small, just compute blob/sample.
            # More accurate: return blob/sample but header makes small samples look worse; so we approximate raw via header stripped?
            # For estimate we keep it simple: blob ratio
            return len(blob) / len(sample) if len(sample) else 0.0
        except Exception:
            return 1.0


def _is_text_like(data: bytes, sample: bytes | None = None) -> bool | None:
    """Heuristic: detect if *data* is text-like vs binary/random.

    Returns:
        True  — likely text (printable / utf8)
        False — likely binary/random
        None  — unknown / empty

    Heuristic:
        - Empty → None
        - Try utf-8 decode; if succeeds and printable ratio >0.85 → True
        - Check byte entropy estimate by compressibility? Use quick ratio.
        - If data is incompressible (estimate_ratio ~1.0) → False (random)
    """
    if data is None or len(data) == 0:
        return None
    b = sample if sample is not None else data[:4096]
    if len(b) == 0:
        return None
    # Printable check
    try:
        text = b.decode("utf-8", errors="strict")
        # Count printable (including whitespace, viet chars)
        printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
        ratio = printable / max(1, len(text))
        if ratio > 0.85:
            return True
        if ratio < 0.5:
            return False
    except UnicodeDecodeError:
        pass
    # Byte-level printable ASCII heuristic
    # Count bytes in typical text ranges (32-126, plus viet utf8 continuation bytes)
    # For utf8 viet, bytes are 0xC3 etc., so not purely ascii; but high-byte is common.
    # Simpler: if many zero bytes or high entropy, treat as binary.
    # Count zero/null bytes
    zeros = b.count(b"\x00")
    if zeros > len(b) * 0.05:
        return False
    # Fallback: unknown → None
    return None


def auto_select(
    data_len: int | None,
    is_text: bool | None = None,
    prefer: str = "balanced",
) -> dict:
    """Auto-select codec, level, chunk_size, use_dict per research §6.5.

    Args:
        data_len: total size bytes (or ``None`` for unknown stream length).
        is_text: hint about content (``True``=text repeat/high compressibility,
                 ``False``=realistic/binary, ``None``=auto-detect/unknown).
                 If ``None`` and ``data_len`` is medium, we default to balanced.
        prefer: strategy preference — ``"balanced"`` (default), ``"speed"``,
                ``"ratio"``, ``"archival"``, ``"store"``, ``"compatibility"``
                (gzip), ``"brotli"`` (force brotli for text).

    Returns:
        dict with keys ``{"codec": str, "level": int, "chunk_size": int, "use_dict": bool}``.

    Raises:
        ValueError: on invalid prefer or data_len negative.

    Examples:
        >>> auto_select(10*1024)
        {'codec': 'zstd', 'level': 3, 'chunk_size': 1048576, 'use_dict': True}
        >>> auto_select(100*1024*1024)
        {'codec': 'zstd', 'level': 3, 'chunk_size': 4194304, 'use_dict': False}
    """
    # Normalize and validate
    if data_len is not None and not isinstance(data_len, int):
        raise TypeError(f"data_len must be int|None, got {type(data_len)}")
    if data_len is not None and data_len < 0:
        raise ValueError(f"data_len must be >=0, got {data_len}")
    if prefer is None:
        prefer = "balanced"
    prefer = str(prefer).lower().strip()

    valid_prefers = {
        "balanced",
        "speed",
        "ratio",
        "high",
        "archival",
        "store",
        "compatibility",
        "gzip",
        "brotli",
        "lzma",
    }
    if prefer not in valid_prefers:
        raise ValueError(f"unknown prefer='{prefer}', expected one of {sorted(valid_prefers)}")

    # Handle explicit store / compatibility
    if prefer == "store":
        chunk = choose_best_chunk(data_len) if data_len is not None else CHUNK_4M
        return {"codec": "store", "level": 0, "chunk_size": chunk, "use_dict": False}
    if prefer in ("compatibility", "gzip"):
        chunk = choose_best_chunk(data_len) if data_len is not None else CHUNK_4M
        return {"codec": "gzip", "level": 6, "chunk_size": chunk, "use_dict": False}
    if prefer == "lzma":
        chunk = choose_best_chunk(data_len) if data_len is not None else CHUNK_4M
        return {"codec": "lzma", "level": 6, "chunk_size": chunk, "use_dict": False}
    if prefer == "brotli":
        # Force brotli-6 (web) or brotli-11 if archival
        chunk = choose_best_chunk(data_len) if data_len is not None else CHUNK_4M
        level = 6 if data_len is None or data_len < THRESH_LARGE else 11
        return {"codec": "brotli", "level": level, "chunk_size": chunk, "use_dict": False}

    # Archival overrides size logic
    if prefer == "archival":
        chunk = choose_best_chunk(data_len) if data_len is not None else CHUNK_4M
        # For archival, use max ratio codec: zstd-19 (or lzma-6 if prefer lzma)
        # Choose zstd-19 as default archival per research (balanced speed vs lzma)
        return {"codec": "zstd", "level": 19, "chunk_size": chunk, "use_dict": False}

    # Unknown length streaming → safe default zstd-3 4M
    if data_len is None:
        return {"codec": "zstd", "level": 3, "chunk_size": CHUNK_4M, "use_dict": False}

    chunk = choose_best_chunk(data_len)

    # ── Size-based tier ─────────────────────────────────────────────
    # <10 KB
    if data_len < THRESH_SMALL:
        # Use dict if available (research shows 80% saving)
        # Caller should check should_use_dict with actual dict_data; we signal True
        return {"codec": "zstd", "level": 3, "chunk_size": chunk, "use_dict": True}

    # 10 KB -1 MB
    if data_len < THRESH_MEDIUM:
        # Text vs realistic branch
        # is_text True → highly compressible text_repeat → zstd-3 (fast, enough)
        # is_text False (realistic) → need higher ratio → zstd-9 / brotli-6
        # If is_text is None (unknown), treat as balanced → zstd-3
        if is_text is True:
            return {"codec": "zstd", "level": 3, "chunk_size": chunk, "use_dict": data_len < THRESH_DICT}
        if is_text is False:
            # Realistic natural text → zstd-9 (or brotli-6 if prefer asks)
            if prefer == "speed":
                return {"codec": "zstd", "level": 3, "chunk_size": chunk, "use_dict": False}
            if prefer == "brotli":
                return {"codec": "brotli", "level": 6, "chunk_size": chunk, "use_dict": False}
            # balanced / ratio → zstd-9
            return {"codec": "zstd", "level": 9, "chunk_size": chunk, "use_dict": False}
        # is_text is None → unknown, choose balanced zstd-3
        if prefer in ("ratio", "high"):
            return {"codec": "zstd", "level": 9, "chunk_size": chunk, "use_dict": False}
        return {"codec": "zstd", "level": 3, "chunk_size": chunk, "use_dict": data_len < THRESH_DICT}

    # 1 MB -100 MB → zstd-3 streaming
    if data_len < THRESH_LARGE:
        # For this range, zstd-3 0% overhead streaming is optimal per baseline
        # If prefer ratio, bump to level 9
        level = 9 if prefer in ("ratio", "high") else 3
        return {"codec": "zstd", "level": level, "chunk_size": chunk, "use_dict": False}

    # >100 MB → GB : zstd-3 streaming 4M (or 8M for >1GB via choose_best_chunk)
    # keep dict=False for now (first chunk benefit is considered in should_use_dict, but auto_select without dict_data keeps False)
    level = 9 if prefer in ("ratio", "high") else 3
    return {"codec": "zstd", "level": level, "chunk_size": chunk, "use_dict": False}


def compress_auto(
    data: bytes,
    dict_data: bytes | None = None,
    prefer: str = "balanced",
) -> bytes:
    """Compress *data* with automatically selected codec/level/chunk.

    Wraps :func:`revhash.compress` with :func:`auto_select` + :func:`should_use_dict`.

    Args:
        data: raw bytes to compress.
        dict_data: optional dictionary bytes (from ``dict_builder``). Only used
                   if ``should_use_dict(len(data), dict_data)`` and
                   ``auto_select(..., prefer)`` suggests ``use_dict``.
        prefer: compression preference forwarded to ``auto_select``.

    Returns:
        revhash blob bytes (including header, footer). Decodable via
        :func:`revhash.decompress` (with embedded dict if used).

    Notes:
        - Imports ``revhash`` lazily to avoid circular import (``selector``
          is imported by ``revhash`` via ``algorithms``).
        - For incompressible/random data where ``estimate_ratio`` >1.0,
          ``revhash.compress`` already auto-fallbacks to ``store``.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"data must be bytes, got {type(data)}")
    data_b = bytes(data)

    # Heuristic text detection for medium range
    text_hint: bool | None = None
    # Only use heuristic for 10KB-1MB where decision matters
    if THRESH_SMALL <= len(data_b) < THRESH_MEDIUM:
        text_hint = _is_text_like(data_b)

    cfg = auto_select(len(data_b), is_text=text_hint, prefer=prefer)

    # Decide dict usage: cfg's use_dict flag AND should_use_dict with actual dict
    use_dict_flag: bool = bool(cfg.get("use_dict", False))
    if dict_data is not None:
        # If cfg suggests dict, double-check with should_use_dict using actual dict size
        if use_dict_flag:
            use_dict_flag = should_use_dict(len(data_b), dict_data)
        else:
            # Even if cfg says no dict, large files may still benefit for first chunk
            # Only re-enable if small or large file heuristic says True
            # To avoid surprising behaviour, we only enable if large and dict exists and small check would say True
            # For now respect cfg: no dict if cfg says no, unless large file
            if len(data_b) >= THRESH_CHUNK_1M and len(data_b) < THRESH_DICT:
                use_dict_flag = should_use_dict(len(data_b), dict_data)
            # For large files (>10MB), cfg returns False but should_use_dict would return True for dict help
            # We choose to enable dict for large files if provided and should_use_dict says True
            elif len(data_b) >= THRESH_CHUNK_1M:
                # Check if dict would help first chunk
                if should_use_dict(len(data_b), dict_data):
                    use_dict_flag = True
    else:
        use_dict_flag = False

    # Estimate random/incompressible: if ratio >1.0 and not store, we let revhash.compress handle auto-store
    # But we can pre-check to avoid overhead: if data looks random and small, force store
    # Use estimate_ratio only for small-medium; for large skip to avoid double compress cost
    if len(data_b) > 0 and len(data_b) < 2 * 1024 * 1024:
        # Quick check: try estimate for default codec, if inflation then force store
        if cfg["codec"] != "store":
            try:
                ratio = estimate_ratio(data_b, codec=cfg["codec"], level=cfg["level"])
                if ratio > 1.0:
                    # Incompressible → store is better (avoid expansion)
                    cfg = {"codec": "store", "level": 0, "chunk_size": cfg["chunk_size"], "use_dict": False}
                    use_dict_flag = False
            except Exception:
                pass

    # Lazy import revhash.compress
    import importlib

    rev = importlib.import_module("revhash")
    # rev.compress is the high-level API in src/revhash/__init__.py
    d = dict_data if use_dict_flag else None
    # Call with selected params
    return rev.compress(data_b, codec=cfg["codec"], level=cfg["level"], chunk_size=cfg["chunk_size"], dict_data=d)

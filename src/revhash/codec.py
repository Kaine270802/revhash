"""Codec dispatch for revhash — frozen M2 contract.

Backend table:
    0 store  — raw copy
    1 gzip   — gzip / zlib
    2 zstd   — zstandard (stream_writer/stream_reader)
    3 lzma   — lzma
    4 brotli — brotli

Streaming API for chunk/file is in stream.py; this module handles
single-shot raw compress/decompress used by in-memory compress() and
for small payloads.
"""

from __future__ import annotations

import gzip
import io

from .exceptions import RevHashDictError, RevHashUnsupportedCodecError
from .header import CODEC_TO_ID, ID_TO_CODEC, _normalize_codec_id

# ── Optional lzma (stdlib but may be missing on minimal builds) ─────────────
try:
    import lzma  # type: ignore

    HAS_LZMA = True
except Exception:  # pragma: no cover
    lzma = None  # type: ignore
    HAS_LZMA = False


# ── Optional brotli ────────────────────────────────────────────────────────
try:
    import brotli as _brotli  # type: ignore

    HAS_BROTLI = True
except Exception:  # pragma: no cover
    _brotli = None  # type: ignore
    HAS_BROTLI = False

# ── Optional zstandard ─────────────────────────────────────────────────────
try:
    import zstandard as _zstd  # type: ignore

    HAS_ZSTD = True
except Exception:  # pragma: no cover
    _zstd = None  # type: ignore
    HAS_ZSTD = False

# Convenience map for public consumption
CODEC_MAP = {
    0: "store",
    1: "gzip",
    2: "zstd",
    3: "lzma",
    4: "brotli",
    "store": 0,
    "gzip": 1,
    "zstd": 2,
    "lzma": 3,
    "brotli": 4,
}
CODEC_ID_TABLE = CODEC_TO_ID
CODEC_NAME_TABLE = ID_TO_CODEC


# ── Helpers ────────────────────────────────────────────────────────────────
def _ensure_codec(codec: str | int) -> tuple[str, int]:
    cid = _normalize_codec_id(codec)
    return ID_TO_CODEC[cid], cid


def _validate_level(codec: str, level: int) -> None:
    if codec == "store":
        return
    if codec == "gzip":
        if not (0 <= level <= 9):
            raise ValueError(f"gzip level {level} must be 0..9")
    elif codec == "zstd":
        if not (1 <= level <= 22):
            raise ValueError(f"zstd level {level} must be 1..22")
    elif codec == "lzma":
        if not (0 <= level <= 9):
            raise ValueError(f"lzma preset {level} must be 0..9")
    elif codec == "brotli":
        if not (0 <= level <= 11):
            raise ValueError(f"brotli quality {level} must be 0..11")


def _make_zstd_dict(dict_data: bytes | None):
    if dict_data is None or len(dict_data) == 0:
        return None
    if not HAS_ZSTD:
        raise RevHashUnsupportedCodecError("zstandard not installed but dict_data requested")
    # zstandard.ZstdCompressionDict expects bytes-like
    return _zstd.ZstdCompressionDict(dict_data)  # type: ignore


# ── Per-codec raw primitives ───────────────────────────────────────────────
def _compress_store(data: bytes, level: int, dict_data: bytes | None) -> bytes:
    return bytes(data)


def _decompress_store(blob: bytes, dict_data: bytes | None) -> bytes:
    return bytes(blob)


def _compress_gzip(data: bytes, level: int, dict_data: bytes | None) -> bytes:
    if dict_data:
        # gzip doesn't support dict; raise dict error per spec policy
        raise RevHashDictError("gzip does not support dictionary")
    # level 0..9, default 6; 0 is store-like
    return gzip.compress(data, compresslevel=level)


def _decompress_gzip(blob: bytes, dict_data: bytes | None) -> bytes:
    if dict_data:
        raise RevHashDictError("gzip does not use dictionary")
    return gzip.decompress(blob)


def _compress_zstd(data: bytes, level: int, dict_data: bytes | None) -> bytes:
    if not HAS_ZSTD:
        raise RevHashUnsupportedCodecError("zstandard not installed")
    dict_obj = _make_zstd_dict(dict_data)
    cctx = _zstd.ZstdCompressor(level=level, dict_data=dict_obj)  # type: ignore
    return cctx.compress(data)


def _decompress_zstd(blob: bytes, dict_data: bytes | None) -> bytes:
    if not HAS_ZSTD:
        raise RevHashUnsupportedCodecError("zstandard not installed")
    dict_obj = _make_zstd_dict(dict_data)
    dctx = _zstd.ZstdDecompressor(dict_data=dict_obj)  # type: ignore
    # Use stream_reader for robustness with unknown output size
    # cctx.compress embeds content size, but if dict changes etc, decompress with max size may fail.
    # Stream path handles max size correctly.
    reader = io.BytesIO(blob)
    out = io.BytesIO()
    with dctx.stream_reader(reader) as sreader:
        while True:
            chunk = sreader.read(16384)
            if not chunk:
                break
            out.write(chunk)
    return out.getvalue()


def _compress_lzma(data: bytes, level: int, dict_data: bytes | None) -> bytes:
    if not HAS_LZMA:
        raise RevHashUnsupportedCodecError("lzma not available in this build")
    if dict_data:
        raise RevHashDictError("lzma does not support external dictionary in this build")
    # preset is 0..9, maps to level
    return lzma.compress(data, preset=level)  # type: ignore


def _decompress_lzma(blob: bytes, dict_data: bytes | None) -> bytes:
    if not HAS_LZMA:
        raise RevHashUnsupportedCodecError("lzma not available in this build")
    if dict_data:
        raise RevHashDictError("lzma dict not supported")
    return lzma.decompress(blob)  # type: ignore


def _compress_brotli(data: bytes, level: int, dict_data: bytes | None) -> bytes:
    if not HAS_BROTLI:
        raise RevHashUnsupportedCodecError("brotli not installed — pip install brotli")
    if dict_data:
        raise RevHashDictError("brotli dict not supported in raw mode")
    # quality 0..11
    return _brotli.compress(data, quality=level)  # type: ignore


def _decompress_brotli(blob: bytes, dict_data: bytes | None) -> bytes:
    if not HAS_BROTLI:
        raise RevHashUnsupportedCodecError("brotli not installed")
    if dict_data:
        raise RevHashDictError("brotli dict not supported")
    return _brotli.decompress(blob)  # type: ignore


# dispatch maps
_COMPRESS_FNS = {
    "store": _compress_store,
    "gzip": _compress_gzip,
    "zstd": _compress_zstd,
    "lzma": _compress_lzma,
    "brotli": _compress_brotli,
}
_DECOMPRESS_FNS = {
    "store": _decompress_store,
    "gzip": _decompress_gzip,
    "zstd": _decompress_zstd,
    "lzma": _decompress_lzma,
    "brotli": _decompress_brotli,
}


# ── Public API ─────────────────────────────────────────────────────────────
def compress_raw(
    data: bytes,
    codec: str | int = "zstd",
    level: int = 3,
    dict_data: bytes | None = None,
    *,
    allow_store_fallback: bool = True,
) -> bytes:
    """Compress *data* with *codec* at *level*.

    Args:
        data: raw bytes to compress.
        codec: codec name ("store","gzip","zstd","lzma","brotli","auto") or id.
        level: codec level (validated per codec).
        dict_data: optional dictionary bytes (only zstd uses it).
        allow_store_fallback: if True, when compressed size > original, return original
            bytes (store semantics). Caller may inspect length to detect fallback.

    Returns:
        Compressed bytes (or raw copy on fallback).

    Raises:
        RevHashUnsupportedCodecError: unknown codec or missing backend.
        RevHashDictError: dict misuse.
    """
    cname, _cid = _ensure_codec(codec)
    if cname == "auto":
        cname = "zstd"
    _validate_level(cname, level)
    # dict sanity: only zstd / maybe future; enforce
    if dict_data is not None and cname not in ("zstd",):
        # Allow but warn? spec says dict only for zstd; so if user passes dict for non-zstd raise
        # However if dict_data is empty don't raise
        if len(dict_data) > 0:
            raise RevHashDictError(f"codec '{cname}' does not support dictionary")
    fn = _COMPRESS_FNS[cname]
    comp = fn(data, level, dict_data)
    if allow_store_fallback and cname != "store":
        if len(comp) > len(data):
            # store fallback — return raw copy to avoid inflation
            comp = bytes(data)
    return comp


def decompress_raw(
    blob: bytes,
    codec: str | int = "zstd",
    dict_data: bytes | None = None,
) -> bytes:
    """Decompress *blob* compressed with *codec*.

    Args:
        blob: compressed payload (raw frame without revhash header).
        codec: codec name or id that was used for compression.
        dict_data: optional dict bytes (must match compressor).

    Returns:
        Decompressed bytes.

    Raises:
        RevHashUnsupportedCodecError / RevHashDictError / others as per backend.
    """
    # Support alternative signature decompress_raw(blob, dict_data) where codec omitted and blob is full revhash blob — but that case should be handled by header layer.
    # For backward compat, allow dict_data as second positional without codec if codec looks like bytes
    # Primary signature is (blob, codec, dict_data)
    cname, _cid = _ensure_codec(codec)
    fn = _DECOMPRESS_FNS[cname]
    # Validate dict
    if dict_data is not None and len(dict_data) > 0 and cname not in ("zstd",):
        raise RevHashDictError(f"codec '{cname}' does not use dict")
    try:
        return fn(blob, dict_data)
    except RevHashDictError:
        raise
    except RevHashUnsupportedCodecError:
        raise
    except Exception as exc:  # noqa: BLE001
        # Wrap backend errors that look like dict mismatch as RevHashDictError for zstd
        msg = str(exc).lower()
        if "dictionary" in msg or "dict" in msg:
            raise RevHashDictError(f"dictionary error: {exc}") from exc
        raise


_CACHE_KEY: tuple | None = None
_CACHE_VAL: dict[str, bool] | None = None


def get_available_codecs() -> dict[str, bool]:
    """Return availability of each codec.

    Returns:
        dict mapping codec name to bool: {"store":True,"gzip":True,"zstd":bool,"lzma":bool,"brotli":bool}
    """
    global _CACHE_KEY, _CACHE_VAL
    key = (HAS_ZSTD, HAS_LZMA, HAS_BROTLI)
    if _CACHE_VAL is not None and _CACHE_KEY == key:
        return _CACHE_VAL
    val = {"store": True, "gzip": True, "zstd": HAS_ZSTD, "lzma": HAS_LZMA, "brotli": HAS_BROTLI}
    _CACHE_KEY = key
    _CACHE_VAL = val
    return val


def _cache_clear() -> None:
    global _CACHE_KEY, _CACHE_VAL
    _CACHE_KEY = None
    _CACHE_VAL = None


# compat for tests that expect lru_cache API
get_available_codecs.cache_clear = _cache_clear  # type: ignore[attr-defined]
get_available_codecs.cache_info = lambda: None  # type: ignore[attr-defined]


# Extra helper that returns flag (useful for header auto-store)
def compress_raw_with_flag(
    data: bytes,
    codec: str | int = "zstd",
    level: int = 3,
    dict_data: bytes | None = None,
) -> tuple[bytes, bool]:
    """Compress and report whether store fallback was triggered.

    Returns:
        (blob, was_stored) — was_stored True if fallback to store (blob == data).
    """
    cname, _cid = _ensure_codec(codec)
    raw_no_fallback = compress_raw(data, codec=cname, level=level, dict_data=dict_data, allow_store_fallback=False)
    if cname != "store" and len(raw_no_fallback) > len(data):
        return bytes(data), True
    return raw_no_fallback, False

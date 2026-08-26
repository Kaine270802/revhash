"""revhash — reversible lossless compression unlimited (O(1) streaming).

Public API frozen M2 (docs/api.md §2):

    import revhash

    blob = revhash.compress(b"hello world"*1000, codec="zstd", level=3)
    orig = revhash.decompress(blob)

    revhash.compress_file("input.txt", "out.rvh", codec="zstd")
    revhash.decompress_file("out.rvh", "restored.txt")

    revhash.compress_stream(reader, writer, codec="zstd")
    revhash.decompress_stream(reader, writer)

    revhash.verify(blob)          # per-chunk CRC + global SHA256
    revhash.get_info(blob)        # header info

All APIs are O(1) streaming friendly; compress_file/decompress_file never
load whole file (use read(chunk_size) loops).
"""

from __future__ import annotations

import io

from .codec import (
    HAS_BROTLI,
    HAS_ZSTD,
    compress_raw_with_flag,
    get_available_codecs as _codec_get_available,
)
from .exceptions import RevHashCorruptedError, RevHashDictError, RevHashError, RevHashUnsupportedCodecError
from .header import (
    FOOTER_MAGIC,
    FOOTER_SHA_SIZE,
    HEADER_SIZE,
    UNKNOWN_SIZE,
    RevHashHeader,
)
from .stream import compress_file, compress_stream, decompress_file, decompress_stream

# HAS_LZMA guard (stdlib may be missing on minimal builds)
try:
    import lzma  # noqa: F401

    HAS_LZMA = True
except Exception:  # pragma: no cover
    HAS_LZMA = False

__version__ = "0.3.0"
__all__ = [
    "__version__",
    "compress",
    "decompress",
    "compress_text",
    "decompress_text",
    "compress_file",
    "decompress_file",
    "compress_stream",
    "decompress_stream",
    "verify",
    "get_info",
    "get_available_codecs",
    "RevHashError",
    "RevHashCorruptedError",
    "RevHashDictError",
    "RevHashUnsupportedCodecError",
    "RevHashHeader",
    # Optimization Builder (M3b) — re-exported for convenience
    "dict_builder",
    "algorithms",
]


# ── Codec availability helpers (Core Embed) ──────────────────────────────────
def get_available_codecs() -> dict[str, bool]:
    """Return availability of each codec.

    Returns:
        dict mapping codec name to bool: {"store":True,"gzip":True,"zstd":bool,"lzma":bool,"brotli":bool}
    """
    try:
        return _codec_get_available()
    except Exception:  # pragma: no cover
        return {"store": True, "gzip": True, "zstd": HAS_ZSTD, "lzma": HAS_LZMA, "brotli": HAS_BROTLI}


def _resolve_codec(codec: str) -> str:
    """Resolve ``codec`` handling ``auto`` fallback and availability.

    Args:
        codec: codec name (may be "auto").

    Returns:
        Resolved codec name.

    Raises:
        RevHashUnsupportedCodecError: if requested codec not available.
    """
    if codec == "auto":
        avail = get_available_codecs()
        if avail.get("zstd"):
            return "zstd"
        if avail.get("gzip"):
            return "gzip"
        return "store"
    avail = get_available_codecs()
    if not avail.get(codec, False):
        raise RevHashUnsupportedCodecError(
            f"codec '{codec}' not available. Available: {[k for k, v in avail.items() if v]}. pip install zstandard brotli or use codec='auto'/'gzip'"
        )
    return codec


# ── In-memory bytes helpers (wrap stream) ──────────────────────────────────


def compress(
    data: bytes | str,
    codec: str = "zstd",
    level: int = 3,
    chunk_size: int = 4 * 1024 * 1024,
    dict_data: bytes | None = None,
    encoding: str = "utf-8",
) -> bytes:
    """Compress *data* bytes → revhash blob.

    Args:
        data: raw bytes (0 B → any size, for huge use compress_file/stream) or str (encoded via *encoding* strict).
        codec: "store"|"gzip"|"zstd"|"lzma"|"brotli"|"auto" (auto→zstd/gzip/store fallback).
        level: codec level (1..22 zstd, 0..9 gzip/lzma, 0..11 brotli).
        chunk_size: chunk size for CRC granularity (default 4MiB).
        dict_data: optional dictionary bytes (zstd only).
        encoding: text encoding when *data* is str (default utf-8 strict).

    Returns:
        revhash blob (header+dict+compressed_stream+footer).

    Notes:
        - Empty input returns valid header+footer.
        - If compressed size > original + header_overhead and codec != store,
          auto-fallback to store (raw) to avoid inflation on random/small data.
        - ``compress("hello")`` is byte-identical to ``compress(b"hello")`` via utf-8.
    """
    if isinstance(data, str):
        data = data.encode(encoding, "strict")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes")
    data = bytes(data)  # copy
    # Allow codec "auto"
    if codec == "auto":
        codec = _resolve_codec("auto")
    else:
        # Validate explicit codec availability early (raises RevHashUnsupportedCodecError)
        _resolve_codec(codec)
    # Try streaming path via BytesIO to ensure header/footer consistency + O(1) logic
    # For small data this is still efficient; we reuse stream implementation.
    # But we also need auto-store fallback: if stream produced larger blob than store,
    # we must return store blob instead.
    # So we call compress_stream and compare.
    # First attempt with requested codec (unless store)
    reader = io.BytesIO(data)
    writer = io.BytesIO()
    compress_stream(reader, writer, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
    blob = writer.getvalue()
    # Auto-store check: if compressed blob > len(data) + minimal header overhead and codec != store,
    # prefer store representation.
    # Minimal overhead = header + footer (no CRC if UNKNOWN? but we have CRCs). Use actual blob len.
    # If codec was not store and decompressed would be correct either way, we compare len(blob) vs store blob len.
    # Store blob size = HEADER_SIZE + dict_len?0 + len(data) + footer_len; but we approximated len(blob) > len(data)+~60
    # Simpler: if len(blob) > len(data) + 100 and codec != "store" and len(data) > 0:
    #   recompress as store and use that if smaller.
    if codec != "store" and len(data) > 0:
        # Only trigger if inflated
        # Check that codec's compressed size (without header/footer) is > data len — currently blob includes header/footer
        # If blob length > len(data) + 64 (header+footer approx) → inflation
        # Use threshold: len(blob) > len(data) + 64 (+ dict)
        overhead = (
            HEADER_SIZE
            + (len(dict_data) if dict_data else 0)
            + (FOOTER_SHA_SIZE + 4 + (len(data) + chunk_size - 1) // chunk_size * 4 if len(data) > 0 else 36)
        )
        # Actually compute store blob size accurately for comparison?
        # We'll just compare blob_len vs store blob len we can generate.
        if len(blob) > len(data) + overhead:  # rare for random
            # Build store blob
            r2 = io.BytesIO(data)
            w2 = io.BytesIO()
            compress_stream(r2, w2, codec="store", level=0, chunk_size=chunk_size, dict_data=None)
            store_blob = w2.getvalue()
            if len(store_blob) < len(blob):
                return store_blob
        # Another heuristic: if raw compress_raw without header would be larger (incompressible) we fallback
        # That case is already partially covered by stream's internal handling but ensure:
        # Use codec raw check
        try:
            raw_comp, was_stored = compress_raw_with_flag(data, codec=codec, level=level, dict_data=dict_data)
            if was_stored:
                # incompressible → store blob smaller
                r2 = io.BytesIO(data)
                w2 = io.BytesIO()
                compress_stream(r2, w2, codec="store", level=0, chunk_size=chunk_size, dict_data=None)
                store_blob = w2.getvalue()
                if len(store_blob) < len(blob):
                    return store_blob
        except Exception:
            pass
    return blob


def decompress(blob: bytes, dict_data: bytes | None = None) -> bytes:
    """Decompress revhash blob → original bytes.

    Automatically detects codec from header, validates CRC32+SHA256.

    Args:
        blob: revhash blob from compress().
        dict_data: external dict if needed (if blob has no embedded dict).

    Returns:
        Original bytes (byte-identical).

    Raises:
        RevHashCorruptedError, RevHashDictError, RevHashUnsupportedCodecError.
    """
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise TypeError("blob must be bytes")
    blob = bytes(blob)
    reader = io.BytesIO(blob)
    writer = io.BytesIO()
    decompress_stream(reader, writer, dict_data=dict_data)
    return writer.getvalue()


def verify(blob: bytes, dict_data: bytes | None = None) -> bool:
    """Verify per-chunk CRC32 + global SHA256 of *blob*.

    Returns:
        True if OK, False otherwise (does not raise on corrupted unless header parse fails).

    Raises:
        RevHashCorruptedError only for header magic/version mismatches that prevent parsing;
        for CRC/SHA mismatch returns False.
    """
    try:
        # decompress to null and verify
        decompress(blob, dict_data=dict_data)
        return True
    except RevHashCorruptedError:
        return False
    except RevHashDictError:
        return False
    except RevHashUnsupportedCodecError:
        return False
    except Exception:  # noqa: BLE001
        return False


def get_info(blob: bytes) -> dict:
    """Return header info without full decompression (except sizes).

    Args:
        blob: revhash blob.

    Returns:
        dict with keys:
            codec, codec_id, level, chunk_size, original_size, compressed_size,
            ratio, has_dict, chunks, dict_len, version, header_len, footer_magic

    Raises:
        RevHashCorruptedError on bad magic/version.
    """
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise TypeError("blob must be bytes")
    blob_b = bytes(blob)
    header, header_end = RevHashHeader.from_bytes(blob_b, 0)
    total = len(blob_b)
    # Determine footer parsing
    if header.original_size == UNKNOWN_SIZE:
        # No CRCs per spec (but decompress_stream handles lenient)
        # compressed_size = total, original_size unknown from stream? Need to decompress to know? But we can return UNKNOWN
        # For info we try to decompress quickly to get actual original_size if blob is small? For O(1) we avoid heavy.
        # We can at least report original_size as UNKNOWN and chunks=0
        compressed_size = total
        original_size_report = UNKNOWN_SIZE
        chunks = 0
        has_dict = header.dict_len > 0
        ratio = 0.0  # can't compute
        # If blob is small enough (< 10MB) we can decompress to get actual size for richer info
        if total < 20 * 1024 * 1024:
            try:
                # decompress to get actual size and sha, but keep lightweight
                dec = decompress(blob_b)
                original_size_report = len(dec)
                chunks = (original_size_report + header.chunk_size - 1) // header.chunk_size if header.chunk_size else 0
                ratio = compressed_size / original_size_report if original_size_report else 0
            except Exception:
                pass
    else:
        nc = header.num_chunks
        # Validate total >= header_end+footer_len
        if total < header_end + FOOTER_SHA_SIZE + 4:
            raise RevHashCorruptedError("blob too short for footer")
        # compressed_len = total - header_end - footer_len (not needed)
        # Parse footer CRCs for validation? Just count
        has_dict = header.dict_len > 0
        compressed_size = total
        original_size_report = header.original_size
        chunks = nc
        ratio = compressed_size / original_size_report if original_size_report else 0

    return {
        "codec": header.codec,
        "codec_id": header.codec_id,
        "level": header.level,
        "chunk_size": header.chunk_size,
        "original_size": original_size_report,
        "compressed_size": compressed_size,
        "ratio": ratio,
        "has_dict": has_dict,
        "chunks": chunks,
        "dict_len": header.dict_len,
        "version": header.version,
        "header_len": header.header_len,
        "footer_magic": FOOTER_MAGIC,
    }


# ── Optimization Builder exports (M3b) — lazy, no side-effects on Core ─────
# These imports are intentionally at the tail to avoid circular import during
# ``algorithms.selector`` → ``revhash`` lazy imports. If the optional
# modules are missing, Core API remains functional.
try:
    from . import dict_builder as dict_builder  # noqa: F401, E402  # type: ignore

    # ``algorithms`` is a package (selector + dict_builder re-export)
    from . import algorithms as algorithms  # noqa: F401, E402
except Exception:  # pragma: no cover - missing in minimal installs
    dict_builder = None  # type: ignore
    algorithms = None  # type: ignore

# ── Text helpers (Core Embed) — lazy at tail to avoid circular ────────────
# ``text.py`` imports ``compress``/``decompress`` from this module, so it must
# be imported after they are defined.
try:
    from . import text as text  # noqa: F401, E402  # type: ignore
    from .text import compress_text, decompress_text  # noqa: F401, E402  # type: ignore
except Exception:  # pragma: no cover - text missing or circular
    text = None  # type: ignore
    compress_text = None  # type: ignore
    decompress_text = None  # type: ignore

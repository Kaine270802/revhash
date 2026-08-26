"""
revhash_embedded — single-file bundle (<500KB), copy 1 file la chay.
AUTO-GENERATED from src/revhash/ — do not edit.
Source hash: sha256:66aeba38600a68e6313109e3c53bcc902d93dd9be73f5043526f2c918aa89923  Sync: python scripts/build_embedded.py
Usage: import revhash_embedded as revhash; revhash.compress_text("xin chao")
"""
# AUTO-GENERATED — do not edit, source: src/revhash/, sha256:66aeba38600a68e6313109e3c53bcc902d93dd9be73f5043526f2c918aa89923
from __future__ import annotations

import hashlib
import struct
import zlib
import gzip
import io
import os
import pathlib
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import BinaryIO, Tuple

__version__ = "0.5.0"
__bundle_hash__ = "sha256:66aeba38600a68e6313109e3c53bcc902d93dd9be73f5043526f2c918aa89923"
__all__ = ["compress","decompress","compress_text","decompress_text","compress_file","decompress_file","compress_stream","decompress_stream","verify","get_info","get_available_codecs","RevHashError","RevHashCorruptedError","RevHashDictError","RevHashUnsupportedCodecError","RevHashHeader"]

# ── exceptions.py ───────────────────────────────────────────────────
"""Exception hierarchy for revhash — frozen M2 contract.

See docs/api.md §4.
"""

class RevHashError(Exception):
    """Base class for all revhash errors."""

class RevHashCorruptedError(RevHashError):
    """Raised when blob is corrupted (CRC / SHA mismatch, bad magic)."""

class RevHashDictError(RevHashError):
    """Raised when dictionary is missing or mismatched."""

class RevHashUnsupportedCodecError(RevHashError):
    """Raised when codec id/name is unknown or backend not available."""

# ── header.py ───────────────────────────────────────────────────────
"""Binary header / footer for revhash — frozen M2 contract.

Header spec (docs/api.md §3.1):

Offset  Size  Field          Type        Description
0       4     magic          bytes       b"RVH1" (0x52 0x56 0x48 0x31)
4       1     version        uint8       0x01
5       1     codec_id       uint8       0=store,1=gzip,2=zstd,3=lzma,4=brotli
6       1     level          uint8
7       4     chunk_size     uint32 LE
11      4     dict_len       uint32 LE
15      8     original_size  uint64 LE   0xFFFFFFFFFFFFFFFF == unknown (stream)
23      N     dict_data      bytes       N = dict_len
23+N    ...   compressed_stream
...     4*Nc  per_chunk_crc  uint32 LE[]  Nc = ceil(original_size/chunk_size) ; 0 if unknown
...     32    header_sha256  bytes       v2 only: SHA256 of final header (+dict), before global_sha256
...     32    global_sha256  bytes       SHA256 of original data
...     4     footer_magic   bytes       b"RVHE"

Footer layouts (docs/api_v05.md §2):
  v1 (read-only): [crc_table nc*4] [global_sha256 32] [RVHE 4]; unknown-size drops crc_table.
  v2 (written):   [crc_table nc*4] [header_sha256 32] [global_sha256 32] [RVHE 4]; unknown-size drops crc_table.
"""

import hashlib
import struct
import zlib
from dataclasses import dataclass
from typing import Tuple

# ── Constants ──────────────────────────────────────────────────────────────
HEADER_MAGIC: bytes = b"RVH1"  # 0x52 0x56 0x48 0x31
FOOTER_MAGIC: bytes = b"RVHE"
HEADER_VERSION: int = 2
UNKNOWN_SIZE: int = 0xFFFFFFFFFFFFFFFF
HEADER_SIZE: int = 23  # 4+1+1+1+4+4+8
FOOTER_SHA_SIZE: int = 32
FOOTER_HEADER_SHA_SIZE: int = 32  # v2 only: sha256 of final header (+dict), sits before global_sha256
FOOTER_MAGIC_SIZE: int = 4

HEADER_STRUCT: struct.Struct = struct.Struct("<4sBBBIIQ")

CODEC_TO_ID: dict[str, int] = {
    "store": 0,
    "gzip": 1,
    "zstd": 2,
    "lzma": 3,
    "brotli": 4,
}
ID_TO_CODEC: dict[int, str] = {v: k for k, v in CODEC_TO_ID.items()}

def _normalize_codec_id(codec: str | int) -> int:
    if isinstance(codec, int):
        if codec not in ID_TO_CODEC:
            raise RevHashUnsupportedCodecError(f"unknown codec_id {codec}")
        return codec
    if isinstance(codec, str):
        c = codec.lower()
        if c == "auto":
            # Graceful fallback for embedded zero-deps (Critic HIGH #1) — check available codecs
            try:

                has_zstd = HAS_ZSTD
            except Exception:
                has_zstd = False
            if has_zstd:
                return CODEC_TO_ID["zstd"]
            # gzip is stdlib always available, fallback to gzip before store
            return CODEC_TO_ID["gzip"]
        if c not in CODEC_TO_ID:
            raise RevHashUnsupportedCodecError(f"unsupported codec '{codec}' (expected one of {list(CODEC_TO_ID)})")
        return CODEC_TO_ID[c]
    raise RevHashUnsupportedCodecError(f"bad codec type {type(codec)}")

def _codec_name(codec_id: int) -> str:
    try:
        return ID_TO_CODEC[codec_id]
    except KeyError:
        raise RevHashUnsupportedCodecError(f"unknown codec_id {codec_id}")

# ── RevHashHeader ──────────────────────────────────────────────────────────
@dataclass
class RevHashHeader:
    """RevHash binary header.

    Attributes:
        version: header version (1 or 2; new blobs write 2 — readers accept both).
        codec: codec name (e.g. "zstd").
        codec_id: numeric codec id.
        level: compression level for the codec.
        chunk_size: chunk size used for splitting / CRC granularity.
        dict_len: length of embedded dict_data.
        original_size: size of original uncompressed data (UNKNOWN_SIZE if streaming unknown).
        dict_data: optional embedded dictionary bytes (None if absent).
    """

    version: int = HEADER_VERSION
    codec: str = "zstd"
    codec_id: int = 2
    level: int = 3
    chunk_size: int = 4 * 1024 * 1024
    dict_len: int = 0
    original_size: int = 0
    dict_data: bytes | None = None

    def __init__(
        self,
        codec: str | int = "zstd",
        level: int = 3,
        chunk_size: int = 4 * 1024 * 1024,
        dict_data: bytes | None = None,
        original_size: int = 0,
        version: int = HEADER_VERSION,
    ) -> None:
        self.version = version
        # codec can be str or id
        if isinstance(codec, int):
            self.codec_id = _normalize_codec_id(codec)
            self.codec = _codec_name(self.codec_id)
        else:
            self.codec = codec.lower() if isinstance(codec, str) else "zstd"
            if self.codec == "auto":
                self.codec = "zstd"
            self.codec_id = _normalize_codec_id(self.codec)
        self.level = int(level)
        self.chunk_size = int(chunk_size)
        if dict_data is not None and len(dict_data) > 0:
            self.dict_data = bytes(dict_data)
            self.dict_len = len(self.dict_data)
        else:
            self.dict_data = None
            self.dict_len = 0
        # if original_size is None treat as unknown
        if original_size is None:
            self.original_size = UNKNOWN_SIZE
        else:
            self.original_size = int(original_size)

    @property
    def num_chunks(self) -> int:
        """Number of chunks = ceil(original_size / chunk_size). 0 if unknown or zero."""
        if self.original_size == UNKNOWN_SIZE or self.original_size == 0:
            return 0
        return (self.original_size + self.chunk_size - 1) // self.chunk_size if self.chunk_size > 0 else 0

    @property
    def header_len(self) -> int:
        """Total header bytes incl. dict_data."""
        return HEADER_SIZE + self.dict_len

    def footer_len(self) -> int:
        """Footer length for this header (version-aware, docs/api_v05.md §2).

        v1: nc*4 + 36 (unknown size: 36). v2: nc*4 + 68 (unknown size: 68).
        """
        extra = FOOTER_HEADER_SHA_SIZE if self.version >= 2 else 0
        if self.original_size == UNKNOWN_SIZE:
            return extra + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
        return self.num_chunks * 4 + extra + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE

    def to_bytes(self) -> bytes:
        """Serialise header (HEADER_SIZE + dict_data) to bytes.

        Returns:
            bytes: header bytes (23 + dict_len).

        Raises:
            RevHashCorruptedError: on invalid fields.
        """
        # validation — added limits for DoS protection (Critic P1-1)
        if self.chunk_size <= 0:
            raise RevHashCorruptedError("chunk_size must be >0")
        if self.chunk_size < 1024 or self.chunk_size > 64 * 1024 * 1024:
            raise RevHashCorruptedError(f"chunk_size {self.chunk_size} out of range [1K, 64M]")
        if self.dict_len > 256 * 1024:
            raise RevHashCorruptedError(f"dict_len {self.dict_len} too large (max 256KB)")
        if not (0 <= self.level <= 255):
            raise RevHashCorruptedError("level must fit in uint8")
        if self.dict_len != (len(self.dict_data) if self.dict_data else 0):
            raise RevHashCorruptedError("dict_len mismatch")
        # pack
        packed = HEADER_STRUCT.pack(
            HEADER_MAGIC,
            self.version,
            self.codec_id,
            self.level,
            self.chunk_size,
            self.dict_len,
            self.original_size,
        )
        if self.dict_data:
            packed += self.dict_data
        return packed

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, offset: int = 0) -> Tuple["RevHashHeader", int]:
        """Parse header from *data* starting at *offset*.

        Returns:
            (header, next_offset) where next_offset points just after dict_data.

        Raises:
            RevHashCorruptedError: on bad magic / version / truncation.
            RevHashUnsupportedCodecError: on unknown codec_id.
        """
        if len(data) < offset + HEADER_SIZE:
            raise RevHashCorruptedError(f"blob too short for header: need {HEADER_SIZE}, got {len(data) - offset}")
        magic, version, codec_id, level, chunk_size, dict_len, original_size = HEADER_STRUCT.unpack_from(data, offset)
        if magic != HEADER_MAGIC:
            # Also accept alternative magic b"RVH\x01" for compatibility with spec typo?
            if magic == b"RVH\x01":
                pass  # accept
            else:
                raise RevHashCorruptedError(f"bad magic {magic!r} expected {HEADER_MAGIC!r}")
        if version not in (1, 2):
            raise RevHashCorruptedError(f"unsupported version {version}, expected 1 or 2")
        if codec_id not in ID_TO_CODEC:
            raise RevHashUnsupportedCodecError(f"unknown codec_id {codec_id}")
        # Validate limits before allocating dict_data (DoS protection)
        if dict_len > 256 * 1024:
            raise RevHashCorruptedError(f"dict_len {dict_len} too large (max 256KB, attacker-controlled)")
        if chunk_size < 1024 or chunk_size > 64 * 1024 * 1024:
            raise RevHashCorruptedError(f"chunk_size {chunk_size} out of range [1K, 64M]")
        dict_data = None
        next_off = offset + HEADER_SIZE
        if dict_len > 0:
            if len(data) < next_off + dict_len:
                raise RevHashCorruptedError(
                    f"blob truncated: dict_len {dict_len} but only {len(data) - next_off} bytes remain"
                )
            dict_data = bytes(data[next_off : next_off + dict_len])
            next_off += dict_len
        else:
            # even if dict_len 0, ensure no dict_data
            pass
        codec_name = ID_TO_CODEC[codec_id]
        hdr = cls(
            codec=codec_name,
            level=level,
            chunk_size=chunk_size,
            dict_data=dict_data,
            original_size=original_size,
            version=version,
        )
        # preserve exact codec_id (redundant)
        hdr.codec_id = codec_id
        return hdr, next_off

    def __repr__(self) -> str:
        return (
            f"RevHashHeader(codec={self.codec!r} id={self.codec_id}, level={self.level}, "
            f"chunk_size={self.chunk_size}, dict_len={self.dict_len}, "
            f"original_size={'UNKNOWN' if self.original_size == UNKNOWN_SIZE else self.original_size}, "
            f"version={self.version})"
        )

# ── Footer helpers ─────────────────────────────────────────────────────────
def parse_footer(blob: bytes, header: RevHashHeader, header_end: int) -> tuple[list[int], bytes, bytes]:
    """Parse footer from a full *blob*.

    Args:
        blob: complete revhash blob (header+dict+stream+footer).
        header: parsed header.
        header_end: offset just after header+dict (start of compressed stream).

    Returns:
        (per_chunk_crcs, global_sha256, footer_magic)

    Raises:
        RevHashCorruptedError: if footer invalid / truncated.
    """
    total = len(blob)
    # minimum footer size = 36 (sha+magic) if unknown, else at least 36
    min_footer = FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
    if total < header_end + min_footer:
        raise RevHashCorruptedError(
            f"blob too short for footer: total {total}, header_end {header_end}, need at least {min_footer} footer bytes"
        )
    footer_magic = blob[-4:]
    if footer_magic != FOOTER_MAGIC:
        raise RevHashCorruptedError(f"bad footer magic {footer_magic!r} expected {FOOTER_MAGIC!r}")
    global_sha = blob[-(FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE) : -FOOTER_MAGIC_SIZE]
    # per-chunk crc area is between compressed_stream end and sha start
    # Compute expected footer_len from header (if known)
    if header.original_size == UNKNOWN_SIZE:
        # spec says 0 CRCs for UNKNOWN (streaming pipe). Per Critic P1-2 fix: do not misinterpret
        # compressed_len as CRC area. For UNKNOWN, footer is always only SHA+MAGIC (36B),
        # and per_crcs is empty. Any extra bytes before footer are compressed data, not CRCs.
        # Keep lenient but correct: just return empty CRCs.
        per_crcs: list[int] = []
        return per_crcs, global_sha, footer_magic
    else:
        nc = header.num_chunks
        mac_len = FOOTER_HEADER_SHA_SIZE if header.version >= 2 else 0
        expected_footer_len = nc * 4 + mac_len + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
        # compressed_len = total - header_end - expected_footer_len
        # However due to auto-store / variable compress, we must verify that blob length accommodates
        if total < header_end + expected_footer_len:
            raise RevHashCorruptedError(
                f"blob truncated: need footer_len {expected_footer_len}, header_end {header_end}, total {total}"
            )
        # For spec compliance, we require exact footer_len match; but compressed_len is variable, so we just check footer slices at tail
        # CRCs are the nc*4 bytes before SHA
        if nc > 0:
            crc_start = total - expected_footer_len
            # need to ensure decompression stream end? For seekable case, this is exact. For in-mem, ok.
            # CRC bytes are blob[crc_start: crc_start + nc*4]
            crc_bytes = blob[crc_start : crc_start + nc * 4]
            if len(crc_bytes) != nc * 4:
                raise RevHashCorruptedError("truncated CRC area")
            per_crcs = list(struct.unpack(f"<{nc}I", crc_bytes)) if nc else []
            # verify SHA position (v2: skip header_sha256 sitting before global_sha256)
            sha_start = crc_start + nc * 4 + mac_len
            global_sha = blob[sha_start : sha_start + 32]
        else:
            # original_size ==0 -> nc==0 -> no CRCs
            per_crcs = []
            # global_sha already sliced at -36:-4? but recompute for consistency
            global_sha = blob[total - 36 : total - 4]
        return per_crcs, global_sha, footer_magic

def compute_per_chunk_crcs(data: bytes, chunk_size: int) -> list[int]:
    """Compute CRC32 per chunk of *data* with *chunk_size*."""
    crcs: list[int] = []
    for i in range(0, len(data), chunk_size):
        chunk = data[i : i + chunk_size]
        crcs.append(zlib.crc32(chunk) & 0xFFFFFFFF)
    return crcs

def global_sha256(data: bytes) -> bytes:
    """Return SHA256 digest of *data*."""
    return hashlib.sha256(data).digest()

# ── codec.py ────────────────────────────────────────────────────────
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

import gzip
import io

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

# ── stream.py ───────────────────────────────────────────────────────
"""Streaming O(1) codec for revhash — single-frame zstd default.

Implements docs/api.md §3.3 correctly:

- Zstd default uses ``ZstdCompressor.stream_writer(writer, closefd=False)``
  single-frame, keeping window across chunks → 0% overhead.
- Fallback codecs (gzip/lzma/brotli/store) streamed per-chunk via their
  incremental compressors.
- Header (RevHashHeader) before stream, dict_data embedded, then
  compressed_stream, then footer: per-chunk CRC32 array + header SHA256
  (v2) + global SHA256 + footer magic ``RVHE``.

Blob format versioning (docs/api_v05.md): new blobs are written as v2
(footer carries ``header_sha256`` = sha256 of the final header bytes).
Readers accept both v1 (legacy, no header_sha256) and v2; v2 blobs have
their header MAC verified before any decompression happens.

All ``compress_*`` paths are O(1) memory: only ``read(chunk_size)`` loops,
never ``read()`` whole file.

File wrappers ``compress_file`` / ``decompress_file`` use ``open(..., 'rb'/'wb')``
and chunk loops — verified not to load whole file.

Decompress detects header, dict, codec, locates footer via header's
original_size (or UNKNOWN), decompresses with appropriate backend while
recomputing SHA + per-chunk CRCs and raises RevHashCorruptedError on mismatch.
"""

import hashlib
import os
import struct
import zlib
from typing import BinaryIO

# ── Internal helpers ───────────────────────────────────────────────────────

# Reusable decode-block size for the zstd hot path (Coordinator M3a-RF).
# Constant regardless of file size — keeps decompress O(1) memory.
_DECOMP_BLOCK_SIZE: int = 1 << 18

def _reader_remaining_seekable(reader: BinaryIO) -> int | None:
    """Try to determine remaining bytes in *reader* without consuming.

    Returns remaining bytes if seekable/tellable, else None.
    Does not change file position on success.
    """
    try:
        if not hasattr(reader, "seek") or not hasattr(reader, "tell"):
            return None
        # check seekable()
        seekable = getattr(reader, "seekable", lambda: False)
        if callable(seekable) and not seekable():
            return None
        cur = reader.tell()
        # seek to end
        reader.seek(0, os.SEEK_END)
        end = reader.tell()
        reader.seek(cur, os.SEEK_SET)
        remaining = end - cur
        if remaining < 0:
            remaining = 0
        return remaining
    except Exception:
        return None

class _LimitedReader:
    """Wrap reader to limit reads to *limit* bytes (for footer isolation)."""

    def __init__(self, base: BinaryIO, limit: int) -> None:
        self._base = base
        self._remaining = limit
        self._closed = False

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size < 0 or size > self._remaining:
            size = self._remaining
        data = self._base.read(size)
        if not data:
            return b""
        self._remaining -= len(data)
        return data

    def readable(self) -> bool:
        return True

    # for zstd which may use readinto?
    def readinto(self, b: bytearray) -> int:
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n

def _parse_header_from_reader(reader: BinaryIO) -> tuple[RevHashHeader, int, bytes]:
    """Read header (+dict) from *reader* at current position.

    Returns (header, header_end_pos, hdr_full_bytes) where header_end_pos is
    absolute tell offset after header+dict (start of compressed stream) and
    hdr_full_bytes are the raw final header bytes (23B header + dict_data).
    Reader must be at start.

    Raises RevHashCorruptedError on truncation/bad magic/unsupported version.
    """
    # Need 23 bytes
    # Some readers are non-seekable streams (no peek); we just read.
    try:
        reader.tell() if hasattr(reader, "tell") else 0
    except Exception:
        pass
    hdr_bytes = reader.read(HEADER_SIZE)
    if len(hdr_bytes) < HEADER_SIZE:
        raise RevHashCorruptedError(f"blob too short for header: got {len(hdr_bytes)} need {HEADER_SIZE}")
    # peek dict_len to know how much more
    # Use header struct unpack without full validation to get dict_len
    # But easier: try RevHashHeader.from_bytes on hdr_bytes padded?
    # Instead read full header via static parse requiring full dict later.
    # We have hdr_bytes (23). Unpack to get dict_len
    magic, version, codec_id, level, chunk_size, dict_len, original_size = HEADER_STRUCT.unpack(hdr_bytes)
    # validate magic/version quickly
    if magic not in (b"RVH1", b"RVH\x01"):
        raise RevHashCorruptedError(f"bad magic {magic!r}")
    if version not in (1, 2):
        raise RevHashCorruptedError(f"unsupported version {version}")
    dict_data = b""
    if dict_len > 0:
        dict_data = reader.read(dict_len)
        if len(dict_data) < dict_len:
            raise RevHashCorruptedError(f"truncated dict: need {dict_len}, got {len(dict_data)}")
    # Build full blob for from_bytes
    full = hdr_bytes + dict_data
    header, next_off = RevHashHeader.from_bytes(full, 0)
    # next_off should equal HEADER_SIZE+dict_len
    try:
        end_pos = reader.tell() if hasattr(reader, "tell") else HEADER_SIZE + dict_len
    except Exception:
        end_pos = HEADER_SIZE + dict_len
    # If reader is BytesIO and we used read, tell matches.
    # For safety, compute header_len
    return header, end_pos, full

def _compute_footer_len(header: RevHashHeader) -> int:
    """Footer length for *header* — version-aware (v1: +0, v2: +32 header MAC)."""
    return header.footer_len()

def _final_header_sha(header: RevHashHeader) -> bytes:
    """SHA256 over the FINAL header bytes (post original_size patch / rewrite) — v2 footer MAC."""
    return hashlib.sha256(header.to_bytes()).digest()

def _verify_header_mac(header: RevHashHeader, hdr_full: bytes, header_sha_expected: bytes) -> None:
    """Verify v2 header MAC (sha256 of raw header+dict bytes) BEFORE decompression.

    Raises RevHashCorruptedError on mismatch. No-op for v1 blobs.
    """
    if header.version >= 2 and hashlib.sha256(hdr_full).digest() != header_sha_expected:
        raise RevHashCorruptedError("header SHA256 mismatch — header fields tampered (v2)")

# ── Compress stream ────────────────────────────────────────────────────────

def compress_stream(
    reader: BinaryIO,
    writer: BinaryIO,
    codec: str | int = "zstd",
    level: int = 3,
    chunk_size: int = 4 * 1024 * 1024,
    dict_data: bytes | None = None,
) -> dict:
    """Compress *reader* → *writer* with O(1) memory.

    Implements docs/research.md §6.2 pseudocode — important: Zstd uses
    single-frame ``stream_writer`` (no per-chunk reset) to preserve window.

    Args:
        reader: binary-readable (supports ``read(chunk_size)``).
        writer: binary-writable.
        codec: codec name/id (default "zstd").
        level: codec level.
        chunk_size: chunk size for CRC / read loop (default 4MiB).
        dict_data: optional dictionary bytes (only zstd).

    Returns:
        info dict with codec, level, chunk_size, original_size, compressed_size,
        ratio, has_dict, chunks, etc.

    Raises:
        RevHashUnsupportedCodecError / RevHashDictError / ValueError.
    """
    # normalise codec early for validation
    cid = _normalize_codec_id(codec)
    codec_name = ID_TO_CODEC[cid]
    if chunk_size <= 0:
        raise ValueError("chunk_size must be >0")
    # dict validation
    if dict_data is not None and len(dict_data) == 0:
        dict_data = None
    if dict_data is not None and codec_name not in ("zstd",):
        if len(dict_data) > 0:
            raise RevHashDictError(f"codec '{codec_name}' does not support dictionary")
    # level validation
    # reuse codec validators indirectly via compress_stream path checks below
    # capture reader start for potential fallback
    reader_start_pos = None
    try:
        if hasattr(reader, "tell"):
            reader_start_pos = reader.tell()
    except Exception:
        reader_start_pos = None
    # Try to determine remaining size for header original_size without loading
    remaining_peek = _reader_remaining_seekable(reader)
    if remaining_peek is not None:
        original_size_for_header: int = remaining_peek
        header_known = True
    else:
        original_size_for_header = UNKNOWN_SIZE
        header_known = False

    header = RevHashHeader(
        codec=codec_name,
        level=level,
        chunk_size=chunk_size,
        dict_data=dict_data,
        original_size=original_size_for_header,
    )
    # Write header (includes dict_data if present)
    header_bytes = header.to_bytes()
    start_pos = writer.tell() if hasattr(writer, "tell") else 0
    writer.write(header_bytes)
    # No separate dict write — already in header_bytes

    sha = hashlib.sha256()
    crcs: list[int] = []
    total_raw = 0

    # Determine if writer seekable for potential patch when header was UNKNOWN
    writer_seekable = False
    try:
        writer_seekable = hasattr(writer, "seek") and hasattr(writer, "tell") and writer.seekable()  # type: ignore
    except Exception:
        writer_seekable = False

    # For UNKNOWN header written to seekable writer we will patch later to known.
    # For non-seekable we keep UNKNOWN and footer will have no CRCs per spec.

    # ── Dispatch compress per codec ───────────────────────────────────
    if codec_name == "zstd":
        if not HAS_ZSTD:
            raise RevHashUnsupportedCodecError("zstandard not installed")
        import zstandard as zstd  # type: ignore

        dict_obj = None
        if dict_data is not None:
            dict_obj = zstd.ZstdCompressionDict(dict_data)  # type: ignore
        # Validate level
        if not (1 <= level <= 22):
            raise ValueError(f"zstd level {level} must be 1..22")
        cctx = zstd.ZstdCompressor(level=level, dict_data=dict_obj)  # type: ignore
        # Single-frame streaming — core requirement
        crc32_local = zlib.crc32
        sha_up = sha.update
        with cctx.stream_writer(writer, closefd=False) as comp:  # type: ignore
            while True:
                chunk = reader.read(chunk_size)
                if not chunk:
                    break
                sha_up(chunk)
                crcs.append(crc32_local(chunk) & 0xFFFFFFFF)
                total_raw += len(chunk)
                comp.write(chunk)
        # after context manager, frame is closed (end-of-frame written)
    elif codec_name == "store":
        crc32_local = zlib.crc32
        sha_up = sha.update
        while True:
            chunk = reader.read(chunk_size)
            if not chunk:
                break
            sha_up(chunk)
            crcs.append(crc32_local(chunk) & 0xFFFFFFFF)
            total_raw += len(chunk)
            writer.write(chunk)
    elif codec_name == "gzip":
        if dict_data:
            raise RevHashDictError("gzip dict not supported")
        if not (0 <= level <= 9):
            raise ValueError(f"gzip level {level} must be 0..9")
        import zlib as _zlib

        comp = _zlib.compressobj(level, _zlib.DEFLATED, _zlib.MAX_WBITS | 16)  # type: ignore[assignment]  # gzip
        crc32_local = zlib.crc32
        sha_up = sha.update
        while True:
            chunk = reader.read(chunk_size)
            if not chunk:
                break
            sha_up(chunk)
            crcs.append(crc32_local(chunk) & 0xFFFFFFFF)
            total_raw += len(chunk)
            c = comp.compress(chunk)
            if c:
                writer.write(c)
        c = comp.flush()  # type: ignore[assignment]
        if c:
            writer.write(c)  # type: ignore[call-overload]
    elif codec_name == "lzma":
        if dict_data:
            raise RevHashDictError("lzma dict not supported")
        if not (0 <= level <= 9):
            raise ValueError(f"lzma preset {level} must be 0..9")
        import lzma as _lzma

        comp = _lzma.LZMACompressor(preset=level)  # type: ignore[assignment]
        crc32_local = zlib.crc32
        sha_up = sha.update
        while True:
            chunk = reader.read(chunk_size)
            if not chunk:
                break
            sha_up(chunk)
            crcs.append(crc32_local(chunk) & 0xFFFFFFFF)
            total_raw += len(chunk)
            c = comp.compress(chunk)
            if c:
                writer.write(c)
        c = comp.flush()  # type: ignore[assignment]
        if c:
            writer.write(c)  # type: ignore[call-overload]
    elif codec_name == "brotli":
        if not HAS_BROTLI:
            raise RevHashUnsupportedCodecError("brotli not installed — pip install brotli")
        if dict_data:
            raise RevHashDictError("brotli dict not supported")
        if not (0 <= level <= 11):
            raise ValueError(f"brotli quality {level} must be 0..11")
        import brotli  # type: ignore

        comp = brotli.Compressor(quality=level)
        crc32_local = zlib.crc32
        sha_up = sha.update
        while True:
            chunk = reader.read(chunk_size)
            if not chunk:
                break
            sha_up(chunk)
            crcs.append(crc32_local(chunk) & 0xFFFFFFFF)
            total_raw += len(chunk)
            c = comp.process(chunk)
            if c:
                writer.write(c)
        c = comp.finish()
        if c:
            writer.write(c)
    else:  # pragma: no cover
        raise RevHashUnsupportedCodecError(f"unknown codec {codec_name}")

    # ── After loop, we have total_raw, crcs, sha ─────────────────────
    # If header was UNKNOWN and writer seekable → patch header original_size to total_raw
    # and we will write CRCs. If not seekable, per spec we must NOT write CRCs (footer only SHA+MAGIC).
    # However we already computed crcs; decide footer contents based on final header state.
    if not header_known and writer_seekable:
        # Patch header original_size field at offset 15 (after 4+1+1+1+4+4 =15)
        try:
            cur_end = writer.tell()
            writer.seek(start_pos + 15)
            writer.write(struct.pack("<Q", total_raw))
            writer.seek(cur_end)
            header_known = True
            header.original_size = total_raw
        except Exception:
            # if seek fails, keep unknown and proceed with unknown footer
            header_known = False
            header.original_size = UNKNOWN_SIZE
    elif not header_known and not writer_seekable:
        # keep UNKNOWN, per spec CRCs are omitted in footer
        # So we discard crcs for footer (but keep for info?)
        pass
    else:
        # header was known via peek; ensure total_raw matches peek if reader was fully consumed
        # For correctness, we could verify but not needed; we keep peek value unless mismatch?
        # If peek gave 10MB but file shrunk/grew while reading, total_raw differs — we patch to actual
        if header.original_size != total_raw and writer_seekable:
            # Patch to actual total_raw to ensure footer correctness
            try:
                cur_end = writer.tell()
                writer.seek(start_pos + 15)
                writer.write(struct.pack("<Q", total_raw))
                writer.seek(cur_end)
                header.original_size = total_raw
            except Exception:
                pass
        # else keep as is

    # Determine what footer to write based on final header state
    if header.original_size == UNKNOWN_SIZE:
        # spec: 0 CRCs; v2 footer still carries header_sha256 (docs/api_v05.md Q6)
        writer.write(_final_header_sha(header))
        writer.write(sha.digest())
        writer.write(FOOTER_MAGIC)
        footer_crcs_written = []
    else:
        # Use computed crcs (based on actual data). But number must match ceil(original_size/chunk_size)
        # For known header, computed crcs length should match header.num_chunks (which was derived from peek).
        # If mismatch due to changing file, we already patched header, so recompute expected nc?
        # Ensure header reflects total_raw => nc is len(crcs) (since crcs len = num chunks)
        # But header.num_chunks now returns correct with updated original_size.
        # Write crcs array
        if crcs:
            writer.write(struct.pack(f"<{len(crcs)}I", *crcs))
        # v2: header MAC computed AFTER any original_size patch above → header.to_bytes() is final
        writer.write(_final_header_sha(header))
        writer.write(sha.digest())
        writer.write(FOOTER_MAGIC)
        footer_crcs_written = crcs

    # Compute compressed_size for info
    try:
        end_pos = writer.tell()  # type: ignore
        compressed_size = end_pos - start_pos
    except Exception:
        # non-seekable writer: estimate via counted header+dict+compressed bytes?
        # compressed_size unknown, set to total_raw? Use 0
        compressed_size = 0

    # Handle auto-store fallback for seekable writer:
    # If codec != store and compressed_size > store_est then store would be smaller.
    store_size_est = 0
    if codec_name != "store" and compressed_size > 0 and total_raw > 0:
        store_size_est = 23 + total_raw + len(crcs) * 4 + FOOTER_HEADER_SHA_SIZE + 32 + 4  # v2 footer
        if compressed_size > store_size_est:
            # Attempt fallback if both reader and writer seekable (so we can reread raw)
            try:
                reader_seekable_for_fallback = False
                try:
                    reader_seekable_for_fallback = (
                        hasattr(reader, "seek") and hasattr(reader, "tell") and reader.seekable()
                    )  # type: ignore
                except Exception:
                    reader_seekable_for_fallback = False
                if writer_seekable and reader_seekable_for_fallback and reader_start_pos is not None:
                    # Truncate writer back to start and recompress as store (raw copy)
                    writer.seek(start_pos)
                    writer.truncate()  # type: ignore
                    # Write store header (codec store, level 0, chunk_size same, no dict, original_size total_raw)
                    store_header = RevHashHeader(
                        codec="store", level=0, chunk_size=chunk_size, dict_data=None, original_size=total_raw
                    )
                    writer.write(store_header.to_bytes())
                    # Seek reader back to start and copy raw
                    reader.seek(reader_start_pos)
                    # We already have sha/crcs from previous pass (same raw), but we still need to write raw bytes
                    # Copy raw data again (O1)
                    while True:
                        chunk = reader.read(chunk_size)
                        if not chunk:
                            break
                        writer.write(chunk)
                    # Footer for store (same crcs/sha as before); v2 MAC over the rewritten store header
                    if crcs:
                        writer.write(struct.pack(f"<{len(crcs)}I", *crcs))
                    writer.write(hashlib.sha256(store_header.to_bytes()).digest())
                    writer.write(sha.digest())
                    writer.write(FOOTER_MAGIC)
                    # Update tracking variables to reflect store fallback
                    try:
                        compressed_size = writer.tell() - start_pos  # type: ignore
                    except Exception:
                        compressed_size = store_size_est
                    codec_name = "store"
                    cid = 0
                    header = store_header
                    footer_crcs_written = crcs
                    # has_dict will be recomputed later
            except Exception:
                pass

    has_dict = header.dict_len > 0 if "header" in locals() else (dict_data is not None)
    ratio = (compressed_size / total_raw) if total_raw > 0 and compressed_size else 0.0
    # Build info dict
    info = {
        "codec": codec_name,
        "codec_id": cid,
        "level": level,
        "chunk_size": chunk_size,
        "original_size": total_raw,
        "compressed_size": compressed_size,
        "ratio": ratio,
        "has_dict": has_dict,
        "chunks": len(crcs),
        "sha256": sha.hexdigest(),
    }
    # For file fallback internal caller may check ratio, but not needed here.
    return info

# ── Decompress stream ──────────────────────────────────────────────────────

def decompress_stream(
    reader: BinaryIO,
    writer: BinaryIO,
    dict_data: bytes | None = None,
) -> dict:
    """Decompress revhash *reader* → *writer* (O(1) streaming).

    Automatically detects codec from header, validates per-chunk CRC32 and
    global SHA256, raises RevHashCorruptedError on mismatch.

    Args:
        reader: binary-readable positioned at start of blob (file or BytesIO).
        writer: binary-writable for restored data.
        dict_data: external dict bytes if required (if blob has no embedded dict).

    Returns:
        info dict similar to compress_stream.

    Raises:
        RevHashCorruptedError, RevHashDictError, RevHashUnsupportedCodecError.
    """
    # Remember start pos
    try:
        start_reader_pos = reader.tell()
    except Exception:
        start_reader_pos = 0

    # Parse header + embedded dict
    header, header_end, hdr_full = _parse_header_from_reader(reader)
    codec_name = header.codec
    codec_id = header.codec_id
    chunk_size = header.chunk_size

    # Determine dict to use
    embedded_dict = header.dict_data  # may be None
    effective_dict: bytes | None = None
    if header.dict_len > 0:
        # embedded
        effective_dict = embedded_dict
        # if external dict provided, could optionally verify equality, but ignore
    else:
        if dict_data is not None and len(dict_data) > 0:
            effective_dict = dict_data
        else:
            effective_dict = None

    # Validate dict requirement for zstd: if header says dict_len>0, we have it; if caller passes external dict for non-zstd request raise later

    # Locate compressed stream boundaries and footer.
    # Need total blob size if reader seekable; otherwise buffer fallback.

    # Try seekable path first
    compressed_len: int | None = None
    footer_len: int | None = None
    per_chunk_crcs_expected: list[int] = []
    global_sha_expected: bytes | None = None

    # Attempt to get total size via seek
    reader_seekable = False
    try:
        reader_seekable = hasattr(reader, "seek") and hasattr(reader, "tell") and reader.seekable()  # type: ignore
    except Exception:
        reader_seekable = False

    # For seekable, compute footer slice tail directly without loading full blob
    if reader_seekable:
        try:
            cur_pos = reader.tell()
            reader.seek(0, os.SEEK_END)
            total_blob = reader.tell()
            reader.seek(cur_pos, os.SEEK_SET)  # back to header_end (should be same as cur_pos)
            # Ensure header_end matches cur_pos (after header+dict)
            # Compute expected footer length based on header
            if header.original_size == UNKNOWN_SIZE:
                footer_len = _compute_footer_len(header)
                # per spec, no CRCs
                # But as argued, remaining bytes after stream is compressed_len.
                # So compressed_len = total_blob - header_end - footer_len
                compressed_len = total_blob - header_end - footer_len
                per_chunk_crcs_expected = []
            else:
                nc = header.num_chunks
                footer_len = _compute_footer_len(header)
                compressed_len = total_blob - header_end - footer_len
                if compressed_len < 0:
                    raise RevHashCorruptedError(
                        f"negative compressed_len {compressed_len}, total {total_blob}, header_end {header_end}, footer {footer_len}"
                    )
                # Read footer CRCs + SHA + magic tail
                # Seek to footer start
                footer_start = total_blob - footer_len
                reader.seek(footer_start)
                footer_bytes = reader.read(footer_len)
                if len(footer_bytes) != footer_len:
                    raise RevHashCorruptedError(f"truncated footer, need {footer_len}, got {len(footer_bytes)}")
                # Parse footer per header.num_chunks (v2: [crcs][header_sha256][sha][magic])
                mac_len = FOOTER_HEADER_SHA_SIZE if header.version >= 2 else 0
                if nc > 0:
                    per_chunk_crcs_expected = list(struct.unpack(f"<{nc}I", footer_bytes[: nc * 4]))
                    header_sha_expected = footer_bytes[nc * 4 : nc * 4 + mac_len]
                    global_sha_expected = footer_bytes[nc * 4 + mac_len : nc * 4 + mac_len + 32]
                    footer_magic = footer_bytes[nc * 4 + mac_len + 32 : nc * 4 + mac_len + 36]
                else:
                    per_chunk_crcs_expected = []
                    header_sha_expected = footer_bytes[:mac_len]
                    global_sha_expected = footer_bytes[mac_len : mac_len + 32]
                    footer_magic = footer_bytes[mac_len + 32 : mac_len + 36]
                if footer_magic != FOOTER_MAGIC:
                    raise RevHashCorruptedError(f"bad footer magic {footer_magic!r}")
                # v2: verify header MAC from buffered hdr_full BEFORE decompressing anything
                _verify_header_mac(header, hdr_full, header_sha_expected)
                # Reset reader to start of compressed stream for decompression
                reader.seek(header_end, os.SEEK_SET)
            # For unknown case, still need global_sha and footer magic, but per_chunk_crcs empty
            if header.original_size == UNKNOWN_SIZE:
                # Need to read sha/magic tail
                footer_start = total_blob - footer_len
                reader.seek(footer_start)
                foot = reader.read(footer_len)
                if len(foot) != footer_len:
                    raise RevHashCorruptedError("truncated footer (unknown size)")
                mac_len = FOOTER_HEADER_SHA_SIZE if header.version >= 2 else 0
                header_sha_expected = foot[:mac_len]
                global_sha_expected = foot[mac_len : mac_len + 32]
                footer_magic = foot[mac_len + 32 : mac_len + 36]
                if footer_magic != FOOTER_MAGIC:
                    raise RevHashCorruptedError(f"bad footer magic {footer_magic!r}")
                _verify_header_mac(header, hdr_full, header_sha_expected)
                reader.seek(header_end, os.SEEK_SET)
            # Now proceed to decompress limited stream
        except RevHashCorruptedError:
            raise
        except Exception:
            # Fallback to non-seekable buffering path
            reader_seekable = False
            # reset to start for buffering path? need full blob bytes
            try:
                reader.seek(start_reader_pos)
            except Exception:
                pass
    if not reader_seekable:
        # Non-seekable: buffer remaining to temp file to avoid OOM for large blobs (Critic P0-1 fix)
        # Use SpooledTemporaryFile (10MB in RAM, then spill to disk) — O(1) memory, O(disk) for huge.
        import tempfile

        tmp = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024, mode="w+b")
        total_tmp = 0
        while True:
            chunk = reader.read(131072)
            if not chunk:
                break
            tmp.write(chunk)
            total_tmp += len(chunk)
            # Guard against absurdly large blobs via pipe (>2GB via non-seekable is likely DoS)
            if total_tmp > 2 * 1024 * 1024 * 1024:
                tmp.close()
                raise RevHashCorruptedError("non-seekable blob too large (>2GB) — use seekable file for large blobs")
        tmp.seek(0)
        # Read back as bytes for parsing, but via temp file we can also parse footer without loading all at once
        # For simplicity, if total_tmp <= 100MB we load to bytes; otherwise we keep file-backed parsing
        if total_tmp <= 100 * 1024 * 1024:
            remaining = tmp.read()
            tmp.close()
        else:
            # Large non-seekable (>100MB): keep temp file for footer parsing without loading all
            # We will parse footer by seeking to tail of tmp file
            tmp.seek(0, 2)
            total_remaining = tmp.tell()
            # Determine footer handling via temp file seek
            # For now, load in chunks to find footer — but to keep code simple, we still need remaining bytes for decompress
            # So we keep tmp file as source and parse footer from tail without full load
            # We will handle large case via tmp file-backed decompress later
            # For this branch, we need to reconstruct logic for large tmp: read tail footer
            tmp.seek(max(0, total_remaining - 8192))
            tmp.read()
            # If header ORIGINAL_SIZE known, footer_len is Nc*4+36, else 36 — we can deduce
            # To avoid complexity, for large we fall back to requiring seekable for >100MB and raise guidance
            tmp.close()
            raise RevHashCorruptedError(
                "non-seekable blob >100MB not supported — use file (seekable) for large blobs (see README Limitations)"
            )
        # At this point remaining is bytes for small non-seekable (<=100MB)
        # Fall through to existing parsing logic using remaining
        # Need to deduce footer vs compressed
        # Since non-seekable, we don't know original_size? Use header
        # We need to find footer tail parsing. For known size, footer_len as before.
        # Then split remaining
        if header.original_size == UNKNOWN_SIZE:
            footer_len_u = _compute_footer_len(header)
            if len(remaining) < footer_len_u:
                raise RevHashCorruptedError("truncated blob (unknown)")
            # per spec, no CRCs; v1 footer 36B, v2 footer 68B (header_sha256 + sha + magic)
            per_chunk_crcs_expected = []
            mac_len_u = FOOTER_HEADER_SHA_SIZE if header.version >= 2 else 0
            header_sha_expected = remaining[-footer_len_u : -footer_len_u + mac_len_u]
            global_sha_expected = remaining[-(FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE) : -FOOTER_MAGIC_SIZE]
            footer_magic = remaining[-FOOTER_MAGIC_SIZE:]
            if footer_magic != FOOTER_MAGIC:
                raise RevHashCorruptedError(f"bad footer magic {footer_magic!r}")
            _verify_header_mac(header, hdr_full, header_sha_expected)
            compressed_bytes = remaining[:-footer_len_u]
            compressed_len = len(compressed_bytes)
            total_blob = header_end + len(remaining)
            # create limited reader over compressed_bytes via BytesIO
            from io import BytesIO

            # Create a BytesIO for compressed stream and wrap reader variable to use it
            # We'll later use BytesIO as decompression source
            # Replace reader with BytesIO(compressed_bytes)
            reader_for_decomp = BytesIO(compressed_bytes)
            # Use this for decompress logic; but we also need to keep writer path
            # Save for later handling.
            # We'll handle decompression differently for this branch.
        else:
            nc = header.num_chunks
            footer_len = _compute_footer_len(header)
            if len(remaining) < footer_len:
                raise RevHashCorruptedError(f"truncated blob: need footer {footer_len}, have {len(remaining)}")
            compressed_bytes = remaining[: len(remaining) - footer_len]
            footer_bytes = remaining[len(remaining) - footer_len :]
            # v2 layout: [crcs][header_sha256][global_sha256][magic]
            mac_len = FOOTER_HEADER_SHA_SIZE if header.version >= 2 else 0
            if nc > 0:
                per_chunk_crcs_expected = list(struct.unpack(f"<{nc}I", footer_bytes[: nc * 4]))
                header_sha_expected = footer_bytes[nc * 4 : nc * 4 + mac_len]
                global_sha_expected = footer_bytes[nc * 4 + mac_len : nc * 4 + mac_len + 32]
                footer_magic = footer_bytes[nc * 4 + mac_len + 32 : nc * 4 + mac_len + 36]
            else:
                per_chunk_crcs_expected = []
                header_sha_expected = footer_bytes[:mac_len]
                global_sha_expected = footer_bytes[mac_len : mac_len + 32]
                footer_magic = footer_bytes[mac_len + 32 : mac_len + 36]
            if footer_magic != FOOTER_MAGIC:
                raise RevHashCorruptedError(f"bad footer magic {footer_magic!r}")
            # v2: verify header MAC BEFORE decompressing anything
            _verify_header_mac(header, hdr_full, header_sha_expected)
            compressed_len = len(compressed_bytes)
            total_blob = header_end + len(remaining)
            from io import BytesIO

            reader_for_decomp = BytesIO(compressed_bytes)

        # For non-seekable we have reader_for_decomp and total values set.
        # Proceed to decompress reader_for_decomp → writer
        # We'll execute codec-specific decompress using reader_for_decomp
        # Duplicate logic below but with reader_for_decomp
        # To avoid doubling code, we will set a flag and set limited_reader = _LimitedReader(reader_for_decomp, compressed_len)
        # But easier to just handle here and return.

        # Compute decompression for non-seekable branch
        sha = hashlib.sha256()
        crc_computed: list[int] = []
        total_out = 0
        # progressive CRC state (replaces pending byte buffer) — docs/api_v05.md §4
        crc_cur = 0
        pos_in_chunk = 0

        # helper to process decompressed chunk for crc/sha — local binding
        chunk_size_local = chunk_size
        crc32_local = zlib.crc32
        crc_append = crc_computed.append
        sha_update = sha.update
        w_write = writer.write

        def _process_out(out: bytes | memoryview) -> None:
            nonlocal total_out, crc_cur, pos_in_chunk
            if not out:
                return
            sha_update(out)
            total_out += len(out)
            # CRC handling: need to handle UNKNOWN (no crcs) vs known — every byte covered
            if header.original_size != UNKNOWN_SIZE:
                mv = out if isinstance(out, memoryview) else memoryview(out)
                off = 0
                n = len(mv)
                room = chunk_size_local - pos_in_chunk
                if n <= room:
                    # fast path: whole block lands inside the current chunk
                    crc_cur = crc32_local(mv, crc_cur)
                    pos_in_chunk += n
                    if pos_in_chunk == chunk_size_local:
                        crc_append(crc_cur & 0xFFFFFFFF)
                        crc_cur = 0
                        pos_in_chunk = 0
                else:
                    while off < n:
                        take = min(n - off, room)
                        crc_cur = crc32_local(mv[off : off + take], crc_cur)
                        pos_in_chunk += take
                        off += take
                        room = chunk_size_local - pos_in_chunk
                        if pos_in_chunk == chunk_size_local:
                            crc_append(crc_cur & 0xFFFFFFFF)
                            crc_cur = 0
                            pos_in_chunk = 0
                            room = chunk_size_local
            # writer write
            w_write(out)

        # Dispatch codec for non-seekable
        if codec_name == "store":
            # reader_for_decomp already contains raw data
            while True:
                c = reader_for_decomp.read(chunk_size)
                if not c:
                    break
                _process_out(c)
        elif codec_name == "zstd":
            if not HAS_ZSTD:
                raise RevHashUnsupportedCodecError("zstandard not installed")
            import zstandard as zstd  # type: ignore

            dict_obj = None
            if effective_dict is not None:
                # zstd uses ZstdCompressionDict for decompressor dict
                try:
                    dict_obj = zstd.ZstdCompressionDict(effective_dict)  # type: ignore
                except Exception as exc:
                    raise RevHashDictError(f"bad dict for zstd: {exc}") from exc
            dctx = zstd.ZstdDecompressor(dict_data=dict_obj)  # type: ignore
            with dctx.stream_reader(reader_for_decomp) as sreader:  # type: ignore
                read_into = getattr(sreader, "readinto", None)
                if read_into is not None:
                    buf = bytearray(_DECOMP_BLOCK_SIZE)
                    buf_view = memoryview(buf)
                    while True:
                        got = read_into(buf_view)
                        if not got:
                            break
                        _process_out(buf_view[:got])
                else:
                    while True:
                        out = sreader.read(_DECOMP_BLOCK_SIZE)
                        if not out:
                            break
                        _process_out(out)
        elif codec_name == "gzip":
            import zlib as _zlib

            dec = _zlib.decompressobj(47)
            while True:
                c = reader_for_decomp.read(65536)
                if not c:
                    break
                out = dec.decompress(c)
                if out:
                    _process_out(out)
            out = dec.flush()
            if out:
                _process_out(out)
        elif codec_name == "lzma":
            import lzma as _lzma  # type: ignore[assignment]

            dec = _lzma.LZMADecompressor(format=_lzma.FORMAT_AUTO)  # type: ignore[assignment]
            while True:
                c = reader_for_decomp.read(65536)
                if not c:
                    break
                out = dec.decompress(c)
                if out:
                    _process_out(out)
                if dec.eof:
                    break
            # lzma has no flush needed
        elif codec_name == "brotli":
            if not HAS_BROTLI:
                raise RevHashUnsupportedCodecError("brotli not installed")
            import brotli  # type: ignore

            dec = brotli.Decompressor()
            while True:
                c = reader_for_decomp.read(65536)
                if not c:
                    break
                out = dec.process(c)
                if out:
                    _process_out(out)
            # brotli finish
        else:
            raise RevHashUnsupportedCodecError(f"unknown codec {codec_name}")

        # Handle tail CRC for known size (partial last chunk held in crc_cur)
        if header.original_size != UNKNOWN_SIZE and pos_in_chunk > 0:
            crc_computed.append(crc_cur & 0xFFFFFFFF)
            crc_cur = 0
            pos_in_chunk = 0

        # Verify
        if header.original_size != UNKNOWN_SIZE:
            # Compare CRCs
            if crc_computed != per_chunk_crcs_expected:
                raise RevHashCorruptedError(
                    f"per-chunk CRC mismatch: computed {crc_computed[:5]}... expected {per_chunk_crcs_expected[:5]}... (len {len(crc_computed)} vs {len(per_chunk_crcs_expected)})"
                )
        # Global SHA verify
        computed_sha = sha.digest()
        if computed_sha != global_sha_expected:
            raise RevHashCorruptedError(
                f"global SHA256 mismatch: computed {sha.hexdigest()} expected {global_sha_expected.hex()}"
            )
        # Original size verify (if known)
        if header.original_size != UNKNOWN_SIZE and total_out != header.original_size:
            raise RevHashCorruptedError(f"original_size mismatch: header {header.original_size} vs actual {total_out}")
        # For unknown, original_size is total_out (stream length)

        (
            total_blob - (header_end - start_reader_pos)
        ) / total_out if total_out else 0  # compressed_size not tracked in this branch use remaining len
        # Better compressed_size is total_blob - start
        compressed_size = (
            total_blob - start_reader_pos if total_blob else len(remaining) + HEADER_SIZE + header.dict_len
        )
        info = {
            "codec": codec_name,
            "codec_id": codec_id,
            "level": header.level,
            "chunk_size": chunk_size,
            "original_size": total_out,
            "compressed_size": compressed_size,
            "ratio": (compressed_size / total_out) if total_out else 0,
            "has_dict": effective_dict is not None,
            "chunks": len(crc_computed) if header.original_size != UNKNOWN_SIZE else 0,
            "sha256": sha.hexdigest(),
        }
        return info

    # ── Seekable path continues here: have header, header_end, compressed_len, expected CRCs/SHA ──
    # Create limited reader
    limited = _LimitedReader(reader, compressed_len) if compressed_len is not None else reader

    sha = hashlib.sha256()  # type: ignore[no-redef]
    crc_computed: list[int] = []  # type: ignore[no-redef]
    total_out = 0  # type: ignore[no-redef]
    # progressive CRC state (replaces pending byte buffer) — docs/api_v05.md §4
    crc_cur = 0  # type: ignore[no-redef]
    pos_in_chunk = 0  # type: ignore[no-redef]
    chunk_size_local = chunk_size  # type: ignore[no-redef]
    crc32_local = zlib.crc32  # type: ignore[no-redef]
    crc_append = crc_computed.append
    sha_update = sha.update
    w_write = writer.write

    def _proc(out: bytes | memoryview) -> None:  # type: ignore[no-redef]
        nonlocal total_out, crc_cur, pos_in_chunk
        if not out:
            return
        sha_update(out)
        total_out += len(out)
        w_write(out)
        if header.original_size == UNKNOWN_SIZE:
            # spec says no CRC for unknown; skip CRC accumulation
            return
        mv = out if isinstance(out, memoryview) else memoryview(out)
        n = len(mv)
        room = chunk_size_local - pos_in_chunk
        if n <= room:
            # fast path: whole block lands inside the current chunk
            crc_cur = crc32_local(mv, crc_cur)
            pos_in_chunk += n
            if pos_in_chunk == chunk_size_local:
                crc_append(crc_cur & 0xFFFFFFFF)
                crc_cur = 0
                pos_in_chunk = 0
        else:
            off = 0
            while off < n:
                take = min(n - off, room)
                crc_cur = crc32_local(mv[off : off + take], crc_cur)
                pos_in_chunk += take
                off += take
                room = chunk_size_local - pos_in_chunk
                if pos_in_chunk == chunk_size_local:
                    crc_append(crc_cur & 0xFFFFFFFF)
                    crc_cur = 0
                    pos_in_chunk = 0
                    room = chunk_size_local

    # Dispatch per codec using limited
    try:
        if codec_name == "store":
            # simple copy limited → writer
            while True:
                c = limited.read(chunk_size)
                if not c:
                    break
                _proc(c)
        elif codec_name == "zstd":
            if not HAS_ZSTD:
                raise RevHashUnsupportedCodecError("zstandard not installed")
            import zstandard as zstd  # type: ignore

            dict_obj = None
            if effective_dict is not None:
                dict_obj = zstd.ZstdCompressionDict(effective_dict)  # type: ignore
            dctx = zstd.ZstdDecompressor(dict_data=dict_obj)  # type: ignore
            with dctx.stream_reader(limited) as sreader:  # type: ignore
                read_into = getattr(sreader, "readinto", None)
                if read_into is not None:
                    buf = bytearray(_DECOMP_BLOCK_SIZE)
                    buf_view = memoryview(buf)
                    while True:
                        got = read_into(buf_view)
                        if not got:
                            break
                        _proc(buf_view[:got])
                else:
                    while True:
                        out = sreader.read(_DECOMP_BLOCK_SIZE)
                        if not out:
                            break
                        _proc(out)
        elif codec_name == "gzip":
            import zlib as _zlib

            dec = _zlib.decompressobj(47)
            while True:
                c = limited.read(65536)
                if not c:
                    break
                out = dec.decompress(c)
                if out:
                    _proc(out)
            out = dec.flush()
            if out:
                _proc(out)
        elif codec_name == "lzma":
            import lzma as _lzma  # type: ignore[assignment]

            dec = _lzma.LZMADecompressor(format=_lzma.FORMAT_AUTO)  # type: ignore[assignment]
            while True:
                c = limited.read(65536)
                if not c:
                    break
                out = dec.decompress(c)
                if out:
                    _proc(out)
                if dec.eof:
                    # there may be trailing unused bytes; ignore
                    break
        elif codec_name == "brotli":
            if not HAS_BROTLI:
                raise RevHashUnsupportedCodecError("brotli not installed")
            import brotli  # type: ignore

            dec = brotli.Decompressor()
            while True:
                c = limited.read(65536)
                if not c:
                    break
                out = dec.process(c)
                if out:
                    _proc(out)
        else:
            raise RevHashUnsupportedCodecError(f"unknown codec {codec_name}")
    except RevHashCorruptedError:
        raise
    except RevHashDictError:
        raise
    except RevHashUnsupportedCodecError:
        raise
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "dict" in msg or "dictionary" in msg:
            raise RevHashDictError(f"dictionary error during decompress: {exc}") from exc
        if codec_name == "zstd" and ("corrupt" in msg or "checksum" in msg or "window" in msg):
            raise RevHashCorruptedError(f"zstd decompress corrupted: {exc}") from exc
        # Wrap as corrupted for generic
        raise RevHashCorruptedError(f"decompress failed ({codec_name}): {exc}") from exc

    # Handle trailing partial-chunk CRC (held in crc_cur)
    if header.original_size != UNKNOWN_SIZE and pos_in_chunk > 0:
        crc_computed.append(crc_cur & 0xFFFFFFFF)
        crc_cur = 0
        pos_in_chunk = 0

    # Ensure limited fully consumed? Not needed.

    # After decompress, the reader's position should be at footer_start (since limited consumed exactly compressed_len)
    # But for zstd stream_reader, it may have consumed exactly compressed_len, so reading footer next will succeed.
    # Verify CRCs & SHA
    if header.original_size != UNKNOWN_SIZE:
        if crc_computed != per_chunk_crcs_expected:
            raise RevHashCorruptedError(
                f"per-chunk CRC mismatch: got {crc_computed[:8]}... expected {per_chunk_crcs_expected[:8]}... (len {len(crc_computed)} vs {len(per_chunk_crcs_expected)})"
            )
    # SHA
    computed_sha = sha.digest()
    if computed_sha != global_sha_expected:
        raise RevHashCorruptedError(
            f"global SHA256 mismatch: computed {sha.hexdigest()} expected {global_sha_expected.hex()}"
        )

    if header.original_size != UNKNOWN_SIZE and total_out != header.original_size:
        raise RevHashCorruptedError(f"original_size header {header.original_size} != decompressed {total_out}")

    # After successful decompress, advance reader past footer (consume footer bytes) so position at end
    # For seekable path we left reader at footer_start; now consume
    try:
        # read remaining footer bytes to advance
        # Reader currently at footer_start (since limited consumed compressed_len); read footer_len bytes and discard
        # Use reader.read to skip
        if footer_len:
            reader.read(footer_len)
    except Exception:
        pass

    # compressed_size = total_blob - start_reader_pos
    try:
        total_blob_size = total_blob  # from earlier seek
        compressed_size = total_blob_size - start_reader_pos
    except Exception:
        compressed_size = 0

    info = {
        "codec": codec_name,
        "codec_id": codec_id,
        "level": header.level,
        "chunk_size": chunk_size,
        "original_size": total_out,
        "compressed_size": compressed_size,
        "ratio": (compressed_size / total_out) if total_out else 0,
        "has_dict": effective_dict is not None,
        "chunks": len(crc_computed) if header.original_size != UNKNOWN_SIZE else 0,
        "sha256": sha.hexdigest(),
    }
    return info

# ── File wrappers (O1) — Flexible File<->Text v0.2.1-filetext ─────────────

def compress_file(
    src: str | os.PathLike | bytes | bytearray | memoryview,
    dst: str | os.PathLike | None = None,
    codec: str | int = "zstd",
    level: int = 3,
    chunk_size: int = 4 * 1024 * 1024,
    dict_data: bytes | str | os.PathLike | None = None,
    encoding: str = "utf-8",
    force_text: bool = False,
    as_text: bool = False,
    show_progress: bool = False,
) -> bytes | dict:
    """Nen linh hoat File<->Van ban O(1) streaming.

    Frozen docs/api_filetext.md Section 2-3:
      src: str|Path|bytes (4 dang), dst: str|Path|None (None->bytes RAM),
      heuristic str path ton tai -> file, force_text, encoding strict.

    Never loads whole file when src is file; uses read(chunk_size) via
    compress_stream. When src is text/bytes small, in-memory BytesIO.

    Returns:
      bytes blob if dst is None else info dict (codec, level, ...)

    Raises:
      TypeError, FileNotFoundError, IsADirectoryError, ValueError (>100MB guard),
      UnicodeEncodeError strict, RevHash* errors.
    """
    dict_data = _load_dict_data(dict_data)
    is_file, data, file_path = _resolve_src(src, encoding=encoding, force_text=force_text)
    dst_path = _resolve_dst(dst)
    if is_file:
        assert file_path is not None
        _guard_large_file_for_ram(file_path, dst_path)
        if dst_path is None:
            # File -> bytes RAM (streaming to BytesIO)
            from io import BytesIO

            with open(file_path, "rb") as rf:
                bio = BytesIO()
                info = compress_stream(rf, bio, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
                blob = bio.getvalue()
            if show_progress:
                print(
                    f"[revhash] compress {file_path} ({info['original_size']} B) -> <bytes> ({len(blob)} B) ratio={info['ratio']:.5f} codec={info['codec']}"
                )
            return blob
        else:
            # File -> file O(1)
            with open(file_path, "rb") as rf, open(dst_path, "wb") as wf:
                info = compress_stream(rf, wf, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
            if show_progress:
                print(
                    f"[revhash] compress {file_path} ({info['original_size']} B) -> {dst_path} ({info['compressed_size']} B) ratio={info['ratio']:.5f} codec={info['codec']}"
                )
            # Auto store fallback for file case (same as v0.2)
            try:
                src_size = file_path.stat().st_size
                dst_size = dst_path.stat().st_size
                if src_size > 0 and codec_name_norm(codec) != "store":
                    nc_store = (src_size + chunk_size - 1) // chunk_size if chunk_size else 0
                    footer_store = nc_store * 4 + FOOTER_HEADER_SHA_SIZE + 32 + 4  # v2 footer
                    header_store = 23
                    store_est = header_store + src_size + footer_store
                    if dst_size > store_est:
                        if show_progress:
                            print(
                                f"[revhash] auto-store fallback: {dst_size} > store estimate {store_est}, recompressing as store"
                            )
                        dst_path.unlink(missing_ok=True)
                        with open(file_path, "rb") as rf, open(dst_path, "wb") as wf:
                            info = compress_stream(
                                rf, wf, codec="store", level=level, chunk_size=chunk_size, dict_data=None
                            )
                        if show_progress:
                            print(f"[revhash] store fallback done: {dst_path} ({info['compressed_size']} B)")
            except Exception:
                pass
            return info
    else:
        # Text/bytes -> file or bytes RAM
        assert data is not None
        _guard_large_bytes_for_ram(data, dst_path)
        from io import BytesIO

        reader = BytesIO(data)
        if dst_path is None:
            writer = BytesIO()
            info = compress_stream(reader, writer, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
            blob = writer.getvalue()
            if show_progress:
                print(f"[revhash] compress <bytes {len(data)} B> -> <bytes> ({len(blob)} B) codec={info['codec']}")
            return blob
        else:
            with open(dst_path, "wb") as wf:
                info = compress_stream(reader, wf, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
            if show_progress:
                print(
                    f"[revhash] compress <bytes {len(data)} B> -> {dst_path} ({info['compressed_size']} B) codec={info['codec']}"
                )
            return info

def decompress_file(
    src: str | os.PathLike | bytes | bytearray | memoryview,
    dst: str | os.PathLike | None = None,
    dict_data: bytes | str | os.PathLike | None = None,
    encoding: str = "utf-8",
    as_text: bool = False,
    force_text: bool = False,
    show_progress: bool = False,
) -> bytes | str | dict:
    """Giai nen linh hoat File<->Van ban.

    Frozen docs/api_filetext.md Section 2-3:
      src: Path|bytes blob hoac str text (force_text), dst: Path|str|None,
      as_text decode strict khi dst is None.

    Never loads whole file when both are files; streaming O(1).

    Returns:
      bytes|str if dst is None (str when as_text=True) else info dict.

    Raises:
      TypeError, FileNotFoundError, IsADirectoryError, ValueError guard,
      UnicodeDecodeError strict, RevHashCorruptedError, etc.
    """
    dict_data = _load_dict_data(dict_data)
    is_file, data, file_path = _resolve_src(src, encoding=encoding, force_text=force_text)
    dst_path = _resolve_dst(dst)
    if is_file:
        assert file_path is not None
        if dst_path is None:
            # File blob -> RAM (bytes or str) — guard both compressed and decompressed size (HIGH #1)
            _guard_large_file_for_ram(file_path, dst_path)
            _guard_large_decompress_for_ram(file_path, dst_path)
            from io import BytesIO

            with open(file_path, "rb") as rf:
                out = BytesIO()
                info = decompress_stream(rf, out, dict_data=dict_data)
                raw = out.getvalue()
            if show_progress:
                print(f"[revhash] decompress {file_path} -> <bytes> ({len(raw)} B) codec={info['codec']}")
            if as_text:
                return raw.decode(encoding, "strict")
            return raw
        else:
            # File blob -> file O(1)
            with open(file_path, "rb") as rf, open(dst_path, "wb") as wf:
                info = decompress_stream(rf, wf, dict_data=dict_data)
            if show_progress:
                print(
                    f"[revhash] decompress {file_path} ({info['compressed_size']} B) -> {dst_path} ({info['original_size']} B) codec={info['codec']}"
                )
            return info
    else:
        assert data is not None
        _guard_large_bytes_for_ram(data, dst_path)
        _guard_large_decompress_for_ram(data, dst_path)
        from io import BytesIO

        reader = BytesIO(data)
        if dst_path is None:
            writer = BytesIO()
            info = decompress_stream(reader, writer, dict_data=dict_data)
            raw = writer.getvalue()
            if show_progress:
                print(f"[revhash] decompress <bytes {len(data)} B> -> <bytes> ({len(raw)} B) codec={info['codec']}")
            if as_text:
                return raw.decode(encoding, "strict")
            return raw
        else:
            with open(dst_path, "wb") as wf:
                info = decompress_stream(reader, wf, dict_data=dict_data)
            if show_progress:
                print(
                    f"[revhash] decompress <bytes {len(data)} B> -> {dst_path} ({info['original_size']} B) codec={info['codec']}"
                )
            # decompress to file ignores as_text (always bytes on disk)
            return info

def codec_name_norm(codec: str | int) -> str:
    try:
        cid = _normalize_codec_id(codec)
        return ID_TO_CODEC[cid]
    except Exception:
        return str(codec).lower()

# ── file_text.py ────────────────────────────────────────────────────
"""Flexible File<->Text helpers for revhash v0.2.1-filetext.

Frozen contract docs/api_filetext.md Section 3:

- _resolve_src / _resolve_dst heuristic file-vs-text (Path.exists + is_file)
- _load_dict_data (Path exists -> read_bytes)
- _guard_large_file_for_ram (100MB guard for dst=None)

All helpers are strict encoding, raise TypeError/FileNotFoundError/
IsADirectoryError/UnicodeError/ValueError per spec.

Owner: Unified I/O Builder — file_text.py 120-180 lines
"""

from pathlib import Path

def _load_dict_data(d: bytes | str | Path | None) -> bytes | None:
    """Load dict_data if it is a Path/str pointing to existing file.

    Mirrors stream.py:1035 legacy behaviour.
    """
    if isinstance(d, (str, Path)):
        p = Path(d)
        if p.exists() and p.is_file():
            return p.read_bytes()
        return None
    return d  # type: ignore[return-value]  # d is bytes|None here

def _resolve_src(src, encoding: str = "utf-8", force_text: bool = False):
    """Resolve src -> (is_file: bool, data: bytes|None, path: Path|None).

    4 forms:
      S4 bytes|bytearray|memoryview -> (False, bytes(src), None)
      S1 Path explicit file -> (True, None, Path) with exists/is_dir checks
      S2/S3 str heuristic: if not force_text and Path(src).exists() and is_file()
            -> file, else -> text encode strict

    Raises:
      TypeError if src is not str|Path|bytes-like
      FileNotFoundError if Path explicit not exists
      IsADirectoryError if Path is directory
      UnicodeEncodeError strict if str cannot be encoded
    """
    if isinstance(src, (bytes, bytearray, memoryview)):
        return False, bytes(src), None
    if isinstance(src, Path):
        p = src
        if not p.exists():
            raise FileNotFoundError(f"source not found: {p}")
        if p.is_dir():
            raise IsADirectoryError(f"source is directory: {p}")
        return True, None, p
    if isinstance(src, str):
        if not force_text:
            p = Path(src)
            try:
                if p.exists() and p.is_file():
                    return True, None, p
            except OSError:
                raise
        # S3 — text direct
        try:
            data = src.encode(encoding, "strict")
        except UnicodeEncodeError:
            raise
        return False, data, None
    raise TypeError(f"src must be str|Path|bytes, got {type(src).__name__}")

def _resolve_dst(dst):
    """Resolve dst -> Path|None with mkdir for dst.parent.

    - None -> None (RAM)
    - str|Path -> Path with parent.mkdir(parents=True, exist_ok=True)
      and IsADirectoryError if dst itself is existing directory.

    Raises:
      TypeError if dst is not str|Path|None
      IsADirectoryError if dst is existing directory
    """
    if dst is None:
        return None
    if isinstance(dst, (str, Path)):
        p = Path(dst)
        if p.exists() and p.is_dir():
            raise IsADirectoryError(f"destination is directory: {p}")
        # mkdir only for dst parent, not for src
        # parents=True handles nested out/nested/file.rvh
        # exist_ok=True safe for race
        # For dst with no parent (e.g., "file.rvh" -> parent "." ), mkdir "." is no-op
        # Use try to handle edge where parent is ""? Path("file").parent is "." which exists.
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            # parent is file? Let open raise later
            pass
        return p
    raise TypeError(f"dst must be str|Path|None, got {type(dst).__name__}")

def _guard_large_file_for_ram(src_path: Path, dst):
    """Guard OOM when src is large file and dst is None (RAM).

    Raises ValueError if dst is None and st_size > 100MB.

    Note: uses stat() syscall; caller should have validated src_path exists/is_file.
    """
    if dst is None:
        try:
            size = src_path.stat().st_size
        except OSError:
            return
        if size > 100 * 1024 * 1024:
            raise ValueError(
                "refusing to load large file (>100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
            )

def _guard_large_bytes_for_ram(data: bytes, dst):
    """Guard OOM for bytes src with dst=None (Critic HIGH #2).

    Raises ValueError if data length >100MB and dst is None.
    """
    if dst is None and isinstance(data, (bytes, bytearray, memoryview)):
        if len(data) > 100 * 1024 * 1024:
            raise ValueError(
                "refusing to load large bytes (>100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
            )

def _guard_large_decompress_for_ram(src_blob_or_path, dst, encoding="utf-8"):
    """Guard OOM for decompress dst=None (Critic HIGH #1).

    Checks header.original_size from blob (bytes or file) without full decompress.
    Raises ValueError if decompressed size >100MB and dst is None.
    """
    if dst is not None:
        return
    try:

        header = None
        if isinstance(src_blob_or_path, (bytes, bytearray, memoryview)):
            blob = bytes(src_blob_or_path)
            if len(blob) >= 23:
                header, _ = RevHashHeader.from_bytes(blob, 0)
        elif isinstance(src_blob_or_path, (str, Path)):
            p = Path(src_blob_or_path)
            if p.exists() and p.is_file() and p.stat().st_size >= 23:
                # Read only header (23 + dict_len) to get original_size
                with open(p, "rb") as f:
                    hdr = f.read(23)
                    if len(hdr) >= 23:
                        import struct

                        _, _, _, _, _, dict_len, original_size = struct.unpack("<4sBBBIIQ", hdr)
                        # Use header parse for dict_len
                        if dict_len <= 256 * 1024:
                            # Need full header for original_size already in hdr
                            # original_size is in hdr
                            if original_size != 0xFFFFFFFFFFFFFFFF and original_size > 100 * 1024 * 1024:
                                raise ValueError(
                                    f"refusing to decompress large blob (original {original_size} bytes >100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
                                )
                            return
                        # Fallback: parse full header
                        f.seek(0)
                        hdr_full = f.read(23 + dict_len)
                        header, _ = RevHashHeader.from_bytes(hdr_full, 0)
        if (
            header is not None
            and header.original_size != 0xFFFFFFFFFFFFFFFF
            and header.original_size > 100 * 1024 * 1024
        ):
            raise ValueError(
                f"refusing to decompress large blob (original {header.original_size} bytes >100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
            )
    except ValueError:
        raise
    except Exception:
        # If header parsing fails, let decompress fail later with CorruptedError
        pass

# ── End of file_text.py ───────────────────────────────────────────────
# This module is intentionally small (120-180 lines) and has no circular
# imports. It is inlined into revhash_embedded.py after stream.py per
# TEAM_PLAN_FILETEXT M3 checklist.

# ── __init__.py public API (compress/decompress/verify/get_info) ─
"""revhash — reversible lossless compression unlimited (O(1) streaming).

Public API frozen M2 (docs/api.md §2):

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

import hashlib
import hmac
import io

# HAS_LZMA guard (stdlib may be missing on minimal builds)
try:
    import lzma  # noqa: F401

    HAS_LZMA = True
except Exception:  # pragma: no cover
    HAS_LZMA = False

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
        overhead = (
            HEADER_SIZE
            + (len(dict_data) if dict_data else 0)
            + (FOOTER_SHA_SIZE + 4 + (len(data) + chunk_size - 1) // chunk_size * 4 if len(data) > 0 else 36)
        )
        if len(blob) > len(data) + overhead:  # rare for random
            # Build store blob (compress_stream's internal auto-store already
            # handles this for seekable writers; this is a defensive second pass)
            r2 = io.BytesIO(data)
            w2 = io.BytesIO()
            compress_stream(r2, w2, codec="store", level=0, chunk_size=chunk_size, dict_data=None)
            store_blob = w2.getvalue()
            if len(store_blob) < len(blob):
                return store_blob
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
    # F2 fix (critique_v05.md): parse + authenticate the header BEFORE any
    # large allocation — a hostile blob must not be able to force a giant
    # sink from a ~100-byte input. api_v05.md §3 verify-first ordering.
    header = _parse_header_lenient(blob)
    if header is not None and header.version >= 2 and not _v2_header_mac_ok(blob, header):
        raise RevHashCorruptedError("header SHA256 mismatch — rejected before preallocation")
    size_hint = _prealloc_size_hint(header)
    reader = io.BytesIO(blob)
    writer = _PreallocWriter(size_hint) if size_hint is not None else io.BytesIO()
    decompress_stream(reader, writer, dict_data=dict_data)
    return writer.getvalue()

# Preallocation cap for the decompress sink. Secondary guard only: the primary
# defence is the v2 header-MAC verification above; hints above this fall back
# to BytesIO. v1 legacy blobs carry no header MAC, so for them this cap stays
# the only bound (accepted behaviour per Coordinator F2 ruling).
_PREALLOC_MAX = 1 << 30

class _PreallocWriter:
    """Fixed-capacity output sink for ``decompress`` (v0.5 speed, Coordinator M3a-FU).

    Replaces io.BytesIO grow+getvalue (measured ~23ms/10MB on the dev box)
    with writes into a preallocated buffer sized from the header's
    original_size, then a single copy to immutable bytes.

    F2 fix: instances are created ONLY after the v2 header MAC has been
    verified (or for v1/legacy blobs, which have no MAC — bounded by
    ``_PREALLOC_MAX``). The buffer is sized by an authenticated header, so a
    hostile blob cannot trigger the allocation before being rejected.
    """

    __slots__ = ("_buf", "_pos", "_view")

    def __init__(self, size_hint: int) -> None:
        self._buf = bytearray(size_hint)
        self._view = memoryview(self._buf)
        self._pos = 0

    def write(self, data: bytes | bytearray | memoryview) -> int:
        pos = self._pos
        end = pos + len(data)
        if end > len(self._buf):
            self._buf.extend(bytes(end - len(self._buf)))
            self._view = memoryview(self._buf)
        self._view[pos:end] = data
        self._pos = end
        return end - pos

    def getvalue(self) -> bytes:
        return bytes(self._view[: self._pos])

def _parse_header_lenient(blob: bytes) -> RevHashHeader | None:
    """Best-effort header parse for sink selection (F2 fix).

    Returns ``None`` when the blob cannot carry a plausible header — no
    preallocation happens in that case and canonical validation/errors remain
    with ``decompress_stream``.
    """
    if len(blob) < HEADER_SIZE:
        return None
    try:
        header, _header_end = RevHashHeader.from_bytes(blob, 0)
    except Exception:  # noqa: BLE001 — malformed input falls back to the BytesIO path
        return None
    return header

def _v2_header_mac_ok(blob: bytes, header: RevHashHeader) -> bool:
    """Constant-time check of the v2 footer ``header_sha256`` (F2 fix).

    In both v2 layouts the MAC sits directly before ``global_sha256``, i.e.
    at ``[-(mac+sha+magic) : -(sha+magic)]`` of the blob. Runs BEFORE any
    large allocation so a forged ``original_size`` cannot force memory.
    """
    tail = FOOTER_HEADER_SHA_SIZE + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE  # 68
    if len(blob) < header.header_len + tail:
        return False  # truncated: cannot carry an authenticatable v2 footer
    stored = blob[-tail : -tail + FOOTER_HEADER_SHA_SIZE]
    computed = hashlib.sha256(memoryview(blob)[: header.header_len]).digest()
    return hmac.compare_digest(computed, stored)

def _prealloc_size_hint(header: RevHashHeader | None) -> int | None:
    """Sink size from an already-authenticated/accepted header (F2 fix).

    ``None`` for unparseable headers, UNKNOWN_SIZE, non-positive or over-cap
    hints — those take the io.BytesIO path; stream-side verification produces
    the canonical errors.
    """
    if header is None:
        return None
    size = header.original_size
    if size == UNKNOWN_SIZE or size <= 0 or size > _PREALLOC_MAX:
        return None
    return size

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

# ── text.py ─────────────────────────────────────────────────────────
# alias for text helpers (original used from . import compress as _compress)
_compress = compress
_decompress = decompress
"""Text helpers for revhash — str <-> bytes strict.

Provides explicit ``compress_text`` / ``decompress_text`` that wrap
``compress`` / ``decompress`` with UTF-8 strict handling. Imported at the
tail of ``revhash/__init__.py`` to avoid circular imports (like dict_builder).
"""

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

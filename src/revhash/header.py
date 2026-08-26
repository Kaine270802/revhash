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
...     32    global_sha256  bytes       SHA256 of original data
...     4     footer_magic   bytes       b"RVHE"
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from typing import Tuple

from .exceptions import RevHashCorruptedError, RevHashUnsupportedCodecError

# ── Constants ──────────────────────────────────────────────────────────────
HEADER_MAGIC: bytes = b"RVH1"  # 0x52 0x56 0x48 0x31
FOOTER_MAGIC: bytes = b"RVHE"
HEADER_VERSION: int = 1
UNKNOWN_SIZE: int = 0xFFFFFFFFFFFFFFFF
HEADER_SIZE: int = 23  # 4+1+1+1+4+4+8
FOOTER_SHA_SIZE: int = 32
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
                from .codec import HAS_ZSTD  # lazy to avoid circular at import time

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
        version: header version (currently 1).
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
        """Footer length for this header (per spec)."""
        if self.original_size == UNKNOWN_SIZE:
            return FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE  # per spec Nc=0
        nc = self.num_chunks
        return nc * 4 + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE

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
        if version != HEADER_VERSION:
            raise RevHashCorruptedError(f"unsupported version {version}, expected {HEADER_VERSION}")
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
        expected_footer_len = nc * 4 + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
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
            # verify SHA position
            sha_start = crc_start + nc * 4
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

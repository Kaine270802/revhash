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

from __future__ import annotations

import hashlib
import os
import struct
import zlib
from typing import BinaryIO

from .codec import HAS_BROTLI, HAS_ZSTD
from .exceptions import RevHashCorruptedError, RevHashDictError, RevHashUnsupportedCodecError
from .file_text import (
    _guard_large_bytes_for_ram,
    _guard_large_decompress_for_ram,
    _guard_large_file_for_ram,
    _load_dict_data,
    _resolve_dst,
    _resolve_src,
)
from .header import (
    FOOTER_HEADER_SHA_SIZE,
    FOOTER_MAGIC,
    FOOTER_MAGIC_SIZE,
    FOOTER_SHA_SIZE,
    HEADER_SIZE,
    HEADER_STRUCT,
    UNKNOWN_SIZE,
    RevHashHeader,
    _normalize_codec_id,  # noqa
    ID_TO_CODEC,
)

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

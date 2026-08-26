# -*- coding: utf-8 -*-
"""Header-integrity regression tests for v0.5 (Verifier-owned, TEAM_PLAN_V05.md M5).

Scope (docs/api_v05.md freeze):
1. Tamper EACH v2 header field (exactly 1 byte) on a real zstd blob ->
   ``verify()`` False OR ``RevHashCorruptedError`` (footer ``header_sha256``
   MAC is verified BEFORE any decompression, stream.py:_verify_header_mac).
2. Tamper ``header_sha256`` inside the v2 footer -> rejected.
3. Backward compat (dual-read): a hand-built valid v1 blob (footer without
   ``header_sha256``, layout ``nc*4+36``) must still decompress + verify OK,
   and a v1 blob with tampered payload must still be blocked like before.
4. CRC boundary matrix: size x codec grid -> roundtrip byte-identical and the
   footer CRC table must equal a manually computed ``zlib.crc32`` oracle per
   chunk; ``get_info()["chunks"]`` agrees with ceil(size/chunk_size).
"""

import hashlib
import struct
import zlib

import pytest

import revhash
from revhash import RevHashCorruptedError
from revhash.header import (
    FOOTER_HEADER_SHA_SIZE,
    FOOTER_MAGIC_SIZE,
    FOOTER_SHA_SIZE,
    RevHashHeader,
)

CHUNK = 1024
_POOL = (
    b"Xin chao the gioi! Hello world! revhash lossless compression test. "
    b"Du lieu lap lai nhieu lan cho ratio nen cao. "
)


def _data(n):
    if n == 0:
        return b""
    return (_POOL * (n // len(_POOL) + 1))[:n]


def _blob(n=256 * 1024, codec="zstd", chunk_size=CHUNK):
    return revhash.compress(_data(n), codec=codec, chunk_size=chunk_size)


def _expect_reject(bad_blob):
    """verify() must return False OR decompress() must raise RevHashCorruptedError."""
    try:
        revhash.decompress(bad_blob)
    except RevHashCorruptedError:
        return
    except Exception:
        pass  # e.g. RevHashUnsupportedCodecError on invalid codec_id — verify() maps it to False
    assert revhash.verify(bad_blob) is False


# ---------------------------------------------------------------------------
# 1. Header field tampering (v2 blob, footer carries header_sha256 MAC)
# ---------------------------------------------------------------------------

_HEADER_FIELDS = [
    ("codec_id", 5),
    ("level", 6),
    ("chunk_size", 7),
    ("dict_len", 11),
    ("original_size", 15),
]


@pytest.mark.parametrize("field,offset", _HEADER_FIELDS)
def test_tamper_each_header_field_rejected(field, offset):
    blob = _blob()
    assert blob[4] == 2, "new blobs must be header version 2"
    assert revhash.verify(blob) is True
    ba = bytearray(blob)
    ba[offset] ^= 0xFF  # flip exactly one byte of the chosen field
    _expect_reject(bytes(ba))


def test_untampered_baseline_ok():
    blob = _blob()
    assert revhash.decompress(blob) == _data(256 * 1024)
    assert revhash.verify(blob) is True


# ---------------------------------------------------------------------------
# 2. Footer tampering (header_sha256 / global_sha256 / CRC table)
# ---------------------------------------------------------------------------


def _v2_mac_offset(blob_len, nc):
    """Offset of header_sha256 inside a known-size v2 footer."""
    footer_len = nc * 4 + FOOTER_HEADER_SHA_SIZE + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
    return blob_len - footer_len + nc * 4


def test_tamper_footer_header_sha256_rejected():
    data = _data(256 * 1024)
    blob = _blob(n=len(data))
    nc = (len(data) + CHUNK - 1) // CHUNK
    ba = bytearray(blob)
    off = _v2_mac_offset(len(ba), nc)
    ba[off] ^= 0xFF
    _expect_reject(bytes(ba))


def test_tamper_footer_global_sha_rejected():
    data = _data(256 * 1024)
    blob = bytearray(_blob(n=len(data)))
    blob[-36] ^= 0xFF  # first byte of global_sha256 (-36:-4)
    _expect_reject(bytes(blob))


def test_tamper_footer_crc_table_rejected():
    data = _data(256 * 1024)
    blob = bytearray(_blob(n=len(data)))
    nc = (len(data) + CHUNK - 1) // CHUNK
    blob[-(FOOTER_HEADER_SHA_SIZE + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE)] ^= 0xFF  # last CRC entry
    assert nc > 0
    _expect_reject(bytes(blob))


# ---------------------------------------------------------------------------
# 3. Dual-read backward compatibility (v1 blobs)
# ---------------------------------------------------------------------------


def _downgrade_to_v1(blob):
    """Convert a known-size v2 blob into the equivalent legacy v1 blob.

    v2 known-size footer: [crcs nc*4][header_sha256 32][global_sha256 32][RVHE 4]
    v1 known-size footer: [crcs nc*4][global_sha256 32][RVHE 4]
    """
    assert blob[4] == 2
    tail_len = FOOTER_HEADER_SHA_SIZE + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE  # 68: mac+sha+magic
    stripped = blob[:-tail_len] + blob[-(FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE) :]
    ba = bytearray(stripped)
    ba[4] = 1  # version byte -> 1
    return bytes(ba)


def test_v1_blob_decompress_verify_ok():
    data = _data(200 * 1024)
    v1 = _downgrade_to_v1(revhash.compress(data, codec="zstd", chunk_size=CHUNK))
    info = revhash.get_info(v1)
    assert info["version"] == 1
    assert revhash.decompress(v1) == data
    assert hashlib.sha256(revhash.decompress(v1)).hexdigest() == hashlib.sha256(data).hexdigest()
    assert revhash.verify(v1) is True


def test_v1_tampered_payload_still_blocked():
    data = _data(200 * 1024)
    v1 = bytearray(_downgrade_to_v1(revhash.compress(data, codec="zstd", chunk_size=CHUNK)))
    v1[23 + 10] ^= 0xFF  # flip one byte inside the compressed stream (no dict embedded)
    _expect_reject(bytes(v1))


def test_v1_header_field_tamper_blocked_by_legacy_checks():
    # v1 has no header MAC, but chunk_size tampering must STILL not silently pass:
    # it changes num_chunks/footer layout -> parse/CRC failure (legacy behaviour).
    data = _data(300 * 1024)
    v1 = bytearray(_downgrade_to_v1(revhash.compress(data, codec="zstd", chunk_size=CHUNK)))
    struct.pack_into("<I", v1, 7, 4096)  # chunk_size 1024 -> 4096 (same total size, fewer chunks)
    _expect_reject(bytes(v1))


# ---------------------------------------------------------------------------
# 4. CRC boundary matrix vs manual zlib.crc32 oracle
# ---------------------------------------------------------------------------

_SIZES = [0, 1, CHUNK - 1, CHUNK, CHUNK + 1, 3 * CHUNK + 123]
_CODECS = ["store", "zstd"]


@pytest.mark.parametrize("codec", _CODECS)
@pytest.mark.parametrize("n", _SIZES)
def test_crc_boundary_matrix_roundtrip_and_oracle(codec, n):
    data = _data(n)
    blob = revhash.compress(data, codec=codec, chunk_size=CHUNK)

    # roundtrip byte-identical
    out = revhash.decompress(blob)
    assert out == data
    assert hashlib.sha256(out).digest() == hashlib.sha256(data).digest()

    hdr, _hdr_end = RevHashHeader.from_bytes(blob, 0)
    nc = hdr.num_chunks
    expected_nc = (n + CHUNK - 1) // CHUNK  # 0 chunks for empty input
    assert nc == expected_nc

    info = revhash.get_info(blob)
    assert info["chunks"] == expected_nc
    assert info["version"] == 2

    # oracle: footer CRC table == manual zlib.crc32 per chunk
    footer_len = nc * 4 + FOOTER_HEADER_SHA_SIZE + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
    crc_bytes = blob[len(blob) - footer_len : len(blob) - footer_len + nc * 4]
    assert len(crc_bytes) == nc * 4
    crc_table = list(struct.unpack("<%dI" % nc, crc_bytes)) if nc else []
    oracle = [zlib.crc32(data[i : i + CHUNK]) & 0xFFFFFFFF for i in range(0, n, CHUNK)]
    assert crc_table == oracle

    assert revhash.verify(blob) is True

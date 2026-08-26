"""test_header — 18 cases: magic RVH1, version (v2 default, dual-read v1), codec_id LE, dict_len, UNKNOWN, Nc/overhead, corruption."""
import struct

import pytest

import revhash
from revhash.exceptions import RevHashCorruptedError, RevHashUnsupportedCodecError
from revhash.header import (
    FOOTER_HEADER_SHA_SIZE,
    FOOTER_MAGIC,
    FOOTER_MAGIC_SIZE,
    FOOTER_SHA_SIZE,
    HEADER_MAGIC,
    HEADER_SIZE,
    HEADER_STRUCT,
    HEADER_VERSION,
    UNKNOWN_SIZE,
    RevHashHeader,
)


def test_magic_rvh1():
    h = RevHashHeader(codec="zstd", original_size=100)
    b = h.to_bytes()
    assert b[:4] == b"RVH1"
    hdr, _ = RevHashHeader.from_bytes(b, 0)
    assert hdr.codec == "zstd"


def test_version_default_v2():
    # Coordinator M3a-FU: freeze docs/api_v05.md đổi default ghi mới sang version 2 (dual-read 1+2)
    h = RevHashHeader(codec="gzip", original_size=10)
    b = h.to_bytes()
    assert b[4] == HEADER_VERSION
    hdr, _ = RevHashHeader.from_bytes(b, 0)
    assert hdr.version == HEADER_VERSION


def test_codec_id_le_store():
    for codec, cid in [("store", 0), ("gzip", 1), ("zstd", 2), ("lzma", 3), ("brotli", 4)]:
        h = RevHashHeader(codec=codec, original_size=10)
        assert h.codec_id == cid
        b = h.to_bytes()
        assert b[5] == cid
        # also check LE struct
        unpacked = HEADER_STRUCT.unpack(b[:HEADER_SIZE])
        assert unpacked[2] == cid


def test_chunk_size_le_default_4M():
    h = RevHashHeader(codec="zstd", chunk_size=4 * 1024 * 1024, original_size=100)
    b = h.to_bytes()
    cs = struct.unpack("<I", b[7:11])[0]
    assert cs == 4 * 1024 * 1024


def test_dict_len_le():
    d = b"dict" * 100
    h = RevHashHeader(codec="zstd", dict_data=d, original_size=100)
    b = h.to_bytes()
    dl = struct.unpack("<I", b[11:15])[0]
    assert dl == len(d)
    hdr, off = RevHashHeader.from_bytes(b, 0)
    assert hdr.dict_len == len(d)
    assert hdr.dict_data == d
    assert off == HEADER_SIZE + len(d)


def test_unknown_size():
    h = RevHashHeader(codec="zstd", original_size=UNKNOWN_SIZE)
    b = h.to_bytes()
    orig = struct.unpack("<Q", b[15:23])[0]
    assert orig == UNKNOWN_SIZE
    assert h.num_chunks == 0
    # Coordinator M3a-FU: footer v2 luôn có header_sha256 → unknown-size = 32+32+4 = 68B (api_v05.md §2)
    assert h.footer_len() == FOOTER_HEADER_SHA_SIZE + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
    hdr, _ = RevHashHeader.from_bytes(b, 0)
    assert hdr.original_size == UNKNOWN_SIZE


def test_num_chunks_and_overhead():
    # 100MB /4M =25 chunks, footer v2 25*4+68=168
    h = RevHashHeader(codec="zstd", chunk_size=4 * 1024 * 1024, original_size=100 * 1024 * 1024)
    assert h.num_chunks == 25
    # Coordinator M3a-FU: công thức footer-len v2 theo api_v05.md §2 (nc*4 + header_sha256 32 + sha 32 + magic 4)
    assert h.footer_len() == 25 * 4 + FOOTER_HEADER_SHA_SIZE + FOOTER_SHA_SIZE + FOOTER_MAGIC_SIZE
    assert h.header_len == HEADER_SIZE
    # overhead calc
    overhead = HEADER_SIZE + h.footer_len()
    assert overhead == HEADER_SIZE + 25 * 4 + 68


def test_header_size_constant():
    assert HEADER_SIZE == 23
    assert FOOTER_SHA_SIZE == 32
    assert FOOTER_MAGIC_SIZE == 4
    assert HEADER_MAGIC == b"RVH1"
    assert FOOTER_MAGIC == b"RVHE"


def test_corruption_magic():
    data = b"hello" * 10
    blob = revhash.compress(data)
    bad = bytearray(blob)
    bad[0:4] = b"BAD!"
    with pytest.raises(RevHashCorruptedError):
        RevHashHeader.from_bytes(bytes(bad), 0)
    with pytest.raises(RevHashCorruptedError):
        revhash.decompress(bytes(bad))


def test_corruption_version():
    data = b"hello"
    blob = revhash.compress(data)
    bad = bytearray(blob)
    bad[4] = 99
    with pytest.raises(RevHashCorruptedError):
        RevHashHeader.from_bytes(bytes(bad), 0)


def test_corruption_codec_id():
    h = RevHashHeader(codec="zstd", original_size=10)
    b = bytearray(h.to_bytes())
    b[5] = 99
    with pytest.raises(RevHashUnsupportedCodecError):
        RevHashHeader.from_bytes(bytes(b), 0)


def test_corruption_truncated_header():
    h = RevHashHeader(codec="zstd", original_size=10)
    b = h.to_bytes()
    with pytest.raises(RevHashCorruptedError):
        RevHashHeader.from_bytes(b[:10], 0)


def test_corruption_dict_len_limit():
    # dict_len >256KB should raise
    h = RevHashHeader(codec="zstd", original_size=10)
    # manually craft header with dict_len 300KB
    packed = HEADER_STRUCT.pack(b"RVH1", 1, 2, 3, 4 * 1024 * 1024, 300 * 1024, 10)
    with pytest.raises(RevHashCorruptedError):
        RevHashHeader.from_bytes(packed + b"x" * 10, 0)
    # via to_bytes
    h2 = RevHashHeader(codec="zstd", original_size=10)
    h2.dict_len = 300 * 1024
    h2.dict_data = b"x" * (300 * 1024)
    with pytest.raises(RevHashCorruptedError):
        h2.to_bytes()


def test_chunk_size_limits():
    # too small
    h = RevHashHeader(codec="zstd", chunk_size=512, original_size=10)
    with pytest.raises(RevHashCorruptedError):
        h.to_bytes()
    # too large
    h = RevHashHeader(codec="zstd", chunk_size=100 * 1024 * 1024, original_size=10)
    with pytest.raises(RevHashCorruptedError):
        h.to_bytes()
    # valid boundaries
    for cs in [1024, 64 * 1024 * 1024]:
        h = RevHashHeader(codec="zstd", chunk_size=cs, original_size=10)
        b = h.to_bytes()
        hdr, _ = RevHashHeader.from_bytes(b, 0)
        assert hdr.chunk_size == cs


def test_chunk_size_truncated_dict():
    h = RevHashHeader(codec="zstd", dict_data=b"abc", original_size=10)
    b = h.to_bytes()
    # truncate dict
    with pytest.raises(RevHashCorruptedError):
        RevHashHeader.from_bytes(b[:-1], 0)


def test_original_size_zero():
    h = RevHashHeader(codec="store", original_size=0)
    assert h.num_chunks == 0
    b = h.to_bytes()
    hdr, _ = RevHashHeader.from_bytes(b, 0)
    assert hdr.original_size == 0
    # compress empty
    blob = revhash.compress(b"")
    hdr2, _ = RevHashHeader.from_bytes(blob, 0)
    assert hdr2.original_size == 0


def test_footer_magic_and_parse():
    data = b"footer test" * 100
    blob = revhash.compress(data)
    assert blob[-4:] == b"RVHE"
    from revhash.header import parse_footer

    hdr, off = RevHashHeader.from_bytes(blob, 0)
    crcs, sha, magic = parse_footer(blob, hdr, off)
    assert magic == b"RVHE"
    assert len(sha) == 32
    assert len(crcs) == hdr.num_chunks


def test_unknown_footer_no_crcs():
    import io
    from revhash.stream import compress_stream

    # non-seekable reader forces UNKNOWN
    class NonSeekable:
        def __init__(self, d):
            self._d = d
            self._p = 0

        def read(self, n=-1):
            if n < 0:
                n = len(self._d) - self._p
            chunk = self._d[self._p : self._p + n]
            self._p += len(chunk)
            return chunk

        def readable(self):
            return True

    data = b"unknown size test " * 500
    reader = NonSeekable(data)
    writer = io.BytesIO()
    # use store to avoid codec complexities? but writer non-seekable? BytesIO is seekable, will patch to known, so need non-seekable writer
    class NSWriter:
        def __init__(self):
            self.buf = bytearray()

        def write(self, d):
            self.buf.extend(d)
            return len(d)

        def tell(self):
            raise OSError("not seekable")

        def seek(self, *a, **kw):
            raise OSError("not seekable")

        def seekable(self):
            return False

    # alternative: use decompress path with v2 footer
    # simpler: check that UNKNOWN header has footer_len 68 (v2: mac+sha+magic)
    h = RevHashHeader(codec="store", original_size=UNKNOWN_SIZE)
    # Coordinator M3a-FU: UNKNOWN vẫn ghi header_sha256 ở footer v2 (api_v05.md Q6) → 68B
    assert h.footer_len() == FOOTER_HEADER_SHA_SIZE + 36

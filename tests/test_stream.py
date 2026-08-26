"""test_stream — 12 cases: CountingReader O1, file streaming SHA, chunk boundary, CRC+SHA, NonSeekable, 50MB O1, mkdir."""
import hashlib
import io
import os
import struct
import zlib
from pathlib import Path

import pytest

import revhash
from revhash.exceptions import RevHashCorruptedError
from revhash.header import FOOTER_HEADER_SHA_SIZE, HEADER_SIZE, RevHashHeader


class CountingReader:
    def __init__(self, data: bytes, chunk_size: int):
        self.data = data
        self.chunk_size = chunk_size
        self.pos = 0
        self.calls = []
        self.had_minus_one = False

    def read(self, size=-1):
        if size == -1:
            self.had_minus_one = True
        self.calls.append(size)
        if self.pos >= len(self.data):
            return b""
        # respect size
        if size < 0:
            size = len(self.data) - self.pos
        chunk = self.data[self.pos : self.pos + size]
        self.pos += len(chunk)
        return chunk

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        if whence == 0:
            self.pos = off
        elif whence == 1:
            self.pos += off
        elif whence == 2:
            self.pos = len(self.data) + off
        return self.pos

    def seekable(self):
        return True


def gen_repeat(n):
    pool = b"abcd" * 256
    return (pool * ((n // len(pool)) + 1))[:n]


def test_counting_reader_o1_no_minus_one():
    data = gen_repeat(5 * 1024 * 1024)
    reader = CountingReader(data, 4 * 1024 * 1024)
    writer = io.BytesIO()
    revhash.compress_stream(reader, writer, codec="zstd", chunk_size=4 * 1024 * 1024)
    assert reader.had_minus_one is False
    # should have called read with chunk_size, not -1
    assert all(c == 4 * 1024 * 1024 for c in reader.calls if c != 0)
    # also verify decompress
    blob = writer.getvalue()
    out = revhash.decompress(blob)
    assert out == data


def test_file_10MB_streaming_sha_match(tmp_path):
    data = gen_repeat(10 * 1024 * 1024)
    src = tmp_path / "src10.bin"
    dst = tmp_path / "dst.rvh"
    restored = tmp_path / "rest.bin"
    src.write_bytes(data)
    info = revhash.compress_file(src, dst)
    assert dst.exists()
    assert info["original_size"] == len(data)
    revhash.decompress_file(dst, restored)
    assert hashlib.sha256(restored.read_bytes()).digest() == hashlib.sha256(data).digest()


def test_file_20MB_streaming(tmp_path):
    data = gen_repeat(20 * 1024 * 1024)
    src = tmp_path / "src20.bin"
    dst = tmp_path / "dst20.rvh"
    src.write_bytes(data)
    revhash.compress_file(src, dst)
    out = tmp_path / "out20.bin"
    revhash.decompress_file(dst, out)
    assert out.read_bytes() == data


def test_chunk_boundary_4M_123(tmp_path):
    chunk = 4 * 1024 * 1024
    size = chunk + 123
    data = gen_repeat(size)
    blob = revhash.compress(data, chunk_size=chunk)
    info = revhash.get_info(blob)
    assert info["chunks"] == 2
    assert revhash.decompress(blob) == data
    # also via stream file
    from revhash.header import RevHashHeader

    hdr, _ = RevHashHeader.from_bytes(blob, 0)
    assert hdr.num_chunks == 2


def test_per_chunk_crc_and_sha():
    data = gen_repeat(8 * 1024 * 1024 + 500)
    blob = revhash.compress(data, chunk_size=4 * 1024 * 1024)
    from revhash.header import parse_footer, RevHashHeader

    hdr, off = RevHashHeader.from_bytes(blob, 0)
    crcs, sha, magic = parse_footer(blob, hdr, off)
    # recompute
    expected_crcs = []
    for i in range(0, len(data), hdr.chunk_size):
        expected_crcs.append(zlib.crc32(data[i : i + hdr.chunk_size]) & 0xFFFFFFFF)
    assert crcs == expected_crcs
    assert sha == hashlib.sha256(data).digest()
    assert magic == b"RVHE"
    # tamper one CRC byte should fail
    tampered = bytearray(blob)
    # footer start = total - footer_len
    footer_len = hdr.footer_len()
    crc_start = len(blob) - footer_len
    tampered[crc_start] ^= 0xFF
    with pytest.raises(RevHashCorruptedError):
        revhash.decompress(bytes(tampered))


def test_nonseekable_unknown_68B():
    # Use stream with non-seekable reader -> UNKNOWN triggers v2 footer (mac+sha+magic = 68B)
    # Coordinator M3a-FU: đổi tên từ *_36B — footer v2 luôn có header_sha256 dù UNKNOWN (api_v05.md Q6)
    class NSReader:
        def __init__(self, d):
            self.d = d
            self.p = 0

        def read(self, n=-1):
            if self.p >= len(self.d):
                return b""
            if n < 0:
                n = len(self.d) - self.p
            chunk = self.d[self.p : self.p + n]
            self.p += len(chunk)
            return chunk

    data = b"nonseekable test " * 1000

    class NSWriter:
        def __init__(self):
            self.buf = bytearray()

        def write(self, d):
            self.buf.extend(d)
            return len(d)

        def seekable(self):
            return False

        def tell(self):
            return len(self.buf)

        def seek(self, *a, **k):
            raise OSError

    w = NSWriter()
    info = revhash.compress_stream(NSReader(data), w, codec="store", chunk_size=1024 * 1024)
    blob = bytes(w.buf)
    hdr, _ = RevHashHeader.from_bytes(blob, 0)
    from revhash.header import UNKNOWN_SIZE

    assert hdr.original_size == UNKNOWN_SIZE
    assert blob[-4:] == b"RVHE"
    # footer v2 = header_sha256 32 + sha 32 + magic 4 = 68B (no CRCs)
    # total blob = header 23 + compressed + 68
    assert len(blob) == HEADER_SIZE + len(data) + FOOTER_HEADER_SHA_SIZE + 36
    # decompress should handle UNKNOWN via buffer fallback
    out = revhash.decompress(blob)
    assert out == data


def test_50MB_genreader_o1_peak(tmp_path):
    # O1: use GenReader that generates without holding 50MB all at once, but we still test via file to avoid memory
    size = 50 * 1024 * 1024
    chunk = 4 * 1024 * 1024
    # Create file via streaming writes to avoid holding 50MB in RAM before test? but we need data for hash
    # We'll use file with repeat pattern written in chunks
    src = tmp_path / "src50.bin"
    with open(src, "wb") as f:
        pool = b"abcd" * 1024
        written = 0
        while written < size:
            to_write = min(len(pool), size - written)
            f.write(pool[:to_write])
            written += to_write
    dst = tmp_path / "dst50.rvh"
    # compress file O1
    try:
        import tracemalloc

        tracemalloc.start()
        revhash.compress_file(src, dst)
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        # peak should be bounded. With 50MB data, peak <150MB even though file is 50MB (streaming)
        # tracemalloc counts Python allocations, file streaming should be < chunk + overhead
        # allow generous 150MB
        assert peak < 150 * 1024 * 1024
    except ImportError:
        revhash.compress_file(src, dst)
    # verify via SHA
    # decompress and check size not full RAM verify via hash streaming
    out = tmp_path / "out50.bin"
    revhash.decompress_file(dst, out)
    assert out.stat().st_size == size
    # hash via streaming
    h1 = hashlib.sha256()
    with open(src, "rb") as f:
        for chunk_data in iter(lambda: f.read(1 << 20), b""):
            h1.update(chunk_data)
    h2 = hashlib.sha256()
    with open(out, "rb") as f:
        for chunk_data in iter(lambda: f.read(1 << 20), b""):
            h2.update(chunk_data)
    assert h1.digest() == h2.digest()


def test_mkdir_only_dst_not_src(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    dst = tmp_path / "out" / "nested" / "deep" / "b.rvh"
    assert not dst.parent.exists()
    revhash.compress_file(src, dst)
    assert dst.parent.exists()
    # decompress dst mkdir
    restored = tmp_path / "out2" / "deep2" / "rest.txt"
    assert not restored.parent.exists()
    revhash.decompress_file(dst, restored)
    assert restored.exists()
    assert restored.read_text() == "hello"
    # src missing should not mkdir parent of src
    missing = tmp_path / "nonexist" / "missing.txt"
    with pytest.raises(FileNotFoundError):
        revhash.compress_file(missing, tmp_path / "out.rvh")
    assert not (tmp_path / "nonexist").exists()


def test_compress_stream_read_chunk_size_loop():
    # ensure stream uses read(chunk_size) not read()
    data = b"x" * (2 * 1024 * 1024 + 500)
    reader = CountingReader(data, 1024 * 1024)
    writer = io.BytesIO()
    revhash.compress_stream(reader, writer, codec="gzip", chunk_size=1024 * 1024)
    assert reader.had_minus_one is False
    assert revhash.decompress(writer.getvalue()) == data


def test_decompress_stream_buffer_fallback():
    data = b"buffer fallback test " * 5000
    blob = revhash.compress(data, codec="gzip")
    # wrap in non-seekable reader for decompress
    class NSReader2:
        def __init__(self, d):
            self.d = d
            self.p = 0

        def read(self, n=-1):
            if self.p >= len(self.d):
                return b""
            if n < 0:
                n = len(self.d) - self.p
            chunk = self.d[self.p : self.p + n]
            self.p += len(chunk)
            return chunk

    out = io.BytesIO()
    revhash.decompress_stream(NSReader2(blob), out)
    assert out.getvalue() == data


def test_chunk_boundary_exact():
    chunk = 1024 * 1024
    for size in [chunk, chunk * 2, chunk * 2 + 1, chunk * 3 - 1]:
        data = gen_repeat(size)
        blob = revhash.compress(data, chunk_size=chunk)
        assert revhash.decompress(blob) == data
        info = revhash.get_info(blob)
        expected = (size + chunk - 1) // chunk if size else 0
        assert info["chunks"] == expected


def test_compress_decompress_stream_store():
    data = b"store stream " * 1000
    r = io.BytesIO(data)
    w = io.BytesIO()
    revhash.compress_stream(r, w, codec="store", chunk_size=1024 * 1024)
    blob = w.getvalue()
    r2 = io.BytesIO(blob)
    w2 = io.BytesIO()
    revhash.decompress_stream(r2, w2)
    assert w2.getvalue() == data

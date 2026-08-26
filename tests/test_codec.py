"""test_codec — 35 cases: store/gzip/zstd/lzma/brotli roundtrip sizes, random auto-store, compress_text vs compress, header LE, tamper, get_available_codecs."""
import hashlib
import os
import random
import struct

import pytest

import revhash
import revhash_embedded
from revhash.exceptions import RevHashCorruptedError


def gen_repeat(n, pool=b"hello world revhash "):
    if n == 0:
        return b""
    rep = (pool * ((n // len(pool)) + 1))[:n]
    return rep


def gen_random(n, seed=42):
    rnd = random.Random(seed)
    return bytes(rnd.getrandbits(8) for _ in range(n))


SIZES = [0, 1, 100, 1024, 10 * 1024, 1024 * 1024, 10 * 1024 * 1024]
CODECS = ["store", "gzip", "zstd", "lzma", "brotli"]


@pytest.mark.parametrize("codec", CODECS)
@pytest.mark.parametrize("size", SIZES)
def test_codec_roundtrip_sizes(codec, size):
    avail = revhash.get_available_codecs()
    if not avail.get(codec):
        pytest.skip(f"codec {codec} not available")
    data = gen_repeat(size)
    blob = revhash.compress(data, codec=codec, level=3 if codec != "store" else 0)
    assert isinstance(blob, bytes)
    # header LE checks for one sample per codec (10KB) to avoid repeating overhead
    if size == 10 * 1024:
        from revhash.header import RevHashHeader

        hdr, _ = RevHashHeader.from_bytes(blob, 0)
        assert hdr.codec == codec or (len(data) < 100 and hdr.codec == "store")
        # LE check: chunk_size bytes at offset 7 should be little endian
        chunk_le = struct.unpack("<I", blob[7:11])[0]
        assert chunk_le == hdr.chunk_size
    out = revhash.decompress(blob)
    assert hashlib.sha256(out).hexdigest() == hashlib.sha256(data).hexdigest()
    assert out == data
    assert revhash.verify(blob) is True
    info = revhash.get_info(blob)
    assert info["codec"] in CODECS
    assert info["compressed_size"] == len(blob)


def test_random_incompressible_auto_store():
    # random 10KB should trigger store fallback (or at least not inflate too much)
    avail = revhash.get_available_codecs()
    data = gen_random(10 * 1024, seed=1)
    for codec in ["gzip", "zstd"]:
        if not avail.get(codec):
            continue
        blob = revhash.compress(data, codec=codec)
        out = revhash.decompress(blob)
        assert out == data
        # compressed should be close to store size, not huge inflation
        # store estimate 23+10KB+36 ~ 10300, so blob should be <= 15000
        assert len(blob) < len(data) + 5000
        # info codec may be store due to fallback
        info = revhash.get_info(blob)
        assert info["codec"] in (codec, "store")


def test_random_1MB_incompressible():
    avail = revhash.get_available_codecs()
    if not avail.get("zstd"):
        pytest.skip("zstd missing")
    data = gen_random(1024 * 1024, seed=99)
    blob = revhash.compress(data, codec="zstd")
    out = revhash.decompress(blob)
    assert hashlib.sha256(out).digest() == hashlib.sha256(data).digest()
    # should fallback to store, ratio ~1.0
    info = revhash.get_info(blob)
    # not hardcoding ratio 0.000151, just check not huge
    assert info["ratio"] < 1.5


def test_compress_text_vs_compress():
    text = "xin chao"
    b1 = revhash.compress(text)
    b2 = revhash.compress(text.encode("utf-8"))
    assert b1 == b2
    assert revhash.decompress(b1) == text.encode("utf-8")
    # also via compress_text wrapper
    b3 = revhash.compress_text(text)
    assert revhash.decompress_text(b3) == text
    assert b3 == b1  # wrapper uses same compress
    # embedded parity
    assert revhash_embedded.compress(text) == b1
    assert revhash_embedded.compress_text(text) == b3


def test_header_le_and_magic():
    data = b"hello" * 200
    blob = revhash.compress(data, codec="zstd")
    assert blob[:4] == b"RVH1"
    # version at offset 4
    # Coordinator M3a-FU: mọi blob mới ghi version=2 theo freeze api_v05.md (dual-read vẫn nhận 1)
    assert blob[4] == 2
    # codec_id LE at offset 5
    codec_id = blob[5]
    assert codec_id in (0, 1, 2, 3, 4)
    # chunk_size LE at 7
    chunk_size = struct.unpack("<I", blob[7:11])[0]
    assert 1024 <= chunk_size <= 64 * 1024 * 1024
    # dict_len LE at 11
    dict_len = struct.unpack("<I", blob[11:15])[0]
    assert dict_len <= 256 * 1024
    # original_size LE at 15
    orig = struct.unpack("<Q", blob[15:23])[0]
    assert orig == len(data)
    # footer magic last 4
    assert blob[-4:] == b"RVHE"


def test_tamper_flip_detection():
    data = b"tamper test " * 1000
    blob = revhash.compress(data, codec="zstd")
    # flip one byte in middle (avoid header magic to test CRC/SHA)
    tampered = bytearray(blob)
    # choose offset after header
    off = 30 if len(tampered) > 40 else len(tampered) // 2
    tampered[off] ^= 0xFF
    tampered = bytes(tampered)
    assert revhash.verify(tampered) is False
    with pytest.raises(RevHashCorruptedError):
        revhash.decompress(tampered)
    # also test header LE tamper: flip magic
    tampered2 = bytearray(blob)
    tampered2[0] ^= 0xFF
    with pytest.raises(RevHashCorruptedError):
        revhash.decompress(bytes(tampered2))


def test_get_available_codecs():
    avail = revhash.get_available_codecs()
    assert isinstance(avail, dict)
    assert avail["store"] is True
    assert avail["gzip"] is True
    assert "zstd" in avail and "lzma" in avail and "brotli" in avail
    # embedded same keys
    avail2 = revhash_embedded.get_available_codecs()
    assert set(avail.keys()) == set(avail2.keys())
    # store and gzip always true
    assert avail2["store"] is True and avail2["gzip"] is True


def test_compress_level_variants():
    data = b"level test " * 5000
    avail = revhash.get_available_codecs()
    for codec, levels in [("gzip", [1, 6, 9]), ("zstd", [1, 3, 9]), ("lzma", [0, 6]), ("brotli", [1, 6, 11])]:
        if not avail.get(codec):
            continue
        for lvl in levels:
            blob = revhash.compress(data, codec=codec, level=lvl)
            out = revhash.decompress(blob)
            assert out == data


def test_store_codec_explicit():
    for n in [0, 1, 10, 1024, 10 * 1024]:
        data = gen_repeat(n)
        blob = revhash.compress(data, codec="store")
        info = revhash.get_info(blob)
        assert info["codec"] == "store"
        assert revhash.decompress(blob) == data


def test_gzip_brotli_lzma_small():
    data = b"small" * 200
    for codec in ["gzip", "lzma", "brotli"]:
        avail = revhash.get_available_codecs()
        if not avail.get(codec):
            continue
        blob = revhash.compress(data, codec=codec)
        assert revhash.decompress(blob) == data


def test_compress_bytes_memoryview_bytearray():
    data = b"hello bytes"
    for variant in [data, bytearray(data), memoryview(data)]:
        blob = revhash.compress(variant)
        assert revhash.decompress(blob) == data


def test_empty_blob_roundtrip():
    blob = revhash.compress(b"")
    out = revhash.decompress(blob)
    assert out == b""
    assert revhash.verify(blob) is True
    info = revhash.get_info(blob)
    assert info["original_size"] == 0
    assert blob[-4:] == b"RVHE"

"""test_fuzz — 4 cases: 100 random blobs seed 42 0-10KB across codecs roundtrip + single-byte tamper 100% detection, 20 stream fuzz, empty/1B."""
import hashlib
import io
import random

import pytest

import revhash
from revhash.exceptions import RevHashCorruptedError


def gen_random(n, seed):
    rnd = random.Random(seed)
    return bytes(rnd.getrandbits(8) for _ in range(n))


def test_fuzz_100_random_blobs_seed42():
    rnd = random.Random(42)
    codecs = ["store", "gzip", "zstd", "lzma", "brotli"]
    avail = revhash.get_available_codecs()
    codecs = [c for c in codecs if avail.get(c)]
    for i in range(100):
        size = rnd.randint(0, 10 * 1024)
        data = bytes(rnd.getrandbits(8) for _ in range(size))
        for codec in codecs:
            level = 3
            if codec == "gzip":
                level = 6
            elif codec == "lzma":
                level = 6
            elif codec == "brotli":
                level = 6
            try:
                blob = revhash.compress(data, codec=codec, level=level)
            except Exception as e:
                # zstd/brotli may not be available
                if "not installed" in str(e) or "not available" in str(e):
                    continue
                raise
            out = revhash.decompress(blob)
            assert out == data, f"fuzz {i} size {size} codec {codec} mismatch"
            assert revhash.verify(blob) is True
            # tamper detection: flip one byte if blob >10
            if len(blob) > 10:
                tampered = bytearray(blob)
                # avoid flipping header magic for determinism? flipping middle still should detect via CRC/SHA
                mid = len(tampered) // 2
                tampered[mid] ^= 0x01
                assert revhash.verify(bytes(tampered)) is False
                with pytest.raises(RevHashCorruptedError):
                    revhash.decompress(bytes(tampered))


def test_fuzz_20_stream():
    rnd = random.Random(123)
    for i in range(20):
        size = rnd.randint(0, 100 * 1024)
        data = bytes(rnd.getrandbits(8) for _ in range(size))
        # stream compress
        r = io.BytesIO(data)
        w = io.BytesIO()
        revhash.compress_stream(r, w, codec="zstd", chunk_size=1 * 1024 * 1024)
        blob = w.getvalue()
        # stream decompress
        r2 = io.BytesIO(blob)
        w2 = io.BytesIO()
        revhash.decompress_stream(r2, w2)
        assert w2.getvalue() == data


def test_fuzz_empty_and_1B():
    for data in [b"", b"\x00", b"\xff", b"a", b"\x00\xff\x01"]:
        for codec in ["store", "gzip", "zstd"]:
            avail = revhash.get_available_codecs()
            if not avail.get(codec):
                continue
            blob = revhash.compress(data, codec=codec)
            out = revhash.decompress(blob)
            assert out == data
            assert revhash.verify(blob) is True
    # many seeds empty/1B
    rnd = random.Random(99)
    for _ in range(20):
        data = bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 1)))
        blob = revhash.compress(data)
        assert revhash.decompress(blob) == data


def test_fuzz_single_byte_tamper_100percent():
    # ensure 100% detection across 100 random blobs
    rnd = random.Random(2024)
    for i in range(100):
        size = rnd.randint(100, 5000)
        data = bytes(rnd.getrandbits(8) for _ in range(size))
        blob = revhash.compress(data, codec="zstd")
        # flip single byte at random position after header
        pos = rnd.randint(23, len(blob) - 5) if len(blob) > 28 else len(blob) // 2
        tampered = bytearray(blob)
        tampered[pos] ^= 0xFF
        assert revhash.verify(bytes(tampered)) is False
        with pytest.raises(RevHashCorruptedError):
            revhash.decompress(bytes(tampered))


def test_fuzz_deterministic_seed42_repeat():
    rnd = random.Random(42)
    for _ in range(10):
        data = bytes(rnd.getrandbits(8) for _ in range(500))
        blob = revhash.compress(data)
        assert revhash.decompress(blob) == data


def test_fuzz_empty_stream():
    for codec in ["store", "gzip", "zstd"]:
        avail = revhash.get_available_codecs()
        if not avail.get(codec):
            continue
        blob = revhash.compress(b"", codec=codec)
        assert revhash.decompress(blob) == b""

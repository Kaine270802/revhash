# -*- coding: utf-8 -*-
"""Performance smoke gates for v0.5 (Verifier-owned, TEAM_PLAN_V05.md M5).

COLD protocol per docs/research_v05.md Phan 3: fresh data object every run via
``bytes(bytearray(base))`` (a real copy — ``bytes(bytes_obj)`` would alias),
``gc.collect()`` + ``revhash.codec._cache_clear()`` before every run, first
(warm-up) run discarded, median of 5 measured runs.

Gate: hard-fail below 200 MB/s. Local cold measurements on the dev box are
~900-950 MB/s compress / ~750-810 MB/s decompress, so 200 MB/s keeps ~3.5x
margin for slow CI machines while still catching a catastrophic regression
(e.g. re-introduction of the v0.4 triple-copy decompress buffer at ~240 MB/s).
"""

import gc
import hashlib
import statistics
import time

import pytest

import revhash

SIZE_BYTES = 2 * 1024 * 1024
GATE_MB_S = 200.0
WARMUP_RUNS = 1
MEASURED_RUNS = 5

_POOL = (
    b"The quick brown fox jumps over the lazy dog. "
    b"revhash cold perf smoke payload 0123456789 "
)


def _make_base(n):
    repeats = n // len(_POOL) + 1
    return (_POOL * repeats)[:n]


def _mb():
    return SIZE_BYTES / (1024.0 * 1024.0)


def _reset_cold_state():
    gc.collect()
    try:
        revhash.codec._cache_clear()
    except Exception:
        pass


@pytest.mark.skipif(
    not revhash.get_available_codecs().get("zstd", False),
    reason="perf gate requires zstandard",
)
def test_compress_cold_gate_200mbps():
    timings = []
    for _ in range(WARMUP_RUNS + MEASURED_RUNS):
        data = bytes(bytearray(_make_base(SIZE_BYTES)))  # NEW object each run (real copy)
        _reset_cold_state()
        t0 = time.perf_counter()
        blob = revhash.compress(data, codec="zstd")
        t1 = time.perf_counter()
        timings.append(_mb() / (t1 - t0))
        assert len(blob) > 0
    median = statistics.median(timings[WARMUP_RUNS:])
    assert median > GATE_MB_S, "cold compress %.1f MB/s below hard gate %.1f MB/s" % (median, GATE_MB_S)


@pytest.mark.skipif(
    not revhash.get_available_codecs().get("zstd", False),
    reason="perf gate requires zstandard",
)
def test_decompress_cold_gate_200mbps():
    data = bytes(bytearray(_make_base(SIZE_BYTES)))
    blob = revhash.compress(data, codec="zstd")
    expected_sha = hashlib.sha256(data).hexdigest()
    timings = []
    for _ in range(WARMUP_RUNS + MEASURED_RUNS):
        _reset_cold_state()
        t0 = time.perf_counter()
        out = revhash.decompress(blob)  # output buffer freshly allocated inside every call
        t1 = time.perf_counter()
        assert hashlib.sha256(out).hexdigest() == expected_sha
        timings.append(_mb() / (t1 - t0))
    median = statistics.median(timings[WARMUP_RUNS:])
    assert median > GATE_MB_S, "cold decompress %.1f MB/s below hard gate %.1f MB/s" % (median, GATE_MB_S)

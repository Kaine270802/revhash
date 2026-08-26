#!/usr/bin/env python3
"""Official COLD benchmark for revhash v0.5+ (protocol: docs/research_v05.md §Phần 3).

Anti-warm-cache rules enforced here:
- fresh data object every run via bytes(bytearray(...)) (no object reuse)
- gc.collect() before each run
- first run discarded (allocator warm-up)
- median of 5 runs, raw runs recorded

Usage:
    python benchmarks/bench_cold.py            # 10MB text_repeat, zstd
    python benchmarks/bench_cold.py --size 1   # 1MB
"""
from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import revhash  # noqa: E402

_MB = 1024 * 1024
_SENT = (b"Xin chao the gioi! Hello world! revhash cold bench. " * 4096)


def _fresh_text(size_bytes: int) -> bytes:
    """Build a brand-new data object (no reuse across runs)."""
    buf = bytearray(size_bytes)
    view = memoryview(buf)
    for off in range(0, size_bytes, len(_SENT)):
        end = min(off + len(_SENT), size_bytes)
        view[off:end] = _SENT[: end - off]
    return bytes(view)


def _cold_median(func, size_bytes: int, runs: int = 5):
    raw: list[float] = []
    for i in range(runs + 1):  # +1 warm-up run, discarded
        data = _fresh_text(size_bytes)
        gc.collect()
        t0 = time.perf_counter()
        func(data)
        dt = time.perf_counter() - t0
        if i > 0:
            raw.append(dt)
    mbs = [size_bytes / _MB / d for d in raw]
    return {"runs_s": [round(d, 5) for d in raw],
            "mbs": [round(v, 1) for v in mbs],
            "median_mbs": round(statistics.median(mbs), 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=10, help="payload MB")
    args = ap.parse_args()
    size = args.size * _MB

    comp = _cold_median(lambda d: revhash.compress(d), size)
    blob = revhash.compress(_fresh_text(size))
    decomp = _cold_median(lambda d: revhash.decompress(blob), size)
    ratio = len(blob) / size

    result = {
        "protocol": "cold: fresh data per run, gc.collect, skip first run, median-of-5",
        "payload_mb": args.size,
        "codec": "zstd",
        "compress": comp,
        "decompress": decomp,
        "ratio": round(ratio, 6),
    }
    out = Path(__file__).resolve().parent / "results_v05.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

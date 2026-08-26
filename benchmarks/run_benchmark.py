#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_benchmark — Verifier harness measuring revhash ratio/speed/memory multi-size (10KB/1MB/10MB)
for zstd/gzip/lzma/brotli, comparing to baseline benchmarks/results.json,
writing benchmarks/results_verifier.json and printing table.

Uses time.perf_counter + tracemalloc / psutil if available.
Wraps logic similar to bench_runner.py but via revhash's own API (with header).
"""
import sys
import os
import pathlib
import time
import hashlib
import json
import tracemalloc
import random
import io
import gc

# Ensure revhash importable from src
ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import revhash

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VI_SENTENCES = [
    "Xin chào thế giới, đây là dữ liệu mẫu tiếng Việt có dấu để kiểm tra nén dữ liệu. ",
    "Thư viện revhash nén dữ liệu văn bản với tỉ lệ tối ưu và giải nén khôi phục byte-identical. ",
    "Công nghệ nén lossless giúp tiết kiệm dung lượng lưu trữ và băng thông mạng đáng kể. ",
    "Dữ liệu lặp lại nhiều lần sẽ cho ratio nén rất cao nhờ dictionary và LZ77 sliding window. ",
    "Streaming chunk 1-4MB giúp xử lý file lớn hơn RAM với memory O(1) bounded. ",
]
EN_SENTENCES = [
    "The quick brown fox jumps over the lazy dog. ",
    "Reversible compression ensures 100% byte-identical reconstruction via checksums. ",
    "Chunked streaming enables O(1) memory processing for files larger than RAM. ",
    "Dictionary training improves ratio on small chunks significantly. ",
]

def gen_text_repeat(size_bytes: int) -> bytes:
    pool = ("".join(VI_SENTENCES + EN_SENTENCES)).encode("utf-8")
    repeats = size_bytes // len(pool) + 1
    return (pool * repeats)[:size_bytes]

def gen_text_realistic(size_bytes: int, seed=42) -> bytes:
    rnd = random.Random(seed)
    vocab = list("".join(VI_SENTENCES + EN_SENTENCES).split())
    out = bytearray()
    while len(out) < size_bytes:
        if rnd.random() < 0.7:
            s = rnd.choice(VI_SENTENCES + EN_SENTENCES)
            out.extend(s.encode("utf-8"))
        else:
            n = rnd.randint(5, 15)
            words = [rnd.choice(vocab) for _ in range(n)]
            out.extend((" ".join(words) + ". ").encode("utf-8"))
    return bytes(out[:size_bytes])

def gen_random_bytes(size_bytes: int, seed=123) -> bytes:
    rnd = random.Random(seed)
    return bytes(rnd.getrandbits(8) for _ in range(size_bytes))

CODEC_LEVELS = {
    "store": (0),
    "gzip": (6),
    "zstd": (3),
    "lzma": (6),
    "brotli": (6),
}
CODECS = ["store", "gzip", "zstd", "lzma", "brotli"]

SIZES = [
    ("10KB", 10*1024),
    ("1MB", 1*1024*1024),
    ("10MB", 10*1024*1024),
]

def bench_revhash(data: bytes, codec: str, level: int, chunk_size: int = 4*1024*1024, repeat: int = 1):
    # memory before
    tracemalloc.start()
    gc.collect()
    start_mem = tracemalloc.get_traced_memory()[0]

    # compress timing
    # warmup
    try:
        blob = revhash.compress(data, codec=codec, level=level, chunk_size=chunk_size)
    except Exception as e:
        tracemalloc.stop()
        return {"codec": codec, "error": str(e)}
    # measure compress
    t0 = time.perf_counter()
    for _ in range(repeat):
        blob = revhash.compress(data, codec=codec, level=level, chunk_size=chunk_size)
    t1 = time.perf_counter()
    comp_time = (t1 - t0) / repeat

    # peak after compress
    cur1, peak1 = tracemalloc.get_traced_memory()

    # decompress timing
    t0 = time.perf_counter()
    for _ in range(repeat):
        out = revhash.decompress(blob)
    t1 = time.perf_counter()
    decomp_time = (t1 - t0) / repeat
    # verify
    ok = (out == data)
    sha_match = hashlib.sha256(out).hexdigest() == hashlib.sha256(data).hexdigest() if ok else False

    cur2, peak2 = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # psutil rss if available
    rss_peak = None
    if HAS_PSUTIL:
        try:
            rss_peak = psutil.Process(os.getpid()).memory_info().rss / (1024*1024)
        except Exception:
            pass

    orig = len(data)
    comp = len(blob)
    ratio = comp / orig if orig else 0
    mb = orig / (1024*1024) if orig else 0
    comp_speed = mb / comp_time if comp_time > 1e-9 else 0
    decomp_speed = mb / decomp_time if decomp_time > 1e-9 else 0

    # header info
    try:
        info = revhash.get_info(blob)
        chunks = info.get("chunks", 0)
    except Exception:
        chunks = 0

    return {
        "codec": codec,
        "level": level,
        "chunk_size": chunk_size,
        "orig_bytes": orig,
        "comp_bytes": comp,
        "ratio": round(ratio, 6),
        "saved_pct": round((1-ratio)*100, 2) if orig else 0,
        "comp_time_s": round(comp_time, 6),
        "decomp_time_s": round(decomp_time, 6),
        "comp_MBps": round(comp_speed, 2),
        "decomp_MBps": round(decomp_speed, 2),
        "ok": ok,
        "sha_match": sha_match,
        "chunks": chunks,
        "peak_mem_MB_tracemalloc": round(peak2 / (1024*1024), 2) if peak2 else None,
        "rss_MB": round(rss_peak, 2) if rss_peak else None,
    }

def load_baseline():
    baseline_path = ROOT / "benchmarks" / "results.json"
    if not baseline_path.exists():
        print(f"[warn] baseline not found: {baseline_path}", file=sys.stderr)
        return {}
    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"[warn] failed to load baseline: {e}", file=sys.stderr)
        return {}

def compare_to_baseline(results_verifier, baseline):
    comparisons = []
    for label, entries in results_verifier.items():
        # Determine dataset type: repeat vs realistic
        is_realistic = "realistic" in label
        search_token = "text_realistic" if is_realistic else "text_repeat"
        for entry in entries:
            codec = entry.get("codec")
            lvl = entry.get("level")
            baseline_codec_key = f"{codec}-{lvl}" if codec != "store" else "store"
            if baseline_codec_key == "store":
                continue  # baseline has no store entry
            matched_ratio = None
            matched_key = None
            for bkey, blist in baseline.items():
                if label.split("__")[0] in bkey and search_token in bkey:
                    for bentry in blist:
                        if bentry.get("codec") == baseline_codec_key:
                            matched_ratio = bentry.get("ratio")
                            matched_key = bkey
                            break
                    if matched_ratio is not None:
                        break
            if matched_ratio is not None:
                verifier_ratio = entry.get("ratio")
                diff_pct = ((verifier_ratio - matched_ratio) / matched_ratio * 100) if matched_ratio else 0
                comparisons.append({
                    "label": label,
                    "codec": baseline_codec_key,
                    "verifier_ratio": verifier_ratio,
                    "baseline_ratio": matched_ratio,
                    "baseline_key": matched_key,
                    "diff_pct": round(diff_pct, 2),
                    "better_than_baseline": verifier_ratio < matched_ratio,
                })
    return comparisons

def main():
    print("=== revhash Verifier Benchmark ===")
    print(f"Python {sys.version.split()[0]}, revhash {revhash.__version__}")
    try:
        import zstandard, brotli, sys as _sys
        print(f"zstandard {zstandard.__version__}, brotli {brotli.__version__ if hasattr(brotli,'__version__') else 'unknown'}, psutil {HAS_PSUTIL}")
    except Exception as e:
        print(f"optional deps missing: {e}")

    baseline = load_baseline()
    all_results = {}
    all_comparisons = []
    # Also test raw vs verifier header overhead note

    for size_label, size_bytes in SIZES:
        print(f"\n--- {size_label} ({size_bytes} bytes) text_repeat ---")
        data = gen_text_repeat(size_bytes)
        sha = hashlib.sha256(data).hexdigest()[:12]
        print(f"  sha={sha} len={len(data)}")
        results = []
        # repeat counts to smooth timing: 10KB repeat 10, 1MB repeat 3, 10MB repeat 1
        repeat = 10 if size_bytes <= 10*1024 else (3 if size_bytes <= 1*1024*1024 else 1)
        for codec in CODECS:
            level = CODEC_LEVELS[codec]
            # skip brotli if not installed
            if codec == "brotli":
                try:
                    import brotli  # noqa
                except ImportError:
                    print(f"  {codec:8s} SKIP (brotli not installed)")
                    continue
            if codec == "zstd":
                try:
                    import zstandard  # noqa
                except ImportError:
                    print(f"  {codec:8s} SKIP (zstd not installed)")
                    continue
            chunk = 1*1024*1024 if size_bytes < 10*1024*1024 else 4*1024*1024
            r = bench_revhash(data, codec, level, chunk_size=chunk, repeat=repeat)
            if "error" in r:
                print(f"  {codec:8s} ERROR {r['error']}")
            else:
                print(f"  {codec:8s} L{level}: ratio={r['ratio']:.6f} ({r['comp_bytes']}B) saved={r['saved_pct']:.1f}% comp {r['comp_MBps']:.1f} MB/s decomp {r['decomp_MBps']:.1f} MB/s ok={r['ok']} sha={r['sha_match']} chunks={r['chunks']} peak {r['peak_mem_MB_tracemalloc']}MB rss {r['rss_MB']}MB")
            results.append(r)
        key = f"{size_label}__text_repeat"
        all_results[key] = results

        # Also test realistic dataset for ratio vs baseline comparison (optional extra)
        # Do only for 1MB and 10MB to save time
        if size_bytes >= 1*1024*1024:
            data_real = gen_text_realistic(size_bytes)
            print(f"  [realistic] len={len(data_real)}")
            for codec in ["zstd", "gzip"]:
                level = CODEC_LEVELS[codec]
                r = bench_revhash(data_real, codec, level, chunk_size=chunk, repeat=repeat)
                if "error" not in r:
                    print(f"  {codec:8s} realistic ratio={r['ratio']:.6f} comp {r['comp_MBps']:.1f} MB/s")
                # store under separate key
                if f"{size_label}__text_realistic" not in all_results:
                    all_results[f"{size_label}__text_realistic"] = []
                all_results[f"{size_label}__text_realistic"].append(r)

    # Load comparisons
    comparisons = compare_to_baseline(all_results, baseline)
    if comparisons:
        print("\n=== Comparison to baseline (results.json) ===")
        print("| Label | Codec | Verifier ratio | Baseline ratio | Diff % | Verifier better? |")
        print("|-------|-------|----------------|----------------|--------|------------------|")
        for c in comparisons:
            print(f"| {c['label']} | {c['codec']} | {c['verifier_ratio']:.5f} | {c['baseline_ratio']:.5f} | {c['diff_pct']:+.1f}% | {'YES' if c['better_than_baseline'] else 'NO'} |")
        # Overall gzip vs zstd improvement check: on text_repeat 10MB, baseline zstd 0.00015 vs gzip 0.00491 => 32x better (96% saving)
        # For verifier, check same
        print("\n--- Gzip vs Zstd improvement on text_repeat ---")
        for size_label, _ in SIZES:
            key = f"{size_label}__text_repeat"
            entries = {e["codec"]: e for e in all_results.get(key, [])}
            if "zstd" in entries and "gzip" in entries:
                gz = entries["gzip"]["ratio"]
                zs = entries["zstd"]["ratio"]
                if gz and zs:
                    improve = (1 - zs/gz)*100
                    factor = gz/zs if zs else 0
                    print(f"  {size_label}: gzip {gz:.5f} vs zstd {zs:.5f} => zstd better {improve:.1f}% ({factor:.1f}x), threshold >=15%: {'PASS' if improve>=15 else 'FAIL'}")
    else:
        print("\n(no baseline comparisons generated)")

    # Add extra metadata
    output = {
        "meta": {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "python": sys.version.split()[0],
            "revhash_version": revhash.__version__,
            "has_psutil": HAS_PSUTIL,
            "baseline_path": str(ROOT / "benchmarks" / "results.json"),
        },
        "results": all_results,
        "comparisons": comparisons,
    }
    out_path = ROOT / "benchmarks" / "results_verifier.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved verifier results to {out_path}")

    # Also print summary table for reports
    print("\n=== Summary Table (size, codec, ratio, speed, chunks) ===")
    print("| Size | Codec | Ratio | Saved% | Comp MB/s | Decomp MB/s | Chunks | SHA | Peak MB |")
    print("|------|-------|-------|--------|-----------|-------------|--------|-----|---------|")
    for key, entries in all_results.items():
        for e in entries:
            if "error" in e:
                continue
            print(f"| {key} | {e['codec']}-{e['level']} | {e['ratio']:.6f} | {e['saved_pct']:.1f}% | {e['comp_MBps']:.1f} | {e['decomp_MBps']:.1f} | {e['chunks']} | {e['sha_match']} | {e['peak_mem_MB_tracemalloc']} |")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())

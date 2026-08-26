#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark runner cho revhash — đo ratio/speed/memory thực tế
trên multi-size synthetic data (10KB, 1MB, 10MB, 100MB) và
so sánh whole-file vs chunked streaming.
"""
import gzip, bz2, lzma, brotli, zstandard as zstd
import time, hashlib, os, json, sys, tracemalloc, io, random, pathlib

# --- Data generators -------------------------------------------------
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
    "Dictionary training improves ratio on small repetitive text blocks significantly. ",
]

def gen_text_repeat(size_bytes: int) -> bytes:
    """Văn bản lặp cao (best-case cho LZ/dictionary)."""
    pool = ("".join(VI_SENTENCES + EN_SENTENCES)).encode("utf-8")
    # repeat pool
    repeats = size_bytes // len(pool) + 1
    data = (pool * repeats)[:size_bytes]
    return data

def gen_text_realistic(size_bytes: int, seed=42) -> bytes:
    """Văn bản realistic hơn: 70% lặp + 30% ngẫu nhiên từ vựng."""
    rnd = random.Random(seed)
    vocab = list("".join(VI_SENTENCES + EN_SENTENCES).split())
    out = bytearray()
    while len(out) < size_bytes:
        if rnd.random() < 0.7:
            s = rnd.choice(VI_SENTENCES + EN_SENTENCES)
            out.extend(s.encode("utf-8"))
        else:
            # random sentence từ vocab shuffle
            n = rnd.randint(5, 15)
            words = [rnd.choice(vocab) for _ in range(n)]
            out.extend((" ".join(words) + ". ").encode("utf-8"))
    return bytes(out[:size_bytes])

def gen_random_bytes(size_bytes: int, seed=123) -> bytes:
    """Dữ liệu ngẫu nhiên (worst-case, không nén được)."""
    rnd = random.Random(seed)
    return bytes(rnd.getrandbits(8) for _ in range(size_bytes))

def gen_mixed(size_bytes: int, seed=99) -> bytes:
    """50% text lặp + 50% binary random — mô phỏng file hỗn hợp."""
    half = size_bytes // 2
    return gen_text_repeat(half) + gen_random_bytes(size_bytes - half, seed=seed)

# --- Compressors -----------------------------------------------------
def comp_gzip(data: bytes, level=6) -> bytes:
    return gzip.compress(data, compresslevel=level)

def decomp_gzip(blob: bytes) -> bytes:
    return gzip.decompress(blob)

def comp_bz2(data: bytes, level=9) -> bytes:
    return bz2.compress(data, compresslevel=level)

def decomp_bz2(blob: bytes) -> bytes:
    return bz2.decompress(blob)

def comp_lzma(data: bytes, preset=6) -> bytes:
    return lzma.compress(data, preset=preset)

def decomp_lzma(blob: bytes) -> bytes:
    return lzma.decompress(blob)

def comp_zstd(data: bytes, level=3) -> bytes:
    cctx = zstd.ZstdCompressor(level=level)
    return cctx.compress(data)

def decomp_zstd(blob: bytes) -> bytes:
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(blob)

def comp_brotli(data: bytes, quality=6) -> bytes:
    return brotli.compress(data, quality=quality)

def decomp_brotli(blob: bytes) -> bytes:
    return brotli.decompress(blob)

CODECS = [
    ("gzip-6",      lambda d: comp_gzip(d, 6),       decomp_gzip),
    ("gzip-9",      lambda d: comp_gzip(d, 9),       decomp_gzip),
    ("bz2-9",       lambda d: comp_bz2(d, 9),        decomp_bz2),
    ("lzma-6",      lambda d: comp_lzma(d, 6),       decomp_lzma),
    ("zstd-3",      lambda d: comp_zstd(d, 3),       decomp_zstd),
    ("zstd-9",      lambda d: comp_zstd(d, 9),       decomp_zstd),
    ("zstd-19",     lambda d: comp_zstd(d, 19),      decomp_zstd),
    ("brotli-6",    lambda d: comp_brotli(d, 6),     decomp_brotli),
    ("brotli-11",   lambda d: comp_brotli(d, 11),    decomp_brotli),
]

# --- Benchmark helpers -----------------------------------------------
def bench_one(name, comp_fn, decomp_fn, data: bytes, repeat=1):
    # warmup
    try:
        blob = comp_fn(data)
    except Exception as e:
        return {"codec": name, "error": str(e)}
    # measure compress
    t0 = time.perf_counter()
    for _ in range(repeat):
        blob = comp_fn(data)
    t1 = time.perf_counter()
    comp_time = (t1 - t0) / repeat
    # measure decompress
    t0 = time.perf_counter()
    for _ in range(repeat):
        out = decomp_fn(blob)
    t1 = time.perf_counter()
    decomp_time = (t1 - t0) / repeat
    # verify
    ok = (out == data)
    orig = len(data)
    comp = len(blob)
    ratio = comp / orig if orig else 0
    saved = (1 - ratio) * 100 if orig else 0
    # speeds MB/s
    mb = orig / (1024*1024)
    comp_speed = mb / comp_time if comp_time > 1e-9 else 0
    decomp_speed = mb / decomp_time if decomp_time > 1e-9 else 0
    return {
        "codec": name,
        "orig_bytes": orig,
        "comp_bytes": comp,
        "ratio": round(ratio, 5),
        "saved_pct": round(saved, 2),
        "comp_time_s": round(comp_time, 6),
        "decomp_time_s": round(decomp_time, 6),
        "comp_MBps": round(comp_speed, 2),
        "decomp_MBps": round(decomp_speed, 2),
        "ok": ok,
    }

def bench_chunked(name, comp_fn, decomp_fn, data: bytes, chunk_size: int):
    """Chunked: nén từng chunk độc lập, nối lại."""
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    t0 = time.perf_counter()
    blobs = [comp_fn(c) for c in chunks]
    t1 = time.perf_counter()
    comp_time = t1 - t0
    total_comp = sum(len(b) for b in blobs)
    # decompress & verify
    t0 = time.perf_counter()
    outs = [decomp_fn(b) for b in blobs]
    t1 = time.perf_counter()
    decomp_time = t1 - t0
    reconstructed = b"".join(outs)
    ok = (reconstructed == data)
    orig = len(data)
    ratio = total_comp / orig if orig else 0
    return {
        "codec": name,
        "chunk_size": chunk_size,
        "num_chunks": len(chunks),
        "orig_bytes": orig,
        "comp_bytes": total_comp,
        "ratio": round(ratio, 5),
        "saved_pct": round((1-ratio)*100, 2) if orig else 0,
        "comp_time_s": round(comp_time, 6),
        "decomp_time_s": round(decomp_time, 6),
        "ok": ok,
    }

def format_table(results):
    # simple markdown table rows
    lines = []
    lines.append("| Codec | Ratio (comp/orig) | Saved % | Comp MB/s | Decomp MB/s | Comp s | OK |")
    lines.append("|-------|-------------------|---------|-----------|-------------|--------|----|")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['codec']} | ERROR: {r['error']} | - | - | - | - | ❌ |")
        else:
            lines.append(f"| {r['codec']} | {r['ratio']:.4f} | {r['saved_pct']:.1f}% | {r['comp_MBps']:.1f} | {r['decomp_MBps']:.1f} | {r['comp_time_s']:.4f} | {'✅' if r['ok'] else '❌'} |")
    return "\n".join(lines)

def main():
    print("=== revhash baseline benchmark ===")
    print(f"Python {sys.version.split()[0]}, zstd {zstd.__version__}, brotli {brotli.__version__ if hasattr(brotli,'__version__') else '1.2.0'}")
    # Dataset sizes — 10KB, 1MB, 10MB, 100MB (100MB có thể skip nếu RAM/time)
    sizes = [
        ("10KB", 10*1024),
        ("1MB", 1*1024*1024),
        ("10MB", 10*1024*1024),
    ]
    # Thử 100MB nếu có thể (tuỳ time)
    include_100mb = True  # sẽ try/catch
    generators = [
        ("text_repeat (lặp cao)", gen_text_repeat),
        ("text_realistic (70% lặp)", gen_text_realistic),
        ("random (worst-case)", gen_random_bytes),
        ("mixed (50/50)", gen_mixed),
    ]
    all_results = {}
    # fix console encoding for Windows
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    # Whole-file benchmarks
    for label, size in sizes:
        for gen_label, gen_fn in generators:
            # skip mixed/random for 10MB để giảm time? vẫn làm đủ
            data = gen_fn(size)
            sha = hashlib.sha256(data).hexdigest()[:12]
            key = f"{label}__{gen_label}"
            print(f"\n--- {key} size={size} sha={sha} ---")
            results = []
            for name, cf, df in CODECS:
                # repeat logic: 10KB repeat 10x, 1MB 3x, 10MB 1x
                rp = 10 if size <= 10*1024 else (3 if size <= 1*1024*1024 else 1)
                r = bench_one(name, cf, df, data, repeat=rp)
                results.append(r)
                print(f"  {name}: ratio={r.get('ratio','ERR')} ok={r.get('ok',False)} comp={r.get('comp_MBps','-')} MB/s")
            all_results[key] = results
            # chunked comparison cho 1MB và 10MB, chỉ với text_repeat (đại diện)
            if gen_label == "text_repeat (lặp cao)" and size >= 1*1024*1024:
                for cs in [1*1024*1024, 4*1024*1024]:
                    if cs >= size:
                        continue
                    print(f"  >> Chunked {cs//1024}KB:")
                    chunk_results = []
                    for name, cf, df in CODECS:
                        cr = bench_chunked(name, cf, df, data, chunk_size=cs)
                        chunk_results.append(cr)
                        print(f"     {name} chunk={cs//1024}KB ratio={cr['ratio']} vs whole {[x['ratio'] for x in results if x['codec']==name][0]:.4f}")
                    all_results[key + f"__chunked_{cs//1024}KB"] = chunk_results

    # 100MB synthetic (chỉ text_repeat, 3 codecs chính để tiết kiệm time)
    if include_100mb:
        try:
            size = 100*1024*1024
            print(f"\n--- 100MB__text_repeat size={size} ---")
            data100 = gen_text_repeat(size)
            sha = hashlib.sha256(data100).hexdigest()[:12]
            print(f"  sha={sha}")
            subset = [c for c in CODECS if c[0] in ("gzip-6","zstd-3","zstd-19","lzma-6","brotli-6")]
            results100 = []
            for name, cf, df in subset:
                r = bench_one(name, cf, df, data100, repeat=1)
                results100.append(r)
                print(f"  {name}: ratio={r.get('ratio')} comp_MBps={r.get('comp_MBps')} ok={r.get('ok')}")
            all_results["100MB__text_repeat (lặp cao)"] = results100
            # chunked 4MB cho 100MB
            print("  >> Chunked 1MB & 4MB cho 100MB:")
            for cs in [1*1024*1024, 4*1024*1024]:
                chunk_results = []
                for name, cf, df in subset:
                    cr = bench_chunked(name, cf, df, data100, chunk_size=cs)
                    chunk_results.append(cr)
                    whole_ratio = [x['ratio'] for x in results100 if x['codec']==name][0]
                    overhead = (cr['ratio'] - whole_ratio) / whole_ratio * 100 if whole_ratio else 0
                    print(f"     {name} chunk={cs//(1024*1024)}MB ratio={cr['ratio']} overhead={overhead:.1f}%")
                all_results[f"100MB__text_repeat__chunked_{cs//(1024*1024)}MB"] = chunk_results
        except Exception as e:
            print(f"100MB benchmark failed: {e}")
            import traceback; traceback.print_exc()

    # Save JSON
    out_path = pathlib.Path(r"D:\data optimization\benchmarks\results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved JSON to {out_path}")

    # Print summary for 10KB text_repeat as quick check
    key = "10KB__text_repeat (lặp cao)"
    if key in all_results:
        print("\n=== Summary 10KB text_repeat ===")
        print(format_table(all_results[key]))

if __name__ == "__main__":
    main()

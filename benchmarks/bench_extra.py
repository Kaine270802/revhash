#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extra benchmarks: streaming API vs chunked independent, dictionary, memory"""
import zstandard as zstd, gzip, lzma, brotli, bz2, io, time, hashlib, json, sys, random

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except: pass

VI = "Xin chao the gioi, du lieu mau tieng Viet lap lai. Thu vien revhash nen toi uu. Streaming chunk 1-4MB. "
EN = "The quick brown fox jumps. Reversible compression O(1) memory. "

def gen_repeat(n): 
    pool = (VI+EN).encode()
    return (pool * (n//len(pool)+1))[:n]

def bench_streaming_vs_chunked():
    print("=== Streaming API vs Chunked Independent (Zstd) ===")
    size = 20*1024*1024
    data = gen_repeat(size)
    print(f"Data {size/1024/1024:.0f}MB sha {hashlib.sha256(data).hexdigest()[:8]}")
    # whole-file
    cctx = zstd.ZstdCompressor(level=3)
    t0=time.perf_counter()
    blob_whole = cctx.compress(data)
    t1=time.perf_counter()
    print(f"Whole-file zstd-3: {len(blob_whole)} bytes ratio {len(blob_whole)/size:.5f} time {t1-t0:.3f}s")
    # chunked independent 1MB
    chunk=1*1024*1024
    chunks=[data[i:i+chunk] for i in range(0,size,chunk)]
    t0=time.perf_counter()
    blobs=[zstd.ZstdCompressor(level=3).compress(c) for c in chunks]
    t1=time.perf_counter()
    total=sum(len(b) for b in blobs)
    print(f"Chunked 1MB independent: {total} bytes ratio {total/size:.5f} overhead {(total-len(blob_whole))/len(blob_whole)*100:.1f}% time {t1-t0:.3f}s")
    # chunked streaming via Zstd streaming writer (single frame, preserves window)
    # Use stream_writer with read/write
    t0=time.perf_counter()
    out=io.BytesIO()
    cctx2=zstd.ZstdCompressor(level=3)
    with cctx2.stream_writer(out, closefd=False) as w:
        for c in chunks:
            w.write(c)
    blob_stream=out.getvalue()
    t1=time.perf_counter()
    print(f"Streaming single-frame (windowed): {len(blob_stream)} bytes ratio {len(blob_stream)/size:.5f} vs whole {(len(blob_stream)-len(blob_whole))/len(blob_whole)*100:+.1f}% vs chunked {(len(blob_stream)-total)/total*100:+.1f}% time {t1-t0:.3f}s")
    # verify
    dctx=zstd.ZstdDecompressor()
    dec=dctx.stream_reader(io.BytesIO(blob_stream)).read()
    print(f"  verify streaming decode: {dec==data} len {len(dec)}")
    # 4MB
    chunk=4*1024*1024
    chunks=[data[i:i+chunk] for i in range(0,size,chunk)]
    blobs=[zstd.ZstdCompressor(level=3).compress(c) for c in chunks]
    total4=sum(len(b) for b in blobs)
    print(f"Chunked 4MB independent: {total4} bytes ratio {total4/size:.5f} overhead {(total4-len(blob_whole))/len(blob_whole)*100:.1f}%")
    out2=io.BytesIO()
    with zstd.ZstdCompressor(level=3).stream_writer(out2, closefd=False) as w:
        for c in chunks:
            w.write(c)
    blob_stream4=out2.getvalue()
    print(f"Streaming 4MB windowed: {len(blob_stream4)} bytes ratio {len(blob_stream4)/size:.5f}")

def bench_dict():
    print("\n=== Dictionary training (zstd) ===")
    # train dict on 100 samples of 10KB text_repeat variant
    samples=[]
    base=(VI+EN).encode()
    for i in range(100):
        # vary slightly
        s=base * 20 + f" id={i} ".encode()*10
        samples.append(s[:10*1024])
    try:
        d=zstd.train_dictionary(112*1024, samples)  # 112KB dict
        print(f"Dict trained: {len(d.as_bytes())} bytes dict_id {d.dict_id()}")
        # test on new data 10KB
        test=gen_repeat(10*1024)
        c_no=zstd.ZstdCompressor(level=3).compress(test)
        c_dict=zstd.ZstdCompressor(level=3, dict_data=d).compress(test)
        print(f"10KB without dict: {len(c_no)} ratio {len(c_no)/len(test):.4f}")
        print(f"10KB with dict:    {len(c_dict)} ratio {len(c_dict)/len(test):.4f} saved {(1-len(c_dict)/len(c_no))*100:.1f}% vs no-dict")
        # 1MB
        test1=gen_repeat(1*1024*1024)
        c_no1=zstd.ZstdCompressor(level=3).compress(test1)
        c_dict1=zstd.ZstdCompressor(level=3, dict_data=d).compress(test1)
        print(f"1MB without dict: {len(c_no1)} ratio {len(c_no1)/len(test1):.5f}")
        print(f"1MB with dict:    {len(c_dict1)} ratio {len(c_dict1)/len(test1):.5f} saved {(1-len(c_dict1)/len(c_no1))*100:.1f}%")
        # chunked streaming with dict
        chunk=256*1024
        chunks=[test1[i:i+chunk] for i in range(0,len(test1),chunk)]
        blobs_no=[zstd.ZstdCompressor(level=3).compress(c) for c in chunks]
        blobs_dict=[zstd.ZstdCompressor(level=3, dict_data=d).compress(c) for c in chunks]
        print(f"Chunked 256KB no-dict total {sum(len(b) for b in blobs_no)} vs dict {sum(len(b) for b in blobs_dict)} saved {(1-sum(len(b) for b in blobs_dict)/sum(len(b) for b in blobs_no))*100:.1f}%")
    except Exception as e:
        print(f"Dict training failed: {e}")
        import traceback; traceback.print_exc()

def bench_small_overhead():
    print("\n=== Small file overhead (header) ===")
    for n in [0,1,10,100,1000,10*1024]:
        data=gen_repeat(n)
        for name, fn in [("gzip-6", lambda d: gzip.compress(d,6)), ("zstd-3", lambda d: zstd.ZstdCompressor(level=3).compress(d)), ("lzma-6", lambda d: lzma.compress(d,preset=6)), ("brotli-6", lambda d: brotli.compress(d,quality=6))]:
            try:
                b=fn(data)
                print(f"  n={n:5d} {name:9s} -> {len(b):5d} bytes ratio {len(b)/n if n else 0:.2f}")
            except Exception as e:
                print(e)
        print("---")

def bench_memory():
    print("\n=== Memory profile (approx via chunked streaming) ===")
    # Simulate O(1) by measuring that chunked streaming doesn't grow with file size
    # We'll do streaming compress of 100MB in 1MB chunks via stream_writer and show memory stable
    import tracemalloc, gc
    tracemalloc.start()
    size=50*1024*1024
    data=gen_repeat(size)
    # whole-file baseline memory
    snap0=tracemalloc.get_traced_memory()
    c=zstd.ZstdCompressor(level=3).compress(data)
    snap1=tracemalloc.get_traced_memory()
    print(f"Whole-file 50MB compress: current {snap1[0]/1024/1024:.1f}MB peak {snap1[1]/1024/1024:.1f}MB (includes 50MB input)")
    del c; gc.collect()
    tracemalloc.reset_peak()
    # streaming
    out=io.BytesIO()
    with zstd.ZstdCompressor(level=3).stream_writer(out, closefd=False) as w:
        for i in range(0,size,1*1024*1024):
            w.write(data[i:i+1*1024*1024])
    blob=out.getvalue()
    snap2=tracemalloc.get_traced_memory()
    print(f"Streaming 1MB chunks 50MB: blob {len(blob)} current {snap2[0]/1024/1024:.1f}MB peak {snap2[1]/1024/1024:.1f}MB")
    print(f"  Note: streaming peak should be ~ O(chunk) not O(file)")
    tracemalloc.stop()

if __name__=="__main__":
    bench_streaming_vs_chunked()
    bench_dict()
    bench_small_overhead()
    bench_memory()

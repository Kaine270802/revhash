# revhash API Spec — Design Freeze (M2)

> **Version:** 0.3.0-awesome (Design Freeze 2026-08-25, sync v0.3 polish — không đổi logic, chỉ bump version)  
> **Owner:** Coordinator (dựa trên `docs/research.md` §6)  
> **Mục tiêu:** Freeze contract cho Core (M3a) + Optimization (M3b) song song, đảm bảo **unlimited streaming O(1)**, byte-identical.

---

## 1. Tổng quan

`revhash` là thư viện Python **lossless reversible compression** (không phải cryptographic hash) tối ưu cho **mọi kích thước** (0 B → 10 GB+).

**Core principle (từ Research):** Dùng **Zstd streaming single-frame** (`ZstdCompressor.stream_writer`) làm default để đạt **0% overhead chunk** + O(1) memory (~50 MB peak cho 50 MB input, không scale theo file size). Fallback sang `gzip`/`store`/`lzma`/`brotli` khi cần.

---

## 2. Public API (frozen)

### 2.1 In-memory bytes

```python
import revhash

# Nén bytes → bytes (tự chọn codec/level, mặc định zstd-3)
blob: bytes = revhash.compress(data: bytes,
                               codec: str = "zstd",   # "zstd"|"gzip"|"lzma"|"brotli"|"store"|"auto"
                               level: int = 3,        # 1..22 cho zstd, 1..9 cho gzip, 0..11 brotli
                               chunk_size: int = 4*1024*1024,
                               dict_data: bytes | None = None) -> bytes

# Giải nén — tự detect codec từ header
orig: bytes = revhash.decompress(blob: bytes,
                                 dict_data: bytes | None = None) -> bytes
# Nếu blob được encode với dict embedded, dict_data không cần truyền (đọc từ header)
# Nếu dùng external dict, phải truyền đúng dict_data

# Helpers checksum
assert revhash.verify(blob)  # kiểm tra per-chunk CRC32 + global SHA256
info: dict = revhash.get_info(blob)  # {codec, level, chunk_size, original_size, compressed_size, ratio, has_dict, chunks}
```

**Contract:**
- `compress(b"")` → valid blob (header + empty stream + SHA256 của rỗng).
- Nếu `len(blob) > len(data) + header_overhead` và `codec != "store"` thì **auto store** (lưu raw + flag `codec=store`) để tránh phình trên random/small.
- `decompress(compress(data)) == data` byte-identical cho mọi `data` và mọi `chunk_size`.

### 2.2 File streaming (UNLIMITED — không load toàn bộ)

```python
# File → File (streaming O(1), chunk loop)
revhash.compress_file(src_path: str | Path,
                      dst_path: str | Path,
                      codec="zstd", level=3,
                      chunk_size=4*1024*1024,
                      dict_data: bytes | None = None,
                      show_progress: bool = False) -> dict  # trả về info

revhash.decompress_file(src_path: str | Path,
                        dst_path: str | Path,
                        dict_data: bytes | None = None,
                        show_progress: bool = False) -> dict

# Stream generic (pipe/socket/BytesIO)
revhash.compress_stream(reader: BinaryIO, writer: BinaryIO,
                        codec="zstd", level=3,
                        chunk_size=4*1024*1024,
                        dict_data: bytes | None = None) -> dict

revhash.decompress_stream(reader: BinaryIO, writer: BinaryIO,
                          dict_data: bytes | None = None) -> dict
```

**Contract O(1):**
- Không bao giờ `reader.read()` toàn bộ; luôn `read(chunk_size)` loop.
- Peak memory < `chunk_size + window(8 MB) + 10 MB` ≈ <150 MB dù input 10 GB.
- Per-chunk CRC32 + global SHA256 được ghi vào footer để verify.

### 2.3 Dictionary

```python
import revhash.dict_builder as dict_builder

# Train dict từ corpus (100-1000 samples, mỗi 8-16KB)
dict_data: bytes = dict_builder.train(samples: list[bytes],
                                      dict_size: int = 112*1024) -> bytes

# Train từ files
dict_data = dict_builder.train_from_files(file_paths: list[str],
                                          dict_size=112*1024,
                                          sample_size=16*1024)

# Lưu / load
dict_builder.save(dict_data, "dicts/vi_text.dict")
dict_data = dict_builder.load("dicts/vi_text.dict")

# Auto: nếu file <64KB, khuyến nghị dùng dict (nếu có) để giảm 80% (theo research §5.4)
```

### 2.4 CLI

```bash
# Nén / giải nén file
python -m revhash compress input.txt output.rvh --codec zstd --level 3 --chunk-size 4M
python -m revhash decompress output.rvh restored.txt
python -m revhash compress big.log big.rvh --dict dicts/vi_text.dict

# Info & verify
python -m revhash info big.rvh
python -m revhash verify big.rvh

# Train dict
python -m revhash train-dict corpus/*.txt --out dicts/vi_text.dict --size 112K

# Benchmark (cho Verifier)
python -m revhash benchmark --size 100M --codec all
```

---

## 3. Binary Format (frozen cho M3a)

### 3.1 Header

```
Offset  Size  Field           Type        Mô tả
0       4     magic           bytes       b"RVH1"  (0x52 0x56 0x48 0x01)
4       1     version         uint8       0x01
5       1     codec_id        uint8       0=store, 1=gzip, 2=zstd, 3=lzma, 4=brotli
6       1     level           uint8       level của codec
7       4     chunk_size      uint32 LE   1M/4M/8M
11      4     dict_len        uint32 LE   len(dict_data), 0 nếu không có
15      8     original_size   uint64 LE   len(data) gốc (0 cho stream không biết trước → để 0xFFFFFFFFFFFFFFFF)
23      N     dict_data       bytes       N = dict_len, nếu có
23+N    ...   compressed_stream bytes     single-frame zstd stream hoặc chunked frames (tùy codec)
...     4*Nc  per_chunk_crc   uint32 LE[] CRC32 cho mỗi chunk (Nc = ceil(original_size/chunk_size), 0 nếu original_size unknown → bỏ qua)
...     32    global_sha256   bytes       SHA256 của original data
...     4     footer_magic    bytes       b"RVHE" (end marker, optional cho stream)
```

**Tổng overhead:** header 23B + dict (nếu có) + footer `4*Nc + 32 + 4`B. Với 100MB / 4MB chunks → Nc=25 → footer 136B.

### 3.2 Codec dispatch

| codec_id | Tên    | Python backend          | Streaming API |
|----------|--------|-------------------------|---------------|
| 0        | store  | raw                     | copy          |
| 1        | gzip   | `gzip`/`zlib`           | `zlib.compressobj` + `decompressobj` |
| 2        | zstd   | `zstandard`             | `ZstdCompressor.stream_writer` / `ZstdDecompressor.stream_reader` |
| 3        | lzma   | `lzma`                  | `LZMACompressor` / `LZMADecompressor` |
| 4        | brotli | `brotli`                | `brotli.Compressor` / `brotli.Decompressor` |

**Default:** `codec_id=2` (zstd) level 3, chunk 4MB.

### 3.3 Stream framing

- **Zstd default:** **single-frame streaming** — một `ZstdCompressor.stream_writer(writer)` duy nhất, `write(chunk)` liên tục, `close()` ghi end-of-frame. Decoder dùng `ZstdDecompressor.stream_reader(reader)` đọc liên tục. **Không** gọi `compress()` per-chunk.
- **Fallback chunked independent (nếu cần resume per-chunk):** mỗi chunk là một frame riêng + per-chunk header `[comp_len(4B) | crc(4B) | data]` — chỉ dùng khi `mode="chunked"`.
- Per-chunk CRC32 tính trên **original chunk** trước khi nén, verify sau khi giải nén.

---

## 4. Error Handling & Edge Cases

| Case | compress | decompress |
|------|----------|------------|
| `data == b""` | header + empty stream + SHA256(empty) | trả `b""` |
| 1 byte | header + 1B stream | OK |
| `len(data) % chunk_size != 0` | chunk cuối nhỏ hơn, vẫn CRC riêng | OK |
| Random incompressible | auto store nếu `comp > orig` | transparent |
| Corrupted blob | — | raise `RevHashCorruptedError` (CRC mismatch hoặc SHA mismatch) |
| Wrong dict | — | raise `RevHashDictError` |
| File > RAM (10GB) | `compress_file` stream loop, không load | `decompress_file` stream |

**Exceptions:**

```python
class RevHashError(Exception): ...
class RevHashCorruptedError(RevHashError): ...
class RevHashDictError(RevHashError): ...
class RevHashUnsupportedCodecError(RevHashError): ...
```

---

## 5. Performance Contract (cho Verifier)

| Metric | Target | Đo trên |
|--------|--------|---------|
| Ratio (text_repeat 10MB) | <0.001 (tốt hơn gzip 5×) | `benchmarks/results.json` đã có 0.00015 zstd-3 |
| Speed encode 100MB text_repeat | >500 MB/s (zstd-3) | research đã đo 7348 MB/s |
| Speed decode 100MB | >1000 MB/s | research 2350 MB/s |
| Memory peak streaming 50MB | <80 MB (O1) | research đã đo 51 MB |
| Multi-size correctness | 0B,1B,10KB,1MB,10MB,100MB,500MB mock SHA256 pass | Verifier harness |

---

## 6. Module Layout (frozen cho Core/Optimization)

```
src/revhash/
├── __init__.py        # public API: compress/decompress/compress_file/...
├── codec.py           # dispatch table codec_id ↔ backend, auto-store logic
├── stream.py          # compress_stream / decompress_stream (O1 loop)
├── header.py          # RevHashHeader pack/unpack, CRC/SHA, constants
├── exceptions.py      # RevHashError hierarchy
├── dict_builder.py    # train/load dict (Optimization Builder owns)
├── algorithms/
│   ├── __init__.py
│   └── selector.py    # auto codec/level selector (Optimization Builder)
└── cli.py             # python -m revhash (argparse)

tests/
├── test_codec.py
├── test_stream.py
├── test_header.py
├── test_dict.py
├── test_large.py      # multi-size 0B→500MB mock
└── test_fuzz.py

benchmarks/
├── bench_runner.py    # (đã có từ Researcher)
├── bench_extra.py     # (đã có)
└── run_benchmark.py   # Verifier harness (wrap bench_runner cho CI)

docs/
├── research.md
├── baseline_report.md
└── api.md             # this file

reports/
├── verification.md
└── critique.md
```

**Ownership:** Core owns `codec.py`, `stream.py`, `header.py`, `exceptions.py`, `__init__.py`, `cli.py`. Optimization owns `dict_builder.py`, `algorithms/selector.py`.

---

## 7. Dependencies

```toml
# pyproject.toml
dependencies = [
    "zstandard>=0.20.0",
    "brotli>=1.0.0",  # optional, fallback nếu không có thì báo lỗi khi codec=brotli
]
# stdlib: gzip, lzma, bz2, hashlib, zlib, struct, io
```

---

## 8. Handoff cho M3a/M3b

- **Core Builder (M3a):** Implement đúng API §2 + header §3 + stream §3.3, **không** thay đổi contract. Ưu tiên làm `header.py` → `codec.py` → `stream.py` → `__init__.py`. Đảm bảo `compress_file` không `read()` toàn bộ.
- **Optimization Builder (M3b):** Implement `dict_builder.py` + `algorithms/selector.py` dựa trên research §5.4/§6.5, hook `dict_data` vào `compress()`. Không sửa public API, chỉ thêm logic auto-select.
- **Verifier:** Dùng §5 làm oracle, test mọi size + fuzz + memory O(1).

---

*— Coordinator, Design Freeze 2026-08-25 — Frozen, không đổi sau khi M3a/M3b bắt đầu trừ khi lỗi critical.*

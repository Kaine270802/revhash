# revhash — Reversible Lossless Compression for Python (Unlimited, O(1) Streaming)

> **Lossless, reversible compression** — optimal ratio, 100% byte-identical decode, **unlimited size** (0 B → 10 GB+), **O(1) streaming** (1–8 MB chunks, <150 MB peak even for 10 GB).

*`revhash` means “reversible hash” — lossless compression with header/checksum, not cryptographic SHA/md5.*

> **Version:** `0.5.0` — `import revhash` — embed in one line `cp revhash_embedded.py ./myproject/` → `import revhash_embedded as revhash` (single-file bundle 111KB `<500KB`, `__bundle_hash__` synced).

![version](https://img.shields.io/badge/version-0.5.0-blue) ![tests](https://img.shields.io/badge/tests-181%20PASS-brightgreen) ![bundle](https://img.shields.io/badge/bundle-111KB-blue) ![ci](https://img.shields.io/badge/CI-GitHub_Actions_3.9%2F3.11%2F3.12-blue) ![coverage](https://img.shields.io/badge/coverage-55.68%25-yellowgreen) ![python](https://img.shields.io/badge/python-%3E%3D3.9-blue) ![github](https://img.shields.io/badge/github-Kaine270802%2Frevhash-black?logo=github)

---

## ✨ Highlights (real benchmarks)

| Metric | revhash (zstd-3 streaming) | gzip-6 | Result |
|--------|---------------------------|--------|--------|
| **Ratio 10 MB text_repeat** | **0.000151** (1.58 KB) | 0.00491 (51 KB) | **32.5× better** (96.9% saved) |
| **Ratio 100 MB text_repeat** | **0.00010** (10 KB) | 0.00485 (509 KB) | 48× |
| **Speed 10 MB encode** | **977–6478 MB/s** | 337 MB/s | 2–20× faster |
| **Chunk overhead** | **0%** streaming single-frame (20 MB 2059 B vs 2060 B whole) | +12% independent | Ratio preserved |
| **Memory 50 MB stream** | **51 MB peak** (O1) | 100 MB whole | Constant memory |
| **Dict small file 10 KB** | **30 B vs 150 B (80% saved)** | — | Embedded dict 327 B demo |
| **Tests** | **181/181 PASS** (0B→50MB + fuzz 100 + tamper 100%, file↔text flex) | — | Independent Verifier + Critic |
| **Decode 10 MB (cold)** | **657–810 MB/s** (~4–4.9× vs v0.4) | 948 MB/s | Incremental CRC, no triple-copy |
| **Header integrity (v2)** | SHA-256 MAC over full header — tamper `codec_id/level/chunk_size/original_size` **8/8 blocked** before decode | — | Dual-read: old v0.4 blobs still valid |

*Numbers from `benchmarks/results.json` (Python 3.12.10, zstd 0.25.0, brotli 1.2.0) and `benchmarks/results_filetext.json:277` (10MB zstd `0.000151` vs gzip `0.00491` = **32.5×**) and `reports/verification.md`.*

> **32.5× detail:** `benchmarks/results_filetext.json:277` 10MB `zstd 0.000151` (1580B) vs `gzip 0.00491` (51516B) → 96.9% saved (see `benchmarks/baseline_report.md`).

---

## 📦 Installation — From GitHub (Recommended, 1 Command)

> **One command and you are ready — no manual clone needed**

```bash
# 1) Install directly from GitHub (fastest, always latest on main)
pip install git+https://github.com/Kaine270802/revhash.git

# 2) Optional: install brotli for brotli-11 codec (best ratio)
pip install brotli zstandard

# 3) Verify installation
python -c "import revhash; print(revhash.__version__); print(revhash.get_available_codecs())"
# → 0.5.0  {'store': True, 'gzip': True, 'zstd': True, 'lzma': True, 'brotli': True}
```

**Other ways (for contributors who want to edit code):**

```bash
# Clone and install editable
git clone https://github.com/Kaine270802/revhash.git
cd revhash
pip install -e .          # editable install
pip install pytest psutil ruff mypy  # dev deps

# Run tests (181 tests)
pytest tests -q            # 181 passed
ruff check src/revhash
mypy src/revhash --ignore-missing-imports
pytest --cov=revhash       # coverage gate 53%
```

**Single-file embed (no pip needed — just copy):**

```bash
# Only 1 file <500KB
cp revhash_embedded.py ./myproject/
python -c "import revhash_embedded as revhash; print(revhash.compress_text('hello'))"
```

**Requirements:** Python ≥3.9, `zstandard>=0.20.0` (auto-installed via `pip install git+...`), `brotli>=1.0.0` optional, `lzma`/`gzip` are stdlib.

---

## 🚀 Quick Start

### In-memory

```python
import revhash

data = b"Hello world! " * 100_000  # ~1.2 MB repeated
blob = revhash.compress(data, codec="zstd", level=3, chunk_size=4*1024*1024)
print(f"{len(data)} -> {len(blob)} ratio={len(blob)/len(data):.5f}")  # 0.0002

orig = revhash.decompress(blob)
assert orig == data  # byte-identical
assert revhash.verify(blob)  # CRC32 per-chunk + SHA256 global

print(revhash.get_info(blob))
# {'codec': 'zstd', 'level': 3, 'chunk_size': 4194304, 'original_size': 1200000,
#  'compressed_size': 250, 'ratio': 0.0002, 'has_dict': False, 'chunks': 1, ...}
```

### Unlimited files (O(1) — never loads whole file)

```python
import revhash
from pathlib import Path
# 100 MB, 1 GB or 10 GB all use <150 MB RAM — demo with 1MB
Path("big.log").write_bytes(b"hello world\n" * 80000)
revhash.compress_file("big.log", "big.rvh", codec="zstd", level=3, chunk_size=4*1024*1024)
revhash.decompress_file("big.rvh", "restored.log")
assert open("big.log","rb").read() == open("restored.log","rb").read()

# Generic streaming (pipe/socket/BytesIO)
Path("in.bin").write_bytes(b"stream demo " * 1000)
with open("in.bin","rb") as r, open("out.rvh","wb") as w:
    revhash.compress_stream(r, w, codec="zstd")
with open("out.rvh","rb") as r, open("rest.bin","wb") as w:
    revhash.decompress_stream(r, w)
assert Path("rest.bin").read_bytes() == Path("in.bin").read_bytes()
```

### Flexible File ↔ Text (NEW v0.2.1)

```python
import revhash
from pathlib import Path

# text -> bytes (dst=None) — no filesystem touch, returns bytes
blob = revhash.compress_file("hello world 🌍", None)
assert isinstance(blob, bytes)

# bytes -> text (as_text=True) — strict utf-8 decode
text = revhash.decompress_file(blob, None, as_text=True)
assert text == "hello world 🌍"

# file -> text (sample.txt -> blob file -> str)
Path("sample.txt").write_text("file content", encoding="utf-8")
revhash.compress_file(Path("sample.txt"), "sample.rvh")
assert revhash.decompress_file("sample.rvh", None, as_text=True) == "file content"

# raw bytes S4 -> bytes
raw = b"\x00\xff raw"
assert revhash.decompress_file(revhash.compress_file(raw, None), None) == raw

# force_text: force "notes.txt" as literal text even if file exists
Path("notes.txt").write_text("file content", encoding="utf-8")
assert revhash.decompress_file(revhash.compress_file("notes.txt", None, force_text=True), None, as_text=True) == "notes.txt"
```

> **Heuristic:** `str` path exists + `is_file()` → file (S2), else → text `encode("utf-8","strict")` (S3); `bytes` → raw (S4); `Path` → file (S1). `dst=None` → RAM, `dst=Path` → file + `mkdir(parents=True)`. Guard `>100MB dst=None → ValueError` — see `src/revhash/file_text.py:104` and `docs/api_filetext.md:170`.

### Diverse file types — `compress_file` handles any file (NEW v0.3)

`compress_file` uses `open(src,"rb")` O(1) streaming, so **any file type** compresses: `.txt`, `.json`, `.csv`, `.bin`, `.log`, large 10MB+...

```python
import revhash, json, csv
from pathlib import Path

# .json file
Path("data.json").write_text(json.dumps({"hello": "world"}), encoding="utf-8")
revhash.compress_file("data.json", "data.json.rvh")
revhash.decompress_file("data.json.rvh", "restored.json")

# .csv file
with open("table.csv","w",newline="",encoding="utf-8") as f:
    csv.writer(f).writerows([[1,"name_1"],[2,"name_2"]])
revhash.compress_file("table.csv", "table.csv.rvh")

# .bin binary
Path("binary.bin").write_bytes(b"\x00\xff\xfe" * 10000)
revhash.compress_file("binary.bin", "binary.bin.rvh")

# JSON text directly (no file needed)
blob = revhash.compress_file('{"hello": "world"}', None)
assert revhash.decompress_file(blob, None, as_text=True) == '{"hello": "world"}'
```

> **Full diverse examples:** `examples/diverse_file_demo.py` — 8 detailed demos (`.txt`/`.json` file + direct text/`.csv`/`.bin`/`.log`/`force_text`/large 10MB O1 + bundle parity + dict) — run `python examples/diverse_file_demo.py` → 8/8 PASS O1.

### Dictionary for small files

```python
import revhash
from revhash import dict_builder
# Train from synthetic corpus (100 samples, each ~10KB) — no real files needed
samples = [b"Hello world! " * 600 for _ in range(100)]
dict_data = dict_builder.train(samples, dict_size=4096)
dict_builder.save(dict_data, "dicts/my.dict")

blob_with_dict = revhash.compress(b"hello " * 2000, dict_data=dict_data)
# Embedded dict: no need to pass again on decompress
orig = revhash.decompress(blob_with_dict)
assert orig == b"hello " * 2000
```

### Auto-select

```python
from revhash.algorithms import selector
selector.auto_select(data_len=10*1024)        # <10KB → zstd-3 + dict, chunk 1M
selector.auto_select(data_len=100*1024*1024)  # 100MB → zstd-3 streaming, chunk 4M
selector.choose_best_chunk(500*1024*1024)     # → 4M (10MB-1GB), >1GB → 8M
```

### Single-file embed (PRIMARY)

```bash
# 1-line embed — copy 1 file, no pip needed
cp revhash_embedded.py ./myproject/
python -c "import revhash_embedded as revhash; print(revhash.compress_text('hello'))"
# vendored folder also works
cp -r src/revhash ./myproject/vendor/
pip install -e . && python -c "import revhash; print(revhash.__version__)"
```

> **DX:** `import revhash` (pip) ↔ `import revhash_embedded as revhash` (single-file) **byte-identical** 10 cases (`tests/test_embedded.py:18`), `get_available_codecs()` fallback `zstd→gzip→store`.

---

## 💻 CLI

```bash
# Compress / decompress
python -m revhash compress input.txt output.rvh --codec zstd --level 3 --chunk-size 4M
python -m revhash decompress output.rvh restored.txt
python -m revhash compress big.log big.rvh --dict dicts/my.dict

# Info & verify (streaming for >50MB to avoid OOM)
python -m revhash info big.rvh
python -m revhash verify big.rvh

# Train dictionary
python -m revhash train-dict corpus/*.txt --out dicts/my.dict --size 112K --sample-size 16K

# Benchmark (lightweight, for CI)
python -m revhash benchmark --size 10M --codec all
python -m revhash benchmark --size 100M --codec zstd

# Full harness (Researcher)
python benchmarks/bench_runner.py        # whole-file vs chunked, 9 codecs
python benchmarks/bench_extra.py         # streaming single-frame vs dict vs memory
python benchmarks/run_benchmark.py       # Verifier harness (comparison table)
```

---

## 🧬 Binary Format (frozen `docs/api.md` §3)

```
[Header 23B] = magic b"RVH1" (4) | version 1 (1) | codec_id 0-4 (1) | level (1) | chunk_size LE (4) | dict_len LE (4) | original_size LE (8)
[dict_data N] (N=dict_len, zstd only)
[compressed_stream] — single-frame zstd `stream_writer` keeps window across chunks → 0% overhead; fallback gzip/lzma/brotli/store
[Footer] = per_chunk_crc32 LE array (Nc*4, Nc=ceil(orig/chunk)) | global_sha256 (32) | magic b"RVHE" (4)
# UNKNOWN stream (non-seekable pipe): footer only SHA+MAGIC (36B), Nc=0
```

**Overhead:** `23 + dict_len + Nc*4 +36` bytes. For 100MB/4M → Nc=25 → footer 136B. **Codec map:** `0=store`, `1=gzip`, `2=zstd` (default), `3=lzma`, `4=brotli`.

---

## 📊 Detailed Benchmark

See `benchmarks/baseline_report.md` (304 lines) and `reports/verification.md` §9.

**Whole-file 10 MB text_repeat:**

| Codec | Ratio | Comp MB/s | Decomp MB/s |
|-------|-------|-----------|-------------|
| gzip-6 | 0.00491 | 337 | 948 |
| lzma-6 | 0.00021 | 97 | 685 |
| zstd-3 | **0.00015** | **6478** | 2409 |
| brotli-6 | 0.00006 | 1318 | 875 |
| brotli-11 | 0.00004 | 88 | 895 |

**Chunked independent overhead (100 MB):** gzip +12%, lzma +433%, zstd +530%, brotli +5100% — but **streaming single-frame zstd 0%** (key to unlimited).

**Improvements:** 1MB **87.7% (8.1×)**, 10MB **96.9% (32.5×)** vs gzip.

---

## ✅ Verification (181/181 PASS)

Run `pytest tests -q` (7s, Python 3.12.10, `__version__ 0.5.0`):

- **Multi-size:** 0B,1B,100B,1KB,10KB,1MB,10MB,50MB streaming, 200MB mock 1GB, 20MB file — all SHA256 byte-identical.
- **O1 memory:** 10MB peak 20MB, 50MB peak 51MB — all `<150MB`.
- **Tamper:** 100/100 fuzz single-byte flip → `verify False` + `RevHashCorruptedError`; header v2 field tamper (`codec_id/level/chunk_size/original_size/footer-MAC`) **24/24 blocked** (`tests/test_header_mac.py`).
- **Fuzz:** 100 random blobs (codecs/chunks random) → 100/100 roundtrip + tamper.
- **Dict:** 10KB raw 79% saved, 100KB 91% — matches research.
- **CLI:** compress/info/verify/decompress/train-dict/benchmark all work.

See `reports/verification.md`, `reports/verification_filetext.md` + `reports/verification_v05.md` (181/181). Cold benchmark: `python benchmarks/bench_cold.py` → `benchmarks/results_v05.json`.

---

## 🔍 Audit & Limitations (v0.5.0)

**Critic found 7 risks, 5 fixed:**

| # | Risk | Status |
|---|------|--------|
| 1 | Header `chunk_size`/`level` not MAC → tamper same Nc still `verify True` | **FIXED v0.5** — header v2 `header_sha256` MAC, verified before decode |
| 2 | `decompress_stream` non-seekable `read()` → OOM 10GB pipe | Fixed `SpooledTemporaryFile` + guard >100MB |
| 7 | `chunk_size`/`dict_len` unlimited → OOM injection | Fixed limit [1K,64M] + 256KB |

**Limitations (documented for v0.5):** MAC is unkeyed digest (integrity not authenticity — HMAC planned v0.6), non-seekable pipe ≤100MB, `dst=None` OOM guard `>100MB → ValueError` (`file_text.py:104`), small file header overhead 59B (+32B footer v2), decode ≥800 MB/s gate borderline (657–810 measured).

---

## 📚 Docs & Roadmap

- `docs/research.md` — 8 algorithms, streaming vs chunked
- `docs/api.md` — frozen API + streaming contract
- `benchmarks/baseline_report.md` — baseline 10KB→100MB
- `examples/diverse_file_demo.py` — 8 diverse file demos (**NEW**)
- `CHANGELOG.md` — v0.1 → v0.5
- `.github/workflows/ci.yml` — CI matrix Python 3.9/3.11/3.12 (pytest+cov, ruff, mypy, bundle check)
- `docs/api_v05.md` — v0.5 design freeze (header v2 spec)
- Roadmap: v0.1 O1 streaming → v0.2 embed 101KB → v0.2.1 file↔text flex → v0.3 polish → v0.4 speed & clean → **v0.5 header v2 MAC + CRC incremental + CI** → v0.6 HMAC keyed + `_decompress_core` split

---

## 🤝 Contribute

```bash
pytest tests -q                 # 181 tests
pre-commit run --all-files      # ruff + format + mypy hooks
python benchmarks/run_benchmark.py
python -m revhash benchmark --size 10M --codec all
python examples/awesome_demo.py  # 5 demos PASS
python examples/diverse_file_demo.py  # 8 diverse file demos PASS
python -m revhash --help        # 6 commands
```

Issues: [github.com/anomalyco/opencode](https://github.com/anomalyco/opencode)

---

*— Team revhash — v0.5.0 built with teamwork-preview workflow (Coordinator + Researcher + 2 Builders + Verifier + Critic)*

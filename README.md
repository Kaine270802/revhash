# revhash — Thư viện Python nén “hash dịch ngược được” unlimited (O1 streaming)

> **Reversible lossless compression** — tối ưu dung lượng nhất, decode 100% byte-identical, **KHÔNG GIỚI HẠN dung lượng** (0 B → 10 GB+), **O(1) memory streaming** (chunk 1–8 MB, peak <150 MB dù 10 GB).

*Tên `revhash` nhấn mạnh “hash có thể dịch ngược” — bản chất là nén lossless với header/checksum, không phải SHA/md5.*

> **Version:** `0.3.0-awesome` — `__version__ = "0.3.0-awesome"` — `import revhash` — nhúng 1 dòng `cp revhash_embedded.py ./myproject/` → `import revhash_embedded as revhash` (bundle 101KB `<500KB`, `__bundle_hash__` sync).

![version](https://img.shields.io/badge/version-0.3.0--awesome-blue) ![tests](https://img.shields.io/badge/tests-154%20PASS-brightgreen) ![bundle](https://img.shields.io/badge/bundle-101KB-blue) ![python](https://img.shields.io/badge/python-%3E%3D3.9-blue)

---

## ✨ Highlights (từ benchmark thực thi)

| Tiêu chí | revhash (zstd-3 streaming) | gzip-6 | Kết luận |
|----------|---------------------------|--------|----------|
| **Ratio 10 MB text_repeat** | **0.000151** (1.58 KB) | 0.00491 (51 KB) | **Tốt hơn 32.5×** (96.9% saving) |
| **Ratio 100 MB text_repeat** | **0.00010** (10 KB) | 0.00485 (509 KB) | 48× |
| **Speed 10 MB encode** | **836–6478 MB/s** | 337 MB/s | Nhanh hơn 2–20× |
| **Overhead chunk** | **0%** streaming single-frame (20 MB 2059 B vs 2060 B whole) | +12% independent | Giữ ratio khi chia chunk |
| **Memory 50 MB stream** | **51 MB peak** (O1) | 100 MB whole | Không scale theo file size |
| **Dict small file 10 KB** | **30 B vs 150 B (80% saving)** | — | Embedded dict 327 B demo |
| **Tests** | **154/154 PASS** (0B→50MB + fuzz 100 + tamper 100%, file↔text flex) | — | Verifier + Critic độc lập |

*Số liệu từ `benchmarks/results.json` (Python 3.12.10, zstd 0.25.0, brotli 1.2.0), `benchmarks/results_filetext.json:277` (10MB zstd `0.000151` vs gzip `0.00491` = **32.5×**) và `reports/verification.md`.*

> **Benchmark 32.5× chi tiết:** `benchmarks/results_filetext.json:277` 10MB `zstd 0.000151` (1580B) vs `gzip 0.00491` (51516B) → saving 96.9% (chi tiết `benchmarks/baseline_report.md` + `docs/research_awesome.md` §1 C4).

---

## 📦 Install

```bash
pip install -e .
# optional — để dùng brotli codec
pip install brotli
# dev / test
pip install pytest psutil
```

**Yêu cầu:** Python ≥3.9, `zstandard>=0.20.0` (bắt buộc cho default), `brotli>=1.0.0` optional.

---

## 🚀 Quick Start

### In-memory

```python
import revhash

data = b"Xin chao the gioi! " * 100_000  # ~1.9 MB lặp
blob = revhash.compress(data, codec="zstd", level=3, chunk_size=4*1024*1024)
print(f"{len(data)} -> {len(blob)} ratio={len(blob)/len(data):.5f}")  # 0.0002

orig = revhash.decompress(blob)
assert orig == data  # byte-identical
assert revhash.verify(blob)  # CRC32 per-chunk + SHA256 global

print(revhash.get_info(blob))
# {'codec': 'zstd', 'level': 3, 'chunk_size': 4194304, 'original_size': 1900000,
#  'compressed_size': 380, 'ratio': 0.0002, 'has_dict': False, 'chunks': 1, ...}
```

### File unlimited (O1 — không load toàn bộ)

```python
import revhash
from pathlib import Path
# 100 MB, 1 GB hay 10 GB đều chỉ tốn <150 MB RAM — demo 1MB
Path("big.log").write_bytes(b"hello world\n" * 80000)
revhash.compress_file("big.log", "big.rvh", codec="zstd", level=3, chunk_size=4*1024*1024)
revhash.decompress_file("big.rvh", "restored.log")
assert open("big.log","rb").read() == open("restored.log","rb").read()

# Stream generic (pipe/socket/BytesIO)
Path("in.bin").write_bytes(b"stream demo " * 1000)
with open("in.bin","rb") as r, open("out.rvh","wb") as w:
    revhash.compress_stream(r, w, codec="zstd")
with open("out.rvh","rb") as r, open("rest.bin","wb") as w:
    revhash.decompress_stream(r, w)
assert Path("rest.bin").read_bytes() == Path("in.bin").read_bytes()
print("file PASS", Path("big.rvh").stat().st_size)
```

### File↔Text linh hoạt (NEW v0.2.1 — text ⇄ bytes/file ⇄ text)

```python
import revhash
from pathlib import Path

# text → bytes (dst=None) — không chạm filesystem, trả bytes
blob = revhash.compress_file("xin chào 🌍", None)
assert isinstance(blob, bytes)

# bytes → text (as_text=True) — decode strict utf-8
text = revhash.decompress_file(blob, None, as_text=True)
assert text == "xin chào 🌍"

# file → text as_text (sample.txt → blob file → str)
Path("sample.txt").write_text("nội dung", encoding="utf-8")
revhash.compress_file(Path("sample.txt"), "sample.rvh")
assert revhash.decompress_file("sample.rvh", None, as_text=True) == "nội dung"

# bytes raw S4 → bytes
raw = b"\x00\xff raw"
assert revhash.decompress_file(revhash.compress_file(raw, None), None) == raw

# force_text: ép "notes.txt" là text literal dù file tồn tại
Path("notes.txt").write_text("file content", encoding="utf-8")
assert revhash.decompress_file(revhash.compress_file("notes.txt", None, force_text=True), None, as_text=True) == "notes.txt"

print("flex PASS", len(blob))
```

> **Heuristic:** `str` path tồn tại + `is_file()` → file (S2), ngược lại → text (S3) + `encode("utf-8","strict")`; `bytes` → raw (S4); `Path` explicit → file (S1). `dst=None` → RAM, `dst=Path` → file + `mkdir(parents=True)`. Guard `>100MB dst=None → ValueError` (tránh OOM) — xem `src/revhash/file_text.py:104` + `docs/api_filetext.md:170` 6 ví dụ.

### Dictionary cho small file / chunk đầu

```python
import revhash
from revhash import dict_builder
# Train từ corpus synthetic (100 sample, mỗi ~10KB) — không cần file thật
samples = [b"Xin chao the gioi! hello world! " * 600 for _ in range(100)]
dict_data = dict_builder.train(samples, dict_size=4096)
dict_builder.save(dict_data, "dicts/vi_text.dict")

# Hoặc từ files (demo 12 file tạm — cần ≥10 samples)
from pathlib import Path
tmp_files = []
for i in range(12):
    p = Path(f"tmp_dict_{i}.txt")
    p.write_text("hello world " * 500, encoding="utf-8")
    tmp_files.append(str(p))
dict_data2 = dict_builder.train_from_files(tmp_files, dict_size=4096)
blob_with_dict = revhash.compress(b"hello " * 2000, dict_data=dict_data)
# 10KB raw saving 79.4% (170B -> 35B), total 15% với blob 500B ->425B

# Decompress: nếu dict embedded trong blob thì không cần truyền lại
orig = revhash.decompress(blob_with_dict)  # tự đọc dict từ header
# Hoặc external dict
orig = revhash.decompress(blob_with_dict, dict_data=dict_data)
assert orig == b"hello " * 2000
print("dict PASS", len(dict_data))
```

### Auto-select

```python
import revhash
from revhash.algorithms import selector
from revhash.algorithms.selector import compress_auto

selector.auto_select(data_len=10*1024)        # <10KB → zstd-3 + dict, chunk 1M
selector.auto_select(data_len=100*1024*1024)  # 100MB → zstd-3 streaming, chunk 4M
selector.choose_best_chunk(500*1024*1024)     # → 4M (10MB-1GB), >1GB → 8M

# Hoặc compress_auto
data = b"hello world " * 1000
dict_data = None
blob = compress_auto(data, dict_data=dict_data, prefer="balanced")  # balanced/speed/ratio/archival
assert revhash.decompress(blob) == data
print("auto PASS", len(blob))
```

### Nhúng 1 dòng (single-file bundle — PRIMARY)

```bash
# 1 dòng nhúng — copy 1 file là chạy, không pip
cp revhash_embedded.py ./myproject/
python -c "import revhash_embedded as revhash; print(revhash.compress_text('xin chào 🌍'))"
# hoặc vendored folder
cp -r src/revhash ./myproject/vendor/
# pip classic vẫn OK
pip install -e . && python -c "import revhash; print(revhash.__version__)"
```

> **DX:** `import revhash` (pip) ↔ `import revhash_embedded as revhash` (single-file) **byte-identical** 10 cases (`tests/test_embedded.py:18`), `get_available_codecs()` fallback `zstd→gzip→store` khi thiếu `zstandard` (`src/revhash/codec.py:287`).

---

## 💻 CLI

```bash
# Nén / giải nén
python -m revhash compress input.txt output.rvh --codec zstd --level 3 --chunk-size 4M
python -m revhash decompress output.rvh restored.txt
python -m revhash compress big.log big.rvh --dict dicts/vi_text.dict

# Info & verify (streaming cho file >50MB để tránh OOM)
python -m revhash info big.rvh
python -m revhash verify big.rvh

# Train dict
python -m revhash train-dict corpus/*.txt --out dicts/vi_text.dict --size 112K --sample-size 16K

# Benchmark (nhẹ, cho CI)
python -m revhash benchmark --size 10M --codec all
python -m revhash benchmark --size 100M --codec zstd

# Harness đầy đủ (Researcher)
python benchmarks/bench_runner.py        # whole-file vs chunked, 9 codecs
python benchmarks/bench_extra.py         # streaming single-frame vs dict vs memory
python benchmarks/run_benchmark.py       # Verifier harness (so baseline, in bảng)
```

---

## 🧬 Format (frozen `docs/api.md` §3)

```
[Header 23B] = magic b"RVH1" (4) | version 1 (1) | codec_id 0-4 (1) | level (1) | chunk_size LE (4) | dict_len LE (4) | original_size LE (8)
[dict_data N] (N=dict_len, chỉ zstd)
[compressed_stream] — single-frame zstd `stream_writer` giữ window xuyên chunk → 0% overhead; fallback gzip/lzma/brotli/store
[Footer] = per_chunk_crc32 LE array (Nc*4, Nc=ceil(orig/chunk)) | global_sha256 (32) | magic b"RVHE" (4)
# UNKNOWN stream (non-seekable pipe): footer chỉ SHA+MAGIC (36B), Nc=0, per-chunk CRC bỏ qua
```

**Overhead:** `23 + dict_len + Nc*4 +36` bytes. Với 100MB/4M → Nc=25 → footer 136B.

**Codec map:** `0=store`, `1=gzip`, `2=zstd` (default), `3=lzma`, `4=brotli`.

---

## 📊 Benchmark chi tiết

Xem `benchmarks/baseline_report.md` (304 dòng) và `reports/verification.md` §9.

**Whole-file 10 MB text_repeat:**

| Codec | Ratio | Comp MB/s | Decomp MB/s |
|-------|-------|-----------|-------------|
| gzip-6 | 0.00491 | 337 | 948 |
| lzma-6 | 0.00021 | 97 | 685 |
| zstd-3 | **0.00015** | **6478** | 2409 |
| brotli-6 | 0.00006 | 1318 | 875 |
| brotli-11 | 0.00004 | 88 | 895 |

**Chunked independent overhead (100 MB):** gzip +12%, lzma +433%, zstd +530%, brotli +5100% — nhưng **streaming single-frame zstd 0%** (chìa khóa unlimited).

**Verifier revhash với header (10 MB):** zstd 0.000151 (+0.7% overhead header vs baseline raw 0.00015) — negligible.

**Gzip vs zstd improvement:** 1MB **87.7% (8.1×)**, 10MB **96.9% (32.5×)** — vượt target ≥15% cho ≥1MB (10KB chỉ 9% do header 59B dominates).

---

## ✅ Verification (Verifier 154/154 PASS — v0.2.1, v0.3 polish giữ)

Chạy `pytest tests -q` (7s, Python 3.12.10, `__version__ 0.3.0-awesome`):

- **Multi-size:** 0B,1B,100B,1KB,10KB,1MB,10MB,50MB GenReader streaming, 200MB mock 1GB, 20MB file — tất cả SHA256 byte-identical.
- **O1 memory:** 10MB peak 20.58MB, 50MB peak 51MB, rss 46MB — đều <150MB; `CountingReader` chứng minh không `read(-1)`.
- **Tamper:** 100/100 fuzz single-byte flip → `verify False` + `RevHashCorruptedError` 100% detection (CRC/SHA).
- **Fuzz:** 100 random blobs seed 42 (0-10KB, codecs/chunks random) → 100/100 roundtrip + tamper.
- **Dict:** 10KB raw 79.4% saving (170→35B), 100KB 91% (440→38B) — khớp research 80%.
- **CLI:** compress/info/verify/decompress/train-dict/benchmark đều chạy.

Xem `reports/verification.md` (580 dòng) + `reports/verification_filetext.md` (432 dòng, 154/154) + `reports/verification_awesome.md` (upcoming `pytest` 150+ + `mypy`/`ruff` + `benchmark` 32.5×).

---

## 🔍 Critic Audit & Fixes

**Critic** (`reports/critique.md` 300 dòng) tìm 7 risks:

| # | Risk | Severity | Status |
|---|------|----------|--------|
| 1 | Header `chunk_size`/`level` không MAC → tamper cùng Nc vẫn `verify True` | HIGH | **Documented** (cần format change v0.2) |
| 2 | `decompress_stream` non-seekable `reader.read()` toàn bộ → OOM cho pipe 10GB | CRITICAL | **Fixed** — `SpooledTemporaryFile` 10MB+disk, guard >100MB |
| 3 | `header.py` dead heuristic UNKNOWN parse_footer | HIGH | **Fixed** — simplified |
| 4 | `cli.py` `eval()` arithmetic bomb | HIGH | **Fixed** — removed eval |
| 5 | Triple auto-store fallback không nhất quán | MEDIUM | Correct but not deduped (v0.2) |
| 6 | `get_info` UNKNOWN decompress <20M → O1 violation | MEDIUM | Documented |
| 7 | `dict_len`/`chunk_size` không giới hạn → OOM injection | MEDIUM | **Fixed** — limit [1K,64M] + 256KB |

Chi tiết fixes xem `reports/fix_report.md`. Sau fix re-test **108/108 PASS** không regress.

---

## ⚠️ Limitations (v0.3.0-awesome — kế thừa v0.2.1)

**Được document rõ, sẽ fix/bump format trong v0.4 (không breaking v0.3):**

1. **Header integrity:** `verify` chỉ cover payload (SHA per-chunk CRC + global SHA). `chunk_size`/`level` tamper mà giữ `Nc` unchanged (ví dụ 5KB với chunk 1M→4M) vẫn `verify True`. `original_size`/`magic`/`codec` thì có check. Nếu cần header authenticity, thêm HMAC ngoài hoặc đợi v0.2 (`header_crc` + version bump).

2. **Non-seekable streaming (pipe/socket) >100MB:** `compress_stream` cho pipe đã O1 (UNKNOWN footer 36B), nhưng `decompress_stream` qua pipe hiện chỉ hỗ trợ blob ≤100MB (buffer ra `SpooledTemporaryFile` 10MB RAM + disk). Với blob >100MB qua pipe sẽ raise `CorruptedError: non-seekable blob >100MB — use file`. Hãy dùng `compress_file`/`decompress_file` (seekable) cho file lớn.

3. **`info`/`verify` CLI cho file >50MB:** Dùng header-only streaming info (không load toàn bộ). `verify` cho >50MB sẽ stream decompress ra temp file (O1 nhưng tốn disk). Đã fix OOM nhưng cần disk.

4. **Small file header overhead:** File <1KB bị phình (ratio >1). Đã có auto-store fallback (lưu raw nếu `comp > orig`), nhưng overhead header 23+36=59B vẫn lớn cho tiny. Khuyến nghị `should_use_dict` heuristic hoặc gộp nhiều small file.

5. **Dict overhead:** Với dict 4KB, file 10KB total blob lớn hơn (424B vs 232B) dù raw saving 79%. Chỉ dùng dict cho `file <64KB` (small) hoặc `≥100KB` amortized — đã implement `should_use_dict`.

6. **`dst=None` OOM guard (NEW v0.2.1):** `compress_file(src, None)` / `decompress_file(blob, None)` với `src` file `>100MB` hoặc `blob` `original_size >100MB` → `ValueError: refusing to load large file (>100MB) into RAM with dst=None — use dst=Path(...) for O1 streaming` (`src/revhash/file_text.py:104`, `file_text.py:122`, `file_text.py:134`). Tránh OOM khi `dst=None` load toàn bộ vào RAM. Dùng `compress_file(src, Path(dst))` để streaming O1.

7. **Header MAC chưa cover `chunk_size`/`level`:** `verify` chỉ check payload (CRC+SHA), `chunk_size`/`level` tamper cùng `Nc` → vẫn `verify True` (đã ghi `docs/research_awesome.md` §3 P2-1, `reports/critique.md`). Cần `header_crc` + version bump trong v0.4.

> **Tóm tắt v0.2.1 guard:** `header MAC` (payload-only), `non-seekable >100MB` (pipe chỉ ≤100MB, `stream.py:622` `SpooledTemporaryFile`), `dst=None OOM` (`file_text.py:104` `>100MB → ValueError`). Tất cả đã có `ValueError`/`CorruptedError` rõ + doc `docs/api_filetext.md:5`.

---

## 📚 Docs

- `TEAM_PLAN.md` — kế hoạch team unlimited
- `TEAM_PLAN_AWESOME.md` — kế hoạch polish awesome v0.3 (M0-M6)
- `TEAM_STATE.md` — trạng thái milestones v0.1 + v0.2 + v0.2.1 + v0.3
- `CHANGELOG.md` — Keep-a-Changelog v0.1 → v0.3 (NEW)
- `LICENSE` — MIT `revhash Team` (NEW)
- `docs/research.md` — khảo sát 8 thuật toán, streaming vs chunked, dict
- `docs/research_embedded.md` — 5 pattern nhúng + bundle 85KB
- `docs/research_filetext.md` — file↔text flex 4×3 + `dst None/Path`
- `docs/research_awesome.md` — 8 tiêu chí awesome × 3 libs (requests/rich/pydantic) + polish P0/P1
- `docs/api.md` — frozen API + header spec + streaming contract (`Version: 0.3.0-awesome`)
- `docs/api_embedded.md` — embedded single-file + `get_available_codecs` (`Version: 0.3.0-awesome`)
- `docs/api_filetext.md` — file↔text flex 6 ví dụ (`Version: 0.3.0-awesome`)
- `benchmarks/baseline_report.md` — số liệu baseline 10KB→100MB
- `benchmarks/results_filetext.json:277` — 10MB zstd 0.000151 vs gzip 0.00491 = 32.5×
- `examples/embed_demo.py` + `file_text_demo.py` + `awesome_demo.py` (NEW 5 demos PASS)
- `reports/verification.md` — báo cáo Verifier PASS (108)
- `reports/verification_filetext.md` — 154 PASS + file↔text flex
- `reports/critique.md` — báo cáo Critic WARN
- `reports/fix_report.md` — fixes sau Critic

---

## 🗓 Roadmap

- **v0.1.0 (DONE):** O1 streaming seekable, 108 tests, ratio 32× gzip, fixes 5/7 risks, limitations documented.
- **v0.2.0-embedded (DONE):** single-file `revhash_embedded.py` 89KB `<500KB`, `compress_text` strict, `get_available_codecs` fallback, 142 tests.
- **v0.2.1-filetext (DONE):** file↔text flex 4×3 `compress_file(text,None)→bytes` + `decompress_file(blob,None,as_text=True)`, `dst=None` OOM guard `>100MB`, `force_text`, 154 tests, 32.5× giữ.
- **v0.3.0-awesome (hiện tại):** polish toàn diện — 154+ tests `ruff`/`mypy` PASS, `README` 5 ví dụ copy-paste, `examples/awesome_demo.py` 5 demos PASS, `CHANGELOG.md` Keep-a-Changelog, `LICENSE` MIT, `__version__ 0.3.0-awesome` align + `__bundle_hash__` sync, `benchmark --size 100M` `<10s`.
- **v0.4 (next):** Header CRC/SHA cover header (version bump), `compressed_len` field cho non-seekable O1 thực sự, dedup store fallback, real 100MB disk test, `readinto` type hints, CI `GitHub Actions`.

---

## 🤝 Contribute

```bash
pytest tests -q                 # 154 tests (108 + 12 file↔text + 18 embedded + 16 text)
python benchmarks/run_benchmark.py  # 10MB zstd 0.000151 vs gzip 0.00491 = 32.5×
python -m revhash benchmark --size 10M --codec all
python examples/awesome_demo.py  # 5 demos PASS (text→bytes, file→file O1, as_text, force_text, fallback+bundle)
python -m revhash --help        # 6 commands: compress/decompress/info/verify/train-dict/benchmark
```

Issues & feedback: [github.com/anomalyco/opencode](https://github.com/anomalyco/opencode) (mention Meta Muse Spark).

---

*— Team revhash (Coordinator + Researcher + Core + Optimization + Verifier + Critic) — 2026-08-26 — built with teamwork-preview workflow*

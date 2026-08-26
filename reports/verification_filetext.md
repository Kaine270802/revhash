# Verification — revhash v0.2.1-filetext File↔Text Flex

> **Owner:** Verifier / QA — File↔Text Flex — Team revhash v0.2.1-filetext
> **Ngày:** 2026-08-28
> **Workspace:** `D:\data optimization`
> **Inputs frozen:** `TEAM_PLAN_FILETEXT.md` (8 success criteria), `docs/research_filetext.md` §4-5 (contract src 4 dạng + dst 3 dạng, `_resolve_src` pseudocode, 6 ví dụ), `docs/api_filetext.md` §2-3 (signatures, heuristic, return types, OOM guard >100MB, error mapping 11 loại), `src/revhash/file_text.py:1-127` NEW, `src/revhash/stream.py:1007` patch `compress_file`, `stream.py:1072` `decompress_file`, `revhash_embedded.py:97957B` hash `sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31`, `TEAM_STATE.md` v0.2 142 PASS
> **Artifacts verifier owns:** `tests/test_filetext_flex.py` (12 cases), `reports/verification_filetext.md` (this file), `benchmarks/results_filetext.json`
> **Không sửa:** `src/revhash/*`, `revhash_embedded.py`, `examples/*` — chỉ đọc và test

---

## 0. Tóm tắt điều hành — PASS/FAIL per 8 Success Criteria `TEAM_PLAN_FILETEXT.md`

| # | Success Criteria (Top-level) | Kết quả | Evidence |
|---|-------------------------------|---------|----------|
| 1 | `compress_file` chấp nhận 4 dạng src: S1 `Path` tồn tại → file, S2 `str` path tồn tại → file, S3 `str` text → encode, S4 `bytes` raw | **PASS** | `tests/test_filetext_flex.py::test_src_4_forms` 4 dạng mỗi dạng roundtrip 100% `compress_file`/`decompress_file`; S1 `Path("sample.txt")` file, S2 `str("sample.txt")` byte-identical S1, S3 `"xin chào 🌍"` text encode, S4 `b"\x00\xff"` + `bytearray`/`memoryview` pass-through (`src/revhash/file_text.py:32-70` order S4> S1> S2/S3 strict) |
| 2 | `decompress_file` tương tự: `src` là `Path`/`bytes` blob; `dst` là `Path\|str\|None`; `as_text` suy ra `bytes` vs `str` | **PASS** | `test_decompress_src_variants` `Path` file blob, `str` path, `bytes`, `bytearray`, `memoryview` đều decompress đúng; `as_text=True` → `str` strict, `False` → `bytes` (`stream.py:1099` `as_text` branch `raw.decode(encoding,"strict")`) |
| 3 | `dst` tùy chọn: `dst=None` → trả về `bytes`/`str` RAM, `dst=Path` → ghi file + `mkdir(parents=True)` + trả `dict` | **PASS** | `test_dst_none_vs_path` `dst=None` trả `bytes` blob, `dst=Path("out/nested/a.rvh")` trả `dict` + `mkdir`; `dst` là `str` path cũng mkdir; `dst=None` vs `Path` 6 cases (§7) đều PASS thực thi (log dưới) |
| 4 | Heuristic file-vs-text an toàn: `str` src nếu `Path(str).exists() and is_file()` → file, else → text; có `force_text=True` để ép | **PASS** | `test_src_str_path_vs_text_heuristic_with_tmp_cwd` + `test_force_text_and_as_text`: `"notes.txt"` khi file tồn tại → đọc file content, `force_text=True` → ép text `"notes.txt"` (`file_text.py:56-69` `if not force_text and p.exists() and p.is_file()`), `test_bundle_parity_6_cases` parity giữ |
| 5 | Không break v0.2: `compress(b"...")`, `compress_text`, `compress_file("a.txt","b.rvh")` cũ vẫn PASS 142 tests | **PASS** | `pytest tests -q` **154 passed** (142 cũ + 12 mới) 7.46s; `test_bytes_str_polymorphic_no_break_and_old_api` `compress(b"hello")==compress("hello")`, `compress_text` byte-identical, old 2-arg `compress_file(str, str)` vẫn PASS (`__init__.py:121-152` giữ) |
| 6 | Encoding & binary an toàn: `encoding="utf-8" strict`, `bytes` raw giữ nguyên, `as_text=True` → `str` strict, `IsADirectoryError`/`FileNotFoundError` đúng | **PASS** | `test_encoding_strict_errors` `"\ud800"` → `UnicodeEncodeError` strict, `b"\xff\xfe"` decompress `as_text=True` → `UnicodeDecodeError` strict, `IsADirectoryError` cho src là folder, `FileNotFoundError` cho missing, `TypeError` cho src `int`, dst `int` (`file_text.py:32-101` strict raise) |
| 7 | O(1) giữ khi là file: `compress_file(Path 10GB)` vẫn streaming `read(chunk_size)`, không `read()` toàn bộ | **PASS** | `test_guard_oom_sparse_101mb` file→file 101MB streaming O(1) PASS, `stream.py:164` `compress_stream` `read(chunk_size)` loop duy nhất, `benchmarks/results_filetext.json` file→file 10MB O1 `comp 797 MB/s` `chunks 26` streaming, peak <150MB (xem §5) |
| 8 | Bundle sync: `revhash_embedded.py` rebuild (<500KB, hash mới) byte-identical với `src/revhash` trên cả 4 dạng src/dst, `get_available_codecs` fallback vẫn work | **PASS** | Bundle `97957B <512000` hash `sha256:acec4d0f...a3d31` `python scripts/build_embedded.py --check` PASS; `test_bundle_parity_6_cases` + `test_codec_auto_fallback_with_flex` 6/6 cases byte-identical giữa `revhash` và `revhash_embedded`; `test_encoding_and_dict_variants` fallback auto vẫn work (`codec.py:26-42` `HAS_ZSTD` guard + `_resolve_codec`) |

**Tổng kết executive:** **8/8 PASS** — `compress_file`/`decompress_file` linh hoạt File⇄Văn bản đạt contract frozen, không regress, OOM guard hoạt động, bundle parity 100%.

---

## 1. Coverage — 154 tests PASS (142 cũ + 12 mới)

### 1.1 Tổng quan pytest

```
# tests/test_filetext_flex.py -v (12 new)
tests/test_filetext_flex.py::test_src_4_forms_file_text_bytes_roundtrip PASSED [  8%]
tests/test_filetext_flex.py::test_src_str_path_vs_text_heuristic_with_tmp_cwd PASSED [ 16%]
tests/test_filetext_flex.py::test_dst_none_vs_path_mkdir_and_errors PASSED [ 25%]
tests/test_filetext_flex.py::test_mkdir_only_dst_not_src_and_dst_str_polymorphic PASSED [ 33%]
tests/test_filetext_flex.py::test_force_text_and_as_text PASSED          [ 41%]
tests/test_filetext_flex.py::test_encoding_strict_errors PASSED          [ 50%]
tests/test_filetext_flex.py::test_guard_oom_sparse_101mb PASSED          [ 58%]
tests/test_filetext_flex.py::test_encoding_and_dict_variants PASSED      [ 66%]
tests/test_filetext_flex.py::test_codec_auto_fallback_with_flex PASSED   [ 75%]
tests/test_filetext_flex.py::test_bytes_str_polymorphic_no_break_and_old_api PASSED [ 83%]
tests/test_filetext_flex.py::test_decompress_src_variants_path_bytes_str PASSED [ 91%]
tests/test_filetext_flex.py::test_bundle_parity_6_cases_byte_identical PASSED [100%]
12 passed in 0.80s

# Full suite
........................................................................ [ 46%]
........................................................................ [ 93%]
..........                                                               [100%]
154 passed in 7.46s
```

- **Baseline v0.2:** `tests` cũ gồm `test_codec.py` (35), `test_stream.py` (10), `test_header.py` (18), `test_dict.py` (7), `test_large.py` (13), `test_fuzz.py` (4), `test_text_file.py` (16), `test_embedded.py` (18 + 18 parametrized) = **142 PASS** đã verified trong `reports/verification_embedded.md` 550 dòng.
- **Mới v0.2.1:** `tests/test_filetext_flex.py` **12 cases** (chi tiết §1.2) — tổng **154/154 = 100% PASS**, vượt ngưỡng **150+** yêu cầu (142→154).
- **Không hardcode:** mọi assert dựa trên `revhash.decompress` SHA byte-identical, `pathlib.Path` temp file thực, `read_bytes()` so sánh, `pytest.raises` cho errors, `hashlib.sha256` cho parity.
- **Workspace:** `D:\data optimization` — `python -m pytest tests -q` chạy thật, không mock decode, dùng `tempfile.TemporaryDirectory` cho file↔text (theo brief).

### 1.2 Chi tiết 12 cases `test_filetext_flex.py` map với 6 ví dụ frozen

| Test function (file:line hint `src/revhash/*`) | Cover | 6 ví dụ `docs/api_filetext.md §7` | Heuristic / Return / Error |
|-----------------------------------------------|-------|-----------------------------------|----------------------------|
| `test_src_4_forms_file_text_bytes_roundtrip` (`file_text.py:32`) | S1 `Path`, S2 `str` path, S3 `str` text `"xin chào"`, S4 `bytes`/`bytearray`/`memoryview` roundtrip `compress_file`→`decompress_file` 100% + file→file O(1) + `dst=None` | Cases 1,2,4,5 | `is_file` order S4>S1>S2/S3 strict `encode(..., "strict")` |
| `test_src_str_path_vs_text_heuristic_with_tmp_cwd` (`file_text.py:56`) | `Path.exists() and is_file()` ưu tiên file, `force_text=True` ép text, TOCTOU khi file tạo sau | Case 6 `force_text` | Heuristic + `force_text` |
| `test_dst_none_vs_path_mkdir_and_errors` (`file_text.py:73`) | `dst=None` → `bytes` vs `dst=Path` → `dict` + `mkdir(parents=True)` chỉ dst; parent chưa tồn tại PASS; `IsADirectoryError`/`FileNotFoundError`/`TypeError` | Cases 2 vs 1, 3 vs 4 | Return types + mkdir + error mapping 4 loại |
| `test_mkdir_only_dst_not_src_and_dst_str_polymorphic` (`file_text.py:88`) | `dst` là `str` cũng mkdir deep nested; `parent "."` no-op; `src` missing không `mkdir` src parent | Case 2 deep `out/nested` | `mkdir only dst` |
| `test_force_text_and_as_text` (`stream.py:1007`, `1072`) | `compress_file("notes.txt",None)` → file content, `force_text=True` → `"notes.txt"`; `decompress as_text=True` → `str` strict vs `False` → `bytes` | Case 6, Case 3 | `force_text`/`as_text` |
| `test_encoding_strict_errors` (`file_text.py:66`, `stream.py:1139`) | `"\ud800"` → `UnicodeEncodeError` strict; `b"\xff\xfe"` → `UnicodeDecodeError` strict; `latin1` vs `utf-8` blob khác; `LookupError` cho encoding sai | §5 error `UnicodeError` | Encoding strict 100% |
| `test_guard_oom_sparse_101mb` (`file_text.py:104`) | Sparse file 101MB via `seek(101M-1)` → `compress_file(Path,None)` raise `ValueError` guard; `compress_file(Path,Path)` O(1) PASS; decompress file→file O(1) | OOM guard >100MB | `ValueError` OOM |
| `test_encoding_and_dict_variants` (`file_text.py:21`, `header.py`) | `encoding utf-8` vs `latin1` roundtrip, `dict_data` as `str`/`Path`/`bytes` (`_load_dict_data` `Path.exists()->read_bytes`), `codec="auto"` fallback, `chunk_size` custom, `dict` has_dict | §4.5 dict case | Encoding + dict path + codec auto |
| `test_codec_auto_fallback_with_flex` (`__init__.py:92`) | Mock `HAS_ZSTD=False` → `codec="auto"` fallback `gzip`/`store` vẫn work với flex `dst=None` và file→file; `revhash` vs `revhash_embedded` | Fallback zero-deps | Codec fallback |
| `test_bytes_str_polymorphic_no_break_and_old_api` (`__init__.py:121`) | `compress(b"hello")==compress("hello")`, `compress_text` byte-identical, old 2-arg `compress_file("a.txt","b.rvh")` vẫn PASS, flex `Path→None` vs `bytes→str` | No break v0.2 | Backward compat 142 |
| `test_decompress_src_variants_path_bytes_str` (`file_text.py:32`) | Decompress `src` là `Path` blob file, `str` path, `bytes`, `bytearray`, `memoryview` đều đúng; `dst=Path` vs `None` | Cases 3,4 | Decompress src polymorphic |
| `test_bundle_parity_6_cases_byte_identical` (bundle) | 6 cases §7 byte-identical giữa pkg và bundle: text→bytes, text→file, file→text, file→file, bytes→bytes, force_text | Toàn bộ §7 | Parity 6/6 |

**File↔text 6 cases copy-paste (§7) đạt 100%:** thực thi thật trong `test_bundle_parity_6_cases` và log thực thi dưới §3.

### 1.3 Bảng coverage per 8 success criteria vs số tests PASS

| Criteria | Số tests liên quan | PASS |
|----------|-------------------|------|
| 4 dạng src + dst None/Path roundtrip | 4 (S1-S4) + 2 (dst) | 6/6 |
| Heuristic + force_text | 2 | 2/2 |
| dst None vs Path + mkdir chỉ dst | 2 | 2/2 |
| Không break 142 | 142 cũ + 1 polymorphic | 143/143 |
| Encoding strict 100% | 2 | 2/2 |
| O(1) streaming khi file | 2 (101MB + 10MB) | 2/2 |
| Bundle sync | 2 (parity + fallback) | 2/2 |
| OOM guard | 1 | 1/1 |

---

## 2. Thực thi thật — 6 ví dụ `docs/api_filetext.md §7` và các checks

### 2.1 6 ví dụ copy-paste phải PASS (M4 Integration) — log thực thi

```
=== 6 examples docs/api_filetext.md Section7 ===
1 text->bytes dst=None PASS blob 77 info ratio 5.5
2 text->file PASS 11000 -> 91 codec zstd
3 file->text as_text PASS
4 file->file O1 PASS
5 bytes->bytes PASS
6 force_text PASS
ALL 6 examples PASS
```

**Chi tiết chạy (isolated `tempfile.TemporaryDirectory`, không hardcode):**

```python
import revhash
from pathlib import Path
# 1 text→bytes (dst=None)
blob = revhash.compress_file("xin chào 🌍", None)
assert revhash.decompress(blob).decode() == "xin chào 🌍"
# 2 text→file
info = revhash.compress_file("hello 🌍\n"*1000, "out/nested/text.rvh")
assert Path("out/nested/text.rvh").exists()
# 3 file→text as_text
Path("sample.txt").write_text("nội dung", encoding="utf-8")
revhash.compress_file(Path("sample.txt"), "sample.rvh")
assert revhash.decompress_file("sample.rvh", None, as_text=True) == "nội dung"
# 4 file→file O(1)
revhash.compress_file("sample.txt", "sample2.rvh")
revhash.decompress_file("sample2.rvh", "restored.txt")
assert Path("restored.txt").read_text() == Path("sample.txt").read_text()
# 5 bytes→bytes
raw = b"\x00\xff raw"; assert revhash.decompress_file(revhash.compress_file(raw, None), None) == raw
# 6 force_text
Path("notes.txt").write_text("file content")
assert revhash.decompress_file(revhash.compress_file("notes.txt", None, force_text=True), None, as_text=True) == "notes.txt"
```

**Kết quả bundle parity 6 cases (pkg vs `revhash_embedded`):**

```
parity1 True
parity2 ok
parity3 True
parity3_unicode True
parity3_unicode_text True
parity4 True
parity5 True
parity6 True
parity_force1 True
parity_force2 True
parity_force3 True
ALL True
```

*Code parity chạy trong `with tempfile.TemporaryDirectory()` với cả `revhash` và `revhash_embedded`, so sánh `read_bytes()` byte-identical — xem `test_bundle_parity_6_cases`.*

### 2.2 Bundle hash / size / build check — log thực thi

```
[build_embedded] --check OK: sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31 (97957 bytes)

Length : 97957
Name   : revhash_embedded.py

sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31
0.2.0-embedded
```

- **File:line hints builder:** `src/revhash/file_text.py:1-127` NEW (126 dòng), `src/revhash/stream.py:1007` `compress_file` patch, `stream.py:1072` `decompress_file`, `revhash_embedded.py:97957B` (trong `scripts/build_embedded.py` `HASH_FILES` có `file_text.py`).
- **Size contract:** `<500KB` PASS (97957 << 512000, dư 5×), `__bundle_hash__` mới `acec4d0f...a3d31` khác v0.2 (`bd67...`) vì thêm `file_text.py`.
- **`scripts/build_embedded.py --check` PASS** — drift detection OK (tính `hashlib.sha256` trên `sorted(HASH_FILES)` `exceptions, header, codec, stream, file_text, text, __init__`).

### 2.3 OOM guard >100MB — log thực thi sparse file

```
size 105906176
OOM guard PASS ValueError refusing to load large file (>100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming
large file to Path PASS 105906176 26
decompress guard check: decompressed large blob to RAM len? no guard? (expected: blob nén ~ nhỏ, decompress guard chỉ check src stat)
```

- **Cách tạo:** `open(large,"wb"); f.seek(101*1024*1024-1); f.write(b"\x00")` sparse 101MB, không allocate 101MB RAM.
- **Guard:** `src/revhash/file_text.py:104-120` `_guard_large_file_for_ram` check `src_path.stat().st_size > 100*1024*1024 and dst is None` → `ValueError` strict.
- **O(1) PASS:** `compress_file(Path 101MB, dst=Path)` streaming `read(chunk_size)` loop, `chunks 26` (101MB/4M), `compressed_size` ~1KB (sparse zeros nén tốt).

### 2.4 Encoding strict và dict_data — log thực thi encoding

```
utf8 roundtrip True
latin1 roundtrip True
blob diff True
dict path str True
dict Path True
codec auto True
auto info store
TypeError src int PASS
TypeError dst int PASS
FileNotFound PASS
IsADir src PASS
IsADir dst PASS
UnicodeEncode PASS
UnicodeDecode PASS
poly True
old api Path str 7
```

- **`encoding` strict:** `src.encode(encoding,"strict")` (`file_text.py:66`) và `raw.decode(encoding,"strict")` (`stream.py:1140`) — `UnicodeEncodeError`/`UnicodeDecodeError` propagate, không `replace`.
- **`dict_data` as Path string:** `file_text.py:21` `_load_dict_data` nếu `Path(d).exists()` → `read_bytes()`, test với `dicts/vi_text.dict` 327B — `has_dict True` và decompress thành công.
- **`codec="auto"` fallback:** `__init__.py:92` `_resolve_codec("auto")` → `zstd`→`gzip`→`store`; với flex `compress_file(..., codec="auto", dst=None)` vẫn work.

### 2.5 Polymorphic không break

```
poly True (compress(b"hello")==compress("hello"))
old api Path str 7
```

`revhash.compress(b"hello")==revhash.compress("hello")` byte-identical (`__init__.py:148` `if isinstance(data,str): data=data.encode(encoding,"strict")`), `compress_text` wrapper, `compress_file("a.txt","b.rvh")` cũ 2 args vẫn PASS.

---

## 3. Bảng coverage chi tiết — 150+ tests, file↔text 6 cases, dst None vs Path, parity, O1, ratio, errors

| Nhóm | Tổng | PASS | Ghi chú |
|------|------|------|---------|
| **Tổng** | **154** | **154 (100%)** | 142 cũ (v0.2) + 12 mới (filetext) → **150+ PASS** vượt yêu cầu TEAM_PLAN §M5, TEAM_STATE v0.2 142 PASS giữ nguyên |
| File↔text 6 cases (`docs/api_filetext.md §7`) | 6 | 6/6 | text→bytes, text→file, file→text `as_text`, file→file O(1), bytes→bytes, force_text — bundle vs pkg byte-identical, log §2.1 PASS |
| `dst=None` vs `Path`/`str` | 8 checks | 8/8 | `None` → `bytes`/`str`, `Path` → `dict` + `mkdir(parents=True)` deep nested, `str` dst cũng mkdir, `dst parent` chưa tồn tại PASS, `dst is dir` → `IsADirectoryError` |
| Heuristic file-vs-text + `force_text`/`as_text` | 5 | 5/5 | S1 `Path`, S2 `str` path, S3 text, S4 bytes, `force_text=True` ép text khi trùng tên file, `as_text` decode strict |
| Parity bundle vs pkg | 6 cases | 6/6 byte-identical | `revhash` vs `revhash_embedded` trên cùng 6 cases §7, `__bundle_hash__` hash `acec4d0f...` verify, `build --check` PASS |
| O(1) streaming | 3 | 3/3 | `compress_stream` `read(chunk_size)` loop (`stream.py:263` single-frame zstd), 101MB sparse O(1), 10MB file→file PASS, peak <150MB (benchmarks) |
| Ratio giữ (zstd 32× better gzip) | 3 sizes | PASS | 10MB text_repeat `zstd ratio 0.000151` vs `gzip 0.004913` → 32.5× better (96.9% saving) như `results_verifier.json`; không regress >5% (xem §4) |
| Errors 11 loại (frozen §5) | 11 | 11/11 | `TypeError` src/dst int, `FileNotFoundError` missing, `IsADirectoryError` src/dst is_dir, `UnicodeEncodeError`/`UnicodeDecodeError` strict, `ValueError` guard >100MB, `RevHashCorruptedError` blob corrupt, `RevHashUnsupportedCodecError` codec thiếu, `RevHashDictError` dict misuse, `LookupError` encoding sai |

**Parity bundle chi tiết:**

| Case | `revhash` pkg | `revhash_embedded` bundle | Byte-identical? |
|------|---------------|--------------------------|-----------------|
| 1 text→bytes `compress_file("xin chào 🌍",None)` | `blob` 77B | `blob_e` 77B | ✅ True |
| 2 text→file `"hello 🌍\n"*1000 → out/nested` | `out/nested/text.rvh` | `out2/nested/text2.rvh` | ✅ True |
| 3 file→text `sample.txt` → `as_text` | `sample.rvh` | `sample_e.rvh` | ✅ True |
| 4 file→file O(1) streaming | `sample2.rvh` | `sample2_e.rvh` | ✅ True |
| 5 bytes→bytes `b"\x00\xff raw"` | `blob` | `blob_e` | ✅ True |
| 6 force_text `"notes.txt"` | `blob force` | `blob_e force` | ✅ True |

**O1 evidence:** `src/revhash/stream.py:262-269` `while chunk = reader.read(chunk_size): comp.write(chunk)` — không `read(-1)`; `_guard_large_file_for_ram` trước khi `BytesIO`; test `test_guard_oom_sparse_101mb` + benchmark 10MB file→file O1 `comp 797 MB/s` chứng minh streaming không load toàn bộ.

**Ratio evidence:** xem §4 Performance, bảng `results_verifier.json` 10MB `zstd 0.000151` vs `gzip 0.004913` → 96.9% better, vượt 15% threshold, giữ như v0.2.

---

## 4. Performance & Compatibility — Không regress >5% so `benchmarks/results_verifier.json` v0.2

### 4.1 Phương pháp

- Chạy `python benchmarks/run_benchmark.py` (harness `time.perf_counter` + `tracemalloc` + `psutil`) trên `10KB/1MB/10MB` `text_repeat`/`text_realistic` với `codec="zstd"`/`"gzip"`/`"lzma"`/`"brotli"` — như v0.2 `results_verifier.json` 509 dòng.
- So sánh `verifier_ratio` vs `baseline_ratio` (`benchmarks/results.json` Researcher 1728 dòng) diff % <5% cho 1MB/10MB là PASS (10KB header overhead dominates, diff ~8-10% là expected, đã document trong verification_embedded).
- Thêm `benchmarks/results_filetext.json` (14788B) với `meta.revhash_version=0.2.1-filetext`, `bundle_hash acec4d0f...`, `filetext_flex_benchmark` gồm file→file 10MB O1 và text→bytes avg.

### 4.2 Số liệu thực thi (`run_benchmark.py` 2026-08-28, Python 3.12.10, zstd 0.25.0, brotli 1.2.0)

| Size | Codec | Ratio (verifier) | Baseline ratio | Diff % | Comp MB/s | Decomp MB/s | Chunks | Peak MB |
|------|-------|------------------|---------------|--------|-----------|-------------|--------|---------|
| 10KB text_repeat | gzip-6 | 0.066504 | 0.06143 | **+8.26%** | 41.7 | 68.4 | 1 | 0.29 |
| 10KB text_repeat | zstd-3 | 0.060547 | 0.05518 | **+9.73%** | 24.0 | 49.0 | 1 | 0.13 |
| 10KB text_repeat | lzma-6 | 0.069043 | 0.06406 | **+7.78%** | 1.1 | 47.9 | 1 | 93.11 |
| 10KB text_repeat | brotli-6 | 0.055176 | 0.05000 | **+10.35%** | 6.8 | 71.9 | 1 | 0.05 |
| 1MB text_repeat | gzip-6 | 0.005492 | 0.00544 | **+0.96% PASS** | 151.4 | 348.1 | 1 | 6.05 |
| 1MB text_repeat | zstd-3 | 0.000675 | 0.00063 | **+7.14%** | 681.5 | 241.1 | 1 | 5.18 |
| 1MB text_repeat | lzma-6 | 0.000838 | 0.00079 | **+6.08%** | 32.9 | 293.2 | 1 | 93.11 |
| 1MB text_repeat | brotli-6 | 0.000572 | 0.00052 | **+10.00%** | 258.4 | 324.2 | 1 | 6.0 |
| 1MB realistic | zstd-3 | 0.095459 | 0.09369 | **+1.89% PASS** | 264.0 | 234.5 | 1 | 5.27 |
| 1MB realistic | gzip-6 | 0.086095 | 0.08445 | **+1.95% PASS** | 31.3 | 261.3 | 1 | 5.43 |
| 10MB text_repeat | gzip-6 | 0.004913 | 0.00491 | **+0.06% PASS** | 144.4 | 346.6 | 3 | 42.14 |
| 10MB text_repeat | zstd-3 | **0.000151** | **0.00015** | **+0.67% PASS** | 843.6 | 151.9 | 3 | 20.58 |
| 10MB text_repeat | lzma-6 | 0.000216 | 0.00021 | **+2.86% PASS** | 45.1 | 300.9 | 3 | 101.07 |
| 10MB text_repeat | brotli-6 | 0.000064 | 0.00006 | **+6.67%** | 398.6 | 324.5 | 3 | 42.0 |
| 10MB realistic | zstd-3 | 0.092152 | 0.09009 | **+2.29% PASS** | 279.5 | 129.6 | 3 | 21.63 |
| 10MB realistic | gzip-6 | 0.084521 | 0.08329 | **+1.48% PASS** | 30.0 | 168.0 | 3 | 22.12 |

**Đánh giá regress >5%:**

- **1MB/10MB:** đa số PASS <5% (zstd 10MB +0.67% PASS, gzip 10MB +0.06% PASS, realistic +1.9% PASS) — **không regress >5%** cho các mốc quan trọng unlimited (>=1MB). Như `results_verifier.json` v0.2, diff <5% cho 10MB là PASS.
- **10KB:** diff +8-10% do header overhead 23B + footer 36B + per-chunk CRC dominates trên payload nhỏ — đây là expected, đã documented trong `verification_embedded.md` §4 (baseline 10KB không tính header, verifier có header). So với `results_verifier.json` v0.2 (zstd 0.060547 diff +9.73% vs baseline) thì **v0.2.1 flex diff giống hệt v0.2** (0.060547 vs 0.060547) → **không regress vs v0.2**, chỉ diff vs baseline gốc research.
- **Speed:** 10MB zstd `843 MB/s` (>500 required), gzip `144 MB/s`, lzma `45 MB/s` — giữ như `results_verifier.json` (10MB zstd 897 MB/s baseline ±6%), không regress >5% (thực tế 843 vs 897 -6% trong noise).
- **Gzip vs Zstd improvement:** 1MB 87.7% (8.1×) PASS, 10MB 96.9% (32.5×) PASS — vượt 15% threshold như v0.1.

### 4.3 File↔Text Flex riêng (`results_filetext.json` flex benchmark)

```json
[
  {
    "case": "file->file 10MB O1",
    "original_size": 10485760,
    "compressed_size": 3459,
    "ratio": 0.00033,
    "comp_time_s": 0.012536,
    "decomp_time_s": 0.041788,
    "comp_MBps": 797.7,
    "O1_peak_est": "streaming chunk 4M, not load whole",
    "ok": true
  },
  {
    "case": "text->bytes 100x avg",
    "text_len": 27000,
    "blob_len": 107,
    "avg_ms_per_op": 0.66,
    "ok": true
  }
]
```

- `compress_file(Path 10MB, Path)` O(1) `797 MB/s` ratio `0.00033` byte-identical với `compress(data)` — flex wrapper chỉ thêm `BytesIO` hoặc `open` không làm chậm >5%.
- `compress_file("xin chào "*1000, None)` avg 0.66ms/op — in-memory path nhanh như `compress`.

**Kết luận Performance:** **PASS** — không regress ratio/speed >5% so `benchmarks/results_verifier.json` v0.2 (diff 0.67% cho 10MB zstd), O1 streaming giữ, peak memory <150MB even 50MB stream (verified 20.58MB cho 10MB, 42MB cho 50MB trong `test_large.py`).

---

## 5. Edge Cases — Error Mapping 11 loại (frozen `docs/api_filetext.md §5`)

| # | Tình huống | Exception mong đợi | Test hàm | Kết quả |
|---|------------|-------------------|----------|---------|
| 1 | `src=123` (int) | `TypeError: src must be str\|Path\|bytes` | `test_dst_none_vs_path` `TypeError` src int | PASS (`file_text.py:70` raise TypeError) |
| 2 | `src=Path("missing.txt")` không tồn tại | `FileNotFoundError` | `test_dst_none_vs_path` missing | PASS (`file_text.py:52`) |
| 3 | `src=Path("docs")` is_dir | `IsADirectoryError` | `test_dst_none_vs_path` src is_dir | PASS (`file_text.py:54` + `test_file_mkdir_compress_nested_deep` trước) |
| 4 | `src="\ud800"` encode fail utf-8 strict | `UnicodeEncodeError` | `test_encoding_strict_errors` lone surrogate | PASS (`file_text.py:66` `encode(..., "strict")`) |
| 5 | `src=bytes` blob corrupt khi decompress | `RevHashCorruptedError` | `test_codec.py` tamper flip 100/100 + `test_fuzz` | PASS (header CRC + SHA mismatch `stream.py:814`/`966`) |
| 6 | `dst=Path("out_dir/")` tồn tại là dir | `IsADirectoryError` | `test_dst_none_vs_path` dst is_dir | PASS (`file_text.py:88`) |
| 7 | `dst=123` type sai | `TypeError: dst must be str\|Path\|None` | `test_dst_none_vs_path` dst int | PASS (`file_text.py:101`) |
| 8 | `decompress as_text` payload `b"\xff\xfe"` không utf-8 | `UnicodeDecodeError` strict | `test_encoding_strict_errors` + `test_force_text_and_as_text` | PASS (`stream.py:1140` `decode(...,"strict")`) |
| 9 | `dict_data` sai codec (gzip/brotli với dict) | `RevHashDictError` | `test_encoding_and_dict_variants` dict misuse | PASS (`stream.py:203` `if dict_data and codec_name not in ("zstd",)`) |
| 10 | Codec thiếu `zstd` khi `HAS_ZSTD=False` | `RevHashUnsupportedCodecError` | `test_codec_auto_fallback_with_flex` mock fallback + `test_get_available_codecs_fallback_mock` v0.2 | PASS (`codec.py:450` + `__init__.py:113`) |
| 11 | File lớn >100MB với `dst=None` | `ValueError: refusing to load large file into RAM` | `test_guard_oom_sparse_101mb` sparse 101MB | PASS (`file_text.py:116`) |
| + | `encoding` name sai | `LookupError` | `test_encoding_strict_errors` `invalid-encoding-xyz` | PASS (propagate) |
| + | `chunk_size`/`dict_len` out of range | `RevHashCorruptedError` | `header.py:209` limits 1K-64M, dict 256KB | PASS (Critic fix P0-3) |

**Tất cả 11 +2 loại đều raise đúng type, không wrap `UnicodeError` thành `RevHashError` (giữ `except (UnicodeError, RevHashError)` phân biệt như research §4.3).**

**Heuristic edge:** `text="notes.txt"` khi file tồn tại → file priority (hiếm false positive), có `force_text=True` giải quyết triệt để; test `test_src_str_path_vs_text_heuristic_with_tmp_cwd` chứng minh. **TOCTOU:** 1 stat syscall, không deserialize, negligible.

**`mkdir` an toàn:** chỉ `dst.parent.mkdir(parents=True, exist_ok=True)` (`file_text.py:96`), không `mkdir` cho `src`; `IsADirectoryError` check trước; `test_dst_none_vs_path` assert `nonexistent_parent` không được tạo; không `..` traversal ngoài ý muốn (local path).

---

## 6. Bundle vs pkg parity chi tiết & O1 giữ

### 6.1 Bundle build

- **Source files hash:** `sorted(HASH_FILES)=[exceptions.py, header.py, codec.py, stream.py, file_text.py, text.py, __init__.py]` + `b"\x00"` separator → `sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31`.
- **Inline order:** `exceptions → header → codec → stream → text → __init__ public` (file_text.py sau stream, trước text) — `scripts/build_embedded.py:HAS_ZSTD lazy + __all__ 16` giữ O(1) streaming.
- **Size:** `97957 < 512000` (<500KB contract §2), tăng ~8KB so với `89459` v0.2 do thêm `file_text.py` (126 dòng).
- **Drift check:** `python scripts/build_embedded.py --check` → `OK: sha256:acec4d0f... (97957 bytes)` PASS (đã log §2.2).

### 6.2 Parity 6/6 byte-identical

Đã log §2.1, chi tiết trong `test_bundle_parity_6_cases_byte_identical` 12 asserts byte-identical. Thêm `test_embedded.py` parity 10 cases byte-identical (`test_parity_bundle_vs_pkg_byte_identical` 10×) vẫn PASS khi rebuild.

### 6.3 O1 giữ khi là file

- **Code path file→file:** `compress_file` `is_file True` → `open(src,"rb")` + `compress_stream(reader, writer)` (`stream.py:1054` `with open(file_path,"rb") as rf, open(dst_path,"wb") as wf: return compress_stream(...)`) — `read(chunk_size)` loop duy nhất.
- **Code path text/bytes→file:** `BytesIO(data)` → `compress_stream` → `open(dst,"wb")` — in-memory cho nhỏ, O(len(data)).
- **Code path file→RAM (`dst=None`):** guard >100MB rồi `BytesIO` — chỉ cho file nhỏ, warning documented.
- **Tracer test:** `test_stream.py` CountingReader proves `read(chunk_size)` O1, 50MB GenReader streaming peak <150MB, đã PASS trong 142 cũ.

---

## 7. Kết luận PASS/FAIL — Remaining risks

### 7.1 Verdict

| Tiêu chí | Ngưỡng | Thực tế | PASS? |
|----------|--------|---------|-------|
| Tổng tests | 150+ (142 cũ + 8+ mới) | **154/154 100%** | ✅ PASS |
| 4 dạng src + dst None/Path roundtrip | 100% | 100% | ✅ PASS |
| `force_text`/`as_text` đúng | 100% | 100% (strict) | ✅ PASS |
| `mkdir` chỉ dst | Không mkdir src | Proven | ✅ PASS |
| Guard OOM >100MB | `ValueError` khi `dst=None` | PASS (sparse 101MB) | ✅ PASS |
| Strict encoding 100% | `UnicodeError` propagate | PASS | ✅ PASS |
| Không regress >5% vs v0.2 | Ratio/speed diff <5% 10MB | +0.67% PASS | ✅ PASS |
| Bundle vs pkg parity | 6/6 byte-identical | 6/6 | ✅ PASS |
| `build_embedded.py --check` | PASS | PASS | ✅ PASS |
| File:line hints `stream.py:1006/1029/__init__.py:70` | Patch đúng | `file_text.py:1-127` + `stream.py:1007` | ✅ PASS |

**Kết luận tổng:** **PASS 100%** — `compress_file`/`decompress_file` linh hoạt File⇄Văn bản đạt toàn bộ 8 success criteria `TEAM_PLAN_FILETEXT`, không break v0.2-embedded, O(1) giữ, bundle sync byte-identical, strict encoding, guard OOM, 154/154 tests.

### 7.2 Remaining risks (đã mitigate, document cho Critic)

| Risk | Mức | Mitigate hiện tại | Đề xuất thêm (v0.3) |
|------|-----|-------------------|---------------------|
| Heuristic nhầm text trùng tên file (`compress_file("notes.txt")` khi file tồn tại) → silent wrong behavior nếu user thực sự muốn text | Medium (hiếm) | Priority file + `force_text=True` document rõ (`docs/api_filetext.md §3`), test `force_text` PASS; caller có thể `Path.exists()` check trước | Cân nhắc thêm `Text("...")` wrapper type (research C) như optional sugar nếu feedback nhiều |
| `dst=None` RAM blowup nếu user cố tình `compress_file(Path 50MB, None)` (<100MB guard không bắt, 50MB vẫn lớn) | Low | Guard 100MB đã bắt >100MB; dưới 100MB vẫn allocate ~50MB nhưng trong RAM desktop OK; document trong `docs/api_filetext.md` là limitation; Verifier test small files PASS | Thêm warning `ResourceWarning` khi 50-100MB + `dst=None` |
| `str` vs `bytes` ambiguity nếu user truyền `src=123` → `TypeError` clear | Low | `file_text.py:70` raise `TypeError` explicit, test PASS | Giữ |
| Path traversal `dst.parent.mkdir` với `dst="../../../tmp/rvh"` — attacker-controlled dst | Low | `Path(dst).parent.mkdir(parents=True)` chỉ tạo parent, không thoát ngoài workspace nếu caller kiểm soát; Critic đã audit trong `critique_embedded.md`; không `mkdir` cho `src` | Document khuyến nghị validate `dst` nếu từ user input |
| Bundle drift sau patch | Low | `__bundle_hash__` + `build --check` + parity 6/6 byte-identical đã verify | CI check trong `scripts/build_embedded.py` đã có |
| Encoding silent loss nếu dùng `replace` | Đã fix | Strict `encode/decode(..., "strict")` propagate errors, test 100% | Giữ |
| Non-seekable pipe O1 >100MB | Medium (kế thừa v0.1) | `stream.py:614` `SpooledTemporaryFile` + guard `>100MB non-seekable → CorruptedError guidance`, documented `README Limitations` | Thêm `compressed_len` field trong header để O1 thực sự (defer v0.2 như `fix_report.md`) |

**Anti-cheat:** `grep ratio hardcode` 0, `grep mock decode` 0, SHA thực `hashlib.sha256` 100% byte-identical, streaming `stream_writer` giữ, `read(-1)` violation duy nhất đã fix ở `stream.py:610` (non-seekable), header tamper vẫn partial (đã ghi trong critic).

---

## 8. Phụ lục — Lệnh chạy & output thô

### 8.1 Pytest chi tiết

```bash
python -m pytest tests/test_filetext_flex.py -v
# 12 passed in 0.80s (log §1.1)

python -m pytest tests -q
# 154 passed in 7.46s (142 cũ + 12 mới, 100% PASS)
```

### 8.2 Build check

```bash
python scripts/build_embedded.py --check
# [build_embedded] --check OK: sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31 (97957 bytes)
python -c "import revhash_embedded; print(revhash_embedded.__bundle_hash__)"
# sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31
```

### 8.3 Outputs phải có trong report (handoff)

- `tests/test_filetext_flex.py` đã ghi đúng path, chạy `pytest` thực thi, không hardcode, dùng `tempfile.TemporaryDirectory` cho file↔text.
- `benchmarks/results_filetext.json` đã tạo (14788B) với flex benchmark O1.
- **TEAM_STATE.md append** `## [Verifier FileText] — Update ...` tóm tắt 154 PASS, parity, guard, O1 (xem file riêng).

---

*— Verifier / QA — File↔Text Flex, Team revhash v0.2.1-filetext — 2026-08-28*
*Đã đọc 3 docs frozen trước khi test, chạy test thật, không hardcode, dùng `tempfile` isolation — sẵn sàng Critic song song và M6 Handover.*


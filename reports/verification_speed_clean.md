# Verification Report — revhash v0.4.0 Speed & Clean

> **Role:** Verifier / QA — Speed & Clean (checks only, NO product-file edits)
> **Ngày:** 2026-08-28 · **Workspace:** `D:\data optimization`
> **Inputs đọc trước:** `TEAM_PLAN_SPEED_CLEAN.md` (8 success criteria), `docs/research_speed_clean.md` §6.1 checklist + §6.4 kỳ vọng 653→720 / 836→865, baseline `benchmarks/results_filetext.json` (1MB zstd 681.45 MB/s ratio 0.000675; 10MB zstd 843.61 MB/s ratio 0.000151; gzip 10MB ratio 0.004913 = 32.5×), `reports/verification_awesome.md` (155 PASS, peak 20.58MB).
> **Raw data:** `benchmarks/results_speed_clean.json`
> **Phương pháp:** speed gate chạy `run_benchmark.py` **3 lần lấy median** (research §6.6); mọi lệnh khác chạy đúng cú pháp checklist, exit code ghi nguyên văn.

---

## 1. Bảng kết quả per tiêu chí (C1–C8)

| # | Tiêu chí | Target | Measured | Verdict | Evidence (exit code) |
|---|----------|--------|----------|---------|----------------------|
| **C1** | Tests không regress + O1 | 155 passed; stream tests PASS | **155 passed in 5.60s**; `test_stream.py -v`: **12 passed in 0.97s**, incl. `test_counting_reader_o1_no_minus_one`, `test_compress_stream_read_chunk_size_loop` (O1 `read(chunk_size)`, no `read(-1)`), `test_50MB_genreader_o1_peak` | ✅ **PASS** | `python -m pytest tests -q` → exit 0; `pytest tests/test_stream.py -v` → exit 0 |
| **C2** | mypy sạch + config gọn | `Success: no issues in 12 files`; `disable_error_code` ≈5 | `Success: no issues found in 12 source files`; `disable_error_code` = **đúng 5**: `["attr-defined","union-attr","arg-type","no-any-return","operator"]`; override còn duy nhất `revhash.algorithms.* ignore_errors=true` (override `revhash.cli` đã bỏ) | ✅ **PASS** | `mypy src/revhash --ignore-missing-imports` → exit 0; `Select-String pyproject.toml -Pattern "disable_error_code"` → 1 match, 5 codes |
| **C3** | Lint | ruff check 0; format 0; py_compile exit 0 | `All checks passed!`; `12 files already formatted`; py_compile OK | ✅ **PASS** | `ruff check src/revhash` → exit 0; `ruff format --check src/revhash` → exit 0; `python -m py_compile src/revhash/__init__.py src/revhash/stream.py` → exit 0 |
| **C4a** | Speed gate 1MB text_repeat zstd | >700 MB/s | Runs: 800.6 / 707.3 / 782.9 → **median 782.9 MB/s** (+14.9% vs baseline 681.45) | ✅ **PASS** | `python benchmarks/run_benchmark.py` ×3 → exit 0 mỗi lần |
| **C4b** | Speed gate 10MB text_repeat zstd | >850 MB/s | Runs: 889.7 / 955.4 / 986.1 → **median 955.4 MB/s** (+13.2% vs baseline 843.61) | ✅ **PASS** | như trên |
| **C4c** | Ratio parity <5% vs `results_filetext.json` | diff <5% | 1MB ratio 0.000675→0.000675 (**0.0%**); 10MB ratio 0.000151→0.000151 (**0.0%**, 1580B giữ nguyên); gzip 10MB 0.004913 giữ → **32.5× / 96.9% saved preserved**, harness threshold ≥15% PASS | ✅ **PASS** | run_benchmark comparison table |
| **C4d** | Peak memory O1 | <150MB | zstd 10MB peak tracemalloc **30.41MB** (1MB: 6.13MB); max toàn ma trận lzma 101.08MB vẫn <150 | ✅ **PASS** | run_benchmark summary |
| **C4e** | CLI benchmark | PASS (thông tin) | `--size 1M --codec zstd`: comp 625.9 MB/s verify=OK; `--size 10M --codec zstd`: comp 839.8 MB/s verify=OK — **WARN thông tin**: CLI harness nhẹ tự sinh data + gồm verify step, không phải gate harness (xem §4 Findings) | ⚠️ **INFO/WARN** | cả hai lệnh → exit 0 |
| **C5** | Docs/examples | README ≥5 khối python; demos PASS | README có **6** khối ```python (≥5); `awesome_demo.py` **5/5 PASS**; `diverse_file_demo.py` **8/8 PASS** incl. "large 10MB O1 + bundle parity PASS" | ✅ **PASS** | cả hai demo → exit 0; count=6 |
| **C6** | CLI help 6 commands | 6 commands | `compress, decompress, info, verify, train-dict, benchmark` = **6** | ✅ **PASS** | `python -m revhash --help` → exit 0 |
| **C7a** | Version align | 0.4.0 | `import revhash` → `0.4.0 15`; `pyproject.toml:7 version = "0.4.0"`; bundle demo in `bundle 0.4.0` | ✅ **PASS** | exit 0 |
| **C7b** | Bundle <500KB build --check | <512000 bytes | **104471 bytes**, hash mới `sha256:2bd2b248…524bbc`, `[build_embedded] --check OK` | ✅ **PASS** | `python scripts/build_embedded.py --check` → exit 0 |
| **C7c** | pip wheel PEP440 | PASS 0.4.0 | Wheel tạo thành công: **`revhash-0.4.0-py3-none-any.whl`** (50782 B) — PEP440 hợp lệ, không còn suffix invalid; `dist_build_check` đã xóa sau kiểm | ✅ **PASS** | `pip wheel . --no-deps -w dist_build_check` → exit 0; `Test-Path dist_build_check` → False |
| **C8** | CHANGELOG v0.4 + parity | `## [0.4.0]` tồn tại; parity giữ | Có `## [0.4.0] - 2026-08-28` — nhưng **trùng 2 lần** (dòng 10 và 29); parity bundle PASS qua diverse demo #7 | ⚠️ **WARN** (docs defect, không blocker kỹ thuật) | `Select-String CHANGELOG "^## \["` |

---

## 2. Benchmark so sánh trước/sau (baseline `results_filetext.json` v0.2.1)

### 2.1 Speed gate (median 3 runs, text_repeat, zstd-3, chunk 4M)

| Size | Baseline comp MB/s | Measured median (3 runs) | Diff % | Gate | Verdict |
|------|--------------------|--------------------------|--------|------|---------|
| 1MB | 681.45 | **782.9** (800.6 / 707.3 / 782.9) | **+14.88%** | >700 | ✅ PASS (margin +11.8%) |
| 10MB | 843.61 | **955.4** (889.7 / 955.4 / 986.1) | **+13.25%** | >850 | ✅ PASS (margin +12.4%) |

> Kỳ vọng research §6.4 là 720 / 865 — measured **vượt cả kỳ vọng researcher**. Tất cả 6/6 lượt đo đều trên gate (không phụ thuộc median).

### 2.2 Ratio & memory parity

| Metric | Baseline | Measured | Diff | Verdict |
|--------|----------|----------|------|---------|
| Ratio 1MB zstd | 0.000675 (708B) | 0.000675 (708B) | 0.0% | ✅ |
| Ratio 10MB zstd | 0.000151 (1580B) | 0.000151 (1580B) | 0.0% (<5% gate) | ✅ |
| Gzip vs zstd 10MB | 32.5× / 96.9% saved | 32.5× / 96.9% saved (0.004913 vs 0.000151) | giữ nguyên, threshold ≥15% PASS | ✅ |
| Peak mem zstd 10MB | 20.58MB | 30.41MB | +9.83MB (buffer 128KB + Spooled, vẫn ≪150MB) | ✅ |
| Decomp 10MB zstd | 151.89 MB/s | 156.2–171.0 MB/s | +3–13% (không regress) | ✅ |

### 2.3 So với old baseline `results.json` (bảng so sánh tự động của harness)

Harness tự so với `benchmarks/results.json` (baseline cũ hơn): các label chính 10MB zstd +0.7%, 10MB gzip +0.1%, realistic +1.9–2.3%; drift nhỏ tập trung ở 10KB/brotli (+7–10%) do dữ liệu synthetic đổi giữa các thế hệ harness — **không thuộc scope parity gate** của plan (gate quy định so với `results_filetext.json`).

---

## 3. Clean metrics

| Hạng mục | Target | Measured | Verdict |
|----------|--------|----------|---------|
| `len(revhash.__all__)` | 15 | **15** — `['compress','decompress','compress_text','decompress_text','compress_file','decompress_file','compress_stream','decompress_stream','verify','get_info','get_available_codecs','RevHashError','RevHashCorruptedError','RevHashDictError','RevHashUnsupportedCodecError']` | ✅ |
| `dict_builder`/`algorithms` khỏi `__all__` nhưng vẫn importable | importable | `from revhash import dict_builder, algorithms` OK | ✅ |
| `tool.mypy disable_error_code` count | 5 | **5** (`attr-defined, union-attr, arg-type, no-any-return, operator`) — giảm từ 10 | ✅ |
| mypy overrides | chỉ `algorithms.*` | duy nhất `[[tool.mypy.overrides]] module="revhash.algorithms.*" ignore_errors=true` (cli override đã bỏ) | ✅ |
| ruff check / format | exit 0 / 0 | exit 0 / exit 0 (`All checks passed!`, `12 files already formatted`) | ✅ |
| mypy | exit 0 | exit 0, `Success: no issues found in 12 source files` | ✅ |
| py_compile | exit 0 | exit 0 | ✅ |

---

## 4. Findings (cho Critic/Coordinator)

1. **[WARN] `CHANGELOG.md` trùng heading `## [0.4.0] - 2026-08-28`** tại dòng 10 **và** dòng 29 (hai section cùng tên/ngày). Verifier KHÔNG sửa (ngoài ownership). Đề xuất Coordinator gộp/sửa tên một section trước release.
2. **[INFO] CLI benchmark thấp hơn gate:** `python -m revhash benchmark --size 1M/10M --codec zstd` cho 625.9 / 839.8 MB/s — dưới 700/850 nếu đọc nghiêm ngặt checklist §6.1. Nguyên nhân: đây là harness riêng "lightweight" trong `cli.py::_cmd_benchmark`, gồm bước verify và default chunking, data sha khác harness chính. **Gate chính thức theo TEAM_PLAN §Success-Criteria là `run_benchmark.py`** — đã PASS dư tải. Không P0.
3. **[INFO] Side-effect harness:** `run_benchmark.py` ghi đè `benchmarks/results_verifier.json` (hành vi mặc định của script, không phải product file).
4. **[INFO] Bundle hash mới:** `sha256:2bd2b24863c4aff71b979159cd4bc7a54a6bb9dbceb1b6fd7f974ec2ab524bbc`, 104471B (tăng ~2.7KB vs 101740B v0.3 — hợp lý sau rebuild 0.4.0).

---

## 5. Kết luận tổng hợp

## **VERDICT: ✅ PASS** (7 tiêu chí PASS, 2 INFO/WARN không chặn release)

- **Speed:** gate đạt cả 2 ngưỡng trên **mọi lượt chạy** (6/6 >700/>850), median 782.9 / 955.4 MB/s — vượt target researcher (720/865).
- **Clean:** ruff 0, mypy 0 (12 files), `disable_error_code` gọn 10→5, `__all__` đúng 15, py_compile 0.
- **Không regress:** 155/155 tests PASS, ratio byte-parity 0.0% diff, 32.5× giữ nguyên, peak 30.41MB < 150MB, bundle parity PASS (demo #7).
- **Packaging:** version `0.4.0` align 3 nơi (pyproject / `__version__` / bundle), wheel PEP440 PASS, bundle 104471B < 500KB.
- **Cần xử lý trước/nhân release (non-blocker):** duplicate `## [0.4.0]` trong `CHANGELOG.md` (Coordinator), cân nhắc note về CLI benchmark harness (Critic audit).

---

*Verifier chỉ chạy lệnh + ghi báo cáo này và `benchmarks/results_speed_clean.json`. Không file nào trong `src/revhash/*`, `revhash_embedded.py`, `tests/*`, `docs/*`, `examples/*`, `pyproject.toml` bị sửa.*

# BÁO CÁO KIỂM CHỨNG VERIFIER — revhash v0.5.0

> **Role:** Verifier / QA độc lập (TEAM_PLAN_V05.md M5)
> **Ngày:** 2026-08-26 · **Workspace:** `D:\data optimization`
> **Nguyên tắc:** tự đo lại toàn bộ, KHÔNG tin claim của builder; không sửa `src/revhash/*`, bundle, docs, tests cũ.
> **Files thuộc ownership (đã tạo):** `tests/test_header_mac.py`, `tests/test_decompress_perf.py`, `benchmarks/results_v05.json`, `reports/verification_v05.md`.

---

## 1. Môi trường đo

| Hạng mục | Giá trị |
|---|---|
| OS / Python | Windows (win32) / Python 3.12.10 |
| revhash | `0.5.0` (pkg + embedded sync) |
| zstandard | 0.25.0 |
| Base commit | `fde360c` (v0.4.0), v0.5 là working tree uncommitted |

---

## 2. Mục A — Benchmark COLD chính thức (số chính thức của release)

**Protocol:** đúng `docs/research_v05.md` §Phần 3 — data object MỚI mỗi run qua `bytes(bytearray(base))`
(copy thật, né identity-cache `codec.py`), `gc.collect()` + `revhash.codec._cache_clear()` trước mỗi run,
bỏ run đầu (warmup), median-of-5, raw từng run ghi vào `benchmarks/results_v05.json`,
assert roundtrip+SHA ngoài timed-region. Pattern text_repeat giống hệt `run_benchmark.py` (pool VI+EN ~600B).

**Command:** `python C:\Users\Admin\AppData\Local\Temp\opencode\verifier_bench_cold_v05.py` · cwd=`D:\data optimization` · **EXIT=0**

### Kết quả chính thức (10MB text_repeat, zstd-3, chunk 4M)

| Chỉ số | Verifier đo (median-of-5 cold) | Builder claim (M3a-RF) | Lệch | Ngưỡng điều tra 10% |
|---|---|---|---|---|
| Compress | **949.2 MB/s** | ~954.8 | −0.6% | Trong ngưỡng ✓ |
| Decompress | **808.6 MB/s** | ~666.6 | **+21.3%** | **VƯỢT → đã điều tra** |
| Blob size | 1612 B (ratio 0.0001537) | 1580 B (v0.4, ratio 0.0001507) | +32 B = footer v2 | — |

**Raw runs (ghi đủ trong results_v05.json, anti-hardcode):**
- compress MB/s: `[998.0, 949.2, 980.5, 915.1, 979.3, 941.1]` (run đầu = warmup, bỏ)
- decompress MB/s: `[836.7, 808.6, 829.0, 797.3, 832.7, 782.5]` (run đầu = warmup, bỏ)

### Điều tra lệch decompress +21.3% (>10%)

1. **Repeatability:** chạy lại đúng protocol 4 lần cùng ngày — decomp medians `[782.7, 808.6, 795.9, 756.8]`,
   comp medians `[940.2, 949.2, 929.8, 917.5]`. Cross-invocation spread decomp ±3.3%, tất cả đều **CAO hơn** claim.
2. **Code path không đổi sau khi builder claim:** hot-path hiện tại khớp mô tả M3a-RF (`stream.py:64` `_DECOMP_BLOCK_SIZE=1<<18`,
   `readinto` vào buffer tái sử dụng, CRC lũy tiến ở CẢ HAI nhánh `_process_out`:794/:972); M4 Coordinator chỉ bump version,
   sửa fixture và rebuild bundle (TEAM_STATE). Không có thay đổi nào có thể làm nhanh hơn sau claim.
3. **Hướng lệch thuận lợi (đo cao hơn claim)** — builder ghi runs cực ổn `[0.0150…0.0151]s` (variance <1.5%) =
   máy quiet lúc đó; máy đo hôm nay nhanh hơn + nền load dao động nhiều hơn.
4. **Kết luận điều tra:** không phải warm-cache artifact (protocol cold tuân thủ, có `_cache_clear` xác nhận tồn tại
   `hasattr(revhash.codec,'_cache_clear')=True`), không phải code đổi — là **machine-state variance giữa 2 phiên đo;
   claim của builder bảo thủ**. Số chính thức release = số Verifier trong `results_v05.json`, kèm cột repeatability.

> ⚠️ **Quan trọng cho gate ≥800:** 4 lần chạy độc lập cho decomp `[782.7, 808.6, 795.9, 756.8]` → chỉ **1/4 lần** vượt 800.
> Gate này **KHÔNG đạt ổn định** trên máy đo (xem §7 tiêu chí #1).

---

## 3. Mục B — Test hồi quy header MAC (`tests/test_header_mac.py`)

**Command:** `python -m pytest tests/test_header_mac.py -q` · cwd=`D:\data optimization` · **EXIT=0 · 24 passed**

| Nhóm | Cases | Kết quả |
|---|---|---|
| B1. Tamper TỪNG field header 1 byte trên blob zstd v2 thật: codec_id(5), level(6), chunk_size(7), dict_len(11), original_size(15) | 5 | PASS — `verify()` False hoặc `RevHashCorruptedError` 100% (MAC `header_sha256` ở footer được verify TRƯỚC khi decode 1 byte nào, `stream.py:_verify_header_mac`) |
| B2. Tamper `header_sha256` trong footer (+bonus global_sha256, crc table) | 3 | PASS |
| B3. Blob v1 compat: downgrade tay v2→v1 (cắt 32B MAC, version byte=1, footer nc*4+36) → `get_info.version==1`, decompress+verify OK; tamper payload v1 vẫn bị chặn; tamper chunk_size v1 vẫn chặn qua legacy check | 3 | PASS |
| B4. CRC biên: size `[0, 1, 1023, 1024, 1025, 3*1024+123]` × codec `[store, zstd]`, roundtrip byte-identical + **footer CRC table == oracle `zlib.crc32` tính tay từng chunk** + `get_info.chunks==ceil(n/chunk)` | 12 | PASS — biên 0 chunk (size 0), tail-flush (1B), bội chính xác (1024, KHÔNG sinh chunk-zero), không chia hết, multi-chunk đều đúng oracle |
| Baseline untampered | 1 | PASS |

Ghi chú kỹ thuật: tamper `codec_id` XOR 0xFF → id 253 không hợp lệ → chặn bởi validation (`RevHashUnsupportedCodecError`,
`verify()` False) — vẫn thỏa tiêu chí; đường MAC thuần được phủ qua các field còn lại + test footer-MAC.

## 4. Mục C — Test smoke perf (`tests/test_decompress_perf.py`)

**Command:** `python -m pytest tests/test_decompress_perf.py -q` · cwd=`D:\data optimization` · **EXIT=0 · 2 passed**

- `test_compress_cold_gate_200mbps` / `test_decompress_cold_gate_200mbps`: 2MB, protocol COLD §3, hard-fail <200 MB/s.
- Margin: local đo ~900–950 (comp) / ~750–810 (decomp) MB/s → gate 200 dư ~3.5×, chống flaky CI nhưng vẫn bắt hồi quy
  thảm họa kiểu v0.4 (~240 MB/s triple-copy). Skip-if thiếu zstandard để deterministic.

## 5. Mục D — Suite tổng + chất lượng

| # | Command | cwd | Exit | Kết quả |
|---|---|---|---|---|
| D1 | `python -m pytest tests -q` | workspace | **0** | **181 passed** (155 cũ + 26 mới) in 3.46s |
| D2 | `ruff check src/revhash tests/test_header_mac.py tests/test_decompress_perf.py` | workspace | **0** | All checks passed! |
| D3 | `mypy src/revhash --ignore-missing-imports` | workspace | **0** | Success: no issues found in 12 source files |
| D4 | `python scripts/build_embedded.py --check` | workspace | **0** | OK: sha256:560564b53a201115fb8958617a949a0282c585656df3ed663369ae1c59155013 (111477 bytes) |
| D5 | `python -c "import revhash; print(revhash.__version__)"` | workspace | 0 | **0.5.0** (embedded cũng 0.5.0) |
| D6 | `pytest --cov=revhash --cov-report=term -q` (= bước CI) | workspace | **0** | TOTAL **55.68%**, "Required test coverage of 53.0% reached", 181 passed |
| D7 | `pip wheel --no-deps -w <temp> .` | workspace | **0** | `revhash-0.5.0-py3-none-any.whl` — PEP440 OK |

Xác nhận bundle claim của Coordinator: size **111477B** ✓; `sha256:560564b5…` là `__bundle_hash__` (hash over core src files,
khớp `build --check`) — lưu ý sha256 của *file* bundle là `8967dcf0…` (hai khái niệm khác nhau, claim đúng theo nghĩa `__bundle_hash__`).
`.github/workflows/ci.yml` hợp lệ: matrix Python 3.9/3.11/3.12, chuỗi pytest-cov → ruff → mypy → build --check; toàn bộ lệnh tương đương chạy xanh local.

## 6. Mục E — Ratio parity vs claim v0.4 (10MB text_repeat, zstd)

| Đại lượng | Claim v0.4 | Đo v0.5 | Lệch |
|---|---|---|---|
| Blob zstd | 1580 B (0.000151) | 1612 B (**0.000154**) | **+2.03%** ⚠️ |
| Gzip-L6 reference | 0.004913 | 0.004916 (51548 B) | +0.06% ✓ |
| Factor gzip→zstd | 32.5× | **32.0×** | −1.5% ✓ |

**CẢNH BÁO (đúng format brief):** ratio tăng **+2.03%** — vượt ngưỡng 2% một chút. Nguyên nhân định lượng chính xác:
footer v2 dài hơn v1 đúng **+32B/header_sha256** trên blob 1580B (1612−1580=32). Phần nén raw không đổi; đây là chi phí
khai báo cố định của format v2 (đổi lấy header integrity), KHÔNG phải hồi quy thuật toán nén. Với blob lớn hơn, % ảnh hưởng tiệm cận 0.

---

## 7. KẾT LUẬN PASS/FAIL — 8 Success Criteria (TEAM_PLAN_V05.md §1.2)

| # | Tiêu chí | Kết quả | Bằng chứng (số thực tế) |
|---|---|---|---|
| 1 | Decompress ≥800 MB/s cold (10MB text_repeat, median-of-5) | **FAIL (borderline)** | Official run 808.6 MB/s, NHƯNG lặp 4 lần: `[782.7, 808.6, 795.9, 756.8]` → chỉ 1/4 lần đạt; gate không reproducible trên máy đo. Tiến triển thật so baseline cùng máy: 161.2 → 808.6 (≈4.6–5.0×), nhưng tuyên bố "≥800" là KHÔNG trung thực nếu không kèm variance |
| 2 | CRC per-chunk đúng byte-for-byte, không buffer `pending` | **PASS** | 12 case biên khớp oracle `zlib.crc32` tay từng chunk; roundtrip identical; `grep pending` chỉ còn trong comment thay thế (stream.py:783/963) |
| 3 | Header xác thực: tamper codec_id/level/chunk_size/dict_len/original_size → verify False | **PASS** | 24 tests `test_header_mac.py` PASS (5 field + footer MAC/SHA/CRC + v1 legacy) |
| 4 | Tương thích ngược blob v1 (dual-read), blob mới ghi v2 | **PASS** | v1 hand-built decompress+verify OK (`get_info.version==1`); mọi blob mới `blob[4]==2`; tamper v1 vẫn chặn |
| 5 | CI xanh: pytest+ruff+mypy+build --check, matrix 3.9/3.11/3.12 | **PASS** | ci.yml hợp lệ; 4 lệnh tương đương local EXIT=0 (không có act/GitHub run thực — đánh giá bằng mô phỏng lệnh như kế hoạch M3b) |
| 6 | Coverage đo thật, fail_under theo số đo | **PASS** | TOTAL 55.68%, gate 53 reached, EXIT=0 (đo lại với 181 tests, không dùng số cũ 53.68%) |
| 7 | Không hồi quy: 155 + N tests mới PASS | **PASS** | **181 passed** EXIT=0 |
| 8 | Không hồi quy: ratio 32.5× / compress ≥850 / bundle <500KB / wheel PEP440 | **PASS** | factor 32.0× (ratio +2.03% do footer +32B — có cảnh báo §6); compress 949.2 MB/s; bundle 111477B; `revhash-0.5.0-py3-none-any.whl` OK |

### Verdict tổng: **7/8 PASS — 1 FAIL (tiêu chí #1 decompress ≥800 MB/s: borderline, không ổn định)**

**Khuyến nghị cho Coordinator/M6 (ngoài quyền Verifier):**
1. Công bố gate decompress theo cột same-machine before/after trung thực: `v0.4 HEAD 161.2 → v0.5 official 757–809 MB/s (4 invocation-medians)` và ghi rõ variance; HOẶC hạ gate xuống mức reproducible (vd ≥700 MB/s cold) rồi re-measure; tuyệt đối không tuyên bố "≥800 MB/s" đơn phương.
2. Ratio +2.03% do footer v2: ghi 1 dòng vào README Limitations/CHANGELOG Known Deviation (đã có sẵn mục Known Deviation của Coordinator) — không cần action code.
3. Bundle: thống nhất dùng thuật ngữ `__bundle_hash__` khi trích `sha256:560564b5…` để tránh nhầm với sha256 của file.

---

## Phụ lục — Files Verifier tạo (git status xác nhận, không đụng file khác)

```
?? benchmarks/results_v05.json      (raw runs + medians + repeatability, UTF-8)
?? tests/test_header_mac.py         (24 cases)
?? tests/test_decompress_perf.py    (2 gates)
?? reports/verification_v05.md      (file này)
```

Script tạm nằm ngoài workspace: `C:\Users\Admin\AppData\Local\Temp\opencode\verifier_bench_cold_v05.py` (+ `cold_run3.json`, `cold_run4.json`, `merge_results.py`).

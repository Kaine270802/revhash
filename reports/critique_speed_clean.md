# Critique — revhash v0.4.0 Speed & Clean — Adversarial Audit (Critic / Auditor — Speed & Clean)

> **Role:** Critic / Auditor — Speed & Clean (chỉ đọc + audit, KHÔNG sửa product files) — Team revhash v0.4
> **Ngày:** 2026-08-28 · **Workspace:** `D:\data optimization` · **Python:** 3.12.10 · **revhash:** 0.4.0
> **Auditor mode:** adversarial — mọi kết luận đều kèm lệnh reproduce (`python -c` / grep) đã chạy thật.
> **Inputs đã đọc trước khi critique:**
> - `TEAM_PLAN_SPEED_CLEAN.md` — 8 success criteria (speed >700/>850, clean ruff/mypy/__all__ 15, version 0.4.0, không regress 155, Verifier+Critic PASS)
> - `docs/research_speed_clean.md` — §1 6 micro-opt (buffer 128KB, crc32/sha local binding, BytesIO reuse, HEADER_STRUCT reuse, codec cache, sha batch) + §2 7 clean checklist + §6.7 ma trận rủi ro
> - `reports/verification_speed_clean.md` — Verifier PASS (median 782.9 / 955.4 MB/s, 155 PASS, ratio parity 0.0%), 2 findings (CHANGELOG dup, CLI benchmark thấp hơn gate)
> - `reports/critique_awesome.md` + `reports/fix_report_filetext.md` — risks kế thừa (header MAC R1, OOM guard UNKNOWN R5, ruff bundle drift R3, mypy lie R4, mkdir traversal)
> - Source: `src/revhash/stream.py` (1236 dòng), `codec.py` (357), `__init__.py` (347), `header.py` (333), `file_text.py` (192), `cli.py`, `pyproject.toml`, `tests/test_embedded.py`, `benchmarks/run_benchmark.py`, `CHANGELOG.md`, `README.md`
>
> **Phạm vi:** audit hardcoding / false claims / incomplete coverage / security regressions sau patch Speed Builder (buffer 128KB, crc32_local binding, codec cache, HEADER_STRUCT reuse) và Clean Builder (__all__ 15, mypy gọn 5 codes, version 0.4.0, bundle rebuild). **Không file nào khác bị sửa** — output duy nhất: report này + append `TEAM_STATE.md`.

---

## 1. Verdict tổng hợp PASS/WARN/FAIL per success criteria

| # | Tiêu chí (TEAM_PLAN_SPEED_CLEAN §1) | Verifier claim | Critic evidence thực đo | Verdict Critic |
|---|-------------------------------------|----------------|-------------------------|----------------|
| SC1a | **Speed 1MB text_repeat zstd >700 MB/s** | PASS median 782.9 (+14.9%) | Harness `run_benchmark.py:101-111` warm-up bằng **cùng một data object** rồi đo loop trên cùng object đó → cache `id()`-based trong `codec.py:244-267` skip toàn bộ bước nén raw thứ 2 (`__init__.py:193`). Đo độc lập cùng máy: **warm (same obj) 917 MB/s vs cold (buffer mới) 682 MB/s (+34.4%)** → một-shot thực ≈ baseline v0.3 (681), **dưới gate 700** | ⚠️ **WARN (gate PASS kỹ thuật, claim +14.9% là warm-cache artifact)** |
| SC1b | **Speed 10MB >850 MB/s** | PASS median 955.4 (+13.2%) | Tương tự: warm 959.1 vs **cold 812.1 MB/s (+18.1%)** → dưới gate 850; CLI benchmark (cold path, `cli.py:344-349`) tự đo 594.9–625.9 MB/s <700 | ⚠️ **WARN (như trên)** |
| SC1c | Ratio parity <5% + 32.5× giữ | PASS 0.0% diff | Re-check: 1580B @10MB, 708B @1MB đúng; roundtrip 10MB compressible byte-identical mọi codec (B2c) | ✅ **PASS** |
| SC1d | Peak <150MB | PASS 30.41MB max 101.08MB | Hợp lý với buffer +64KB; không đo lại full matrix | ✅ **PASS (tin Verifier)** |
| SC2a | ruff check/format 0 | PASS | Re-run pass; **nhưng** `ruff format --check revhash_embedded.py` → `1 file would be reformatted` (drift kế thừa critique_awesome R3, chưa fix — `pyproject.toml:41-56` không exclude bundle) | ✅ **PASS src / ⚠️ bundle drift kế thừa** |
| SC2b | mypy 0 + `disable_error_code` gọn 5 | PASS | Config pass thật; **--strict phơi 80 errors** (52 unused-ignore, 13 type-arg, 10 no-untyped-def, 5 no-untyped-call); bỏ 5 disabled codes lộ **8 errors thật ở 4 file core** (chi tiết §5) — đa số cosmetic, **không thấy logic bug bị che** | ✅ **PASS (progress thật 10→5) / ⚠️ không được quảng cáo "strict"** |
| SC2c | `__all__` 15 align | PASS | Đúng 15; `from revhash import dict_builder` + `.train` OK, `RevHashHeader` import trực tiếp OK; **nhưng `from revhash import *` mất `__version__` + `RevHashHeader`** so với v0.3 (19 entries) — behavior change có chủ đích, đã ghi CHANGELOG:17 | ✅ **PASS (WARN nhỏ star-import)** |
| SC3a | Version 0.4.0 align 3 nơi + wheel PEP440 | PASS | `pyproject.toml:7`, `__init__.py:51`, bundle `__version__="0.4.0"`; wheel 50782B (tin Verifier) | ✅ **PASS** |
| SC3b | Bundle rebuild <500KB + build --check | PASS 104471B hash `2bd2b248…` | Re-run `build_embedded.py --check` → OK, hash khớp; `test_bundle_hash_version_size` recompute khớp | ✅ **PASS** |
| SC3c | CHANGELOG v0.4 | WARN trùng 2 lần | Confirm: `## [0.4.0]` tại dòng 10 **và** 29; section 2 còn **sai lịch sử** ("version `0.1.0` → `0.4.0`" — thực ra là nội dung polish v0.3-awesome); `[Unreleased]` empty dòng 8 kế thừa | ❌ **FAIL docs (blocker release nhỏ, fix 10 phút)** |
| SC4a | Không regress 155 tests | PASS | Re-run: **155 passed in 5.38s** | ✅ **PASS** |
| SC4b | get_available_codecs fallback mock | (không tách riêng) | `pytest -k fallback` → **6/6 PASS**; cache key = tuple flags nên mock `HAS_ZSTD=False` invalidate đúng (B1) | ✅ **PASS** |
| SC4c | Decompress byte-identical buffer 128KB | (implicit) | Random/compressible 10MB ×5 codecs + stream seekable/non-seekable: identical + SHA match + verify True (B2/B2c/B2d) | ✅ **PASS** |
| SC4d | `verify` 100% tamper (plan §non-regress) | implied PASS | Tamper **payload** 100% detect (tests); tamper **header** `chunk_size`/`level` single-chunk → `verify=True` (B3, kế thừa R1) | ⚠️ **WARN (kế thừa, đã document Limitations)** |
| SC5 | Không hardcode | — | `grep 782|955` trong src/tests/docs → **0 hit**; ratio/hash không hardcode (kế thừa audit cũ) | ✅ **PASS anti-hardcode** |

**Tổng hợp: 10 PASS, 3 WARN (speed claim chất lượng đo, header MAC kế thừa, bundle format drift), 1 FAIL nhỏ (CHANGELOG dup + sai lịch sử).**

> **Verdict tổng: ⚠️ WARN — KHÔNG FAIL nghiêm túc (không có security regression mới, không hardcode, tests/ratio/clean đều thật), NHƯNG finding #1 (benchmark warm-cache artifact) làm mọi con số speed "+14.9%/+13.2%" trở nên gây hiểu nhầm cho use-case one-shot. Phải xử lý mục 6-P0 trước khi tag v0.4.0 public.**

---

## 2. Top 7 Risks (Severity, file:line, evidence, impact, fix đề xuất)

### R1 — **HIGH (finding mới quan trọng nhất)** — Speed gate PASS nhờ warm-cache artifact; one-shot thực tế KHÔNG nhanh hơn v0.3

- **Location:**
  - `benchmarks/run_benchmark.py:101-111` — warmup `blob = revhash.compress(data, ...)` rồi timed-loop `for _ in range(repeat): revhash.compress(data, ...)` trên **cùng object `data`**.
  - `src/revhash/__init__.py:192-203` — mỗi lần `compress()` (codec≠store) gọi `compress_raw_with_flag(data, …)` → **nén raw đầy đủ thêm 1 lần nữa** chỉ để kiểm tra incompressible.
  - `src/revhash/codec.py:244-267` — single-entry cache keyed `(cname, level, id(dict_data), allow_store_fallback, len(data))` + `data is _LAST_RAW_DATA_REF` → cùng object ⇒ skip toàn bộ phép nén raw thứ 2.
- **Evidence (đã chạy, cùng máy, median-of-5):**
  ```
  1MB : cold(new buffer)=682.4 MB/s | warm(same obj)=917.2 MB/s | lift=+34.4%
  10MB: cold(new buffer)=812.1 MB/s | warm(same obj)=959.1 MB/s | lift=+18.1%
  ```
  Baseline v0.3 (`results_filetext.json`) 681.45 / 843.61 ≈ đúng bằng mức cold hôm nay ⇒ **micro-opt v0.4 gần như không cải thiện one-shot compress** (buffer 128KB chỉ tác động decompress; crc32/sha local binding ~1%). Con số 782.9/955.4 là chế độ "nén lặp lại cùng buffer" — hiếm trong thực tế. Lưu ý thêm: `bytes(bytes_obj)` ở `__init__.py:145` trả về **chính object gốc** (CPython tối ưu) nên ngay cả lời gọi tưởng như "mới" với cùng biến vẫn hit cache.
- **Impact:** Success criteria #1 của cả team + bảng so sánh trước/sau trong verification report dựa trên số bị inflate; người dùng một-shot (CLI, server nén request đầu tiên) sẽ không thấy 700/850. Đây là dạng false-claim gián tiếp — không hardcode, nhưng methodology biased.
- **Fix đề xuất (P0):**
  1. Sửa harness: `payload = bytes(bytearray(data))` (copy thật) bên trong timed-loop, hoặc gọi `codec._cache_clear()` giữa các repeat; ghi rõ "steady-state warm" vs "cold" trong results JSON.
  2. Sửa root cause (khuyến nghị): bỏ hẳn lệnh `compress_raw_with_flag` vô điều kiện tại `__init__.py:193` — store-fallback đã được xử lý trong `compress_stream` (stream.py:429-478) và nhánh `len(blob) > len(data)+overhead` (dòng 181); nếu giữ, chỉ chạy khi blob đã nghi ngờ inflate → one-shot tăng thật ~30-40% và gate đạt cold.

### R2 — **HIGH** — Cache `compress_raw` trả stale blob khi `id(dict_data)` tái sử dụng hoặc data mutable mutate in-place

- **Location:** `src/revhash/codec.py:245-267` — key dùng `id(dict_data)` (không giữ reference tới dict_data!) và identity-check chỉ áp dụng cho `data`.
- **Evidence A (id-reuse, đã chạy):**
  ```python
  d1 = (b"PATTERN-ALPHA-0123456789_"*170)[:4096]; payload=(d1[0:48]+b"#")*85
  b1 = compress_raw(payload, 'zstd', 3, dict_data=d1, allow_store_fallback=False)  # len 24
  del d1; gc.collect()
  d2 = (b"TOTALLY-DIFFERENT-BETA-9876543210-"*128)[:4096]     # id(d2)==id(d1) reused=True
  b2 = compress_raw(payload, 'zstd', 3, dict_data=d2, allow_store_fallback=False)
  # b2==truth_d1: True ; b2==truth_d2: False ; len(truth_d2)=49  => STALE (nén bằng dict CŨ)
  revhash.decompress(b2, dict_data=d2)  # -> RevHashCorruptedError: bad magic b'(\xb5/\xfd'
  ```
- **Evidence B (bytearray mutate, đã chạy):** `ba[:200]=b'Y'*200` cùng length/id → `compress_raw(ba,…)` lần 2 trả **y hệt blob cũ** (`r2==r1 True`, `r2!=truth True`).
- **Impact:** Caller gọi thẳng `revhash.codec.compress_raw` (public module-level, dùng trong test_dict) nhận blob không tương ứng tham số vừa truyền → dữ liệu hỏng im lặng hoặc CorruptedError lúc decode. Qua public `revhash.compress()` rủi ro thấp hơn (data luôn là cùng object bytes immutable) nhưng **latent**: chỉ cần `data` giữ nguyên identity + dict_data bị GC tái sử dụng địa chỉ là dính.
- **Fix (P1):** giữ strong reference cho cả dict (`_LAST_RAW_DICT_REF = dict_data`) và chỉ cache khi `type(data) is bytes` (loại bytearray/memoryview); hoặc bỏ hẳn equality-by-identity cache, thay bằng so sánh giá trị rẻ (hash prefix) — đúng như comment `codec.py:255-256` mô tả nhưng **code không hề implement** (comment lie).

### R3 — **HIGH (kế thừa, chưa fix v0.4)** — Header MAC bypass: tamper `chunk_size`/`level` single-chunk vẫn `verify=True`

- **Location:** `src/revhash/header.py:160-192` (`to_bytes` không CRC/MAC cover header fields); `stream.py:886,898-901` CRC slice theo `chunk_size` đọc từ header bị tamper.
- **Evidence (re-run trên v0.4.0, B3):**
  ```python
  blob = bytearray(revhash.compress(b"x"*500, codec="gzip", chunk_size=1024*1024))
  struct.pack_into("<I", blob, 7, 4*1024*1024)      # chunk_size 1M->4M
  revhash.verify(bytes(blob))    # True   (BUG kế thừa)
  revhash.decompress(bytes(blob)) == b"x"*500   # True — tamper không phát hiện
  blob[6] = 9                      # tamper level
  revhash.verify(bytes(blob2))     # True
  ```
- **Impact:** Mọi blob Nc=1 (<4MB — phổ biến nhất) attacker đổi `chunk_size`/`level` mà verify PASS. Đã document `README` Limitations + plan defer v0.5, nhưng TEAM_PLAN_SPEED_CLEAN §"Không regress" vẫn ghi "verify 100% tamper" — tiêu chí này **không đúng với header-field tamper**.
- **Fix (P2 theo plan, khuyến nghị nâng P1 cho v0.4.1):** `header_crc = crc32(header_bytes[0:23-dict])` + `HEADER_VERSION=2`. Ít nhất: sửa mốc "tamper 100%" trong docs thành "tamper payload 100%; header fields = known limitation".

### R4 — **MEDIUM** — CHANGELOG duplicate `## [0.4.0]` + section 2 sai lịch sử version

- **Location:** `CHANGELOG.md:10` và `CHANGELOG.md:29` (cùng heading `## [0.4.0] - 2026-08-28`); dòng 43 ghi "version `0.1.0` → `0.4.0`" trong khi thực tế chuỗi bump là `0.1.0 → 0.3.0-awesome → 0.4.0` (section 2 chính là nội dung polish v0.3-awesome bị đổi tiêu đề). Thêm `## [Unreleased]` rỗng dòng 8 (anti-pattern Keep-a-Changelog, kế thừa critique_awesome R7).
- **Evidence:** `Select-String "^## \["` → dòng 8/10/29/52/73/93; nội dung dòng 31 "Polish toàn diện production-grade awesome (8 tiêu chí C1-C8)" = bản sao 0.3-awesome.
- **Impact:** Release notes sai → người dùng không biết chính xác v0.4 thay đổi gì (buffer/cache/mypy nằm ở section 1, còn section 2 là nội dung cũ); tooling parse changelog sẽ lỗi.
- **Fix (P0, 10 phút, Coordinator owns):** gộp hai section thành một `## [0.4.0]`, đổi dòng 43 thành `0.3.0-awesome → 0.4.0`, xóa `[Unreleased]` rỗng.

### R5 — **MEDIUM (kế thừa critique_awesome R3, Clean Builder không xử lý)** — `ruff format` toàn repo sẽ làm drift bundle hash

- **Location:** `pyproject.toml:41-56` — không có `exclude = ["revhash_embedded.py"]`; `scripts/build_embedded.py` không format bundle sau build.
- **Evidence:** `python -m ruff format --check revhash_embedded.py` → `1 file would be reformatted` (vẫn còn y như v0.3); trong khi `build --check` OK 104471B.
- **Impact:** Maintainer chạy `ruff format .` theo CI habit → bundle đổi → `build --check` FAIL ở commit sau, hoặc tệ hơn: bundle committed đã format nhưng `HASH_FILES` hash tính từ src → mismatch khó hiểu.
- **Fix (P1, 5 phút):** thêm `exclude` vào `[tool.ruff]`, hoặc CI step `build_embedded.py && ruff format --check src only`.

### R6 — **MEDIUM** — Global caches không lock + giữ reference bộ nhớ lớn + dict availability trả by-reference (poisonable)

- **Location/Evidence:**
  - `codec.py:26-28,264-266` — `_LAST_RAW_DATA_REF` giữ **strong ref buffer cuối**: sau `del big; gc.collect()`, module vẫn giữ **10.0MB input** + cached blob (đã đo A3b). Với payload 100MB → giữ thêm ~100MB vô thời hạn cho tới lần `compress_raw` kế tiếp.
  - `codec.py:320-327` — `_CACHE_VAL` trả **cùng object dict** mỗi lần: caller `avail['gzip']=False` → poison toàn process (đã chứng minh B1b, `gzip=False` persist sau khi caller hết tham chiếu).
  - Cả 2 cache không có lock: window non-atomic `REF→KEY→VAL` cho phép thread khác thấy `REF/KEY` mới với `VAL` cũ → trả nhầm blob (low-probability, free-threading 3.13 làm tăng rủi ro).
- **Impact:** memory bloat dài hạn cho service nén payload lớn; một caller vô tình mutate dict availability làm hỏng `_resolve_codec` toàn app.
- **Fix (P1/P2):** trả `dict(val)` copy (hoặc `MappingProxyType`); giới hạn size cached entry (ví dụ chỉ cache khi `len(data)<=1MB`); thêm `threading.Lock` hoặc chuyển sang `functools.lru_cache` chuẩn (tự thread-safe) cho `get_available_codecs`.

### R7 — **LOW-MEDIUM** — Buffer 128KB chỉ phủ zstd-decompress + Spool; gzip/lzma/brotli decompress vẫn 64KB (incomplete coverage của P0-1)

- **Location:** `stream.py:642,783,925` = `read(131072)` ✓; nhưng `stream.py:792,806,822,934,948,964` (gzip/lzma/brotli cả 2 branch) vẫn `read(65536)`.
- **Evidence:** grep `read\(131072\)|read\(65536\)` → 3 hit 128KB, 6 hit 64KB.
- **Impact:** không bug, nhưng research §1.1 hứa "decompress cũng +5%" chỉ đúng cho zstd; các codec fallback không hưởng. Claim CHANGELOG:15 "buffer … cho decompress" đọc rộng hơn thực tế.
- **Fix (P2):** đồng nhất 131072 cho 6 chỗ còn lại (1-line × 6, zero-risk) hoặc thu hẹp câu chữ CHANGELOG.

---

## 3. Anti-cheat check (cache correctness, hardcode speed, stale blob, mock invalidation)

| Check | Lệnh / Evidence (đã chạy) | Kết quả |
|-------|---------------------------|---------|
| **Cache correctness — id-reuse stale** | script A1b/A1c (§2-R2): id(d1)==id(d2) reused=True → `compress_raw(payload, dict_data=d2)` trả blob của d1; decompress với d2 raise CorruptedError | ❌ **BUG thật (codec layer)** — fails loud ở case này nhưng vi phạm contract |
| **Cache correctness — mutable in-place** | script A2: bytearray mutate cùng length → lần 2 trả stale (r2==r1) | ❌ **BUG thật** (chỉ khi gọi `compress_raw` trực tiếp; `revhash.compress()` copy bytes nên miễn nhiễm) |
| **Memory leak qua cache ref** | script A3b: `del big; gc.collect()` → `_LAST_RAW_DATA_REF` vẫn giữ 10MB | ⚠️ bounded 1 entry nhưng entry unbounded size — retention, không phải leak kinh điển |
| **Mock HAS_ZSTD=False invalidate?** | `pytest -k fallback -v` → 6 passed; script B1: flags False→dict zstd=False→restore→True | ✅ **PASS** — cache key = tuple flags, invalidate đúng theo thiết kế (research §1.4 mitigation được implement đúng) |
| **Comment lie trong cache** | `codec.py:255-256` mô tả "fallback: if same length and same first 1KB, assume same" — code **không có** logic đó | ⚠️ comment mô tả hành vi nguy hiểm hơn cả code thật — nên xóa/sửa (may mắn code an toàn hơn comment) |
| **Hardcode speed 782/955?** | `Get-ChildItem src,tests,docs,README.md \| Select-String "782\.9\|955\.4"` → **0 hit**; README:19 vẫn số cũ "836–6478 MB/s" (stale chứ không hardcode số mới) | ✅ **PASS** |
| **Benchmark methodology bias** | `run_benchmark.py:101-111` warmup+timed cùng object + `__init__.py:193` double-compress + `codec.py` identity cache → A/B cold/warm lệch +34%/+18% | ❌ **FINDING** — số gate PASS nhưng mang tính steady-state, không phản ánh one-shot (§2-R1) |
| **Bundle hash hardcode/stale?** | `build --check` OK `sha256:2bd2b248…` (104471B); test recompute HASH_FILES khớp | ✅ **PASS** |
| **Version sync** | pyproject 0.4.0 = `__init__.__version__` = bundle `__version__`; wheel PEP440 (Verifier) | ✅ **PASS** |
| **Ratio parity không regress** | 10MB zstd 1580B / 1MB 708B đúng như baseline; roundtrip byte-identical 5 codecs (B2c) | ✅ **PASS** |

**Kết luận anti-cheat:** không có hardcode giả exit-code; implementation honest. Vấn đề nằm ở **measurement validity** (R1) và **cache semantics** (R2/R6) — đúng kiểu "optimization giúp benchmark chứ không giúp user".

---

## 4. Security & Correctness (header MAC kế thừa, OOM guard, traversal, correctness buffer)

| Hạng mục | Evidence file:line | Trạng thái v0.4.0 | Severity |
|----------|--------------------|--------------------|----------|
| **Header MAC `chunk_size`/`level`** | `header.py:160-192` không MAC; repro B3 verify=True khi tamper single-chunk | **Chưa fix** — kế thừa R1 critique_awesome, plan defer v0.5; đã có Limitations doc | High (known/deferred) |
| **OOM guard UNKNOWN bypass** | `file_text.py:174-181`: `original_size == UNKNOWN` → guard skip; pipe blob craft 500MB vẫn vào RAM khi `dst=None` | Chưa fix (kế thừa R5 critique_awesome; non-seekable >100MB có raise ở `stream.py:672` nhưng đường seekable-UNKNOWN/BytesIO vẫn mở) | Medium-High (known) |
| **Traversal `mkdir(parents=True)` dst** | `file_text.py:97` — `../outside` tạo thư mục ngoài cwd | Chưa sanitize (documented) | Low-Medium (documented) |
| **Buffer-128KB correctness** | Roundtrip 10MB compressible + random × {store,gzip,lzma,zstd,brotli} + stream seekable/non-seekable: identical=True, SHA match, verify=True (B2/B2c/B2d) | ✅ Không regress | — |
| **HEADER_STRUCT reuse** | `stream.py:47` import + dùng tại `stream.py:135`; không còn `_STRUCT` local; circular import tránh đúng (header không import ngược) | ✅ PASS như research §1.3 | — |
| **crc32_local/sha_up binding** | Có ở cả 5 codec branch (`stream.py:267-268,280-281,298-299,321-322,346-347`) + `chunk_size_local/crc32_local` ở `_process_out` (741-742) và `_proc` (886-887) | ✅ Đúng checklist, semantics giữ (tamper payload vẫn detect qua tests) | — |
| **Non-seekable >100MB** | `stream.py:672` raise guidance — giữ nguyên | ✅ (limitation documented) | — |
| **Thread safety caches** | §3/R6 — không lock, non-atomic triple-write | ⚠️ mới xuất hiện v0.4 (cache mới) | Medium (multi-threaded hosts) |

**Nhận xét security:** v0.4 **không tạo security regression mới**; mọi vấn đề là kế thừa đã document. Điểm trừ: cache mới (R2/R6) là bề mặt correctness/safety **mới** do Speed Builder thêm — cần xử lý vì `compress_raw` là API bán-public (test_dict dùng trực tiếp).

---

## 5. Style & Maintainability (type ignore count, __all__ tradeoff, dead code)

| Tiêu chí | Evidence | Đánh giá |
|----------|---------|----------|
| **mypy "gọn" 10→5 codes** | Config pass; `--strict` → **80 errors** (52 `unused-ignore`, 13 `type-arg`, 10 `no-untyped-def`, 5 `no-untyped-call`); temp-config bỏ 5 disabled codes → **8 errors thật**: `stream.py:307,330 attr-defined` (ZstdCompressionWriter.compress — **false positive** do stub zstandard), `stream.py:1006 union-attr` (defensive None.hex), `stream.py:1076,1175 arg-type` (`os.PathLike` vs `Path` — type debt thật, nên widen signature `_load_dict_data`), `dict_builder.py:115` + `cli.py:429 no-any-return` (cosmetic) | ✅ Progress thật, **không che logic bug**; nhưng 52 `unused-ignore` stale là rác cần dọn; đừng claim "strict-clean" |
| **Override còn algorithms.\*** | `pyproject.toml:65-67` — selector 430 dòng vẫn ngoài typecheck (kế thừa) | ⚠️ debt cũ, chấp nhận được |
| **ruff per-file-ignores cli.py 9 rules** | `pyproject.toml:49-52` | Kế thừa, không đổi trong v0.4 — "clean" của cli vẫn là ignore-driven |
| **`__all__` 15 tradeoff** | Đúng spec; mất `RevHashHeader` + `__version__` khỏi `import *` (đã test C1: star-ns thiếu cả hai). Direct import vẫn OK. Bundle embedded đồng bộ | ✅ chấp nhận được, đã ghi CHANGELOG:17; khuyến nghị thêm note trong docs/api.md |
| **Dead code / style** | `stream.py:857-859` expression statement không effect (no-op tuple) trong non-seekable branch; comment `codec.py:255-256` mô tả logic không tồn tại; duplicate decompress ~600 dòng (C5 research) **chưa tách** — plan ghi "P0/P1 nếu defer" và thực tế defer | ⚠️ nợ kỹ thuật còn nguyên |
| **README stale metrics** | `README.md:19` "Speed 10MB encode 836–6478 MB/s"; Verification section chưa cập nhật v0.4 | ⚠️ docs drift nhẹ |

---

## 6. Đề xuất fix P0 / P1 / P2

### P0 — trước khi tag/publish v0.4.0 (tổng ~1 giờ)

1. **Re-benchmark trung thực + ghi chú phương pháp (R1):** sửa `run_benchmark.py` timed-loop dùng buffer mới mỗi repeat (hoặc `codec._cache_clear()`), chạy lại 3×median, cập nhật `results_speed_clean.json` + verification report với 2 cột **cold / warm**. Nếu muốn giữ gate >700/>850 cold: xử lý #2 thì gate tự đạt.
2. **Bỏ double-compress trong `compress()` (root cause R1):** `__init__.py:192-203` — chỉ gọi `compress_raw_with_flag` khi `len(blob) > len(data) + overhead` đã nghi ngờ inflate, hoặc bỏ hẳn (store-fallback trong `compress_stream` + nhánh overhead đã đủ). Kỳ vọng one-shot +30-40% thật sự.
3. **CHANGELOG merge (R4):** gộp 2 section `## [0.4.0]`, sửa "0.1.0 → 0.4.0" thành "0.3.0-awesome → 0.4.0", xóa `[Unreleased]` rỗng. Sau đó rebuild bundle (bundle chứa `__init__.py` → hash đổi) + re-run `build --check` + `pytest -q`.
4. **Sửa cache stale tối thiểu (R2):** giữ `_LAST_RAW_DICT_REF` strong-ref cho dict_data và chỉ cache khi `type(data) is bytes` (~4 dòng, không phá perf).

### P1 — v0.4.1 (nên làm sớm)

5. **`get_available_codecs` trả copy + lru_cache chuẩn (R6);** giới hạn cache entry ≤1MB; xóa comment lie `codec.py:255-256`.
6. **Exclude bundle khỏi ruff (R5):** `pyproject.toml [tool.ruff] extend-exclude=["revhash_embedded.py"]`.
7. **Đồng nhất 128KB cho gzip/lzma/brotli decompress (R7)** — 6 dòng.
8. **Docs:** README cập nhật số v0.4 (cold+warm), docs/api.md note `import *` không có `__version__`/`RevHashHeader`; sửa mốc "verify 100% tamper" → "payload tamper 100%, header fields = known limitation".
9. **Dọn 52 `# type: ignore` stale** (ruff RUF100 hoặc mypy `--warn-unused-ignores` gate).

### P2 — backlog v0.5 (giữ nguyên kế hoạch)

10. `header_crc` + HEADER_VERSION=2 (R3); OOM guard streaming cho UNKNOWN (decompressed_so_far >100MB raise); tách `_decompress_core` (duplicate 600 dòng); mkdir `resolve().is_relative_to(cwd)` option; thread-lock cho caches hoặc migrate lru_cache hoàn toàn; CI workflow.

---

## 7. Kết luận — release v0.4.0 được không?

**Verdict Critic: ⚠️ WARN — release được nội bộ/rc NGAY SAU khi xử lý P0 (ước 1 giờ); CHƯA nên tag stable public trước khi re-benchmark trung thực, vì hiện tại câu chuyện "nhanh hơn +14.9%/+13.2%" không đúng cho one-shot thực tế.**

| Trụ cột | Đánh giá |
|---------|----------|
| Đúng đắn (tests 155, ratio parity, roundtrip, bundle parity) | ✅ Thật, không regress — tin được |
| Clean (ruff 0 src, mypy 0, `__all__` 15, version align) | ✅ Thật (progress 10→5 disable codes là có lý), kèm nợ: 52 unused-ignore, algorithms override, bundle format drift |
| Speed claim | ⚠️ **Kết quả đo thật nhưng methodology biased** — warm-cache artifact; cold ≈ baseline v0.3 |
| Anti-hardcode | ✅ Không phát hiện hardcode số/hash/ratio |
| Security | Không regression mới; 2 known limitations kế thừa (header MAC, OOM UNKNOWN) + 1 bề mặt mới (cache stale — đã có fix 4 dòng) |

**So sánh Verifier vs Critic:** Verifier PASS 7/9 + 2 WARN là **quá lạc quan ở C4a/C4b**: exit codes đều đúng, nhưng ý nghĩa con số không được kiểm soát (không ai để ý `run_benchmark.py` warm-up cùng object + `__init__.py:193` double-compress + cache identity = đo steady-state). Critic xác nhận 2 findings của Verifier (CHANGELOG dup — nâng mức độ vì còn sai lịch sử; CLI benchmark thấp — giải thích đúng nguyên nhân cold-path). Critic bổ sung 5 finding mới: R1 warm-artifact, R2 stale cache, R6 cache hygiene, R7 buffer coverage lệch, comment lie.

**So sánh chi tiết Verifier vs Critic:**

| Hạng mục | Verifier (`verification_speed_clean.md`) | Critic (report này) | Lý do chênh |
|----------|------------------------------------------|---------------------|-------------|
| **Overall** | ✅ PASS (7 PASS + 2 WARN/INFO) | ⚠️ WARN (10 PASS / 3 WARN / 1 FAIL docs) | Verifier đo exit-code đúng nhưng không kiểm soát **methodology** của số nó đo |
| C4a/C4b Speed gate | PASS median 782.9/955.4 "+14.9%/+13.2%, margin dư tải" | ⚠️ WARN — cold thực 682/812 ≈ baseline v0.3; lift +34%/+18% là warm-cache artifact (R1) | Không ai để ý warm-up dùng cùng object (`run_benchmark.py:101-111`) kết hợp cache identity mới (`codec.py:244`) |
| C4e CLI benchmark | INFO/WARN "harness riêng gồm verify step" | Xác nhận + định lượng đúng nguyên nhân: CLI đo **cold path** (594.9–625.9 MB/s) — chính là byproduct của R1, không phải do "verify step" (verify nằm ở timer decompress, tách riêng) | Critic đọc `_cmd_benchmark` (`cli.py:344-357`): comment "# warmup" nhưng **không hề có vòng warmup** — đo lần chạy đầu tiên |
| C8 CHANGELOG | WARN trùng heading dòng 10 & 29 | ❌ FAIL nhỏ — cộng thêm **sai lịch sử version** ("0.1.0→0.4.0" tại dòng 43, nội dung là v0.3-awesome) + `[Unreleased]` rỗng | Đọc nội dung, không chỉ đếm heading |
| C2 mypy | PASS "Success 12 files" | ✅ đồng ý PASS + bổ sung: strict=80, no-disable=8 errors thật (0 logic bug), 52 unused-ignore | Đo cả hai phía của cấu hình |
| C1 tests / C4c ratio / C7 packaging | PASS | ✅ xác nhận độc lập (155 passed 5.38s; roundtrip 5 codecs byte-identical; build --check hash khớp) | Không chênh |
| Security | Không nêu ngoài kế thừa | Header MAC re-confirm exploitable trên v0.4 (B3); OOM UNKNOWN bypass còn nguyên; cache stale = bề mặt correctness MỚI | Adversarial re-run thay vì tin Limitations |

**Handoff Coordinator (M6):**
- [ ] P0-1..P0-4 (§6) → rebuild bundle → `pytest -q` 155 → `run_benchmark.py` (cold methodology) → cập nhật verification + results JSON.
- [ ] Quyết định: nếu giữ methodology cũ thì **bắt buộc** ghi "steady-state (warm) measurement" everywhere số xuất hiện.
- [ ] P1 cho 0.4.1; P2 giữ roadmap v0.5 (header CRC, UNKNOWN OOM, dedup decompress).

---

### Phụ lục — Lệnh reproduce chính (đã chạy 2026-08-28, Python 3.12.10)

```powershell
# Full suite + fallback mocks
python -m pytest tests -q                       # 155 passed in 5.38s
python -m pytest tests -q -k "fallback" -v      # 6 passed

# Warm vs cold (R1) — script critic_check_cache3.py (temp)
# 1MB: cold=682.4 MB/s | warm=917.2 MB/s (+34.4%)
# 10MB: cold=812.1 MB/s | warm=959.1 MB/s (+18.1%)

# Stale cache (R2) — script critic_check_cache2.py (temp)
# id(d1)==id(d2) reused=True; b2==truth_d1 True; decompress(stale,d2) -> RevHashCorruptedError bad magic

# Memory retention (R6) — sau del+gc, _LAST_RAW_DATA_REF vẫn giữ 10.0MB

# Availability cache (B1/B1b): mock invalidate OK; avail['gzip']=False poison global OK

# Roundtrip buffers (B2/B2c/B2d): 10MB × 5 codecs + stream seekable/non-seekable identical+SHA OK

# Header tamper (B3): pack_into('<I',blob,7,4M) -> verify True; level tamper -> verify True

# mypy: config PASS; --strict 80 err; no-disable config 8 err in 4 core files
# ruff format --check revhash_embedded.py -> 1 file would be reformatted (drift kế thừa)
# build_embedded --check -> OK sha256:2bd2b248… (104471B)
# grep 782|955 src/tests/docs -> 0 hit (không hardcode)
```

### Phụ lục A — Transcript đầy đủ các lệnh adversarial (đã chạy 2026-08-28, Python 3.12.10, win32)

```
PS D:\data optimization> python -m pytest tests -q
........................................................................ [ 92%]
...........                                                              [100%]
155 passed in 5.38s

PS> python -m pytest tests -q -k "fallback" -v
tests\test_embedded.py ..            [ 33%]
tests\test_filetext_flex.py .        [ 50%]
tests\test_stream.py .               [ 66%]
tests\test_text_file.py ..           [100%]
6 passed, 149 deselected in 0.15s

PS> python critic_check_cache2.py
=== A1b. dict_data id-reuse stale blob (dict-dependent payload) ===
id reused=True
len(b1)=24 len(b2)=24 len(truth_d2)=49
b2==truth_d2: False   b2==truth_d1(rebuilt): True
=> STALE (returns blob made with OLD dict d1 while claiming d2): True
=== A3b. cache pins last input (memory retention) ===
_LAST_RAW_DATA_REF is our 10MB input: True
after del user ref + gc: cache still holds 10.0 MB input + 339 B cached blob

PS> python critic_check_cache3.py
decompress(stale, d2) RAISES: RevHashCorruptedError bad magic b'(\xb5/\xfd'
=== A4b. TRUE cold vs warm (force real copy) ===
1MB: cold(new buffer)=682.4 MB/s | warm(same obj)=917.2 MB/s | lift=+34.4%
10MB: cold(new buffer)=812.1 MB/s | warm(same obj)=959.1 MB/s | lift=+18.1%

PS> python critic_check_b.py          (tóm tắt)
B1 invalidation OK (mock HAS_ZSTD False -> zstd False -> restore True)
B1b poison: caller set avail['gzip']=False; next call gzip=False (poisoned=True)
B2 5 codecs random-10MB identical=True verify=True sha_match=True
B2b non-seekable compress+decompress identical=True
B3 tamper chunk_size 1M->4M single-chunk(Nc=1): verify=True decompress_ok=True
    tamper level 3->9: verify=True

PS> python critic_check_c.py          (tóm tắt)
B2c compressible 10MB: zstd/gzip/lzma/brotli ratio .13-.18 identical=True sha=True verify=True
B2d seekable + non-seekable stream roundtrip: True / True
C1 from revhash import dict_builder OK (.train exists); star-import 15 names,
   __version__ NOT in star-ns, RevHashHeader NOT in star-ns
C2 pyproject version="0.4.0"; bundle __version__ 0.4.0; hash sha256:2bd2b248…; 104471 B

PS> python -m mypy src/revhash --ignore-missing-imports
Success: no issues found in 12 source files
PS> python -m mypy src/revhash --ignore-missing-imports --strict
Found 80 errors in 6 files  (52 unused-ignore, 13 type-arg, 10 no-untyped-def, 5 no-untyped-call)
PS> python -m mypy src/revhash --config-file mypy_nodisable.ini   (bỏ 5 disable codes)
Found 8 errors in 4 files:
  dict_builder.py:115 no-any-return | stream.py:307,330 attr-defined (stub FP)
  stream.py:1006 union-attr | stream.py:1076,1175 arg-type (PathLike vs Path)
  cli.py:429 no-any-return

PS> python -m ruff format --check revhash_embedded.py
1 file would be reformatted          (drift kế thừa critique_awesome R3 — chưa fix)

PS> python scripts/build_embedded.py --check
[build_embedded] --check OK: sha256:2bd2b24863c4aff71b979159cd4bc7a54a6bb9dbceb1b6fd7f974ec2ab524bbc (104471 bytes)

PS> Select-String "782\.9|955\.4" -Path src\*,tests\*,docs\*,README.md -Recurse
(no output — 0 hit, không hardcode số gate mới)

PS> python -m revhash benchmark --size 1M --codec zstd
  zstd L3: ratio=0.003465 (3633 B) comp 594.9 MB/s decomp 272.7 MB/s verify=OK sha_match=True
  (cold path <700 — khớp finding INFO của Verifier, nguyên nhân thật = R1)
```

### Phụ lục B — Vị trí code đã kiểm tra từng micro-opt (đối chiếu research §1)

| Micro-opt (research) | Kỳ vọng vị trí | Vị trí thực tế v0.4.0 | Trạng thái |
|----------------------|----------------|------------------------|------------|
| P0-1 buffer 128KB `sreader.read` | `stream.py:770,912,634` (line numbers research) | `stream.py:642, 783, 925` (file đã dài hơn sau patch) | ✅ x3 — nhưng chỉ zstd + Spool; gzip/lzma/brotli còn 64KB ×6 |
| P0-2 crc32/sha local binding | `stream.py:271-275, 883-888` | `stream.py:267-268, 280-281, 298-299, 321-322, 346-347` + `741-742`, `886-887` | ✅ đủ 5 codec branches |
| P0-3 BytesIO/memoryview tránh copy | `__init__.py:150` | **KHÔNG làm** — `__init__.py:145` vẫn `data = bytes(data)` vô điều kiện (no-op cho bytes nhờ CPython trả same object) | ❌ deferred ngầm; thay bằng cache identity ở codec layer |
| P1-1 HEADER_STRUCT reuse | bỏ `_STRUCT` local | `stream.py:47` import + dùng `:135` | ✅ |
| P1-2 get_available_codecs cache | lru_cache + cache_clear | manual `_CACHE_KEY/_CACHE_VAL` keyed flags + `_cache_clear` gắn attribute (`codec.py:310-338`) | ✅ semantics đúng (key=flags → mock invalidate), ⚠️ hygiene R6 |
| P1-3 sha batch decompress | local binding `_proc` | `chunk_size_local/crc32_local` tại `886-887` (sha.update chưa bind trong `_proc`, có bind `sha_up` ở compress side) | 🟡 một phần |
| C3 `__all__` 15 | bỏ dict_builder/algorithms | `__init__.py:52-68` đúng 15 (+ mất luôn `RevHashHeader`, `__version__` khỏi `*`) | ✅ với tradeoff |
| C5 tách duplicate decompress | `_decompress_core` helper | **Chưa làm** — 2 branch vẫn ~600 dòng trùng (`stream.py:675-876` vs `878-1042`) | ❌ defer (plan cho phép P0/P1) |

*Critic chỉ ghi `reports/critique_speed_clean.md` này + append `TEAM_STATE.md`. Không file product nào bị sửa.*

# CRITIQUE v0.5.0 — Critic/Auditor đối kháng (reports/critique_v05.md)

> **Role:** Critic / Auditor — team revhash v0.5.0 · **Ngày audit:** 28-08-2026 · **Workspace:** `D:\data optimization`
> **Phương pháp:** tự viết 7 script tái hiện ở `C:\Users\Admin\AppData\Local\Temp\opencode\critic_v05\` (ngoài workspace), **không sửa** src/tests/docs/bundle. Mọi assertion dưới đây đều chạy ra số thật, không hardcode.
> Scripts: `c1_mac_mutation.py`, `c2_crc_oracle.py`, `c3_dualread.py`, `c4_bench.py`, `c5_extra.py`, `c6b_baseline.py`, `c7_brotli.py`.

---

## TÓM TẮT DÀNH CHO COORDINATOR

| # | Finding | Severity | Verdict |
|---|---------|----------|---------|
| F1 | CHANGELOG [0.5.0] trích dẫn 2 artifact benchmark **không tồn tại**; toàn bộ artifact Verifier M5 missing | **HIGH** | Docs/process gian lận nhẹ (claim-vô-cụng) |
| F2 | Prealloc sink cấp phát bộ nhớ **trước mọi verify** (cả blob v2): blob 111B → peak 600MB; docstring tuyên bố ngược sự thật | **HIGH** | Lỗi security-honesty thật |
| F3 | "MAC" là digest **không khoá** — bypass đầy đủ bởi kẻ chủ động; docs tạo kỳ vọng sai | **MEDIUM** | Ranh giới bảo mật cần diễn đạt lại |
| F4 | Claim 666.6 MB/s lệch −18…−21% so với đo độc lập (tôi đo 784–809); "sàn kiến trúc ~700" **không tái hiện được** — 1 run của tôi vượt chính gate 800 | **MEDIUM** | Không phải warm-cache fraud (claim chậm hơn số thật), nhưng rationale floor sai |
| F5 | Coverage drift 53.68% → 54.98% (môi trường khác), pass ngưỡng | LOW | Sạch |
| V1-V8 | Các claim kỹ thuật còn lại (CRC oracle, dual-read, UNKNOWN/store-fallback MAC, brotli fix, bundle hash, 155 tests, scope, deviation honesty) — **đã tái hiện độc lập, ĐÚNG** | — | VERIFIED |

**Kết luận: APPROVE-WITH-FIXES** (chi tiết cuối file). Không có bytе-level data-corruption nào tìm thấy; các vấn đề nằm ở docs trung thực + một lỗi DoS-memory + quy trình M5 bỏ trống.

---

## F1 — HIGH: CHANGELOG claim artifact không tồn tại; M5 không có Verifier/Critic

**Claim bị soát:** CHANGELOG `[0.5.0] > Added`: *"Benchmark quy trinh COLD chuan hoa …: `benchmarks/bench_cold.py`, ket qua `benchmarks/results_v05.json`"*.

**Tái hiện:**
```powershell
Test-Path benchmarks/bench_cold.py        # -> False
Test-Path benchmarks/results_v05.json     # -> False
Test-Path reports/verification_v05.md     # -> False
Test-Path tests/test_header_mac.py        # -> False
Test-Path tests/test_decompress_perf.py   # -> False
rg "\[Verifier|\[Critic" TEAM_STATE.md    # entries cuối cho v0.5: KHÔNG TỒN TẠI (TEAM_STATE dừng ở [Coordinator] M4, dòng 1405)
```

**Kết quả chạy thật:** cả 5 path trên đều `False`; TEAM_STATE không có mục `[Verifier]`/`[Critic]` nào cho chu trình v0.5 (chỉ còn log các team cũ 0.1→0.4).

**Đánh giá:** Con số 666.6/954.8 hiện chỉ có nguồn gốc là prose của Core Stream Builder trong TEAM_STATE (raw runs `[0.0150…]`) — tôi xác nhận lại được (F4) nên không coi là bịa số, nhưng:
1. CHANGELOG ghi tên file như thể đã tồn tại → sai sự thật tài liệu, bắt buộc sửa hoặc tạo file;
2. Toàn bộ M5 (Verifier ∥ Critic song song theo plan §4) chưa diễn ra đúng thiết kế — "155 tests PASS" và coverage là số Coordinator/Infra tự chạy. Tôi đã chạy lại: **155 passed, EXIT=0** (số ĐÚNG), nên hậu quả thực tế thấp — nhưng đây là lỗ hổng quy trình, không phải bằng chứng.

---

## F2 — HIGH: Prealloc sink cấp phát TRƯỚC mọi verification — DoS memory + docstring sai

**Code:** `src/revhash/__init__.py:208-211` — `decompress()` tạo `_PreallocWriter(size_hint)` ngay từ đầu; MAC check (`_verify_header_mac`) nằm ở `stream.py` và chạy **sau đó**, bên trong `decompress_stream()`. Guard duy nhất là `_PREALLOC_MAX = 1GiB` (`__init__.py:216`).

**Docstring bị soát:** `_PreallocWriter` / `_peek_size_hint` (`__init__.py:220-266`): *"Grows only if the stream produces more bytes than hinted (hostile/corrupt header)"*, *"a tampered original_size field cannot force a giant allocation"*. → **SAI**: hint 600MB từ blob hostile đã cấp phát đủ 600MB trước khi bất kỳ kiểm tra nào chạy.

**Tái hiện (c5_extra.py):**
```python
blob = revhash.compress(b"x"*60KB ...)            # blob v2 hợp lệ
v1 = downgrade(blob)                               # bản v1 không MAC
b[15:23] = struct.pack("<Q", 600*1024*1024)        # giả original_size
tracemalloc.start(); revhash.decompress(bytes(b))
```
**Kết quả chạy thật:**
```
[T2] v1 KHONG MAC: ... Corrupted nhu mong ... tracemalloc peak during reject = 600.0 MB  (hint 600MB)
[T3] vong doi v2 cung attack -> Corrupted (header MAC mismatch chan TRUOC khi decompress)
     tracemalloc peak = 600.0 MB
```
Cả v1 lẫn **v2** đều peak đúng 600MB từ blob 111 byte (amplification ≈ 5.400×; tối đa 1GiB ≈ 47 triệu × với header 23B). Kịch bản: nạn nhân gọi `decompress()` trên blob untrusted → OOM crash/swap death với chi phí attacker ~100 bytes.

**Đề xuất fix (theo thứ tự ưu tiên):**
1. Với v2: parse footer + verify MAC **trước** khi cấp phát sink (di chuyển logic hoặc truyền lazy-sink);
2. Hoặc hạ cap: `hint = min(hint, 64MiB, compressed_len * 1024)` kiểu hệ số tỉ lệ;
3. Bắt buộc sửa docstring cho đúng sự thật dù không đổi code.

---

## F3 — MEDIUM: Header "MAC" là digest không khoá — bypass chủ động đầy đủ

**Tái hiện (c1_mac_mutation.py):**
```
[T1] tamper bitflip tung field: version@4/codec_id@5/level@6/chunk_size@7/@10/dict_len@11/
     original_size@15/@22  -> 8/8 verify=False          (chặn tamper NGÂY THƠN: ĐÚNG claim)
[T2] level 3->99 + recompute sha256(header) vào ô footer[-68:-36]
     -> verify=True                                      (BYPASS 5 dòng code)
[T3] attacker tự nén payload riêng + patch original_size + tự tính đủ CRC/SHA/MAC
     -> verify=True                                      (FULL FORGE)
```
**Ranh giới bảo mật THẬT (cần ghi vào docs):**
- Digest keyless = **phát hiện hỏng hóc/ngẫu nhiên + tamper ngây thơ**, KHÔNG phải xác thực nguồn. Kẻ chủ động chỉ cần `hashlib.sha256` là forge sạch.
- `docs/api_v05.md` Q1 chọn SHA-256 thay CRC32 với lý do "CRC32 quá yếu chống tamper có chủ đích" → tạo ấn tượng SHA-256 chống chủ đích. Sai về mặt mật mã học; cái thật sự chống chủ đích là **HMAC** (đã backlog v0.6 theo Q5 — nhưng CHANGELOG [0.5.0] không hề có caveat này).
- Ghi nhận đúng chỗ: MAC đặt đúng vị trí ở **cả 3 đường ghi** — UNKNOWN (T4: footer MAC == sha256(hdr23), decompress OK), store-fallback (T5: codec_id=0, MAC == sha256(store_header), roundtrip True), dict (T6: MAC phủ hdr23+dict, tamper dict → False). Không có đường ghi nào quên MAC.

**Không phải blocker kỹ thuật** — nhưng CHANGELOG/docs phải thêm một câu: *"header_sha256 là checksum phi khoá, chỉ chống lỗi ghi; chống kẻ chủ động cần HMAC (v0.6)"*.

---

## F4 — MEDIUM: Benchmark audit — claim 666.6 chậm hơn số đo độc lập 18–21%; "sàn ~700" không bền

**Quy trình của tôi (c4_bench.py):** 10MB text_repeat zstd, data object mới mỗi run qua `bytes(bytearray(...))`, `gc.collect()` trước mỗi run, bỏ run đầu, median-of-5, blob mới mỗi lần decompress, timer chỉ bọc `decompress`. Không reuse output, không chọn lọc run.

**Kết quả chạy thật (2 lần chạy độc lập cùng ngày):**
```
run A: decompress raw=[0.0125,0.0120,0.0124,0.0125,0.0120] median=12.36ms -> 809.0 MB/s
       compress  raw=[0.0100,0.0100,0.0099,0.0101,0.0109] median=10.04ms -> 996.1 MB/s
run B: decompress raw=[0.0132,0.0126,0.0127,0.0129,0.0127] median=12.75ms -> 784.5 MB/s
       compress  raw=[0.0104,0.0100,0.0106,0.0106,0.0105] median=10.53ms -> 949.8 MB/s
baseline v0.4 (git archive HEAD ra temp, guard __version__=='0.4.0'):
       decompress median=60.21ms -> 166.1 MB/s
```

**Đối chiếu claim:**
| Đại lượng | Claim | Tôi đo | Dev |
|---|---|---|---|
| Decompress v0.5 cold | 666.6 | 784.5–809.0 | **+17.7…+21.4% → FLAG theo ngưỡng >15%** |
| Compress v0.5 cold | ~954.8 | 949.8–996.1 | ±5% (OK) |
| Baseline v0.4 same-machine | 161.2 | 166.1 | +3% (OK) |
| Ratio | ~4.1× | ~4.8× | hướng thuận |

**Nhận xét:** Chênh lệch >15% nhưng **ngược chiều gian lận**: claim của builder CHẬM hơn máy chạy lúc audit → loại trừ warm-cache/cherry-pick inflating. Raw runs của builder (14.9–15.2ms) cũng tight, tương tự của tôi (12.0–13.4ms) → khác biệt nhiều khả năng do trạng thái máy (turbo/nhiệt/background) giữa hai thời điểm.
**Hệ quả quan trọng:** run A của tôi (809 MB/s) **vượt chính gate ≥800** mà CHANGELOG tuyên bố "KHÔNG ĐẠT" do "sàn kiến trúc ~700 MB/s". Profile thành phần của tôi (sha 2.46ms + crc 2.68ms + zstd readinto 1.78ms = 6.92ms/10MB ≈ 1445 MB/s capacity lý tưởng; zstd+sink+final-copy 6.72ms) cho thấy tổng 12.36ms đạt được — tức khoảng cách tới "floor" không phải định luật. Lập luận "muốn ≥800 phải đổi API trả về của decompress()" vì vậy **chưa được chứng minh**; deviation khai báo là trung thực (giữ nguyên 666.6, không làm đẹp) nhưng nhãn "sàn kiến trúc" cần hạ xuống "quan sát tại thời điểm đo". Khuyến nghị: Verifier chạy lại bench chính thức trên máy sạch trước khi trình user quyết gate.

---

## F5 — LOW: Coverage drift nhẹ, gate hoạt động

Claim: 53.68% branch-mode, `fail_under=53`. Chạy lại thật: `155 passed in 4.57s`, TOTAL **54.98%**, *"Required test coverage of 53.0% reached."*, EXIT=0. Số thay đổi theo môi trường là bình thường; ngưỡng set theo số đo thật (làm tròn xuống) — **PASS, không fraud**.

---

## CÁC CLAIM ĐÃ TÁI HIỆN ĐỘC LẬP — VERIFIED (không finding)

**V1 — CRC lũy tiến đúng tuyệt đối (c2_crc_oracle.py, 9/9 PASS).** Tự parse footer theo spec §2 (`nc*4+68`), tự tính `zlib.crc32` từng chunk **từ ORIGINAL data** (không dùng code thư viện), so từng entry:
```
[10MB+12345 mixed] nc=3 crc_oracle=OK mac=True gsha=True roundtrip=True -> PASS
[0B] nc=0 | [1B tail-flush] nc=1 | [exact 1024x1024] nc=1 (KHÔNG sinh chunk-zero)
[multiple+1 1025/1024] nc=2 | [24581/4096] nc=7 | [1MB/999983-prime] nc=2
[gzip crosscheck] | [store crosscheck]           => 9/9 PASS
```
Byte-for-byte identical với oracle độc lập trên mọi biên spec §4 yêu cầu — claim "byte-for-byte identical" của refactor **CHẤP NHẬN**.

**V2 — Dual-read thật, không giả (c3_dualread.py).** v1 known-size từ data thật: decompress+verify OK; **v1 + dict_len>0**: OK (2500 bytes khớp); **v1 UNKNOWN-size** (gzip NS downgrade): OK; **v3 → RevHashCorruptedError("unsupported version 3") trong 0.0ms**; **v2 cắt 32B MAC → Corrupted ("bad footer magic") trong 0.1ms** — không treo, không crash loại khác; MAC zeroed → Corrupted; version/footer mismatch → Corrupted (zstd wrap).

**V3 — Mutation MAC (c1).** 8/8 field bitflip bị chặn (xem F3/T1) — claim "tamper codec_id/level/chunk_size/original_size đều bị chặn" **đúng cho threat model vô tình** (xem F3 cho ranh giới).

**V4 — brotli non-seekable fix (c7_brotli.py).** `rg can_accept_more_input src/revhash/stream.py` → 0 hit; NS brotli roundtrip 90000 bytes equal=True; seekable brotli OK; `get_info` v2 OK.

**V5 — Bundle hash (build --check).** `python scripts/build_embedded.py --check` → `[build_embedded] --check OK: sha256:560564b5…(111477 bytes)`, EXIT=0. Size 111477B khớp TEAM_STATE M4. **Lưu ý trung thực:** `560564b5…` là **hash-over-src** (`__bundle_hash__`, build script tự tính từ HASH_FILES) — KHÔNG phải sha256 của file `revhash_embedded.py` (file-hash thật = `8967dcf0…`). TEAM_STATE ghi "Rebuild bundle: 111477B, sha256:560564…" dễ đọc nhầm thành file-hash → khuyến nghị ghi rõ "hash-over-src" ở lần sau. Không phải drift, không phải fake.

**V6 — 155 tests + ruff.** `pytest tests -q --cov` → **155 passed, EXIT=0**; `ruff check src/revhash` → All checks passed, EXIT=0.

**V7 — Scope audit CLEAN (có uỷ quyền).** `git status --porcelain` + `git diff --stat HEAD`: mọi file đụng tới đều quy được owner:
- `stream.py`/`header.py` — Core Stream Builder (đúng Owns);
- `__init__.py` (prealloc sink) — NGOÀI phạm vi gốc nhưng Coordinator cấp phép M3a-FU (TEAM_STATE:1327-1346) và M3a-RF (1370-1403);
- 4 file tests Nhóm A — Quyết định 2 của Coordinator (:1329); tôi review **toàn bộ diff từng hunk**: asserts cập nhật sang đúng công thức v2 (`nc*4+68` v.v.), không có assert bị làm yếu/bỏ;
- `test_embedded.py` 2 version-string — Coordinator (:1411); `pyproject.toml` version bump — Coordinator M4 (:1406) trên file thuộc Infra (vi phạm kỹ thuật nhỏ, đã self-declare);
- File mới `.github/`, `tox.ini`, `.pre-commit-config.yaml`, `docs/*_v05.md`, `TEAM_PLAN_V05.md` — đúng owner Infra/Researcher/Coordinator.
Không phát hiện file nào bị đụng ngoài danh sách.

**V8 — Deviation honesty PASS.** Gate ≥800 FAIL được khai báo đầy đủ ở CHANGELOG "Known Deviation" + TEAM_STATE M3a-RF/M4; raw runs công khai; không thấy dấu hiệu làm đẹp số (thực ra số claim còn thua số thật của tôi — xem F4). Trừ điểm "sàn kiến trúc ~700" như phân tích F4.

---

## KẾT LUẬN: APPROVE-WITH-FIXES

**Lý do APPROVE:** toàn bộ claim về tính đúng đắn dữ liệu được tái hiện độc lập thành công — CRC oracle 9/9, dual-read v1/v2/v3 + truncation, tamper-ngây thơ 8/8, MAC đúng chỗ ở cả 3 đường ghi (known/UNKNOWN/store-fallback/dict), 155 tests thật, bundle sync, scope sạch, deviation trung thực. Không có dấu hiệu "tự sướng" hay hỏng ngầm về data.

**FIX list trước khi handover user (M6):**
1. **[Bắt buộc, code]** F2 — dời/lazy prealloc sau MAC-verify hoặc hạ cap theo hệ số `compressed_len`; sửa docstring `_PreallocWriter`/`_peek_size_hint` đang tuyên bố ngược hành vi thật.
2. **[Bắt buộc, docs]** F1 — xóa hoặc tạo thật `benchmarks/bench_cold.py` + `benchmarks/results_v05.json`; CHANGELOG không được trích dẫn artifact không tồn tại.
3. **[Bắt buộc, docs]** F3 — thêm caveat "header_sha256 = digest phi khoá, chống lỗi ghi; chống chủ đích = HMAC (v0.6)" vào CHANGELOG + README Limitations.
4. **[Khuyến nghị, process]** F4/F1 — chạy lại M5 đúng thiết kế: Verifier bench cold chính thức (kèm baseline same-machine trong cùng phiên) trước khi trình quyết định gate; nhãn "sàn kiến trúc ~700" đổi thành "quan sát đo được tại thời điểm X".
5. **[Cosmetic]** V5 — ghi rõ `560564b5…` là hash-over-src, khác file-hash `8967dcf0…`.

*Critic — 2026-08-28. Scripts tái hiện: `C:\Users\Admin\AppData\Local\Temp\opencode\critic_v05\`.*

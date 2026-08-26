# DESIGN FREEZE — revhash v0.5.0 (docs/api_v05.md)

> **Trạng thái:** ĐÓNG BĂNG bởi Coordinator sau M1. Core Stream Builder triển khai theo đúng spec này.
> **Nguồn:** `docs/research_v05.md` (M1) + spot-check code thật ngày 28-08-2026.
> **Quyết định thay đổi spec này chỉ do Coordinator** — builder phát hiện mâu thuẫn phải DỪNG và báo, không tự sửa.

---

## 0. Chốt 7 câu hỏi mở từ M1

| # | Câu hỏi | Quyết định |
|---|---|---|
| 1 | MAC header = SHA-256 32B hay CRC32 4B | **SHA-256 32B** — nhất quán với `global_sha256`, không thêm dependency, CRC32 4B quá yếu chống tamper có chủ đích |
| 2 | Ghi v2 mặc định hay opt-in | **Mặc định ghi v2**, đọc chấp nhận cả v1 lẫn v2 (dual-read) |
| 3 | Tách `_decompress_core` trước hay sửa song song 2 nhánh | **Sửa trực tiếp CẢ HAI nhánh trùng lặp** (`_process_out` stream.py:744-758 và `_proc` stream.py:889-903); refactor tách hàm dời sang v0.6 để giảm rủi ro |
| 4 | Gate tốc độ cold v0.5 | **Decompress ≥800 MB/s** (10MB text_repeat, cold median-of-5); **Compress ≥850 MB/s** giữ nguyên; đo theo quy trình §4 |
| 5 | HMAC opt-in vào v0.5 hay v0.6 | **Backlog v0.6** — ghi vào CHANGELOG phần "Unreleased" |
| 6 | Blob UNKNOWN_SIZE có MAC header không | **Có** — footer v2 luôn chứa `header_sha256` bất kể `original_size == UNKNOWN_SIZE` |
| 7 | Version bump + bundle | **0.5.0**; Coordinator rebuild bundle duy nhất ở M4 |

---

## 1. Header — KHÔNG ĐỔI layout

23 byte, struct `<4sBBBIIQ` (header.py:39): magic `RVH1`, **version**, codec_id, level, chunk_size, dict_len, original_size.

## 2. Footer v2 — thêm `header_sha256`

```
v1 (cũ, chỉ đọc):  [crc_table nc*4]  [global_sha256 32] [RVHE 4]      # unknown-size: bỏ crc_table
v2 (mới, ghi):     [crc_table nc*4]  [header_sha256 32] [global_sha256 32] [RVHE 4]  # unknown-size: bỏ crc_table
```

- `header_sha256 = sha256(23 byte header FINAL)` — tính SAU khi patch `original_size` (stream.py:368-398) và SAU store-fallback rewrite header (stream.py:444-466).
- `global_sha256`: giữ nguyên ngữ nghĩa (phủ toàn bộ payload).
- `_compute_footer_len` (stream.py:159-163) thành **version-aware**: v1 → `nc*4+36` / `36`; v2 → `nc*4+68` / `68`. Đồng bộ đủ 4 nơi theo research §điểm 5: header.py:153-158, header.py:285-319, stream.py:159-163, stream.py:703-719.
- `HEADER_VERSION` (header.py:33) `1 → 2`. Nới đúng 2 điểm check đọc: header.py:214-215 và stream.py:139-140 thành `version not in (1, 2)`.

## 3. Verify pipeline v2

Đọc (decompress + verify chung đường): parse 23B header → nếu `version==2`: tính `sha256(hdr_bytes + dict_data)` so với `header_sha256` trong footer **TRƯỚC khi decompress** (buffer sẵn có `full` ở stream.py:147) — sai → `RevHashCorruptedError`; `verify()` trả `False` tự nhiên. Nếu `version==1`: hành vi cũ nguyên vẹn (payload-only).

Ghi: mọi blob mới là v2 (kể cả UNKNOWN_SIZE, kể cả store-fallback).

## 4. CRC lũy tiến — thuật toán bắt buộc (thay `pending`)

Chỉ chạy khi `original_size != UNKNOWN_SIZE`. State: `crc_cur: int` (giá trị crc đang dở của chunk hiện tại), `pos_in_chunk: int`, `crc_computed: list`.

```python
def _feed(mv_block: bytes) -> None:          # mv_block = block decode ra, KHÔNG copy thêm
    o = 0; n = len(mv_block)
    while o < n:
        take = min(n - o, chunk_size_local - pos_in_chunk)
        crc_cur = crc32_local(mv_block[o:o + take], crc_cur)
        pos_in_chunk += take; o += take
        if pos_in_chunk == chunk_size_local:
            crc_computed.append(crc_cur & 0xFFFFFFFF)
            crc_cur = 0; pos_in_chunk = 0

# sau vòng decode kết thúc (flush):
if header.original_size != UNKNOWN_SIZE and pos_in_chunk > 0:
    crc_computed.append(crc_cur & 0xFFFFFFFF)
```

- Kết quả phải **byte-for-byte identical** với cách cũ trên mọi input (tính chất chaining của `zlib.crc32`).
- Biên bắt buộc test: 0B (0 chunk), 1B (tail flush), đúng bằng bội chunk_size (KHÔNG được phát sinh chunk-zero), size không chia hết, multi-chunk lớn.
- `sha.update(out)` + `writer.write(out)` giữ nguyên vị trí/thứ tự.

## 5. Benchmark COLD (ràng buộc cho Verifier, không phải builder)

Theo `docs/research_v05.md` §Phần 3: data object mới mỗi run qua `bytes(bytearray(...))`, `gc.collect()` trước mỗi run, bỏ run đầu (warm-up allocator), median-of-5, ghi raw từng run vào `benchmarks/results_v05.json`. Script mẫu: `benchmarks/bench_cold.py`.

## 6. Deliverable & ràng buộc Core Stream Builder

- Sửa CHỈ: `src/revhash/stream.py`, `src/revhash/header.py`.
- KHÔNG đụng: tests/, pyproject.toml, revhash_embedded.py, README, CHANGELOG, docs/.
- Gate thoát M3a: (a) 155 tests cũ PASS; (b) blob mới verify=True, tamper `codec_id/level/chunk_size/original_size` từng field 1 byte → verify=False hoặc raise Corrupted; (c) blob v1 tạo bằng script tạm (ghi tay version=1 + footer không header_sha256) vẫn decompress+verify OK; (d) smoke tốc độ decompress cải thiện rõ (>2× so với 241 MB/s, số chính thức do Verifier chốt).
- Ghi chú trong `TEAM_STATE.md` mục `[Core Stream Builder]`.

## 7. Deliverable Infra Builder (M3b)

- Tạo `.github/workflows/ci.yml`: matrix Python 3.9/3.11/3.12; steps: install `-e .[dev]` + brotli zstandard; `pytest --cov=revhash --cov-report=term-missing`; `ruff check src/revhash`; `mypy src/revhash --ignore-missing-imports`; `python scripts/build_embedded.py --check`.
- Tạo `tox.ini` (py39/py311/py312 map cùng lệnh) + `.pre-commit-config.yaml` (ruff + ruff-format + mypy-local tuỳ chọn).
- `pyproject.toml`: chỉ thêm `[tool.coverage.run]`/`[report]` + dev-deps cần thiết (`pytest-cov`). KHÔNG đổi version, KHÔNG đụng mục khác.
- Gate thoát M3b: chạy local được đúng chuỗi lệnh CI (pytest --cov ra số thật; đặt `fail_under` THEO SỐ ĐO THẬT làm tròn xuống, không bịa). KHÔNG đụng `src/revhash/*`, tests/.

## 8. Rủi ro chốt từ M1 (theo dõi ở M5)

1. Bundle hash `54400620…` sẽ đổi sau rebuild — cập nhật mọi nơi tham chiếu (Coordinator M4).
2. Fixture cứng version/footer-length: test_header.py:32-33,136, test_codec.py:109 — Verifier bổ sung test riêng, không sửa ý nghĩa test cũ.
3. CRC biên chunk — Critic bắt buộc tái hiện độc lập với size lạ (4M+123, 1B, bội chính xác).

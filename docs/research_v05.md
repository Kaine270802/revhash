# Research v0.5 — Header v2 (chống tamper bypass) + CRC lũy tiến + Benchmark COLD

> **Role:** Researcher — Team revhash v0.5 · **Ngày:** 2026-08-26 · **Workspace:** `D:\data optimization`
> **Inputs đã đọc (file:line thật):** `src/revhash/header.py` (333 dòng), `src/revhash/stream.py` (1236 dòng — phần header/footer/dispatch/_proc/_finish), `tests/test_header.py`, `tests/test_codec.py`, `reports/critique_speed_clean.md`, `reports/critique.md`, `docs/api.md`, `pyproject.toml`.
> **Phạm vi:** READ-ONLY trừ file này. Không sửa product file nào.

---

## 0. Tóm tắt trạng thái đo được (evidence đầu vào)

| Vấn đề | Evidence |
|---|---|
| Tamper `chunk_size` 1M→4M → `verify()==True` (phải là False) | Repro của team; trùng khít B3 trong `reports/critique_speed_clean.md:82-92` và Risk #1 trong `reports/critique.md:31-46` |
| Tamper `level` 3→22 → `verify()==True` | Như trên |
| Nguyên nhân gốc | `global_sha256` ở footer chỉ phủ **payload gốc** — `sha.update(chunk)` chỉ được gọi trên dữ liệu đọc từ reader (vd `stream.py:352`); không có byte header nào được đưa vào hash/CRC. `verify()` (`src/revhash/__init__.py:212-233`) chỉ gọi `decompress()` rồi bắt exception, không hề kiểm tra riêng header fields |
| Decompress chậm do copy 3 lần buffer pending | `stream.py:897` (`pending.extend(out)`), `stream.py:899` (`chunk = bytes(pending[:chunk_size_local])`), `stream.py:901` (`del pending[:chunk_size_local]`) → đo team: decompress 241 MB/s vs raw zstd 2388 MB/s; khớp hướng CLI cold đo được 272.7 MB/s (`reports/critique_speed_clean.md:325`) |
| Warm-cache artifact benchmark v0.4 | R1 `reports/critique_speed_clean.md:45-62`: warm 917 vs cold 682 MB/s @1MB (+34.4%); warm 959 vs cold 812 @10MB (+18.1%). Nguyên nhân: harness tái sử dụng cùng data object (`benchmarks/run_benchmark.py:101-111`) + identity cache `codec.py:244-267` + double-compress vô điều kiện `__init__.py:193` |

Struct thật (cơ sở mọi phân tích dưới đây) — `header.py:31-39`:

```
HEADER_MAGIC = b"RVH1"          # dòng 31
HEADER_VERSION = 1              # dòng 33
HEADER_SIZE = 23                # dòng 35  (4+1+1+1+4+4+8)
HEADER_STRUCT = struct.Struct("<4sBBBIIQ")   # dòng 39: magic4, ver1, codec_id1, level1, chunk_size4LE, dict_len4LE, original_size8LE
```

Layout đầy đủ theo spec `docs/api.md` §3.1 (dòng 124-138) và docstring `header.py:5-17`:

```
[0..22]   header 23B (magic|version|codec_id|level|chunk_size|dict_len|original_size)
[23..]    dict_data (dict_len byte, nếu có)
[...]     compressed_stream
[...]     per_chunk_crc: Nc*4 byte LE  (Nc = ceil(original_size/chunk_size), header.py:142-146)
[...+32]  global_sha256  ← CHỈ PHỦ PAYLOAD GỐC
[tail 4]  footer_magic b"RVHE"
```

---

## Phần 1 — Header v2 options (chống tamper header bypass)

### 1.0 Yêu cầu ràng buộc rút ra từ code thật

Trước khi so sánh phương án, 4 ràng buộc kỹ thuật bắt buộc phải thoả (đã verify trên source):

1. **Có đúng 2 nơi hard-check version==1** khi đọc:
   - `header.py:214-215` — `if version != HEADER_VERSION: raise RevHashCorruptedError("unsupported version ...")`
   - `stream.py:139-140` — `if version != 1: raise RevHashCorruptedError("unsupported version {version}")` trong `_parse_header_from_reader`.
   Dual-read chỉ cần nới 2 điểm này thành `in (1, 2)`.
2. **Header bị patch SAU khi đã ghi compressed stream**: `original_size` được vá trực tiếp vào blob tại offset 15 khi writer seekable (`stream.py:368-398`, cụ thể `writer.seek(start_pos + 15); writer.write(struct.pack("<Q", total_raw))`). Store-fallback còn ghi lại header + footer lần thứ 2 (`stream.py:444-466`). ⇒ **Bất kỳ MAC nào tính trên header đều phải tính SAU khi header đã final**, tức là lúc ghi footer — không thể nhét MAC vào trong header rồi ký chính nó trước khi biết `original_size`.
3. **Footer length là phép toán nhiều nơi phụ thuộc**: `header.footer_len()` (`header.py:153-158`), `_compute_footer_len` (`stream.py:159-163`), tách footer ở nhánh seekable (`stream.py:703-719`: `compressed_bytes = remaining[:-footer_len]`), và `parse_footer` (`header.py:258-319`, vị trí CRC area `crc_start = total - expected_footer_len` tại dòng 304). Thay đổi kích thước footer ⇒ phải đồng bộ cả 4 nơi, nếu không phép tách stream/footer lệch toàn bộ.
4. **Đã sẵn có buffer header bytes hoàn chỉnh khi đọc**: `_parse_header_from_reader` ghép `full = hdr_bytes + dict_data` (`stream.py:147`) — tái sử dụng được ngay để tính MAC phía decoder mà không cần seek ngược.

> **Ghi chú an ninh trung thực:** mọi checksum/MAC lưu **in-band** (cùng blob) đều chỉ chống *hỏng ngẫu nhiên* và *tamper ngây thơ* — kẻ tấn công chủ động đủ công cụ luôn recomput được CRC32/SHA256. Muốn authenticity thật phải dùng keyed-HMAC với key ngoài blob (xem PA3). Mức độ bảo vệ của PA1/PA2 là: `verify()` phải trả **False** cho mọi bit-flip/sửa-field, kể cả header — đóng đúng bypass đã đo.

### 1.1 So sánh 3 phương án

| Tiêu chí | **PA1 — Dual-read (khuyến nghị)** | **PA2 — Strict bump** | **PA3 — HMAC-keyed (opt-in)** |
|---|---|---|---|
| Version byte ghi mới | `2` | `2`, đọc v1 bị từ chối | `2` (kèm cờ `hmac_key`) |
| Blob v0.4 (version=1) đọc được? | ✅ Có — nhánh verify cũ (payload-only) | ❌ Không — `RevHashUnsupportedVersion` | ✅ Có (nhánh v1 như PA1) |
| Layout byte | Header **giữ nguyên 23B** (`HEADER_SIZE` không đổi). Footer v2 thêm 32B: `[per_chunk_crc Nc*4][header_sha256 32B][global_sha256 32B][b"RVHE"]`; UNKNOWN: `[header_sha256 32B][global_sha256 32B][b"RVHE"]` | Như PA1 (footer mở rộng) hoặc mở header 23→27B thêm `header_crc32` | Như PA1, `header_sha256` → `hmac_sha256(key, header)` |
| MAC tính thế nào | **Sau khi header final** (post-patch `stream.py:368-398`, post store-fallback rewrite `stream.py:449-452`): `mac = sha256(header_final_bytes).digest()` ghi ngay trước `sha.digest()` tại 2 điểm ghi footer (`stream.py:404-405` nhánh UNKNOWN, `stream.py:414-417` nhánh known, và bản ghi lại ở `stream.py:462-466`). Decoder: sau `_parse_header_from_reader` lấy `full` (`stream.py:147`) hoặc `blob[:header_end]`, so `sha256(full) == header_sha256` **trước khi** decompress 1 byte nào | Như PA1 | `hmac.new(hmac_key, header_final_bytes, hashlib.sha256).digest()`; API `compress(..., hmac_key=b"...")`, `verify(..., hmac_key=...)`; key KHÔNG lưu blob |
| Verify header tamper? | ✅ chunk_size/level/codec_id/dict_len/original_size flip bất kỳ → `verify()==False` ngay trước decompress | ✅ Như PA1 | ✅ và kẻ sửa mà **không có key** không thể forge MAC (authenticity thật) |
| Tương thích ngược cụ thể | Chỉ sửa 2 điểm check version (`header.py:214-215`, `stream.py:139-140`) thành accept `(1,2)`; 4 nơi footer-length thêm nhánh `if version==2: +32B`; `parse_footer` (`header.py:285-319`) thêm nhánh cắt `header_sha256` trước global_sha. Blob v1 đi nguyên luồng cũ — zero risk cho dữ liệu cũ | Người dùng v0.4 phải decompress bằng 0.4 rồi recompress; mọi fixture/test dùng blob dựng tay version=1 (`test_header.py:136`) chết | Như PA1 + thêm surface API key management |
| Chi phí hiệu năng | sha256 trên 23–262KB header ≈ **<0.2 ms/blob** (worst case dict 256KB, sha256 ~1–2 GB/s); payload path không đụng tới | Như PA1 | Như PA1 (HMAC ≈ SHA256 + vài µs) |
| Độ phức tạp code | **~40–60 dòng** thay đổi (header.py + stream.py + tests). Không đổi HEADER_SIZE ⇒ không vỡ offset test hiện có (`test_codec.py:114-121` đọc offset 7–23 không ảnh hưởng) | ~15–20 dòng nhưng breaking change | PA1 + ~30 dòng API/key plumbing |
| Rủi ro chính | Quên đồng bộ 1 trong 4 nơi footer-length; fixture test cứng version byte (mục 4) | Mất người dùng cũ, trái yêu cầu kế hoạch (dual-read là bắt buộc) | Key distribution — ngoài scope thư viện nén mặc định |

### 1.2 Vì sao PA2 (strict) bị loại

- PA2 chỉ đơn giản hoá ~25 dòng code so với PA1 nhưng đánh đổi **mọi blob v1 hiện hành không đọc được** — vi phạm chính yêu cầu của kế hoạch v0.5 ("blob cũ vẫn đọc được").
- Lợi thế "một luồng verify duy nhất" của PA2 là ảo: PA1 vốn đã phải giữ luồng verify v1 cho blob cũ, nên thêm nhánh v2 chỉ là if-version, không phải nhân đôi code.
- Thư viện mới (v0.x), nhưng format blob là dữ liệu dài hạn trên đĩa — strict bump là lựa chọn cuối cùng khi PA1 chứng minh không khả thi. Code thật cho thấy PA1 khả thi (ràng buộc 1–4 ở §1.1 đều có đường xử lý rõ).

### 1.3 PA3 — đánh giá và vị trí trong roadmap

- **HMAC-keyed** là phương án DUY NHẤT cho authenticity thật (chống attacker chủ động recompute MAC). Nhưng cần key management (sinh/lưu/truyền key) — vượt phạm vi một thư viện nén; nên làm **opt-in** `hmac_key=None` mặc định, backlog v0.5.x/v0.6.
- Biến thể nhẹ hơn của ý tưởng "MAC nhanh": `CRC32C` (SSE4.2 hardware) cho phần header — nhanh hơn zlib.crc32 nhưng Python stdlib **không có** CRC32C (cần package `google-crc32c` → thêm dependency, trái định hướng zero-deps của bundle embedded). zlib.crc32 trên 23 byte đã quá nhanh để tối ưu thêm. **Không khuyến nghị cho v0.5.**

### 1.4 Kết luận đề xuất

> **Chọn PA1 (dual-read) cho v0.5** — xác nhận KHẢ THI dựa trên struct thật:
>
> 1. `HEADER_VERSION` giữ constant `1` cho việc *đọc*; thêm `WRITE_HEADER_VERSION = 2` (hoặc nâng `HEADER_VERSION = 2` và đọc accept `(1, 2)` — chốt ở Design Freeze, xem mục 4 Q2).
> 2. Nới đúng 2 điểm check version: `header.py:214-215`, `stream.py:139-140`.
> 3. Footer v2 = footer cũ **+ 32B `header_sha256`** đặt ngay trước `global_sha256`. Đồng bộ 4 nơi footer-length: `header.py:153-158`, `stream.py:159-163`, `stream.py:703-719`, `parse_footer` `header.py:285-319`.
> 4. MAC tính **sau cùng** ở 3 điểm ghi footer (UNKNOWN `stream.py:404-405`, known `stream.py:414-417`, store-fallback rewrite `stream.py:462-466`) trên header bytes đã final — khắc phục đúng vấn đề patch-original_size muộn (`stream.py:368-398`).
> 5. Decoder verify header-MAC **trước** khi decompress (dùng `full` từ `stream.py:147`) → tamper header trả `RevHashCorruptedError`, `verify()` tự động trả False vì đã catch (`__init__.py:222-233`) — không cần sửa `verify()`.
> 6. Ghi rõ Limitation: in-band MAC = integrity, không phải authenticity; nhu cầu thật → PA3 opt-in sau.

---

## Phần 2 — CRC lũy tiến (incremental) thay buffer `pending`

### 2.1 Hiện trạng và chi phí

Nhánh seekable `decompress_stream`, `stream.py:885-903`:

```python
pending = bytearray()                       # 885
def _proc(out):                             # 889
    ...
    if header.original_size != UNKNOWN_SIZE:
        pending.extend(out)                 # 897  ← copy (1)
        while len(pending) >= chunk_size_local:
            chunk = bytes(pending[:chunk_size_local])   # 899  ← copy (2) + slice
            crc_computed.append(crc32_local(chunk) & 0xFFFFFFFF)
            del pending[:chunk_size_local]  # 901  ← memmove phần còn lại (3)
```

Nhánh non-seekable lặp lại y hệt tại `stream.py:752-756` (tail `834-837`), seekable tail tại `988-990`. Với N byte decompressed: **3N byte copy** qua bytearray (extend + slice + delete-memmove) — giải thích decompress 241 MB/s vs raw zstd 2388 MB/s. Lưu ý `del pending[:N]` là O(len(pending)) memmove mỗi chunk.

### 2.2 Nền tảng: CRC32 hỗ trợ chaining chuẩn

`zlib.crc32(data, value)` cộng dồn: `zlib.crc32(b"c", zlib.crc32(b"ab")) == zlib.crc32(b"abc")`. Codebase đã dùng crc32 từng-chunk độc lập ở `compute_per_chunk_crcs` (`header.py:322-328`) — ta giữ đúng ngữ nghĩa đó nhưng tính **lũy tiến trên từng mảnh nhỏ** của `out`.

### 2.3 Pseudocode thay thế (áp dụng cho CẢ HAI nhánh: `_process_out` 744-758 và `_proc` 889-903)

```python
# ── State thay cho `pending` (khởi tạo trước dispatch codec):
crc_cur      = 0    # CRC đang dồn của chunk HIỆN TẠI (chưa đóng)
pos_in_chunk = 0    # số byte đã tiêu thụ trong chunk hiện tại  (= total_out % chunk_size)

def _proc(out: bytes) -> None:
    nonlocal total_out, crc_cur, pos_in_chunk
    if not out:
        return
    sha.update(out)                     # giữ nguyên (893)
    total_out += len(out)
    writer.write(out)                   # giữ nguyên (895)
    if header.original_size == UNKNOWN_SIZE:
        return                          # spec: UNKNOWN không có per-chunk CRC (như guard cũ 896/751)

    mv  = memoryview(out)               # slice của memoryview KHÔNG copy dữ liệu
    off = 0
    while off < len(mv):
        take = min(chunk_size_local - pos_in_chunk, len(mv) - off)
        crc_cur = crc32_local(mv[off : off + take], crc_cur)   # chaining, không buffer trung gian
        pos_in_chunk += take
        off += take
        if pos_in_chunk == chunk_size_local:       # chunk vừa đầy → đóng
            crc_computed.append(crc_cur & 0xFFFFFFFF)
            crc_cur = 0
            pos_in_chunk = 0
    # hết `out`: phần dư (< chunk_size) nằm gọn trong (crc_cur, pos_in_chunk)
    #             → KHÔNG cần buffer byte nào giữ lại
```

Tail sau khi dispatch kết thúc — **thay** `stream.py:987-990` và `834-837`:

```python
if header.original_size != UNKNOWN_SIZE and pos_in_chunk > 0:
    # chunk CUỐI nhỏ hơn chunk_size → đóng bằng CRC đã dồn
    crc_computed.append(crc_cur & 0xFFFFFFFF)
    crc_cur = 0
    pos_in_chunk = 0
```

### 2.4 Chứng minh xử lý đúng biên

| Trường hợp | Diễn biến | Kết quả |
|---|---|---|
| `out` không chia hết chunk_size (thực tế: zstd trả `read(131072)` — `stream.py:783/925` — gần như không bao giờ thẳng hàng biên chunk 4MB) | Vòng `while` bên trong đóng các chunk đầy; phần dư mang sang lần `_proc` kế tiếp qua `(crc_cur, pos_in_chunk)` — chaining CRC nối đúng mảnh | CRC từng chunk == oracle |
| Chunk cuối nhỏ hơn chunk_size | Sau dispatch, `pos_in_chunk ∈ (0, chunk_size)` → tail flush đúng 1 CRC cuối | Khớp `compute_per_chunk_crcs` (`header.py:322-328`, iterate `range(0, len, chunk)`) |
| Tổng đúng bội chunk_size | Khi chunk cuối đầy, đã đóng trong vòng lặp → `pos_in_chunk == 0` → tail **không** phát sinh chunk-zero thừa | Số CRC == `num_chunks` đúng |
| 0 byte | Không `_proc` nào có dữ liệu; `crc_computed == []`, `num_chunks == 0` (`header.py:144-146`) | Khớp footer rỗng |
| 1 byte | 1 lần partial → tail flush 1 CRC của 1 byte | Khớp oracle |
| UNKNOWN_SIZE | Guard sớm return — không tích lũy gì (giữ semantics cũ `stream.py:896`, `751`) | Footer 36B như spec |

Độ phức tạp copy giảm từ **3N byte → 0 byte** (memoryview slice là view; chỉ tốn O(số-mảnh) overhead gọi hàm crc32). Chi phí CPU crc32 thuần không đổi.

### 2.5 Test biên bắt buộc (builder phải thêm trước khi thay code)

1. **Oracle diff**: với `sizes = [0, 1, 1023, 1024, 1025, 3*chunk+123, 4*chunk]` × 5 codec × {seekable, non-seekable}: `crc_computed == header.compute_per_chunk_crcs(raw, chunk_size)` (`header.py:322-328`).
2. **0B và 1B** roundtrip + `verify()` True (đã có pattern `test_codec.py:196-203`).
3. **Multi-chunk không chia hết** (vd 4M+123 — pattern cũ `reports/critique.md:174`).
4. **Fuzz mảnh đọc lệch biên**: mock decompressor trả `out` kích thước ngẫu nhiên 1..200KB để chứng minh state `(crc_cur, pos_in_chunk)` xuyên `_proc` calls đúng (giả lập zstd/gzip thực tế).
5. **Tamper vẫn detect**: flip 1 byte payload → CRC mismatch raise (`stream.py:998-1001` logic giữ nguyên).
6. **Hai nhánh song song**: non-seekable `_process_out` (`stream.py:744-758`) và seekable `_proc` (`stream.py:889-903`) là code TRÙNG LẶP ~600 dòng chưa tách (`reports/critique_speed_clean.md` mục 5, C5 defer) — **cả hai phải patch giống nhau**, kèm test chạy cả hai đường (`tests/test_stream.py` NonSeekable pattern).

---

## Phần 3 — Quy trình benchmark COLD chống warm-cache

### 3.1 Quy trình chuẩn (builder + verifier dùng chung, bắt buộc ghi vào results JSON)

| # | Bước | Lý do (evidence) |
|---|---|---|
| 1 | **Tạo data object MỚI mỗi run**: `data = bytes(bytearray(base_payload))` bên trong timed-region setup | (a) CPU L1/L2/L3 giữ nội dung buffer cũ giữa các lần lặp cùng object → throughput giả. (b) Né identity-cache `codec.py:244-267` (key chứa `id(data)` + `data is _LAST_RAW_DATA_REF`) khiến loop same-object **skip toàn bộ bước nén raw thứ 2** (`__init__.py:193`) — đúng artifact R1 (+34.4%/+18.1%, `critique_speed_clean.md:51-56`). (c) Phải đi qua `bytearray` vì CPython `bytes(bytes_obj)` trả về **chính object gốc** — copy ảo (`critique_speed_clean.md:56`) |
| 2 | `gc.collect()` ngay trước mỗi run | Phá allocator-reuse: pymalloc arena của run trước được trả lại và cấp phát tức thì cho run sau → cache-warm ảo; đồng thời đẩy GC pause ra khỏi timed-region |
| 3 | `revhash.codec._cache_clear()` (tồn tại tại `codec.py:306`) trước mỗi run | Belt-and-braces: vô hiệu single-entry cache kể cả khi bước 1 bị ai đó "tối ưu" lại |
| 4 | **Bỏ run đầu tiên** (warmup), lấy **median của 5 run** tiếp theo | Run đầu chứa lazy-init (HAS_ZSTD detect, code objects, import zstandard). Median bền với outlier scheduler/OS; **raw số từng run vẫn ghi đủ vào JSON** (anti-hardcode, audit được) |
| 5 | **Đo compress và decompress RIÊNG BIỆT** (2 timer) | Hai pipeline chi phí khác nhau (decompress có thêm CRC-slice + SHA-verify); đo gộp che giấu regression một phía (đúng bài toán 241 vs 2388 MB/s đang điều tra v0.5) |
| 6 | Assert roundtrip + SHA trong mỗi run (ngoài timed-region) | Đảm bảo đo đúng đường đi functional, không phải fast-path lỗi im lặng |
| 7 | Ghi `runs_raw` từng run + `median` + python/platform vào `results_cold.json` | Verifier/Critic đối chiếu độc lập; cấm chỉ publish median không có raw |

### 3.2 Script ví dụ chạy được (PowerShell-safe — viết ra file rồi chạy)

Lưu thành `benchmarks/bench_cold.py`:

```python
"""Cold benchmark cho revhash — chống warm-cache artifact (docs/research_v05.md §3).

Mỗi run: buffer dữ liệu MỚI (bytearray->bytes copy thật) + gc.collect() +
_cache_clear(); bỏ run đầu; median của N run; ghi raw từng run vào JSON.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import statistics
import sys
import time

import revhash


def make_base(n: int) -> bytes:
    pool = b"hello world revhash "
    return (pool * ((n // len(pool)) + 1))[:n]


def run_once(n: int, codec: str) -> dict:
    data = bytes(bytearray(make_base(n)))  # buffer MỚI mỗi lần — copy thật, né identity-cache
    gc.collect()
    try:
        revhash.codec._cache_clear()
    except Exception:
        pass
    t0 = time.perf_counter()
    blob = revhash.compress(data, codec=codec)
    t1 = time.perf_counter()
    out = revhash.decompress(blob)
    t2 = time.perf_counter()
    assert out == data
    assert hashlib.sha256(out).digest() == hashlib.sha256(data).digest()
    mb = n / (1024 * 1024)
    return {
        "compress_s": t1 - t0,
        "decompress_s": t2 - t1,
        "compress_mb_s": mb / (t1 - t0),
        "decompress_mb_s": mb / (t2 - t1),
        "blob_len": len(blob),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="10M")           # vd 1K, 10M, 100M
    ap.add_argument("--codec", default="zstd")
    ap.add_argument("--runs", type=int, default=6)     # 1 warmup + 5 đo
    ap.add_argument("--out", default="benchmarks/results_cold.json")
    a = ap.parse_args()

    mult = {"K": 1024, "M": 1024**2, "G": 1024**3}
    n = int(a.size[:-1]) * mult[a.size[-1].upper()]

    runs = [run_once(n, a.codec) for _ in range(a.runs)]
    used = runs[1:] if len(runs) > 1 else runs         # bỏ run warmup đầu
    result = {
        "mode": "cold",
        "size_bytes": n,
        "codec": a.codec,
        "runs_total": a.runs,
        "warmup_discarded": 1,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "runs_raw": runs,                              # raw từng run — bắt buộc lưu
        "median_compress_mb_s": statistics.median(r["compress_mb_s"] for r in used),
        "median_decompress_mb_s": statistics.median(r["decompress_mb_s"] for r in used),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(
        f"[cold {a.codec} {a.size}] "
        f"comp={result['median_compress_mb_s']:.1f} MB/s "
        f"decomp={result['median_decompress_mb_s']:.1f} MB/s -> {a.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Chạy (PowerShell — không heredoc đa dòng):

```powershell
python benchmarks\bench_cold.py --size 1M  --runs 6 --codec zstd --out benchmarks\results_cold_1m.json
python benchmarks\bench_cold.py --size 10M --runs 6 --codec zstd --out benchmarks\results_cold_10m.json
```

### 3.3 Lưu ý áp dụng cho v0.5

- Gate speed v0.5 (nếu đặt) **phải dựa trên số cold này**, không dùng số warm v0.4 (782.9/955.4 — `critique_speed_clean.md:21-22` đã verdict WARN).
- Khi so sánh trước/sau patch CRC-lũy tiến (Phần 2), dùng cùng script, cùng size, cùng codec; kỳ vọng decompress tăng mạnh vì xoá 3N copy — đây là con số cần baseline cold **trước** khi patch.

---

## Phần 4 — Rủi ro migration & câu hỏi mở cho Design Freeze

### 4.1 Rủi ro migration header v2 (PA1)

| ID | Rủi ro | Chi tiết / vị trí | Mitigation |
|---|---|---|---|
| R-M1 | **Bundle embedded rebuild** | `revhash_embedded.py` chứa bản sao header/stream/init — mọi thay đổi src làm hash bundle đổi từ `sha256:54400620df8aa6bb…` (102337B). Test hash recompute từ HASH_FILES sẽ tự sync nhưng **file bundle phải regenerate + commit** (`scripts/build_embedded.py`, quy trình đã dùng ở v0.4 — `critique_speed_clean.md` SC3b) | Bắt buộc step cuối PR: build → `--check` → pytest |
| R-M2 | **Test fixture cứng version byte** | `test_header.py:32-33` assert `b[4]==1` + `hdr.version==1`; `test_header.py:136` `HEADER_STRUCT.pack(b"RVH1", 1, …)`; `test_codec.py:109` assert `blob[4]==1`; `test_header.py:89-94` assert constants. Nếu default ghi mới = 2, các assert này fail | Quyết Q2 (dưới đây); update fixture + thêm test dual-read v1/v2 cạnh nhau |
| R-M3 | **Footer-length lệch 1 trong 4 nơi** | `header.py:153-158`, `stream.py:159-163`, `stream.py:703-719`, `header.py:285-319` — sót một chỗ là tách compressed/footer sai toàn bộ blob v2 | Thêm unit test `footer_len(version=2)` + roundtrip v2 cho cả UNKNOWN/known/store-fallback |
| R-M4 | **Patch-original_size invalidate MAC sớm** | Nếu builder vô tình tính header-MAC trước `stream.py:368-398` → MAC stale với header đã patch | MAC chỉ tính tại 3 điểm ghi footer; test store-fallback path riêng (`stream.py:444-466` ghi footer lần 2) |
| R-M5 | **Docs frozen drift** | `docs/api.md` §3.1 là Design Freeze (dòng 120-140) — thêm footer field + version 2 phải có amendment + CHANGELOG, nếu không Verifier sẽ report mismatch spec-vs-code | Coordinator sign-off amendment cùng lúc freeze design v0.5 |
| R-M6 | **Integrity ≠ authenticity hiểu sai** | In-band SHA/CRC kẻ chủ động recomput được; không được quảng cáo "chống attacker" | README Limitations + docstring `verify()` nói rõ; HMAC (PA3) mới là authenticity |
| R-M7 | **CRC-lũy tiến sửa thiếu nhánh** | Hai implementation trùng lặp `_process_out` (`stream.py:744-758`) vs `_proc` (`stream.py:889-903`) — sửa một quên một → hành vi lệch giữa seekable/non-seekable | Test matrix cả 2 đường (§2.5-6); cân nhắc Q3 tách `_decompress_core` trước |
| R-M8 | **Perf gate cũ gây hiểu nhầm** | Gate 700/850 MB/s của v0.4 đo warm; v0.5 đo cold sẽ "thấp hơn" trên giấy dù trung thực hơn | Publish cột cold/warm song song như khuyến nghị P0-1 `critique_speed_clean.md:179` |

### 4.2 Câu hỏi Coordinator cần chốt ở Design Freeze

1. **Q1 — Loại MAC cho v0.5:** `header_sha256` (32B, nhất quán với global_sha256 — khuyến nghị) hay `header_crc32` (4B, tiết kiệm 28B/blob nhưng yếu hơn, vẫn đủ chống tamper ngây thơ)?
2. **Q2 — Version ghi mặc định:** nâng `HEADER_VERSION = 2` (ghi mới = v2, đọc accept 1&2 — khuyến nghị, phải update fixture R-M2) hay giữ ghi v1 mặc định + tham số `header_version=2` opt-in?
3. **Q3 — Trình tự refactor:** có tách `_decompress_core` (~600 dòng duplicate, deferred từ v0.4) **trước** khi patch CRC-lũy tiến để chỉ sửa một nơi, hay patch song song 2 nhánh như hiện trạng để thu hẹp diff?
4. **Q4 — Gate tốc độ cold v0.5:** con số cụ thể (vd decompress cold ≥ 500 MB/s @10MB zstd?) — cần chạy baseline `bench_cold.py` trước khi freeze, đừng đặt gate trên số warm cũ.
5. **Q5 — Scope HMAC (PA3):** đưa `hmac_key` opt-in vào v0.5 hay backlog v0.6?
6. **Q6 — UNKNOWN_SIZE blob v2:** xác nhận header-MAC vẫn được ghi cho blob UNKNOWN (header không bao giờ bị patch trong trường hợp này — `stream.py:381-384` — nên MAC tĩnh, đơn giản) — đề xuất: CÓ, ghi luôn.
7. **Q7 — Version bump release:** 0.5.0 đồng bộ 3 nơi (`pyproject.toml:7`, `__init__.__version__`, bundle `__version__`) + wheel PEP440 — xác nhận lịch rebuild bundle (R-M1).

---

*Tài liệu research — READ-ONLY output duy nhất: `docs/research_v05.md`. Toàn bộ file:line trích dẫn đã đối chiếu trực tiếp với source ngày 2026-08-26.*

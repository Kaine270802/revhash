# Critique Report — revhash v0.1.0 (Adversarial Audit)

> **Role:** Critic / Auditor — Team revhash  
> **Date:** 2026-08-26  
> **Auditor:** Muse Spark (Critic)  
> **Workspace:** `D:\data optimization`  
> **Scope:** `src/revhash/*.py`, `src/revhash/algorithms/*.py`, `tests/*`, `benchmarks/*`, `docs/*`, `reports/verification.md`, `TEAM_STATE.md`  
> **Mode:** Adversarial — không optimism, chỉ evidence `file:line`

---

## 1. Tổng quan — PASS/FAIL per Success Criteria (TEAM_PLAN.md)

| # | Success Criteria (TEAM_PLAN §1) | Target | Evidence thực đo | Verdict |
|---|----------------------------------|--------|------------------|---------|
| 1 | Encode mọi kích thước (0B→10GB) giảm dung lượng, tốt hơn gzip ≥15%, tiệm cận zstd/lzma | Ratio < gzip 5×, stable khi scale | `benchmarks/results.json`: zstd-3 10MB `0.00015` vs gzip `0.00491` **32×** tốt hơn; `benchmarks/results_verifier.json`: revhash header 10MB `0.000151` vs gzip `0.004913` → **96.9% (32.5×)** PASS cho ≥1MB. Nhưng 10KB text_repeat `0.06055` vs gzip `0.06650` chỉ **9.0%** FAIL threshold 15% do header overhead 59B | **CONDITIONAL PASS** — đạt cho ≥1MB, fail cho tiny <64KB |
| 2 | Decode 100% byte-identical SHA256 | 100% | `reports/verification.md` §3: 108/108 pass, 100 fuzz × tamper 100% detection, 50MB GenReader SHA iterative match. Tự verify extra: `py -3.12` `revhash.compress(b'hello'*1000) → decompress ==` PASS | **PASS** |
| 3 | Streaming O(1) memory <150MB cho mọi size (chunk 1-8MB) | Never `read()` toàn bộ, peak <150MB | `src/revhash/stream.py:257-263` dùng `stream_writer` đúng; `tests/test_stream.py:125-145` CountingReader chứng minh `read(chunk_size)` no `-1`. Peak tracemalloc: 20.6MB cho 10MB, 21.6MB cho 20MB PASS seekable. **Nhưng** `stream.py:610` non-seekable path `remaining = reader.read()` load toàn bộ compressed+footer → **FAIL O(1) cho pipe**; `cli.py:112/141` `p.read_bytes()` load toàn bộ blob cho `info/verify` → **FAIL cho file >RAM** | **FAIL** — O(1) chỉ đạt cho seekable file/BytesIO, không cho non-seekable pipe |
| 4 | Throughput tuyến tính O(n) 80-150 MB/s encode, 150-250 MB/s decode | Scale tuyến tính | Baseline `results.json`: zstd-3 100MB **7348 MB/s** encode, 2350 MB/s decode. Verifier `results_verifier.json`: revhash zstd 10MB 843 MB/s encode (header overhead làm chậm nhưng vẫn >500). PASS | **PASS** |
| 5 | API Python đơn giản `compress/decompress/compress_file/compress_stream/CLI` | Freeze `docs/api.md` | `src/revhash/__init__.py:70-172` exports đủ, `cli.py:286-325` argparse đủ 6 subcommands. Imports ok `py -3.12 -c "import revhash"` PASS | **PASS** |
| 6 | Robust: resume header, CRC per-chunk + global SHA, empty/1B/sparse/non-divisible | All edge | `header.py:23+N`, `stream.py:382-395` footer CRC+SHA+RVHE, empty 68B, 4M+123 →2 chunks PASS. **Nhưng** header fields (chunk_size/level) không được MAC → tamper không phát hiện khi Nc unchanged (see Risk #1) | **WARN** |
| 7 | Packaging `pyproject.toml`, `pip install -e .`, type hints, docs, 90%+ coverage | 90%+ | `pyproject.toml:24` chỉ `zstandard` mandatory, `brotli` optional hợp lý; `pip install -e .` ok verifier; 108 tests >90% gate PASS. Type hints thiếu 1 hàm `stream.py:98 readinto` nhưng chấp nhận | **PASS** |
| 8 | Verifier+Critic không hardcode, không fake ratio, test multi-size thực | Independent | `grep ratio hardcode` → không có; `results.json` 1728 dòng raw với `ok:true`, decompress thực PASS. Critic check §3 confirms | **PASS** |

**Overall:** **5/8 PASS, 1 CONDITIONAL, 1 WARN, 1 FAIL** → Không đủ điều kiện `PASS` toàn bộ. Cần fix P0 trước release.

---

## 2. Top 7 Risks thực (có file:line + evidence)

### Risk #1 — **HIGH** — Header malleability: `chunk_size`/`level` không được integrity-protect → tamper cùng Nc vẫn `verify==True`

- **Location:** `src/revhash/header.py:150-178` (header pack), `src/revhash/stream.py:914-925` (SHA chỉ cover payload, không cover header), `src/revhash/__init__.py:175-196` (verify = decompress, không check header MAC)
- **Evidence (tự reproduce `py -3.12`):**
  ```python
  blob = revhash.compress(b'hello'*1000, codec='zstd', chunk_size=1*1024*1024)
  # Nc = ceil(5000/1M)=1, tamper 1M->4M vẫn Nc=1
  ba=bytearray(blob); struct.pack_into('<I',ba,7,4*1024*1024)
  revhash.verify(bytes(ba))  # → True (BUG)
  revhash.decompress(bytes(ba)) == b'hello'*1000  # → True
  # level tamper 3->22 cũng True
  ba[6]=22; revhash.verify(bytes(ba)) # → True
  ```
  Verifier đã note trong `reports/verification.md §5`: *“chunk_size field corruption from 1048576 to 4278190080 still yields same Nc=1 for 10KB and passes CRC/SHA (header not MAC'd)”* nhưng vẫn mark PASS. Đây là **bypass**: attacker có thể đổi chunk_size hoặc level mà vẫn pass `verify`, làm sai `get_info` và per-chunk CRC boundary cho file lớn hơn (với file 4M+100 tamper 1M→4M đã **FAIL**: `py -3.12` big test `verify False` + `RevHashCorruptedError: Unknown frame descriptor` — nghĩa là tamper chỉ phát hiện khi Nc đổi, không phải mọi trường hợp).
- **Impact:** Toàn vẹn header không đảm bảo. `chunk_size` sai làm decoder chia chunk sai cho future incremental decode/resume. `level` sai làm audit khó. Nếu coi `verify` là security guarantee (docs/api.md §4 raise `RevHashCorruptedError`), thì header tamper là lỗ hổng.
- **Đề xuất fix:** Thêm `header_crc32` (4B) hoặc đưa header bytes vào `global_sha256` (tính SHA trên `header+original_data`) hoặc HMAC header. Đơn giản nhất: `header_crc = zlib.crc32(header_bytes)` thêm sau magic, verify trước khi decompress. Hoặc `sha.update(header_bytes)` trước payload. P0 nếu threat model gồm tamper.

### Risk #2 — **CRITICAL** — `decompress_stream` non-seekable path `reader.read()` toàn bộ → phá vỡ O(1), DoS OOM cho blob 1GB qua pipe

- **Location:** `src/revhash/stream.py:606-610` và `641-656`
  ```python
  # stream.py:610
  remaining = reader.read()  # read rest (compressed+footer)  ← non-seekable
  # ...
  compressed_bytes = remaining[:-36]  # all compressed held in RAM
  reader_for_decomp = BytesIO(compressed_bytes)
  ```
  Và `cli.py:112,123,141` cũng `p.read_bytes()` toàn bộ.
- **Evidence:** Grep `read()` violation duy nhất chính là dòng này. Verifier `reports/verification.md §11.5` đã thừa nhận: *“Non-seekable decompress buffer: reads entire remaining blob into memory. For GB file over non-seekable pipe, this would OOM.”* nhưng vẫn PASS. Test `test_stream.py:36-46` `NonSeekableReader` chỉ test 2MB, không test 100MB non-seekable decompress → không phát hiện OOM. `py -3.12` check confirms `remaining = reader.read()` tồn tại.
- **Impact:** Unlimited claim “file lớn hơn RAM” chỉ đúng cho **seekable file** (`open(..., 'rb')`). Với pipe/socket (đúng use-case `compress_stream`/`decompress_stream` cho pipe/socket per TEAM_PLAN), file 10GB sẽ OOM. Vi phạm contract `stream.py:14` *“never read() whole file”* và doc `decompress_stream(reader, writer)` hứa O(1).
- **Fix:** Streaming incremental cho non-seekable: cần framing với `chunk_len` prefix hoặc buffer vòng. Hiện tại format không có length prefix cho compressed stream (single-frame zstd không biết trước `compressed_len` cho đến khi đọc footer ở tail). Giải pháp: (a) yêu cầu `reader` seekable cho blob > memory và document rõ limitation, hoặc (b) đổi format streaming cho non-seekable: ghi `compressed_len` vào header (đã có `original_size` nhưng chưa có `compressed_size`) hoặc dùngChunked framing fallback. Ít nhất thêm check `if remaining_len > 500M raise RevHashCorruptedError("non-seekable blob too large")` và document. P0 cho unlimited pipe.

### Risk #3 — **HIGH** — `header.py:269-290` dead heuristic cho `UNKNOWN_SIZE` misinterprets `compressed_len` làm CRC area, có thể raise spurious `CorruptedError`

- **Location:** `src/revhash/header.py:262-293` `parse_footer` UNKNOWN branch
  ```python
  remaining_for_crc = total - header_end - FOOTER_SHA_SIZE - FOOTER_MAGIC_SIZE
  if remaining_for_crc > 0:
      if remaining_for_crc % 4 != 0:
          raise RevHashCorruptedError(...)
  ```
  Với `UNKNOWN` header, `total - header_end -36 = compressed_len` (ví dụ 708B cho 1MB payload), không phải CRC area. Nếu `compressed_len %4 !=0` (hầu hết 708%4=0 pass ngẫu nhiên, nhưng 620%4=0, 707%4=3) sẽ **raise sai**. Tuy nhiên decompress seekable không gọi `parse_footer` cho UNKNOWN mà tự xử lý riêng (`stream.py:550` footer_len=36), nên bug chưa kích hoạt trong verifier. Nhưng `revhash.get_info` gọi `RevHashHeader.from_bytes` + branch? `get_info` cho UNKNOWN với `total <20M` thì decompress toàn bộ để lấy size, nên tránh parse_footer. Trực tiếp gọi `parse_footer(blob, hdr, hdr_end)` với UNKNOWN blob (test_header không cover UNKNOWN + parse_footer) sẽ fail.
- **Evidence:** Đọc code: `header.py:269` `per_crcs=[]` khởi tạo, `remaining_for_crc` luôn >0 (compressed_len), nhưng ngay sau đó tính `nc_guess` và rồi lại `per_crcs=[]` unconditionally (`stream.py:290` comment *“Heuristic ... but then we cannot deduce CRCs”*). Code dead, raise path unreachable trong hầu hết test nhưng sai logic.
- **Impact:** Nếu ai dùng `parse_footer` public API (exported) cho UNKNOWN blob sẽ gặp lỗi giả. Maintainability risk, confuses future contributors. Không blocking runtime hiện tại nhưng là correctness bug.
- **Fix:** Sửa `parse_footer` UNKNOWN branch thành `return [], global_sha, footer_magic` ngay, bỏ heuristic hoặc document. Thêm test `test_header_unknown_parse_footer` . P1.

### Risk #4 — **HIGH** — `cli.py:58-59` `eval()` cho `_parse_size` cho phép DoS CPU/Memory (arithmetic bomb)

- **Location:** `src/revhash/cli.py:56-59`
  ```python
  if all(c in "0123456789*+ -/" for c in s):
      return int(eval(s, {"__builtins__": {}}, {}))
  ```
  Mặc dù filter chỉ cho số và `*+ -/`, attacker vẫn có thể truyền `--chunk-size "999999999*999999999*999999999"` → `~1e27` → `int` huge allocation cho `chunk_size` → `revhash.compress(..., chunk_size=1e27)` sẽ `read(chunk_size)` thử allocate 1e27? Thực tế `read(1e27)` sẽ cố đọc toàn bộ file vào RAM (O(1) broken) hoặc `header.chunk_size` sẽ pack `uint32` overflow? `struct.pack("<I", chunk_size)` sẽ fail hoặc wrap. Chưa kể eval loop có thể chạy lâu với `999999*999999*...` repeated? Filter không chặn `**`? `*` allowed nên `**` thành power? `eval("2**999999")` với `*` filter cho phép `*`, nhưng `**` cần `*` twice, vẫn pass? Thực tế `eval("2**30")` với filter `*` allowed yes, `**` là two chars, both in set, nên `eval` có thể tính power huge.
- **Evidence:** Grep `eval(s` found 1. Manual test: `py -3.12 -c "eval('2**30', {'__builtins__':{}},{})"` → 1073741824 . Với chunk_size parsing, user có thể pass `--chunk-size "2**30"` → 1GB chunk → OOM. Verifier không test CLI fuzz.
- **Impact:** Low exploitability (CLI local), nhưng là anti-pattern. Best practice: không dùng `eval`, dùng `ast.literal_eval` hoặc chỉ parse `M/K/G` suffix đã đủ.
- **Fix:** Xóa eval fallback, chỉ giữ `M/K/G` + int. P2.

### Risk #5 — **MEDIUM** — `src/revhash/__init__.py:122-147` & `stream.py:410-453` double auto-store fallback không nhất quán + đọc file 2 lần

- **Location:** `__init__.py:122-147` compress() does:
  1. `compress_stream` → blob
  2. `if len(blob) > len(data)+overhead` → recompress store via second `compress_stream`
  3. `compress_raw_with_flag` check again → nếu `was_stored` lại recompress store lần 3
  - `stream.py:410-451` compress_stream cũng tự fallback store nếu `compressed_size > store_est` và reader/writer seekable (truncate & rewrite store)
  - `stream.py:963-1022` `compress_file` lại fallback lần thứ 3 dựa trên `stat` sau khi đã đóng file.

- **Evidence:** Đọc code 3 nơi đều fallback store với điều kiện hơi khác: `__init__.py:122` dùng `overhead= HEADER_SIZE + dict_len + footer`, `stream.py:411` dùng `store_size_est=23+total_raw+ len(crcs)*4+32+4`, `compress_file:1011` dùng `store_est=23+src_size+footer_store`. Kết quả: `py -3.12` random 10KB với zstd fallback thành `store` (info `codec store`) đúng, nhưng logic lặp không deterministic cho edge size. Verifier `test_codec.py` random incompressible auto-store PASS nhưng không check rằng fallback không làm sai `info['codec']` vs header codec. `compress(b'hello'*1000)` với zstd không inflated nên không trigger fallback, không cover path lồng nhau.
- **Impact:** Không corrupt data (vẫn byte-identical) nhưng overhead code, khó maintain, double I/O cho file lớn (đọc file 2 lần nếu fallback) → chậm. Tiềm năng race nếu file bị modify giữa 2 lần đọc (peek `remaining_peek` vs `total_raw` mismatch đã patch nhưng phức tạp).
- **Fix:** Tập trung fallback duy nhất trong `codec.compress_raw_with_flag` hoặc trong `stream.py`, bỏ fallback trong `__init__.py` và `compress_file` (chỉ giữ 1). Document rõ khi nào fallback. P1.

### Risk #6 — **MEDIUM** — `get_info` cho UNKNOWN header decompress toàn bộ blob (<20MB) → O(1) violation + DoS, và `header.original_size` patching có race

- **Location:** `src/revhash/__init__.py:219-238`
  ```python
  if header.original_size == UNKNOWN_SIZE:
      if total < 20*1024*1024:
          dec = decompress(blob_b)  # ← full decompress for info!
  ```
  Và `stream.py:346-376` patch header `writer.seek(start_pos+15); writer.write(pack<Q>)` sau khi đã ghi compressed stream.

- **Evidence:** `get_info` spec nói *“without full decompression”* (`__init__.py:199` docstring) nhưng implementation lại decompress nếu <20MB để lấy `original_size`/`chunks`. Với blob 10MB UNKNOWN (pipe case), `get_info` sẽ decompress 10MB → tốn 10MB RAM, vi phạm O(1) cho info. Verifier `test_stream.py:194` `header.original_size == UNKNOWN` cho NonSeekableWriter store 1M chỉ check `blob[-36:-4]` SHA, không check `get_info` path. `stream.py:367` patch logic assumes `writer_seekable` true thì header sẽ được fix sau khi biết `total_raw`; nhưng nếu file bị truncate giữa chừng, patch có thể ghi sai offset (15 là constant nhưng nếu dict_len >0 thì offset 15 vẫn đúng vì original_size ở 15, dict sau 23). Race: nếu `remaining_peek` đo được 1M nhưng actual read 1M+1 do file grow, patch sẽ sửa header nhưng `crcs` đã tính cho actual, mismatch? Code có patch lại lần 2 ở `367-376` nhưng phức tạp.
- **Impact:** Info path không O(1), CLI `info` (`cli.py:112` `blob = p.read_bytes(); info = get_info(blob)`) load toàn bộ blob rồi có thể decompress nữa → double decompress cho UNKNOWN. For large file 500MB UNKNOWN, `get_info` sẽ không decompress (vì >20M) nhưng trả `UNKNOWN` và `chunks=0`, gây misleading.
- **Fix:** `get_info` không nên decompress; trả `original_size=UNKNOWN` và `chunks=0` luôn cho UNKNOWN, document. Hoặc nếu cần info chính xác, thêm `decompress_stream` with NullWriter và đếm. P2.

### Risk #7 — **MEDIUM** — `dict_len` / `chunk_size` không giới hạn → OOM injection, và `dict_builder.train` cho phép dict 112KB+ nhưng header cho phép 4GB

- **Location:** `src/revhash/header.py:160-175` không validate `chunk_size` max, `dict_len` max; `_parse_header_from_reader` `stream.py:134-137` `dict_data = reader.read(dict_len)` với `dict_len` từ header (attacker controlled). `dict_builder.py:30-33` `DEFAULT_DICT_SIZE=112*1024` nhưng `train()` cho phép bất kỳ `dict_size` >0.
- **Evidence:** Grep không thấy `if dict_len > 1*1024*1024: raise`. Thử `RevHashHeader(chunk_size=0)` đã raise `CorruptedError`, nhưng `chunk_size=2**31` (2GB) vẫn pack được `uint32` và `read(2GB)` sẽ thử allocate 2GB. Header spec không nêu max, nhưng thực tế zstd window max 128MB, chunk >8M là waste. `test_header.py:130-138` test dict_len 112KB nhưng không test large dict_len rejection. Verifier `test_dict.py` chỉ test 327B-4KB dict.
- **Impact:** For untrusted blob (download từ network), attacker gửi blob với `dict_len=1_000_000_000` → `reader.read(1e9)` OOM DoS. Tương tự `chunk_size=0` đã chặn nhưng `chunk_size=1` cũng absurd nhưng cho phép (1 byte chunk → Nc huge, footer `Nc*4` có thể 4GB cho 1GB file với chunk 1). Thiếu validation giới hạn hợp lý (chunk 4KB-64MB, dict 0-256KB).
- **Fix:** Thêm `if chunk_size < 1024 or chunk_size > 64*1024*1024: raise CorruptedError`, `if dict_len > 256*1024: raise` (hoặc `1<<20`). Trong `_parse_header_from_reader`, check `dict_len > 1_000_000` early. P1.

---

## 3. Anti-cheat check

| Check | Lệnh / Evidence | Kết quả |
|-------|-----------------|---------|
| **Hardcode ratio** | `grep -r "ratio.*=" src/` → chỉ `__init__.py:228 ratio=0.0` và `selector.py:190 return len(blob)/len(sample)` tính thực. `results.json` không hardcode mà sinh từ `bench_runner.py`. `benchmarks/run_benchmark.py:139 ratio = comp/orig` tính runtime. `grep "0.00015" src/` → không có | **PASS** — không hardcode ratio |
| **Mock decode (bypass verify)** | `grep "return data" src/revhash/codec.py` → chỉ `store` raw copy; các codec khác gọi `zstd.ZstdDecompressor.stream_reader`, `gzip.decompress`, `lzma.decompress`, `brotli.decompress` thực. `__init__.py:187-196` `verify()` gọi `decompress()` thực, không `return True` shortcut | **PASS** — decode thực, không mock |
| **Fake SHA** | `grep "hashlib.sha256" src/` → `header.py:332 global_sha256`, `stream.py:227 sha=hashlib.sha256()`, `stream.py:281 sha.update`, `stream.py:775 computed_sha != global_sha_expected`. Không có constant SHA. Test `global_sha256(b"") == e3b0c442...` đúng | **PASS** — SHA thực |
| **Bypass verify flag** | `grep "hardcode|bypass" src/` → 0. `verify()` catch `RevHashCorruptedError` return False, không bỏ qua lỗi. Fuzz 100 random tamper 100/100 detected `reports/verification.md §5` | **PASS** |
| **O(1) thực O(1) hay `read()` toàn bộ?** | `grep "read(" src/revhash/stream.py` → 23 hits, tất cả `read(chunk_size)` hoặc `read(65536)` trừ **1 violation** `stream.py:610 remaining = reader.read()` cho non-seekable decompress (Critical Risk #2). `CountingReader` test `test_stream.py:125` PASS cho seekable, nhưng non-seekable FAIL O(1) | **WARN** — seekable O(1) đúng, non-seekable phá vỡ |
| **Streaming single-frame vs per-chunk compress** | `grep "stream_writer" src/` → 3 hits, `stream.py:255 cctx.stream_writer(writer, closefd=False) as comp: comp.write(chunk)` loop là single-frame đúng spec `research.md §6.2`. Không có per-chunk `compress()` trong zstd branch. `benchmarks/bench_runner.py` chunked independent từng là test riêng, không dùng trong lib | **PASS** — đúng single-frame, ratio 0% overhead verify `test_large.py:309 overhead <0.02` |
| **Header/footer tamper** | Verifier note `chunk_size malleability` + Critic reproduce `chunk 1M→4M same Nc verify True` (§2 Risk #1) và `footer magic flip → CorruptedError` PASS, nhưng header fields khác không MAC | **PARTIAL** — footer+SHA/CRC tốt, header chưa |
| **Dict handling validate** | `header.py:192-208` check `dict_len` vs `len(data)-next_off` truncated → raise. `codec.py:221-225` raise `DictError` nếu non-zstd có dict. `stream.py:193` validate dict only zstd. `dict_builder.py:52-69` validate `samples>=10` else ValueError, `load` check empty. PASS nhưng chưa giới hạn max dict_len (Risk #7) | **PASS với lưu ý** |

**Kết luận anti-cheat:** Không phát hiện hardcode/mock/fake. Implementation诚实 (honest). Hai vấn đề là O(1) non-seekable violation và header malleability, không phải cheat mà là thiếu sót thiết kế.

---

## 4. Security & Correctness

### 4.1 Header tampering
- **Magic/version/codec_id:** Được validate (`header.py:194-203` raise `CorruptedError`/`UnsupportedCodecError`). `test_header.py:138-183` cover. PASS.
- **chunk_size/level/original_size:** **Không** được MAC (Risk #1). `original_size` có cross-check `total_out != header.original_size → CorruptedError` (`stream.py:927`), nên `original_size` tamper sẽ bị phát hiện sau khi decompress (phải decompress xong mới biết). Nhưng `chunk_size` sai chỉ ảnh hưởng CRC boundary; nếu Nc unchanged thì CRC vẫn khớp → bypass.
- **dict_len:** Có check `truncated dict` (`header.py:207 raise truncated`). Nhưng không check max → DoS (Risk #7).
- **Footer magic/SHA/CRC:** Tốt. `stream.py:914-925` check CRC và SHA sau khi decompress incremental. Fuzz 100% tamper detection (`reports/verification.md §5`). PASS.

### 4.2 CRC/SHA bypass
- CRC tính trên `original chunk` trước compress (`stream.py:261 zlib.crc32`), verify sau decompress incremental với `pending` buffer đúng chunk boundary (`stream.py:682-684` và `815-821`). SHA tính `hashlib.sha256` streaming. Thứ tự: CRC trước, SHA sau, đều raise `RevHashCorruptedError`. Không bypass.
- Tuy nhiên **điểm yếu**: với `UNKNOWN_SIZE` header (non-seekable compress), CRC array empty per spec → chỉ còn SHA bảo vệ, mất per-chunk granularity. Nếu attacker tamper 1 chunk trong UNKNOWN blob mà vẫn giữ SHA? Không thể vì SHA sẽ mismatch. Nên vẫn an toàn, chỉ mất granularity.
- No timing side-channel, no lazy verify.

### 4.3 Dict injection
- Header embed `dict_data` sau header (`header.py:176 packed += dict_data`), decompress lấy `effective_dict = header.dict_data` (`stream.py:510`). Nếu attacker thay dict_data trong blob mà không cập nhật `dict_len`/header, sẽ bị `truncated dict` hoặc `decompress_raw` sẽ raise `DictError` do mismatch (`codec.py:270`). Zstd dictionary mismatch sẽ raise `RevHashDictError` wrap (`stream.py:900`).
- Thiếu: không giới hạn dict_len → OOM DoS (Risk #7). Không có `dict_id` versioning, nhưng research đề cập, không critical cho v0.1.
- `dict_builder.train` không sanitize sample content, nhưng train là offline tool, không phải attack surface runtime.

### 4.4 DoS via huge decompress
- **Bombe nén?** Revhash dùng zstd/gzip/lzma nên tỉ lệ nén cao nhất cho repeat 10MB→1.5KB (6667×). Decompress 1.5KB → 10MB không phải bombe lớn. Nhưng attacker có thể craft store blob với `original_size = 10GB` nhưng `compressed_size` nhỏ (store thì `compressed_len ≈ original_size`, không bombe). Zstd decompress stream sẽ allocate incremental `sreader.read(65536)` loop, không pre-allocate `original_size`, nên không OOM do `original_size` header. Check `stream.py:927` sẽ verify `total_out != header.original_size` sau khi decompress, nhưng nếu attacker khai `original_size = 10GB` mà payload chỉ 10 bytes zstd, decompress sẽ ra 10 bytes, rồi raise `CorruptedError` (không OOM). PASS, không bị bombe pre-allocate.
- **Decompress non-seekable OOM:** Risk #2 là DoS vector chính.
- **Compress huge file:** `compress_stream` đọc `remaining_peek` qua `seek/tell` không allocate, rồi loop `read(chunk_size)` O(1) PASS cho seekable. `compress_file` mở `open(..., 'rb')` O(1).
- **CLI `read_bytes()`:** DoS cho file lớn qua `info/verify` (Risk #2 companion).

### 4.5 Path traversal CLI
- `cli.py:66-76` `compress` nhận `args.input/output` là `pathlib.Path(args.input)` không sanitize `..` hay absolute path. Nhưng CLI là local tool, chạy với quyền user, không phải server. Path traversal không phải security issue nếu user tự chạy. Tuy nhiên `compress_file` trong lib nhận `Path` bất kỳ, không check symlink, nhưng đó là intended. Không có `path traversal` qua network.
- Một lưu ý: `cli.py:189` `glob.glob(pat)` cho `train-dict corpus/*.txt` có thể expand ra nhiều file, nhưng không sanitize, okay.
- **Thiếu:** `cli.py:74` `dict_path.read_bytes()` không giới hạn size dict file → nếu dict file là 1GB do user nhầm, sẽ OOM. Nên thêm check `if len(dict_data) > 1<<20: warn`.
- **Kết luận Security:** Không có RCE hay traversal nguy hiểm. Các lỗ hổng chính là integrity (header MAC) và availability (OOM O(1) violation), không phải confidentiality.

### 4.6 Correctness edge
- Empty file 0B → header 23B + zstd empty 9B + footer 36B =68B đúng verifier. `test_large.py:69` parametrize 0 PASS.
- `chunk_size` boundary `4M+123` →2 chunks PASS (`test_stream.py:231`).
- Incompressible random auto-store → `store` codec PASS (`py -3.12` check random 1M → store).
- `level` validation ở `stream.py:251-252` (zstd 1..22) và `codec.py:67-81` đúng, nhưng decompress không re-validate level (Risk #1).
- `UNKNOWN_SIZE` footer 36B only cho non-seekable writer store 1M test PASS (`test_stream.py:186`).

---

## 5. Style & Maintainability

| Tiêu chí | Đánh giá | Evidence |
|----------|----------|----------|
| **Type hints** | 85% đầy đủ, thiếu 1 chỗ | `stream.py:98 def readinto(self, b):` thiếu `-> int` và type cho `b`; `__init__.py:70 compress(data: bytes, codec: str = "zstd", ...)` có; `selector.py` đầy đủ; `dict_builder.py` đầy đủ. Tổng thể tốt, không block. |
| **Error handling** | Tốt, hierarchy rõ | `exceptions.py:9-22` 3 subclass, không dùng bare `except Exception` nhiều ngoài `codec.py:267` wrap dict error có filter `if "dict" in msg`. `stream.py:896-905` wrap chi tiết. Không swallow silent. |
| **O(1) guarantee** | Code comment đúng nhưng implementation 1 violation | `stream.py:13-14` doc *“never read() whole file”* đúng cho seekable, nhưng `610 remaining = reader.read()` vi phạm. Cần update doc hoặc fix code. |
| **Dependencies** | Tối thiểu, hợp lý | `pyproject.toml:24 dependencies = ["zstandard>=0.20.0"]`, `brotli` optional. Không có `numpy`, `cryptography` bloat. `zstandard 0.25.0` pinned? `>=0.20.0` okay. Không có `psutil` mandatory (chỉ verifier). PASS. |
| **Naming / Structure** | Freeze theo `docs/api.md §6` | `src/revhash/{header,codec,stream,exceptions,__init__,cli,dict_builder,algorithms/selector}` đúng layout. `CODEC_MAP`/`ID_TO_CODEC` rõ. `RevHashHeader` dataclass với `to_bytes/from_bytes` đối xứng. Tốt. |
| **Complexity** | Cao ở `stream.py` 1054 dòng | `decompress_stream` dài 600 dòng với 2 branches (seekable vs non-seekable) duplicate decompress dispatch. Khó maintain, risk bug khi thêm codec mới phải sửa 2 chỗ. Nên tách helper `_decompress_with_reader(reader, writer, effective_dict, chunk_size)`. P2 refactor. |
| **Dead code / TODO** | Có | `header.py:273-288` heuristic dead code cho UNKNOWN chưa xóa. `stream.py:344-358` comment *“if seek fails, keep unknown”* okay. `selector.py:398-406` dict heuristic nested `if` hơi rối. `cli.py:58 eval` nên xóa. |
| **Docs** | `docs/research.md` 409 dòng + `docs/api.md` frozen + `README.md` minimal, đủ cho v0.1. Nhưng `README.md` chưa nêu limitation non-seekable O(1) và header malleability. |  |
| **Tests** | 108 tests >90% gate, nhưng coverage file lớn (>500MB) chỉ mock GenReader, không có test real disk 100MB+ | `tests/test_large.py:158` 200MB mock với NullWriter là best-effort, nhưng không test `compress_file` với file 100MB thực trên disk (Verifier có 20MB file test). Nên bổ sung benchmark file 100MB thực cho CI. |

**Tổng:** Code style tốt hơn mức trung bình, type hints + docstring đầy đủ, không có `print` debug, không hardcode magic ngoài `b"RVH1"`. Điểm trừ chính là duplicate decompress logic và 1 O(1) violation + dead heuristic.

---

## 6. Đề xuất fix ưu tiên (P0/P1/P2)

### P0 — Blocker cho release (phải fix trước v0.1.0)
- **P0-1 — Fix non-seekable decompress O(1) violation (`stream.py:610`)**  
  Option A (quick): Document rõ *“decompress_stream với non-seekable reader chỉ hỗ trợ blob < 100MB; với blob lớn hơn phải dùng seekable file”* và thêm guard `if total_estimated > 100*1024*1024 and not reader_seekable: raise RevHashCorruptedError("non-seekable blob too large, use file")`.  
  Option B (proper): Đổi format để ghi `compressed_len` 8B vào header (thêm field) hoặc dùng chunked framing cho non-seekable. Với header hiện tại, có thể implement incremental buffering: đọc `remaining` theo chunks 64KB và stream qua temp file thay vì `read()` một lần. Thêm test `test_decompress_nonseekable_100mb_should_not_oom`.

- **P0-2 — Header integrity (`header.py` + `stream.py`)**  
  Thêm 4B `header_crc32` sau magic hoặc extend `global_sha256` để cover header bytes. Ví dụ:
  ```python
  # compress
  header_bytes = header.to_bytes()
  sha.update(header_bytes)  # SHA cover header + payload
  # decompress
  sha.update(header_bytes_read_from_blob)
  ```
  Hoặc đơn giản: `header_crc = zlib.crc32(header_bytes)` thêm vào footer trước per-chunk CRCs. Update `parse_footer` và verifier. Thêm test `test_header_tamper_chunk_size_same_Nc_should_fail`.

- **P0-3 — CLI `read_bytes()` cho large file (`cli.py:112,123,141`)**  
  Đổi `info`/`verify` sang streaming: `with open(p,'rb') as rf: info = get_info_stream(rf)` hoặc dùng `mmap` + `header.from_bytes` không load toàn bộ. Guard: nếu `p.stat().st_size > 50*1024*1024` thì không `read_bytes()` mà dùng `open` streaming. Thêm vào `get_info` Stream variant.

### P1 — High, nên fix trước v0.1.0 nếu có thời gian (hoặc v0.1.1)
- **P1-1 — Giới hạn `dict_len`/`chunk_size` (`header.py:160`, `stream.py:134`)** Thêm `if dict_len > 256*1024: raise CorruptedError("dict too large")` và `if chunk_size < 4096 or chunk_size > 32*1024*1024: raise`. Tránh OOM injection.
- **P1-2 — Dead heuristic trong `header.py:269-290`** Xóa hoặc sửa cho đúng. Thêm test `test_parse_footer_unknown` để đảm bảo không raise spurious.
- **P1-3 — Tập trung store fallback logic** Gộp 3 nơi (`__init__.py`, `stream.py:410`, `stream.py:963`) thành 1 hàm `should_fallback_store(compressed_size, original_size, chunk_size)` và chỉ gọi trong `stream.py`. Bỏ duplicate trong `__init__.py`.
- **P1-4 — `get_info` UNKNOWN decompress** (`__init__.py:219`) Bỏ branch `if total <20M: decompress(blob)` cho UNKNOWN; trả `original_size=UNKNOWN` và doc rằng cần `decompress` để biết size. Tránh O(1) violation.

### P2 — Medium, backlog v0.2
- **P2-1 — Xóa `eval` trong `cli.py:58`** Thay bằng parse đơn thuần `int(s)`, `float(num)*mult`. Không cần hỗ trợ `4*1024*1024` expression (user có thể dùng `4M`).
- **P2-2 — Refactor `decompress_stream` duplicate** Tách `_stream_decompress(codec, reader, writer, ...)` dùng chung cho seekable/non-seekable, giảm 300 dòng duplicate.
- **P2-3 — Thêm real 100MB file test** Trong `tests/test_large.py` thêm `test_compress_file_100mb_real` (skip nếu CI disk slow) để chứng minh O(1) trên disk thực, không chỉ GenReader.
- **P2-4 — Document header malleability known limitation** Nếu không fix P0-2 trước v0.1.0, phải ghi rõ trong `README.md` và `reports/verification.md` rằng header `chunk_size`/`level` không authenticated và `verify` chỉ cover payload.
- **P2-5 — Type hints cho `readinto`** Thêm annotation `def readinto(self, b: bytearray) -> int:` và cho `dict_builder.save/load` PathLike overload.

---

## 7. Kết luận: có đủ điều kiện release v0.1.0 không?

**Verdict: `WARN` — Chưa đủ điều kiện `PASS` toàn bộ, nhưng có thể release `v0.1.0-rc` với blockers P0 được document hoặc fix.**

- **Nếu giữ nguyên code hiện tại:** **FAIL** cho production unlimited qua pipe/socket do Risk #2 (non-seekable OOM) và Risk #1 (header malleability) vi phạm contract `TEAM_PLAN.md: Streaming O(1) memory` và `tính robust với header checksum`. Không nên tag `v0.1.0` stable mà nên `v0.1.0-rc1` với known limitations ghi trong `README.md`.
- **Blockers phải fix để thành PASS:**
  1. **P0-1 non-seekable O(1)** — hoặc fix incremental hoặc thêm guard + document giới hạn <100MB cho pipe.
  2. **P0-2 header MAC** — hoặc thêm header CRC vào SHA, hoặc document rằng `chunk_size`/`level` tamper với cùng Nc không phát hiện và `get_info` có thể sai.
  3. **P0-3 CLI `read_bytes()`** — đổi sang streaming cho `info`/`verify` hoặc guard large file.

- **Nếu fix 3 P0 trên (ước ~1-2 ngày):** thì đạt **PASS** — các tiêu chí còn lại đều vượt: ratio 32×, SHA 100%, streaming seekable O(1) đã chứng minh 20-50MB peak <51MB, 108/108 tests, throughput >800 MB/s, không hardcode.

**So với Verifier report `PASS with Minor Risks`:** Verifier đánh PASS vì O(1) seekable + fuzz + ratio đều đạt, và liệt kê 5 minor risks nhưng không đánh CRITICAL cho non-seekable `read()` và header MAC. Critic **không đồng ý optimism**: non-seekable `read()` là **CRITICAL** cho “unlimited” claim (file lớn hơn RAM qua pipe là core use-case), header malleability là **HIGH** cho security audit. Cần nâng từ `Minor` thành `P0 Blocker` hoặc document rõ limitation.

**Handoff cho Coordinator:**
- Chọn 1 trong 2:
  - **A (nhanh):** Giữ code, update `README.md` + `docs/api.md` §3.1 thêm *“Non-seekable streaming chỉ hỗ trợ blob <100MB; header chunk_size/level không được verify, dùng verify chỉ đảm bảo payload SHA/CRC”*, tag `v0.1.0-rc`.
  - **B (proper):** Fix P0-1/2/3 rồi mới tag `v0.1.0` stable. Khuyến nghị B nếu muốn đúng “unlimited O(1) for pipe/socket” như TEAM_PLAN.

---

### Phụ lục — Lệnh reproduce chính

```bash
# O(1) check
py -3.12 -c "import sys; sys.path.insert(0,'src'); import io, revhash; class C(io.BytesIO):
 def read(self,s=-1):
  assert s!=-1 and s<=1*1024*1024
  return super().read(s)
r=C(b'x'*5*1024*1024); w=io.BytesIO(); revhash.compress_stream(r,w,codec='zstd',chunk_size=1*1024*1024); print('O1 ok')"

# Header tamper same Nc still True (bug)
py -3.12 -c "import sys; sys.path.insert(0,'src'); import revhash, struct; b=revhash.compress(b'hello'*1000,codec='zstd',chunk_size=1024*1024); ba=bytearray(b); struct.pack_into('<I',ba,7,4*1024*1024); print(revhash.verify(bytes(ba)))"
# → True (expected False after fix)

# Non-seekable read() violation
grep -n "remaining = reader.read()" src/revhash/stream.py
# → 610

# Ratio anti-cheat
grep -rn "0.00015\|hardcode\|mock.*decode" src/
# → no hardcode
```

### Phụ lục B — So sánh Verifier vs Critic (điểm khác)

| Phát hiện | Verifier (`reports/verification.md`) | Critic (report này) | Lý do khác |
|-----------|--------------------------------------|---------------------|------------|
| Header malleability | Ghi nhận là “Minor — chunk_size tamper not detected when Nc unchanged, header not MAC'd” (§11.1) → vẫn PASS | Nâng thành **HIGH P0** — verify True cho payload 5KB tamper 1M→4M là bypass, không phải minor | Verifier chỉ test 1 case 10KB với `verify` bypass nhưng không reproduce systematic; Critic reproduce 2 cases (5KB True, 4M+100 False) → chứng minh header MAC thiếu là lỗ hổng integrity |
| Non-seekable O(1) | Ghi “Non-seekable decompress buffer: reads entire remaining blob → OOM, but rare, documented low” (§11.5) → PASS | **CRITICAL P0** — vi phạm contract “never read() whole file” `stream.py:14`, fail “unlimited pipe/socket” core goal | Verifier đánh low vì “rare”; Critic đánh CRITICAL vì `TEAM_PLAN.md: streaming pipe/socket` là explicit success criteria, 10GB pipe sẽ OOM |
| CLI `read_bytes()` | Không đề cập | **HIGH P0** — `cli.py:112/141` load toàn bộ blob cho `info/verify` → OOM cho file >RAM | Verifier chỉ test 128KB CLI, không test 100MB+ file |
| `parse_footer` UNKNOWN dead code | Không phát hiện | **MEDIUM P1** — heuristic sai logic `header.py:274 raise` spurious cho `compressed_len%4!=0` | Cần đọc code path `parse_footer`, verifier không cover UNKNOWN + parse_footer |
| `eval` trong CLI | Không đề cập | **P2** — `cli.py:58` eval arithmetic bomb | Security audit |
| Overall verdict | **PASS with Minor Risks** (108/108) | **WARN (FAIL nếu đòi stable)** với 3 P0 blockers | Verifier optimism: 108 tests pass nên PASS; Critic adversarial: contract O(1) pipe + header MAC là must, không thể PASS nếu chưa fix/document |

### Phụ lục C — Checklist cho Coordinator M6

- [ ] Quyết định A (rc) hay B (fix 3 P0) trước khi tag `v0.1.0`
- [ ] Nếu chọn B, tạo issues cho P0-1/2/3 và assign Core Builder (stream.py/header.py/cli.py)
- [ ] Update `README.md` với Limitations section (header MAC, non-seekable <100MB)
- [ ] Thêm `tests/test_critic_repro.py` với 2 repro header tamper + non-seekable OOM guard để prevent regression
- [ ] Re-run `benchmarks/run_benchmark.py` sau fix P0 để đảm bảo ratio không regress
- [ ] Tag `v0.1.0-rc1` nếu chưa fix, `v0.1.0` nếu đã fix P0

*— Critic / Auditor — Team revhash — 2026-08-26*  
*Evidence-based, adversarial, không optimism. File:line trích dẫn đã verify bằng `py -3.12` execution, không đoán.*

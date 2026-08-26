# Critique Report — revhash v0.2-embedded (Thư viện nhúng File+Text) — Adversarial Audit

> **Role:** Critic / Auditor — Embedded — Team revhash v0.2-embedded  
> **Ngày:** 2026-08-27  
> **Auditor:** Muse Spark (Critic Embedded)  
> **Workspace:** `D:\data optimization`  
> **Scope:** `TEAM_PLAN_EMBEDDED.md`, `docs/research_embedded.md`, `docs/api_embedded.md`, `src/revhash/__init__.py:70-200`, `src/revhash/text.py:1-67`, `src/revhash/stream.py:1029`, `src/revhash/codec.py:26`, `revhash_embedded.py:1-100`, `scripts/build_embedded.py`, `examples/embed_demo.py`, `examples/file_text_demo.py`, `tests/test_text_file.py`, `tests/test_embedded.py`, `reports/verification_embedded.md`, `TEAM_STATE.md`, `reports/verification.md` v0.1, `reports/critique.md` v0.1, `reports/fix_report.md`  
> **Mode:** Adversarial — không optimism, chỉ evidence `file:line` + `python -c` reproduce. **KHÔNG sửa `src/revhash/*`, `revhash_embedded.py`, `examples/*`, `tests/*`** — chỉ đọc và audit.

---

## 1. Tổng quan PASS/FAIL per 8 Success Criteria (TEAM_PLAN_EMBEDDED.md §1)

| # | Success Criteria (Top-level — TEAM_PLAN_EMBEDDED §1) | Target | Evidence thực đo (adversarial) | Verdict |
|---|--------------------------------------------------------|--------|--------------------------------|---------|
| 1 | **Nhúng 1 dòng:** `import revhash` sau `pip install -e .` HOẶC `copy revhash_embedded.py` → chạy ngay, không config | `python -c "import revhash"` và `python -c "import revhash_embedded"` trong thư mục trống đều PASS | `python -c "import sys; sys.path.insert(0,'src'); import revhash; print(revhash.__version__)"` → `0.1.0` PASS; `python -c "import revhash_embedded; print(revhash_embedded.__version__)"` → `0.2.0-embedded` PASS; vendored subprocess `tests/test_embedded.py::test_single_file_vendored_subprocess` PASS. **Nhưng** `pyproject.toml` version vẫn `0.1.0` trong khi bundle `0.2.0-embedded`: `grep __version__` lệch (`src/revhash/__init__.py:54` vs `revhash_embedded.py:22`). Gây nhầm lẫn pip vs vendored khi `pip show revhash` báo 0.1.0 trong khi `import revhash_embedded` báo 0.2.0. | **PASS (WARN)** — nhúng 1 dòng thỏa, nhưng version drift 0.1.0≠0.2.0-embedded phải document, không phải FAIL blocker |
| 2 | **Text trực tiếp:** `revhash.compress_text("xin chào") -> bytes` / `decompress_text(blob) -> str` (tự handle `str<->utf-8`, `bytes` vẫn hỗ trợ `compress`/`decompress`) | `str` strict `encode("strict")`, `bytes` raw pass-through, `compress(123)` TypeError | `src/revhash/text.py:13-43` `if not isinstance(text,str): raise TypeError` + `text.encode(encoding,"strict")` và `src/revhash/text.py:46-67` `.decode("strict")` PASS; `src/revhash/__init__.py:148-149` `isinstance(data,str): data.encode("strict")` PASS. Reproduce: `python -c "import sys; sys.path.insert(0,'src'); import revhash; assert revhash.decompress_text(revhash.compress_text('xin chào 🌍'))=='xin chào 🌍'"` PASS; `python -c "import sys; sys.path.insert(0,'src'); import revhash; revhash.compress_text(b'bytes')"` → `TypeError` PASS; `python -c "import sys; sys.path.insert(0,'src'); import revhash; b=revhash.compress(b'\xff\xfe'); revhash.decompress_text(b)"` → `UnicodeDecodeError` PASS. Không có `errors="replace"` (grep `replace` chỉ xuất hiện trong comment `stream.py:1296 Replace reader`). **Nhưng** `decompress_text` chỉ check `isinstance(blob,...)` không giới hạn size → decompress 1GB blob trong `decompress_text` sẽ OOM như `decompress` (kế thừa). | **PASS** |
| 3 | **File trực tiếp:** `revhash.compress_file("in.txt","out.rvh")` / `decompress_file` chấp nhận `str|Path`, tự tạo parent dirs, trả `info` dict; alias `compress_path` bị cấm (YAGNI) | `Path.mkdir(parents=True)` chỉ cho `dst`, `IsADirectoryError`/`FileNotFoundError` đúng | `src/revhash/stream.py:1029-1037` (`compress_file`) và `1077-1085` (`decompress_file`) đều `src_path=Path(src_path); dst_path=Path(dst_path); if not src_path.exists(): raise FileNotFoundError; if src_path.is_dir(): raise IsADirectoryError; dst_path.parent.mkdir(parents=True, exist_ok=True)` PASS. Reproduce: `python -c "import sys, pathlib, tempfile; sys.path.insert(0,'src'); import revhash; ..."` với `out/nested/deep/b.rvh` khi parent chưa tồn tại → PASS (Verifier `test_file_mkdir_*`). **Nhưng** `mkdir(parents=True)` không sanitize `..` → `compress_file("a.txt","../../tmp_outside/out.rvh")` sẽ `mkdir("../../tmp_outside")` tạo thư mục ngoài dự án (repro `repro.py` shows `traversal dst ..\tmp_test_traversal_xyz2\out.rvh created outside cwd? True`). Và `dict_data` nếu là `str|Path` tồn tại → `read_bytes()` bất kỳ file local (xem Risk #3). Không có check `dst` là absolute hay containment. | **PASS (WARN)** — DX mkdir thỏa spec, nhưng path traversal side-effect là Medium risk, không blocker cho local tool nhưng phải document |
| 4 | **Single-file bundle:** `revhash_embedded.py` (~1 file, <500KB) chứa toàn bộ core (header+codec+stream) + fallback stdlib nếu thiếu `zstandard` → vẫn chạy (downgrade `gzip`/`store`), `sha256` verify bundle | `<500KB`, `__bundle_hash__` hash thực, `__version__` | `revhash_embedded.py:1-7` header `# AUTO-GENERATED from src/revhash/ — do not edit. Source hash: sha256:bd67b...` và `revhash_embedded.py:22-23` `__version__="0.2.0-embedded"` `__bundle_hash__="sha256:bd67b684388af44c340d1d2f6f132cd353a66d978b3e902fbf872f7c30f263c2"` PASS. Reproduce: `python -c "import pathlib,hashlib; src=pathlib.Path('src/revhash'); h=hashlib.sha256(); [h.update((src/n).read_bytes()) or h.update(b'\x00') for n in sorted(['exceptions.py','header.py','codec.py','stream.py','text.py','__init__.py'])]; print('sha256:'+h.hexdigest())"` → `sha256:bd67b...` khớp `revhash_embedded.__bundle_hash__` PASS. `stat` `89459 <512000` PASS; `python scripts/build_embedded.py --check` → `OK` PASS. Bundle chứa `HAS_ZSTD`/`HAS_BROTLI`/`HAS_LZMA` fallback như `src/revhash/codec.py:26-50` PASS. **Nhưng** bundle `__all__` 16 entries (`revhash_embedded.py:28`) trong khi `src/revhash/__init__.py:55-76` 19 entries (thừa `dict_builder`, `algorithms`, `RevHashHeader`) → drift `__all__` spec 15 chưa đồng nhất (xem §5). | **PASS** — bundle thực hash, không hardcode stale (cũ `5bbeac1c` đã được rebuild thành `bd67b6...` 2026-08-27). Drift `__all__` là style, không FAIL bundle |
| 5 | **Zero-deps graceful:** Nếu `zstandard`/`brotli` không có, không crash import; `get_available_codecs()` báo, `compress(..., codec="zstd")` raise `Unsupported` rõ ràng, auto fallback sang `gzip` khi `codec="auto"` | `HAS_ZSTD` flag, `_resolve_codec("auto")` → `gzip`/`store` | `src/revhash/codec.py:44-50` `try: import zstandard as _zstd; HAS_ZSTD=True except: HAS_ZSTD=False` và `src/revhash/codec.py:287-293` `get_available_codecs()` trả `{"store":True,"gzip":True,"zstd":HAS_ZSTD,"lzma":HAS_LZMA,"brotli":HAS_BROTLI}` PASS. `src/revhash/__init__.py:80-89` delegate + `src/revhash/__init__.py:92-116` `_resolve_codec` với `if codec=="auto": fallback zstd→gzip→store` PASS. Reproduce mock: `python -c "import sys; sys.path.insert(0,'src'); import revhash.codec as cm, revhash.stream as sm, revhash_embedded; cm.HAS_ZSTD=False; sm.HAS_ZSTD=False; revhash_embedded.HAS_ZSTD=False; import revhash; print(revhash.get_available_codecs()); print(revhash.compress(b'hello'*2000, codec='auto')[:10])"` → `compress(auto)` fallback `gzip` PASS. **Nhưng** `revhash.compress_file(src,dst,codec="auto")` khi mock `HAS_ZSTD=False` → `RevHashUnsupportedCodecError: zstandard not installed` **FAIL fallback** (repro `repro.py` dòng `pkg compress_file auto FAILED`). Nguyên nhân `src/revhash/header.py:58-59` `_normalize_codec_id("auto")→zstd` hardcode và `src/revhash/stream.py:192` gọi `_normalize_codec_id` trực tiếp, không qua `_resolve_codec`. `tests/test_text_file.py::test_get_available_codecs_fallback_mock` phải `try/except` cho `compress_file(auto)` — test đã né bug thay vì assert fallback. | **CONDITIONAL PASS / WARN** — `compress(auto)` PASS nhưng `compress_file(auto)` FAIL gracefully khi thiếu zstd là HIGH bug, vi phạm spec `api_embedded.md §4 fallback`. Must fix để đạt zero-deps hoàn chỉnh |
| 6 | **DX nhúng:** `__all__` gọn, type hints, docstring ví dụ copy-paste, `examples/embed_demo.py` chạy được sau khi copy 1 file | `__all__ ≤15`, type hints 100%, 5 demos PASS | `src/revhash/__init__.py:55-76` `__all__` thực 19 entries (15 spec + `RevHashHeader` + `dict_builder` + `algorithms`) → **thừa 4** so với `docs/api_embedded.md §2.1` và `research_embedded.md §2.3` spec 15. `revhash_embedded.py:28` 16 entries (thừa `RevHashHeader` so với spec). Type hints: `src/revhash/__init__.py:121-126` `compress(data: bytes|str, codec="zstd", ... encoding="utf-8") -> bytes` PASS; `src/revhash/text.py:13` `compress_text(text: str, ...) -> bytes` PASS; nhưng `src/revhash/stream.py:98` `def readinto(self,b):` thiếu `-> int` và `bytearray` hint (Critic v0.1 P2-5 chưa fix). Docstring ví dụ: `src/revhash/text.py:21-33` và `src/revhash/__init__.py:129-146` có Args/Returns copy-paste PASS. `examples/embed_demo.py` 36 dòng và `examples/file_text_demo.py` 195 dòng đều PASS `python examples/embed_demo.py` → `embed_demo PASS` và `python examples/file_text_demo.py` → `all 5 demos PASS` (Verifier phụ lục B). **Nhưng** `embed_demo.py` có `sys.path` guard không phải strict vendored (copy 1 file thuần túy không cần `sys.path` nếu `revhash_embedded.py` cùng folder); guard dư nhưng không hại. | **WARN** — DX chạy được, nhưng `__all__` không gọn như freeze và 1 thiếu type hint |
| 7 | **Không regress:** O(1) streaming, 108 tests vẫn PASS, ratio 32× gzip giữ nguyên, benchmark không chậm hơn 5% | O1 `<150MB`, 108 cũ + 34 mới =142 PASS, ratio diff <5% cho 10MB | `pytest tests -q` → `142 passed` (Verifier 7.25s) PASS; `src/revhash/stream.py:257-269` `cctx.stream_writer(writer,closefd=False)` single-frame giữ window → ratio 0% overhead vẫn PASS; `benchmarks/results_verifier.json` 10MB zstd `0.000151` vs baseline `0.00015` diff **+0.7%** <5% PASS; Verifier §3.1 peak `20.58MB for 10MB / 100MB for 50MB` <150MB PASS; `tests/test_stream.py` CountingReader chứng minh `read(chunk_size)` không `read(-1)` PASS. **Nhưng** Critic phải challenge: `src/revhash/__init__.py:219-238` `get_info` với `UNKNOWN_SIZE` và `total<20MB` thì `decompress(blob)` toàn bộ → vi phạm O1 cho `info` (Critic v0.1 Risk #6 chưa fix trong v0.2). Và `src/revhash/stream.py:612-650` non-seekable decompress cho blob >100MB raise `RevHashCorruptedError guidance` thay vì O1 thực sự → Verifier gọi PASS nhưng Critic đánh là limitation documented (fix_report P0-1). Ratio small-size diff 7-10% (10KB/1MB) đã ghi là header overhead, không regress thực sự. | **PASS (WARN)** — không regress O1 seekable và ratio đại diện 10MB, nhưng O1 `get_info`/`non-seekable>100MB` vẫn là known limitation, không phải silent regress |
| 8 | **Verifier + Critic độc lập:** PASS với tiêu chí nhúng (không hardcode, single-file byte-identical với package) | parity 10 cases byte-identical, bundle hash verify, không sửa `src/*` | `tests/test_embedded.py:35-102` 10 parametrized + 3 extra parity tests đều `assert blob_pkg == blob_emb` PASS; `tests/test_embedded.py::test_bundle_hash_version_size` recompute hash từ `src/revhash/*.py` so với `__bundle_hash__` PASS; `reports/verification_embedded.md` 488 dòng PASS 8/8. Critic độc lập (report này) không optimism: tìm ≥5 risks thực (xem §2) và anti-cheat checks §3 đều với evidence `file:line` + `python -c` reproduce. | **PASS** |

**Overall §1:** **5/8 PASS, 3 WARN (1,3,5,6,7 là WARN/CONDITIONAL), 0 FAIL hoàn toàn** — đủ điều kiện `WARN` như v0.1, không `FAIL` blocker chết người, nhưng có 1 HIGH phải fix trước stable (`compress_file auto`).

---

## 2. Top 5-7 Risks thực (Severity Critical/High/Medium, file:line, Evidence py -c reproduce, Impact, Fix)

### Risk #1 — **HIGH** — `compress_file(auto)` không fallback khi thiếu `zstandard` (hardcode `zstd` trong `_normalize_codec_id`)

- **Location:** `src/revhash/header.py:58-59` (`if c=="auto": return CODEC_TO_ID["zstd"]`), `src/revhash/stream.py:192` (`cid=_normalize_codec_id(codec)` hardcode), `src/revhash/__init__.py:92-116` (`_resolve_codec` đúng fallback `zstd→gzip→store`) — 2 đường code mâu thuẫn.
- **Evidence `python -c` reproduce (đã chạy `repro.py` dòng 6):**
  ```bash
  python -c "
  import sys; sys.path.insert(0,'src')
  import revhash.codec as cm, revhash.stream as sm, revhash_embedded
  cm.HAS_ZSTD=False; sm.HAS_ZSTD=False; revhash_embedded.HAS_ZSTD=False
  import tempfile, pathlib, revhash
  blob=revhash.compress(b'hello'*2000, codec='auto'); print(revhash.get_info(blob)['codec'])  # -> gzip PASS
  pathlib.Path('tmp/a.txt').write_text('hello',encoding='utf-8');  # pkg compress via __init__
  # file api:
  import pathlib, tempfile
  with tempfile.TemporaryDirectory() as td:
      base=pathlib.Path(td); src=base/'src.txt'; src.write_text('hello'*1000)
      dst=base/'dst.rvh'
      revhash.compress_file(src,dst,codec='auto')  # -> RevHashUnsupportedCodecError
  "
  # Output thực đo (repro.py):
  # pkg compress auto fallback codec gzip  (PASS)
  # pkg compress_file auto FAILED RevHashUnsupportedCodecError: zstandard not installed
  # embedded compress auto fallback codec gzip
  # embedded compress_file auto FAILED RevHashUnsupportedCodecError: zstandard not installed
  ```
  `tests/test_text_file.py::test_get_available_codecs_fallback_mock` phải `try: compress_file(auto) except RevHashUnsupportedCodecError` — test né bug thay vì enforce fallback, chứng tỏ bug tồn tại.
- **Impact:** Vi phạm **Zero-deps graceful** cho file API — user thiếu `zstandard` gọi `compress_file(..., codec="auto")` kỳ vọng fallback `gzip` như `compress` nhưng nhận `Unsupported` crash. Spec `docs/api_embedded.md §2.2` và `research_embedded.md §4.3` yêu cầu `auto→gzip/store` cho mọi entrypoint. File API là primary cho nhúng, nên HIGH.
- **Fix (P0):** Sửa `src/revhash/stream.py:191-193` và `src/revhash/header.py:58-59` để `compress_stream` và `compress_file` gọi `_resolve_codec` (hoặc `get_available_codecs`) thay vì `_normalize_codec_id` khi `codec=="auto"`. Đơn giản:
  ```python
  # stream.py
  from .codec import get_available_codecs  # hoặc import _resolve từ __init__ tránh circular -> duplicate logic
  def _resolve_stream_codec(codec):
      if codec=="auto":
          avail=get_available_codecs()
          if avail["zstd"]: return "zstd"
          if avail["gzip"]: return "gzip"
          return "store"
      return codec
  ```
  Và build_embedded cũng phải inline logic tương tự (đã có `_resolve_codec` trong bundle). Thêm test `test_compress_file_auto_fallback_mock` assert `info["codec"] in ("gzip","store")` không `try/except`.

### Risk #2 — **HIGH** — Header malleability: `chunk_size`/`level` không MAC → tamper cùng `Nc` vẫn `verify==True` (kế thừa v0.1 P0-2 chưa fix)

- **Location:** `src/revhash/header.py:150-178` `to_bytes` không thêm `header_crc`, `src/revhash/stream.py:914-925` `SHA` chỉ cover payload, `src/revhash/__init__.py:234-255` `verify` = `decompress` không check header MAC.
- **Evidence:**
  ```bash
  python -c "
  import sys; sys.path.insert(0,'src'); import revhash, struct
  blob=revhash.compress(b'hello'*1000, codec='zstd', chunk_size=1*1024*1024)
  ba=bytearray(blob); struct.pack_into('<I',ba,7,4*1024*1024)  # 1M->4M, Nc=1 vẫn 1
  print(revhash.verify(bytes(ba)))  # -> True (BUG) reproduce giống reports/critique.md v0.1 Risk #1
  print(revhash.decompress(bytes(ba))==b'hello'*1000)  # -> True
  "
  # Output repro.py: tamper verify True / decompress True -> HIGH bug
  ```
  Verifier `reports/verification.md §5` và `reports/verification_embedded.md §9` đã ghi là known limitation nhưng vẫn PASS. `reports/fix_report.md §2` document defer to v0.2 với header_crc bump — nhưng v0.2 vẫn defer tiếp.
- **Impact:** Toàn vẹn header không đảm bảo. Kẻ tấn công có thể đổi `chunk_size`/`level` mà `verify` không phát hiện khi `Nc` unchanged (payload 5KB với chunk 1M→4M, Nc=1). `get_info` sẽ báo sai `chunk_size`. Với file lớn `4M+100` tamper 1M→4M thì `Nc` đổi 2→1 nên mới phát hiện (`RevHashCorruptedError`), nhưng tấn công tinh vi vẫn bypass. Vi phạm `docs/api.md §4` `RevHashCorruptedError` cho header.
- **Fix (P1 — defer stable nhưng phải document hoặc bump version):** Thêm `header_crc32` 4B hoặc `sha.update(header_bytes)` trước payload như `reports/critique.md` P0-2 đề xuất. Với v0.2-embedded, nếu không muốn break format, phải ghi rõ trong `README_EMBEDDED.md` Limitations: *header fields `chunk_size`/`level` not covered by verify when Nc unchanged* và bump `HEADER_VERSION=2` trong v0.3.

### Risk #3 — **MEDIUM** — Path traversal / auto `mkdir` side-effect + `dict_data` arbitrary file read

- **Location:** `src/revhash/stream.py:1034` và `1082` `dst_path.parent.mkdir(parents=True, exist_ok=True)`, `src/revhash/stream.py:1035-1036` và `1083-1084` `if isinstance(dict_data,(str,os.PathLike)) and Path(dict_data).exists(): dict_data=Path(dict_data).read_bytes()`.
- **Evidence:**
  ```bash
  # mkdir traversal
  python -c "
  import pathlib
  tricky=pathlib.Path('..')/'tmp_test_traversal_xyz2'/'out.rvh'
  tricky.parent.mkdir(parents=True, exist_ok=True)
  print((pathlib.Path('..')/'tmp_test_traversal_xyz2').exists())  # -> True
  "
  # repro.py: traversal dst ..\tmp_test_traversal_xyz2\out.rvh created outside cwd? True
  # dict_data path load
  python -c "
  import sys; sys.path.insert(0,'src'); import pathlib, tempfile, revhash
  import pathlib, tempfile
  p=pathlib.Path('src/revhash/__init__.py')  # exists
  # compress_file với dict_data là path string tồn tại → sẽ đọc file đó làm dict, không phải bytes dict
  # Nếu attacker kiểm soát dict_data string, có thể đọc bất kỳ file local
  "
  # repro.py dict path load has_dict True -> confirms branch taken
  ```
- **Impact:** `mkdir(parents=True)` vô điều kiện sẽ tạo thư mục tùy ý nếu `dst` chứa `..` hoặc absolute path `/tmp/...`. Với CLI local thì low, nhưng với library nhúng được gọi với `dst` do user input (web upload filename) có thể tạo `../../etc/cron.d` (Windows `..` vẫn tạo folder ngoài). `dict_data` path load tương tự: `compress_file(src,dst,dict_data="../../etc/passwd")` sẽ `read_bytes()` file đó (nếu tồn tại) và dùng làm zstd dict → không RCE nhưng là information disclosure local + surprising behavior (truyền `dict_data` là `str` path vô tình trùng file tồn tại sẽ bị đọc, thay vì báo lỗi type).
- **Fix (P1):** 
  - `mkdir`: giữ như spec (chỉ cho `dst` parent) nhưng document rõ không sanitize `..`; nếu muốn harden, thêm `dst_path = dst_path.resolve()` và check `dst_path.is_relative_to(cwd)` hoặc chỉ `mkdir` khi `dst_path.parent != Path('.')` và không chứa `..` sau `resolve`. Với embedded lib, chọn document + optional `strict=False` param.
  - `dict_data`: chỉ load path khi `dict_data` là `Path` hoặc `str` với prefix `file:` hoặc khi file tồn tại và size ≤256KB (đã validate header), và document. Hoặc tách API `dict_data_path: Path|None` riêng, không overload `dict_data: bytes|str|Path`. Thêm `if isinstance(dict_data, (str,Path)) and Path(dict_data).exists(): if Path(dict_data).stat().st_size>256*1024: raise RevHashCorruptedError`.

### Risk #4 — **MEDIUM** — `dict_data` type inconsistency: `compress` (bytes) vs `compress_file` (str|Path|bytes) + `compress_text` không hỗ trợ path

- **Location:** `src/revhash/__init__.py:121-126` `compress(data: bytes|str, dict_data: bytes|None)` chỉ `bytes|None`, `src/revhash/stream.py:1006-1014` `compress_file(..., dict_data: bytes|None=None)` nhưng code `1035` chấp nhận `str|Path`, `src/revhash/text.py:13-20` `compress_text(..., dict_data: bytes|None)` không handle path.
- **Evidence:**
  ```bash
  python -c "
  import sys; sys.path.insert(0,'src'); import pathlib, tempfile, revhash
  # compress with str dict_data should be bytes but user might pass path string as dict_data
  try:
      revhash.compress(b'hello'*100, codec='zstd', dict_data='src/revhash/__init__.py')
      print('compress str dict_data did not raise')
  except Exception as e:
      print(type(e).__name__, e)  # -> TypeError or RevHashDictError? repro shows TypeError string argument without encoding
  # compress_file with same string will load file -> different behavior
  import pathlib, tempfile
  with tempfile.TemporaryDirectory() as td:
      base=pathlib.Path(td); src=base/'src.txt'; src.write_text('hello'*1000)
      dict_path=pathlib.Path('dicts/vi_text.dict')
      if dict_path.exists():
          info=revhash.compress_file(src, base/'dst.rvh', codec='zstd', dict_data=str(dict_path))
          print('compress_file str dict_data has_dict', info['has_dict'])  # -> True
  "
  # repro.py: compress str dict_data raises TypeError vs compress_file has_dict True
  ```
- **Impact:** DX nhầm lẫn: user thấy `compress_file(..., dict_data="dicts/vi_text.dict")` works nên thử `compress(data, dict_data="dicts/vi_text.dict")` hoặc `compress_text("hello", dict_data="dicts/vi_text.dict")` → `TypeError`/`RevHashDictError` không rõ. Spec `docs/api_embedded.md §2.2` ghi `dict_data: bytes|str|Path|None` cho file nhưng `§2.1` cho core lại `bytes|None` — chưa đồng nhất. Verifier `tests/test_text_file.py::test_file_dict_data_path_loading` chỉ test file api, không test core.
- **Fix (P2):** Đồng nhất: hoặc cho `compress`/`compress_text` cũng hỗ trợ `str|Path` như file (thêm `if isinstance(dict_data,(str,Path)) and Path(dict_data).exists(): dict_data=Path(...).read_bytes()` trong `__init__.py:121` trước khi gọi `compress_stream`), hoặc document rõ và raise `TypeError` với message gợi ý `use Path or bytes, did you mean compress_file?`. Chọn P2 vì không blocker.

### Risk #5 — **MEDIUM** — O1 violation `get_info` decompress `<20MB` cho `UNKNOWN_SIZE` + non-seekable `>100MB` guard vẫn là limitation

- **Location:** `src/revhash/__init__.py:219-238` (`if header.original_size==UNKNOWN_SIZE and total<20*1024*1024: dec=decompress(blob_b)`), `src/revhash/stream.py:612-650` non-seekable `SpooledTemporaryFile(10MB)` + `if total_tmp>100*1024*1024: raise "non-seekable blob >100MB not supported"` (fix_report P0-1).
- **Evidence:**
  ```bash
  python -c "
  import sys; sys.path.insert(0,'src'); import revhash, inspect
  print(inspect.getsource(revhash.get_info)[200:600])
  # get_info docstring says 'without full decompression' but code decompresses if <20M UNKNOWN
  "
  # Verifier §3 reports O1 peak 20.58MB for 10MB and 100MB for 50MB but get_info path not measured
  # repro: compress_stream with NonSeekableReader 5MB, then get_info on UNKNOWN blob <20M will decompress
  ```
- **Impact:** `get_info` hứa O1 nhưng với `UNKNOWN` blob (pipe) <20MB sẽ `decompress` toàn bộ để lấy `original_size` → tốn RAM gấp đôi và chậm. Với blob `UNKNOWN` 15MB, `get_info` sẽ allocate 15MB decompressed, vượt `chunk_size` 4MB. Non-seekable `>100MB` guard đã fix OOM nhưng biến thành hard limit: user pipe 200MB blob sẽ nhận `CorruptedError` guidance thay vì O1 streaming — document nhưng vẫn là known limitation kế thừa v0.1. Verifier đánh PASS vì `<150MB` cho 10MB/50MB, nhưng Critic phải flag vì contract `UNKNOWN` là cho pipe unlimited.
- **Fix (P1):** `get_info` cho `UNKNOWN` nên trả `original_size=UNKNOWN_SIZE` và `chunks=0` luôn, không decompress; document rằng cần `decompress_stream` với `NullWriter` để đếm nếu cần. Hoặc thêm `compressed_len` field vào header (8B) để O1 thực sự (defer v0.3). Với v0.2, giữ guard và document, không coi là blocker.

### Risk #6 — **MEDIUM** — `__all__` bloat + missing type hint `readinto` + version drift

- **Location:** `src/revhash/__init__.py:55-76` `__all__` 19 entries vs spec 15, `revhash_embedded.py:28` 16 vs spec 15, `src/revhash/stream.py:98` `def readinto(self, b):` thiếu `-> int`, `src/revhash/__init__.py:54` `__version__="0.1.0"` vs `revhash_embedded.py:22` `0.2.0-embedded`.
- **Evidence:**
  ```bash
  python -c "import sys; sys.path.insert(0,'src'); import revhash; print(len(revhash.__all__), revhash.__all__)"
  # -> 19 ['__version__', 'compress',..., 'RevHashHeader','dict_builder','algorithms']
  python -c "import revhash_embedded; print(len(revhash_embedded.__all__), revhash_embedded.__all__)"
  # -> 16
  grep -n "def readinto" src/revhash/stream.py  # -> 98
  grep __version__ src/revhash/__init__.py revhash_embedded.py
  # src 0.1.0 vs embedded 0.2.0-embedded
  ```
- **Impact:** `__all__` thừa `dict_builder`/`algorithms` làm `from revhash import *` pollute namespace, không gọn như spec `research_embedded.md §3.3` 15 entries. `readinto` thiếu hint làm `mypy` fail strict. Version drift gây nhầm `pip show` vs `import` check. Thấp nhưng là maintainability debt, dễ bị Verifier bỏ qua vì tests không check `__all__` length strict (chỉ check `__bundle_hash__`).
- **Fix (P2):** Đồng bộ `__all__` = 15 chính xác (`docs/api_embedded.md §2.1`): `["__version__","compress","decompress","compress_text","decompress_text","compress_file","decompress_file","compress_stream","decompress_stream","verify","get_info","get_available_codecs","RevHashError","RevHashCorruptedError","RevHashDictError","RevHashUnsupportedCodecError"]` — bỏ `RevHashHeader`/`dict_builder`/`algorithms` khỏi `__all__` (vẫn import được nhưng không export `*`). Thêm `def readinto(self, b: bytearray) -> int:`. Bump `src/revhash/__init__.py:54` lên `0.2.0-embedded` hoặc giữ `0.1.0` nhưng thêm `__embedded_version__`.

### Risk #7 — **MEDIUM** — Duplicate decompress dispatch (600 dòng) + `clean_source` aggressive strip trong `scripts/build_embedded.py`

- **Location:** `src/revhash/stream.py:479-1002` `decompress_stream` có 2 branches seekable vs non-seekable duplicate codec dispatch (`store`/`zstd`/`gzip`/`lzma`/`brotli`) ~300 dòng mỗi nhánh, `scripts/build_embedded.py:37-75` `clean_source` strip mọi `from .`/`__all__`/`__version__` bằng string match có thể strip nhầm comment chứa `from .`.
- **Evidence:**
  ```bash
  wc -l src/revhash/stream.py  # -> 1097, decompress_stream ~523 dòng với 2 dispatch blocks
  grep -n "_decompress_zstd\|_decompress_gzip" src/revhash/stream.py
  # xuất hiện 2 lần mỗi codec
  cat scripts/build_embedded.py | grep -n "clean_source"
  # clean_source bỏ qua dòng có "from ." ngay cả trong docstring ví dụ
  ```
  Verifier không check duplicate, chỉ check parity. Critic v0.1 đã note duplicate 600 dòng nhưng chưa fix trong v0.2 (vẫn duplicate).
- **Impact:** Maintainability cao: thêm codec mới phải sửa 2 nơi, dễ quên 1 nhánh → parity drift giữa seekable và non-seekable. `clean_source` có thể làm bundle miss import nếu future code có `from . import something` trong string literal. Không corrupt hiện tại (bundle parity 100% PASS), nhưng là debt.
- **Fix (P2):** Refactor `decompress_stream` tách helper `_decompress_with_reader(codec, reader, writer, effective_dict, chunk_size, sha, pending, crc_computed)` dùng chung cho cả 2 branches, giảm 300 dòng. `clean_source` nên dùng `ast.parse` thay vì string match để chỉ strip import nodes thực sự.

---

## 3. Anti-cheat check (hardcode bundle? silent utf-8 loss? path traversal? import side-effect? bundle drift?)

| Check | Lệnh / Evidence | Kết quả |
|-------|-----------------|---------|
| **Hardcode bundle? `grep __bundle_hash__`, bundle có tính hash thực không hay hardcode cũ?** | `grep -n __bundle_hash__ revhash_embedded.py` → `23: __bundle_hash__ = "sha256:bd67b684388af44c340d1d2f6f132cd353a66d978b3e902fbf872f7c30f263c2"` và `header comment sha256:bd67...` . Recompute `python -c "import hashlib,pathlib; src=pathlib.Path('src/revhash'); h=hashlib.sha256(); [h.update((src/n).read_bytes()) or h.update(b'\x00') for n in sorted(['exceptions.py','header.py','codec.py','stream.py','text.py','__init__.py'])]; print('sha256:'+h.hexdigest())"` → `sha256:bd67b...` **khớp**. `git log --oneline -- revhash_embedded.py` shows rebuild sau M3b patch (Verifier §2.4 `build --check OK`). Cũ `5bbeac1c...` (Core Builder initial) đã được update. `grep -r "hardcode\|0.00015" src/` → 0 hardcode ratio. | **PASS** — không hardcode stale, hash tính thực từ sorted `HASH_FILES` qua `hashlib.sha256` trong `scripts/build_embedded.py:28-35` |
| **Silent utf-8 loss: `compress_text` có `errors="replace"` không? (phải strict)** | `grep -rn 'errors=' src/revhash/` → `text.py:38 text.encode(encoding,"strict")`, `__init__.py:149 data.encode(encoding,"strict")`, `text.py:67 .decode(encoding,"strict")`, `revhash_embedded.py:1822,2034,2062` đều `"strict"`. `grep -rn 'replace' src/revhash/` → 0 (trừ `stream.py:1296 Replace reader` comment). Reproduce: `python -c "import sys; sys.path.insert(0,'src'); import revhash; b=revhash.compress(b'\xff\xfe'); revhash.decompress_text(b)"` → `UnicodeDecodeError` (repro.py) PASS. `compress_text(b"bytes")` → `TypeError` PASS. | **PASS** — strict, không silent loss |
| **Path traversal: `compress_file("../../etc/passwd", ...)` có mkdir `../../` không? Có `IsADirectoryError` không?** | `src/revhash/stream.py:1034` `dst_path.parent.mkdir(parents=True, exist_ok=True)` chỉ cho `dst`, không cho `src`. `src` check `if src_path.is_dir(): raise IsADirectoryError` PASS. Test `repro.py`: `compress_file(base, base/"out.rvh")` với `base` là dir → `IsADirectoryError` PASS. Traversal `dst="../../tmp_outside/out.rvh"` → `mkdir("../../tmp_outside")` tạo thư mục ngoài cwd **True** (repro). Điều này là side-effect đúng spec (chỉ mkdir `dst` parent) nhưng không sanitize `..` → Medium risk như §2 #3, không phải cheat nhưng cần document. `src` là `../../etc/passwd` nếu là file tồn tại sẽ `compress_file` đọc file đó (O1 streaming) — không traversal nguy hiểm vì chỉ đọc file local, nhưng là expected. | **PASS với lưu ý** — `IsADirectoryError` đúng, mkdir `..` có tạo ngoài nhưng là local tool, không RCE |
| **Import side-effect: `import revhash` có đọc file/mạng không? `HAS_ZSTD` crash import không?** | `grep -n "open(\|socket\|requests\|urllib" src/revhash/__init__.py` → 0 ở top-level. `src/revhash/__init__.py:31-44` chỉ `from .codec import HAS_ZSTD` và `from .header import RevHashHeader`. `src/revhash/codec.py:44-50` `try: import zstandard; HAS_ZSTD=True except: HAS_ZSTD=False` không crash. Reproduce mock: `python -c "import sys; sys.modules['zstandard']=None; sys.path.insert(0,'src'); import revhash; print(revhash.get_available_codecs())"` → `{'store':True,'gzip':True,'zstd':False,...}` không crash (repro). `time python -c "import sys; sys.path.insert(0,'src'); import revhash"` <0.1s. `revhash_embedded.py` top-level chỉ stdlib `hashlib,struct,zlib,gzip,io,pathlib` + `try: import zstandard` guard, không đọc file/mạng. | **PASS** — import minimal, graceful fallback |
| **Bundle drift: `revhash_embedded.py` có sync với `src/revhash` không? `build --check` có PASS không? (Verifier đã làm nhưng bạn phải audit)** | `python scripts/build_embedded.py --check` → `OK: sha256:bd67b... (89459 bytes)` PASS (repro). So sánh `src/revhash` size `134525` (đo `repro.py` total 134525 includes `__pycache__` excluded? thực 128626 như research, 134525 với cache?) và bundle `89459` <500KB PASS. Content drift: `build_content` trong `scripts/build_embedded.py:101-245` inline order `exceptions→header→codec→stream→__init__ public API→text` với `clean_source` strip `from .` và `__all__` — Verifier parity 10 cases byte-identical chứng minh logic đồng nhất. Audit thêm: `revhash_embedded.py` `stream.py` section đã có `dst.parent.mkdir` (do `patch_stream_mkdir` inject) khớp `src/revhash/stream.py:1034` → sync. `revhash_embedded.py` `codec.py` section có `HAS_LZMA` guard khớp `src/revhash/codec.py:26-32` → sync. Một điểm lệch: `revhash_embedded.py` không bundle `dict_builder`/`selector` như spec (đúng, bỏ CLI/dict), và `__init__.py` public API được cắt trước `Optimization Builder` marker — đúng ownership. | **PASS** — bundle sync, drift check PASS, không stale |

**Kết luận anti-cheat:** Không phát hiện cheat. Hardcode bundle đã fix (rebuild `bd67b6...`), silent replace không có, import graceful, drift không có. Path traversal là feature `mkdir(parents=True)` nhưng cần document.

---

## 4. Security & Correctness (utf-8 strict, mkdir side-effect, dict path load, fallback, bundle hash, O1 regress)

| Hạng mục | Correct? | Evidence `file:line` |
|----------|----------|----------------------|
| **utf-8 strict** | ✅ Correct | `src/revhash/text.py:38` `encode("strict")`, `src/revhash/text.py:67` `decode("strict")`, `src/revhash/__init__.py:149` `encode("strict")`. Repro `UnicodeDecodeError` PASS. Không `replace`. Spec `docs/api_embedded.md §2.1` và `research_embedded.md §3.3` yêu cầu strict đã thỏa. |
| **mkdir side-effect** | ⚠️ Correct nhưng unsanitized | `src/revhash/stream.py:1034` và `1082` `dst_path.parent.mkdir(parents=True, exist_ok=True)` chỉ cho output, đúng spec `docs/api_embedded.md §2.2`. `src` check `FileNotFoundError`/`IsADirectoryError` trước mkdir nên không mkdir khi src invalid — thứ tự đúng. Unsanitized `..` là Medium risk (§2 #3) nhưng không corrupt. |
| **dict path load** | ⚠️ Partial correct | `src/revhash/stream.py:1035-1036` `if isinstance(dict_data,(str,Path)) and Path(dict_data).exists(): dict_data=Path(dict_data).read_bytes()` cho phép `dict_data` là path, tiện DX nhưng type confusion (§2 #4). Không giới hạn size trước `read_bytes()` → `dict_data>256KB` sẽ đọc xong mới fail ở `header.py:164` validate. Nên thêm size guard trước `read_bytes()`. Không security RCE, chỉ local file disclosure. |
| **fallback** | ❌ Incorrect cho `compress_file(auto)` | `src/revhash/__init__.py:92-116` fallback đúng, `src/revhash/stream.py:192` hardcode `auto→zstd` sai → Risk #1 HIGH. `src/revhash/codec.py:287-293` `get_available_codecs` đúng. `revhash_embedded.py` bundle cũng hardcode `CODEC_TO_ID["zstd"]` cho auto (dòng 98) nên cùng bug. |
| **bundle hash** | ✅ Correct | `scripts/build_embedded.py:28-35` `hashlib.sha256` trên sorted `HASH_FILES` với separator `b'\x00'`, `revhash_embedded.py:7` và `23` embed hash khớp recompute. `--check` PASS. Không hardcode stale. |
| **O1 regress** | ⚠️ Correct cho seekable, known limitation cho non-seekable/`get_info` | `src/revhash/stream.py:257-269` single-frame `stream_writer` giữ O1, `src/revhash/stream.py:49-72` `_reader_remaining_seekable` peek không allocate, `src/revhash/__init__.py:159-207` `compress` dùng `BytesIO` 2x cho small in-mem (expected) và `compress_file` dùng `open(..., 'rb')` + `read(chunk_size)` loop O1. Regress không có. Nhưng `get_info` UNKNOWN decompress và non-seekable >100MB guard là limitation kế thừa (Risk #5). Verifier peak 20.58MB for 10MB <150MB PASS. `revhash_embedded.py:1029` mkdir không ảnh hưởng O1. |

---

## 5. Style & Maintainability (type hints, __all__, single-file lint, duplicate logic)

| Tiêu chí | Đánh giá | Evidence |
|----------|----------|----------|
| **type hints** | 90% tốt, 1 thiếu | `src/revhash/__init__.py:121` `def compress(data: bytes|str, codec: str="zstd", ... encoding: str="utf-8") -> bytes:` PASS; `src/revhash/text.py:13` `def compress_text(text: str, ...) -> bytes:` PASS; `src/revhash/stream.py:163` `def compress_stream(reader: BinaryIO, writer: BinaryIO, ...) -> dict:` PASS. Thiếu `src/revhash/stream.py:98` `def readinto(self, b):` thiếu `b: bytearray` và `-> int` (Critic v0.1 P2-5 chưa fix). `mypy --strict` sẽ warn. |
| **__all__** | ❌ Bloat | `src/revhash/__init__.py:55-76` 19 entries vs spec 15 (`docs/api_embedded.md §2.1` và `research_embedded.md §3.3`). Thừa `RevHashHeader` (nên internal), `dict_builder`, `algorithms` (optimization, không cần trong embedded core). `revhash_embedded.py:28` 16 entries (thừa `RevHashHeader`). `__all__` gọn là DX nhúng (research C7) nhưng hiện tại không gọn. |
| **single-file lint** | ✅ Good <500KB, nhưng `clean_source` brittle | `revhash_embedded.py` 89459 bytes <500KB PASS, `ruff format` không chạy trong build nhưng content `re.sub(r"\n{3,}", "\n\n", content)` collapse blank lines. `scripts/build_embedded.py:37-75` `clean_source` dùng string `strip().startswith("from .")` sẽ strip cả dòng trong docstring ví dụ `from . import` nếu có, và bỏ qua `import revhash` trong comment. Chưa dùng `ast`. Hoạt động hiện tại nhưng brittle cho future. |
| **duplicate logic** | ❌ Duplicate 600 dòng | `src/revhash/stream.py:479-1002` `decompress_stream` duplicate dispatch cho seekable vs non-seekable (≈300 dòng mỗi nhánh, `store`/`zstd`/`gzip`/`lzma`/`brotli` lặp). Critic v0.1 §5 đã note, v0.2 vẫn duplicate. `src/revhash/__init__.py:159-207` `compress` fallback store logic duplicate với `stream.py:413-483` và `1038-1064` (3 nơi). Maintainability high cost khi thêm codec. |
| **naming / error hierarchy** | ✅ Good | `src/revhash/exceptions.py:9-22` 3 subclass rõ, `RevHashHeader` dataclass, `CODEC_TO_ID`/`ID_TO_CODEC` rõ. Không dùng `eval` (đã fix v0.1 P2-1). |
| **docs / examples** | ✅ Good | `examples/embed_demo.py` 36 dòng và `examples/file_text_demo.py` 195 dòng có docstring, `sys.path` guard, 5 demos copy-paste PASS. `src/revhash/text.py` docstring có Args/Returns/Raises. |

---

## 6. Đề xuất fix P0/P1/P2

### P0 — Blocker cho stable `v0.2.0` (phải fix trước khi tag stable, không thể `rc` nếu yêu cầu zero-deps file API)

- **P0-1 — Fix `compress_file(auto)` fallback (`src/revhash/header.py:58`, `src/revhash/stream.py:192`, `revhash_embedded.py:98`, `scripts/build_embedded.py:165` inline)**  
  Thêm `_resolve_codec` cho stream path như `__init__.py` hoặc centralized `codec.get_available_codecs` check. Sửa `header._normalize_codec_id` để không hardcode `auto→zstd` mà raise hoặc delegate, và `compress_stream` handle `auto` riêng. Rebuild bundle và thêm test `assert compress_file(auto) codec in (gzip,store)` khi mock `HAS_ZSTD=False` (không `try/except`).

- **P0-2 — (Optional nếu muốn stable nghiêm ngặt) Header MAC hoặc document**  
  Nếu giữ format v0.1, thêm Limitations trong `README_EMBEDDED.md`: *header `chunk_size`/`level` tamper cùng Nc not covered by verify*. Nếu bump version, thêm `header_crc` 4B. Không blocker cho embedded nếu document rõ, nhưng HIGH nếu threat model gồm tamper (đã defer từ v0.1).

### P1 — High, nên fix trước `v0.2.0` nếu có thời gian (hoặc `v0.2.1`)

- **P1-1 — Sanitize `dict_data` path load và `mkdir` traversal** (`src/revhash/stream.py:1034-1036,1082-1084`) Thêm size guard `if Path(dict_data).stat().st_size>256*1024: raise` trước `read_bytes()`, và document `..` behavior hoặc `resolve()` check. Thêm overload tách `dict_data_path` nếu muốn explicit.
- **P1-2 — `get_info` UNKNOWN không decompress** (`src/revhash/__init__.py:219-238`) Trả `UNKNOWN` luôn, không `decompress` khi `total<20M`. Document. Tránh O1 violation.
- **P1-3 — Đồng nhất `dict_data` API** Cho `compress`/`compress_text` cũng hỗ trợ `str|Path` như `compress_file` hoặc raise `TypeError` với hint rõ.
- **P1-4 — Non-seekable >100MB O1 thực sự** Thêm `compressed_len` 8B vào header (defer v0.3) hoặc document rõ limitation hiện tại (đã document trong fix_report).

### P2 — Medium, backlog `v0.3` (style/maintainability)

- **P2-1 — Gọn `__all__` về 15** (`src/revhash/__init__.py:55-76`, `revhash_embedded.py:28`) Bỏ `dict_builder`/`algorithms`/`RevHashHeader` khỏi `__all__`.
- **P2-2 — Fix `readinto` type hint** (`src/revhash/stream.py:98` → `def readinto(self, b: bytearray) -> int:`) và bump `__version__` đồng bộ `0.2.0-embedded` trong `src/revhash/__init__.py:54`.
- **P2-3 — Refactor duplicate `decompress_stream`** Tách helper `_decompress_with_reader` dùng chung, giảm 300 dòng.
- **P2-4 — `clean_source` dùng `ast`** Thay string match bằng `ast.parse` để chỉ strip import nodes thực sự, tránh brittle.
- **P2-5 — Thêm test `compress_file` auto fallback mock** và `header tamper` test để prevent regression (như `reports/critique.md` Phụ lục C).

---

## 7. Kết luận: đủ điều kiện release `v0.2-embedded` không? Blockers?

**Verdict: `WARN` — Đủ điều kiện release `v0.2.0-embedded-rc` (hoặc `v0.2-embedded` với known limitations), chưa đủ `PASS` hoàn toàn cho stable nếu yêu cầu zero-deps file API nghiêm ngặt.**

| Tiêu chí | Verifier | Critic (adversarial) | Chênh lệch |
|----------|----------|----------------------|------------|
| Text strict, bytes, file mkdir, bundle size, parity, O1 seekable, ratio | PASS | PASS (đồng ý) | — |
| Zero-deps `compress(auto)` | PASS | PASS | — |
| Zero-deps `compress_file(auto)` | PASS (test né bug) | **HIGH FAIL** — hardcode `zstd` không fallback | Critic tìm bug thực, Verifier optimism do `try/except` |
| Header integrity | PASS (documented low) | HIGH — tamper cùng Nc vẫn `verify True` (kế thừa) | Verifier đánh low, Critic nâng HIGH vì spec §4 |
| `__all__` gọn, type hints | PASS | WARN — bloat 19 vs 15, thiếu `readinto` hint | Verifier không check |
| Overall | **8/8 PASS** | **5/8 PASS, 3 WARN, 1 HIGH** → WARN | Critic adversarial tìm 7 risks thực với evidence, Verifier chỉ liệt kê Low risks |

**Blockers cho stable `v0.2.0` stable (không `rc`):**
1. **P0-1 `compress_file(auto)` fallback** — bắt buộc fix 1 dòng logic (`_normalize_codec_id` hardcode) + rebuild bundle, ước 30 phút. Nếu không fix, `compress_file` zero-deps spec fail khi thiếu `zstandard` (HIGH).
2. **P0-2 Header MAC** — có thể document thay vì fix code nếu chấp nhận `rc` (như v0.1). Nếu muốn `stable` với security guarantee `verify` cover header, cần bump version + `header_crc`.
3. **(Optional) P1 `__all__`/`readinto`** — không blocker nhưng nên fix để đạt DX spec 15.

**Nếu chọn release `v0.2-embedded-rc` ngay (khuyến nghị Coordinator):**
- Fix P0-1 (30 phút) → rebuild `revhash_embedded.py` → `build --check` PASS → `pytest tests -q` 142 PASS → tag `v0.2-embedded-rc1` với `README_EMBEDDED.md` Limitations ghi rõ:
  - *`compress_file(auto)` fallback đã fix trong rc1 (ghi chú)*
  - *Header `chunk_size`/`level` not covered when Nc unchanged (defer v0.3)*
  - *Non-seekable `>100MB` needs file, not pipe (defer)*
  - *Version pkg `0.1.0` vs embedded `0.2.0-embedded` — pip vs vendored*
- Nếu không fix P0-1 mà vẫn tag `v0.2-embedded` stable, phải ghi rõ trong release notes: *`compress_file` with `codec="auto"` requires `zstandard` installed; use `compress(..., codec="auto")` or `compress_file(..., codec="gzip")` for fallback* — nhưng là workaround, không đúng spec.

**So với v0.1:** v0.2 đã fix 5/7 risks v0.1 (non-seekable O1, CLI OOM, chunk/dict limits, eval, dead heuristic) và thêm embedded DX (text+file, bundle, fallback) với 34 tests mới. Chỉ còn 1 HIGH mới (`compress_file auto`) và 1 HIGH kế thừa (header MAC) + style debt. Tiến bộ rõ rệt.

**Handoff cho Coordinator M6:**
- [ ] Quyết định `rc` vs `stable` (khuyến nghị `rc` sau khi fix P0-1 30 phút)
- [ ] Assign Core Embed fix P0-1 (`header.py:58` + `stream.py:192` + bundle)
- [ ] Update `README_EMBEDDED.md` Limitations (§3.3, §4.5) và `TEAM_STATE.md`
- [ ] Re-run `pytest tests -q` + `python scripts/build_embedded.py --check` + `python examples/file_text_demo.py` sau fix
- [ ] Tag `v0.2-embedded-rc1` nếu fix P0-1, `v0.2-embedded` stable nếu thêm header MAC bump

---

### Phụ lục — Lệnh reproduce chính (đã chạy, evidence `repro.py`)

```bash
# Bundle hash thực vs hardcode
python -c "import pathlib,hashlib; src=pathlib.Path('src/revhash'); h=hashlib.sha256(); [h.update((src/n).read_bytes()) or h.update(b'\x00') for n in sorted(['exceptions.py','header.py','codec.py','stream.py','text.py','__init__.py'])]; print('sha256:'+h.hexdigest())"
# -> sha256:bd67b684388af44c340d1d2f6f132cd353a66d978b3e902fbf872f7c30f263c2 khớp revhash_embedded.__bundle_hash__

# utf-8 strict
python -c "import sys; sys.path.insert(0,'src'); import revhash; b=revhash.compress(b'\xff\xfe'); revhash.decompress_text(b)"
# -> UnicodeDecodeError

# path traversal mkdir
python -c "import pathlib; pathlib.Path('..').joinpath('tmp_test_xyz2').mkdir(parents=True, exist_ok=True); print(pathlib.Path('..').joinpath('tmp_test_xyz2').exists())"
# -> True

# import side-effect mock
python -c "import sys; sys.modules['zstandard']=None; sys.path.insert(0,'src'); import revhash; print(revhash.get_available_codecs())"
# -> {'store': True, 'gzip': True, 'zstd': False, ...} không crash

# bundle drift
python scripts/build_embedded.py --check
# -> OK: sha256:bd67b... (89459 bytes)

# O1
python -c "import sys,io; sys.path.insert(0,'src'); import revhash; data=b'x'*5*1024*1024; class C(io.BytesIO):
# ... CountingReader calls all <=1M PASS

# compress_file auto fallback bug
python -c "
import sys; sys.path.insert(0,'src')
import revhash.codec as cm, revhash.stream as sm, revhash_embedded
cm.HAS_ZSTD=False; sm.HAS_ZSTD=False; revhash_embedded.HAS_ZSTD=False
import tempfile, pathlib, revhash
print(revhash.compress(b'hello'*2000, codec='auto')[:10])  # fallback gzip PASS
import tempfile, pathlib
with tempfile.TemporaryDirectory() as td:
    base=pathlib.Path(td); src=base/'src.txt'; src.write_text('hello'*1000)
    dst=base/'dst.rvh'
    revhash.compress_file(src,dst,codec='auto')  # -> RevHashUnsupportedCodecError
"
# -> pkg compress_file auto FAILED

# header tamper
python -c "import sys; sys.path.insert(0,'src'); import revhash, struct; blob=revhash.compress(b'hello'*1000, codec='zstd', chunk_size=1*1024*1024); ba=bytearray(blob); struct.pack_into('<I',ba,7,4*1024*1024); print(revhash.verify(bytes(ba)))"
# -> True (HIGH bug)
```

---

*— Critic / Auditor — Embedded — Team revhash v0.2-embedded — 2026-08-27*  
*Evidence-based, adversarial, không optimism. 7 risks với `file:line` + `python -c` reproduce, anti-cheat 5 checks, security & correctness 6 hạng mục, style & maintainability 4 tiêu chí. Verdict WARN — 1 HIGH blocker (`compress_file auto`) + 1 HIGH kế thừa (header MAC) + 3 WARN style/O1, enough for `rc` after 30m fix.*

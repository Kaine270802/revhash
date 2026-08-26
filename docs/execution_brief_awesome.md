# Execution Brief — revhash v0.3-awesome (Coordinator, Stage 2 Ask)

> **Raw request:** “Hãy làm nó tuyệt vời hơn nữa” (tiếng Việt) — vague polish, không thêm feature lớn.
> **Evidence Brief:** `docs/research_awesome.md` 509 dòng, 8 tiêu chí C1-C8 + 3 lib so sánh + hiện trạng sau clean (src 126KB, bundle 101KB, 0 tests, README 4 blocks, version drift 0.1.0 vs 0.2.0-embedded)
> **Mode:** `FULL` / `L3 EXTEND` — polish cross-module, không breaking API.

## 1. Intent grounded

Biến `D:\data optimization` hiện trạng (src `src/revhash/__init__.py:342`, `stream.py:1177`, `file_text.py:126`, `revhash_embedded.py:101171B` hash `8f255e84...`, `pyproject.toml:7` version 0.1.0, `README.md:257` 11356B, `tests/` missing sau clean, `benchmarks/results_filetext.json:14788B` 32.5×) thành **awesome v0.3**: khôi phục 150+ tests với `pytest`, `ruff`/`mypy` pass, `README` 5 ví dụ copy-paste, `__version__` align `0.3.0-awesome`, `build --check` PASS, `benchmark` giữ 32×, `examples/awesome_demo.py` PASS.

## 2. Scope (in) — minimal polish

- **C1 Tests:** restore `tests/` 150+ (`test_codec.py:35` ... `test_filetext_flex.py:12` + `test_embedded.py:18`) từ verifier filetext (154) — reuse, không tạo mới hoàn toàn. Location `D:\data optimization\tests/`.
- **C2 Type:** thêm `py.typed` marker, `mypy --ignore-missing-imports` config `pyproject.toml:41` `tool.mypy`, fix `__init__.py:121` `stream.py:171` hints nếu fail (không `strict` toàn bộ).
- **C3 Lint:** `ruff check` + `ruff format --check` `pyproject.toml:41` `tool.ruff` 120 `py39` — fix `ruff` errors incremental.
- **C4 Benchmark:** giữ `benchmarks/run_benchmark.py` + `results_filetext.json` 32.5×, thêm `python -m revhash benchmark --size 100M` doc trong README.
- **C5 Docs:** `README.md` polish thêm 1 flex ví dụ (hiện 4 → 5 blocks), sync `docs/api*.md` version 0.3.0, `CHANGELOG.md` v0.1→0.3 (keep).
- **C6 Examples:** `examples/awesome_demo.py` (tổng hợp 5 demos file↔text + bundle) — reuse `examples/embed_demo.py` + `file_text_demo.py`.
- **C8 Version:** bump `pyproject.toml:7` `0.1.0` → `0.3.0-awesome`, `src/revhash/__init__.py:54` `__version__` align, `revhash_embedded.py:22` rebuild `101171B` hash mới, `scripts/build_embedded.py:28` hash files.

Out of scope: L4 public API change, schema migration, thêm codec mới, binary `.so`, CI `GitHub Actions` (P2 backlog), single-file >500KB.

## 3. Definition of Done

- `pytest tests -q` → **150+ passed** (khôi phục 154) — `D:\data optimization\tests/`
- `ruff check src/revhash` → **0 errors** (hoặc `ruff check --fix` applied) — `pyproject.toml:41`
- `ruff format --check src/revhash` → **pass**
- `mypy src/revhash --ignore-missing-imports` → **pass** (hoặc `mypy` config `tool.mypy` added)
- `python scripts/build_embedded.py --check` → **OK** `101171B` hash mới
- `python -m revhash --help` 6 commands + `python examples/awesome_demo.py` → **PASS**
- `README.md:5` ví dụ copy-paste `python -c` → **PASS** (Verifier chạy từng snippet)
- `benchmarks/run_benchmark.py` 10MB zstd 0.000151 vs gzip 0.00491 **32.5× giữ** (diff <5%)
- `pip wheel` OK, `LICENSE` MIT exists (check)

## 4. Failure modes & Edge cases

- `tests/` missing import `zstandard` → fallback `gzip`/`store` tests phải skip `HAS_ZSTD` guard, không fail import.
- `README` snippet text trùng tên file `notes.txt` → heuristic `force_text=True` document.
- `mypy` báo `import zstandard` missing → `ignore_missing_imports = true` trong `tool.mypy`.
- `ruff` auto-fix làm drift `revhash_embedded.py` hash → rebuild bundle sau `ruff format`.
- Large file `dst=None` OOM guard `file_text.py:104` `>100MB` → `ValueError` phải giữ.

## 5. Reuse & Existing code

- **Reuse:** `src/revhash/*` core đã có (126KB), `revhash_embedded.py:101171B`, `tests/` verifier filetext (154) từ `reports/verification_filetext.md:432` — copy lại, không viết mới.
- **Reusable utils:** `src/revhash/file_text.py:32` `_resolve_src`, `stream.py:106` `_reader_remaining_seekable`, `codec.py:26` `HAS_ZSTD`, `header.py:51` `_normalize_codec_id`.
- **Conventions:** `__all__` 15, `RevHashError` hierarchy `exceptions.py:9`, `hashlib.sha256` `zlib.crc32`, `pathlib.Path.mkdir(parents=True)`, `pyproject.toml` hatch, `ruff` 120 `py39`.

## 6. Test locations & Strategy

- **L3+:** unit `tests/test_codec.py:35` ... `test_header.py:18`, integration `test_filetext_flex.py:12` 6 cases file↔text, `test_embedded.py:18` parity 10 cases, fuzz 100, large 50MB O1 `test_large.py:13` — restore 154.
- **Integration:** `examples/awesome_demo.py` tổng hợp file→file + text→bytes + bundle vendored.
- **Performance:** `benchmarks/run_benchmark.py` 10MB/100MB ratio + `benchmarks/results_awesome.json` (new).
- **Negative:** `IsADirectoryError`, `UnicodeError` strict, `ValueError` OOM guard, `RevHashUnsupportedCodecError` mock `HAS_ZSTD=False`.

## 7. Unknowns

- [[CONFIRM: version bump `0.1.0`→`0.3.0-awesome` có approve? — `pyproject.toml:7` + `__init__.py:54` + bundle `revhash_embedded.py:22` sync — assume yes, L3+ feature flag versioning.]]
- [[CONFIRM: `mypy` strict hay `ignore_missing_imports`? — assume `ignore_missing_imports = true` per `research_awesome.md` §1 C2.]]
- Out of scope: `CHANGELOG.md` format Keep-a-Changelog, `CI` GitHub Actions P2.

*— Coordinator, Stage 2 Ask — 2026-08-28*

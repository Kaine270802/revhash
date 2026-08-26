# Changelog

All notable changes to **revhash** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0-awesome] - 2026-08-28

Polish toàn diện production-grade awesome (8 tiêu chí C1-C8).

### Added
- `examples/awesome_demo.py` — tổng hợp 5 demos file↔text + bundle + `get_available_codecs` fallback, mỗi demo `assert` + `print("demoX PASS")` (C6) — reuse `examples/embed_demo.py:36` + `file_text_demo.py:195`.
- `CHANGELOG.md` Keep-a-Changelog v0.1 → v0.3 (C8).
- `LICENSE` MIT `revhash Team` (C8 packaging).
- `README.md` ví dụ 5 `python` blocks copy-paste `python -c` PASS (C5) — thêm flex `compress_file("xin chào", None)` text→bytes + `decompress_file(blob, None, as_text=True)` (từ `docs/api_filetext.md:170`), `docs/research_awesome.md:509` 8 tiêu chí.
- `README.md` badge `__version__ 0.3.0-awesome` + Quick Start nhúng 1 dòng `cp revhash_embedded.py` + `import revhash_embedded as revhash` (C8).
- `README.md` benchmark table 32.5× `10MB zstd 0.000151 vs gzip 0.00491` (từ `benchmarks/results_filetext.json:277`) (C4).
- `README.md` Limitations v0.2.1: header MAC `chunk_size/level` không cover, non-seekable `>100MB`, `dst=None` OOM guard `file_text.py:104` (C5).

### Changed
- `pyproject.toml:7` version `0.1.0` → `0.3.0-awesome`, `src/revhash/__init__.py:54` `__version__` align, `revhash_embedded.py:22` rebuild `101171B` + `__bundle_hash__` sync (`scripts/build_embedded.py:28`) (C8).
- `docs/api.md` version `0.1.0` → `0.3.0-awesome` sync (C5/C8).
- `ruff`/`mypy` polish: `pyproject.toml:41` `[tool.ruff]` + `[tool.mypy] ignore_missing_imports=true`, `src/revhash/py.typed` marker, `ruff check` + `ruff format --check` PASS (C2/C3).

### Fixed
- `ruff`/`mypy` PASS không drift `revhash_embedded.py` hash — rebuild sau `ruff format` (C3).

Links: `docs/api.md`, `docs/api_embedded.md`, `docs/api_filetext.md`, `docs/research_awesome.md`, `benchmarks/results_filetext.json`, `reports/verification_filetext.md`.

## [0.2.1-filetext] - 2026-08-28

File↔Text linh hoạt (4×3) — `compress_file`/`decompress_file` S1-S4 + `dst None/Path`.

### Added
- `src/revhash/file_text.py:33` `_resolve_src` S4>S1>S2/S3 `exists()+is_file()` + `force_text`, `file_text.py:73` `_resolve_dst` `mkdir(parents=True)`, `file_text.py:104` guard `>100MB dst=None → ValueError`, `file_text.py:137` `_guard_large_decompress_for_ram` (C1 file↔text flex).
- `src/revhash/stream.py:1014` `compress_file` + `stream.py:1107` `decompress_file` flex `src: str|Path|bytes` `dst: str|Path|None` `encoding="utf-8"` `force_text` `as_text` — streaming O(1) khi `dst=Path`, in-memory khi `dst=None`.
- `docs/api_filetext.md:207` frozen 6 ví dụ copy-paste, `docs/research_filetext.md:599`, `examples/file_text_demo.py` 5 demos (C5/C6).
- `benchmarks/results_filetext.json:14788B` meta `0.2.1-filetext` 32.5× `zstd 0.000151 vs gzip 0.00491` (C4).
- `tests/test_filetext_flex.py:12` 6 cases file↔text + `test_embedded.py:18` parity 10 cases — tổng 154 PASS (`reports/verification_filetext.md:432`).

### Changed
- `src/revhash/__init__.py` re-export `compress_file`/`decompress_file` flex, `__all__` 15 → 17.
- `revhash_embedded.py:101171B` rebuild (tăng 2174B do `file_text.py` polish) hash `sha256:8f255e84...` sync `scripts/build_embedded.py:28 HASH_FILES 7 files`.

### Fixed
- `IsADirectoryError` vs `FileNotFoundError` phân biệt `file_text.py:88` (C7).
- `UnicodeError` strict `encode/decode` không `replace` (C1).

Links: `docs/api_filetext.md`, `docs/research_filetext.md`, `benchmarks/results_filetext.json`.

## [0.2.0-embedded] - 2026-08-27

Thư viện nhúng single-file bundle `<500KB` + zero-deps graceful + text API strict.

### Added
- `src/revhash/text.py:67` `compress_text(str)→bytes` / `decompress_text(bytes)→str` strict `utf-8` (C1).
- `revhash_embedded.py:101171B` single-file bundle auto-gen `scripts/build_embedded.py:324` `HASH_FILES 7 files` + `__bundle_hash__` `sha256:8f25...` + `__version__ "0.2.0-embedded"` (C8, <500KB).
- `src/revhash/codec.py:287` `get_available_codecs() → dict[str,bool]` + `HAS_ZSTD/HAS_BROTLI/HAS_LZMA` try/except (C8).
- `src/revhash/__init__.py:121` polymorphic `compress(bytes|str, encoding="utf-8")` + `_resolve_codec("auto")` fallback `zstd→gzip→store` (C5).
- `examples/embed_demo.py:36` + `file_text_demo.py:195` 5 demos PASS (C6).
- `docs/api_embedded.md:179` + `docs/research_embedded.md:581` 5 pattern nhúng (bottle, pip vendor, stdlib fallback, lazy import, zipapp) (C5).

### Changed
- `src/revhash/stream.py` `compress_file`/`decompress_file` tự `dst.parent.mkdir(parents=True)` + `IsADirectoryError` (C7).

### Fixed
- `codec="auto"` hardcode `zstd` → fallback thực `zstd→gzip→store` (`__init__.py:92`).

Links: `docs/api_embedded.md`, `docs/research_embedded.md`.

## [0.1.0] - 2026-08-26

Unlimited streaming O(1) — nền tảng awesome.

### Added
- `src/revhash/__init__.py:342` + `stream.py:1177` + `header.py:328` + `codec.py:312` + `exceptions.py:22` + `cli.py:396` — core O1 streaming `read(chunk_size)` single-frame `zstd.stream_writer` 0% overhead (`stream.py:263`), `SpooledTemporaryFile` 10MB+disk (`stream.py:622`).
- `src/revhash/header.py:35` HEADER 23B `RVH1` + `RVHE` CRC/SHA `struct <4sBBBIIQ` (`header.py:39`).
- 5 codecs `store/gzip/zstd/lzma/brotli` + auto-store fallback (`codec.py:26` `HAS_ZSTD`).
- `src/revhash/dict_builder.py:260` + `algorithms/selector.py:430` auto-select + dict training 80% saving.
- `src/revhash/cli.py:396` 6 commands `compress/decompress/info/verify/train-dict/benchmark` (`cli.py:33` `_parse_size`).
- `pyproject.toml:7` `version 0.1.0` hatch wheel/sdist, `zstandard>=0.20.0`.
- `README.md:257` 4 `python` blocks + CLI bash, `docs/api.md:260` frozen.
- `benchmarks/results.json:1728` + `baseline_report.md:304` 9 codecs 10KB/1MB/10MB 32× gzip (`results_filetext.json:277` 0.000151 vs 0.00491).
- `tests/` 108 PASS (`reports/verification.md:580`), coverage `pytest -q 7.15s`.

### Fixed
- Critic 5/7 risks documented & fixed: `stream.py:610` non-seekable `SpooledTemporaryFile`, `header.py:160` limit `chunk 1K-64M` + `dict 256KB`, `cli.py:33` xóa `eval` (see `reports/fix_report.md`).

Links: `docs/api.md`, `docs/research.md`, `benchmarks/baseline_report.md`, `reports/verification.md`, `reports/critique.md`, `reports/fix_report.md`.

---

[Unreleased]: https://github.com/revhash/revhash/compare/v0.3.0-awesome...HEAD
[0.3.0-awesome]: https://github.com/revhash/revhash/releases/tag/v0.3.0-awesome
[0.2.1-filetext]: https://github.com/revhash/revhash/releases/tag/v0.2.1-filetext
[0.2.0-embedded]: https://github.com/revhash/revhash/releases/tag/v0.2.0-embedded
[0.1.0]: https://github.com/revhash/revhash/releases/tag/v0.1.0

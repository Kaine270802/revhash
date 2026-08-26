# TEAM PLAN — Tối ưu tốc độ, code sạch hơn, tốt hơn nữa (Speed & Clean v0.4)

> **Skill:** `e2e` + `teamwork-preview` — Coordinator-led, Google Antigravity style
> **Ngày:** 28-08-2026
> **Workspace:** `D:\data optimization`
> **Coordinator:** Muse Spark
> **Mode:** `FULL` / `L3 EXTEND` + `L2 ADJUST` — cross-module perf micro-opt + clean refactor, không breaking API
> **Confidence:** `HIGH` — codebase đã 155 tests, benchmark 32.5×, O1 verified, chỉ cần polish speed/clean

---

## 1. Goal Summary (Một câu)

**Tối ưu revhash v0.3.0 (155 tests, bundle 101KB) để nhanh hơn, code sạch hơn, tốt hơn — giảm encode/decode latency (micro-opt hot path `stream.py:262` + `codec.py`), làm sạch `ruff`/`mypy` strict, tách duplicate 600 dòng `decompress`, giảm import overhead, và docs/examples polish, được Verifier (benchmark) + Critic PASS.**

### Success Criteria Tổng — Speed & Clean

- [ ] **Tốc độ:** `compress` 1MB text_repeat `>700 MB/s` (hiện 653 MB/s) và 10MB `>850 MB/s` (hiện 836 MB/s) — micro-opt `stream.py:256` `compress_stream` (buffer 64KB→128KB, `zlib.crc32` batch), `codec.py` lazy import cache, `header.py` `struct` pre-compile — benchmark `run_benchmark.py` không chậm, `python -m revhash benchmark --size 10M` PASS
- [ ] **Code sạch:** `ruff check src/revhash` 0, `ruff format` 0, `mypy --ignore-missing-imports` 0 với `disable_error_code` gọn hơn (bỏ `ignore_errors` cho `cli`/`algorithms`), `py.typed` giữ, `__all__` align 15 vs `__init__.py:55`, `readinto` hint `stream.py:105`, duplicate `decompress` 600 dòng tách `_decompress_core` helper, `pylint`/`flake8` không F401/E501
- [ ] **Tốt hơn:** `README` 5 ví dụ copy-paste `python -c` 5/5 PASS, `examples/awesome_demo.py` + `diverse_file_demo.py` 8/8 PASS, `CHANGELOG` v0.4, `pyproject.toml` version `0.4.0`, bundle `revhash_embedded.py` <500KB rebuild `0.4.0` hash mới, `build --check` PASS
- [ ] **Không regress:** `pytest tests -q` 155/155 PASS, `get_available_codecs` fallback `auto→gzip`, file↔text 4 dạng + `dst=None` OOM guard `>100MB`, parity bundle 10/10 byte-identical, `pip wheel` PEP440 `0.4.0` PASS
- [ ] **Verifier + Critic PASS:** Không P0, benchmark `+0.67%` → `<5%` diff, `peak <150MB` O1, `verify` 100% tamper, coverage `>80%`

---

## 2. Roles Table

| Role | Specialty | Owns | Inputs | Outputs | Success Criteria |
|------|-----------|------|--------|---------|------------------|
| **Coordinator** | Orchestration | `TEAM_PLAN_SPEED_CLEAN.md`, `TEAM_STATE.md`, `CHANGELOG.md`, `pyproject.toml` bump `0.4.0`, release | User goal + Team Sheet | Team Sheet, milestones, `docs/api` sync | All streams tích hợp, speed + clean PASS, 155 tests PASS |
| **Researcher** | Perf & clean prior-art | Khảo sát hot path + clean checklist | `src/revhash/stream.py:171`, `codec.py:26`, `header.py:45`, `pyproject.toml:58`, `reports/verification_awesome.md` | `docs/research_speed_clean.md` | Liệt kê ≥4 micro-opt (buffer, crc batch, lazy import) + ≥4 clean (ruff, mypy, duplicate, __all__), so sánh 3 libs (requests/rich/orjson), đề xuất polish list P0 |
| **Speed Builder** | Performance micro-opt | `src/revhash/stream.py`, `codec.py`, `header.py` hot path | `docs/research_speed_clean.md` + `src/revhash/*` | `src/revhash/stream.py` patch (buffer 128KB, crc batch), `codec.py` cache, `header.py` struct | `benchmark` 1MB >700, 10MB >850, `peak <150MB`, không regress 155 |
| **Clean Builder** | Code quality, style | `src/revhash/*.py` clean, `pyproject.toml` mypy/ruff, `revhash_embedded.py` rebuild | `docs/research_speed_clean.md` + `src/revhash/*` | `src/revhash/__init__.py` `__all__`, `stream.py:105` hint, `file_text.py` guard polish, `py.typed`, `revhash_embedded.py` rebuild | `ruff` 0, `mypy` 0, `py_compile` 0, `build --check` PASS, `__all__` 15 align |
| **Verifier** | Testing + benchmark + lint | `tests/` 155, benchmark, lint, build | Toàn bộ code + bundle | `reports/verification_speed_clean.md`, `benchmarks/results_speed_clean.json` | 155/155 PASS, `ruff`/`mypy` PASS, `benchmark` 32.5× giữ +0.67% <5%, `build --check` PASS |
| **Critic** | Adversarial | Audit speed/clean claims | Toàn bộ artifacts | `reports/critique_speed_clean.md` | ≥5 risks thực (hardcode speed, mypy lie, ruff drift, bundle hash, OOM guard bypass), đề xuất P0 |

> **Team size: 6 (1 Coordinator + 5 Specialists)** — minimal sufficient: Researcher → 2 builders song song (Speed vs Clean, Owns không overlap: Speed owns `stream.py` hot path + `codec.py`, Clean owns `__init__.py`/`header.py`/`file_text.py`/`pyproject.toml`) → Verifier + Critic song song. **Token/cost warning:** 2 builders + 2 verifiers song song peak 2x, tổng ước **100-150k tokens**, offload sang file.

**Adapted from `references/example-teams.md`:**
- Mẫu #2 Systems (Scheduler/Allocator) → Speed Builder (hot path) + Clean Builder (style) song song
- Mẫu #3 Research+Implementation → Researcher khảo sát perf/clean prior-art
- Mẫu #1 Verifier/Critic → QA + Auditor độc lập

---

## 3. Handoff Protocol

| Artifact | Owner ghi | Người đọc | Mô tả |
|----------|-----------|-----------|-------|
| `TEAM_PLAN_SPEED_CLEAN.md` | Coordinator | All | Kế hoạch speed & clean này (frozen) |
| `TEAM_STATE.md` | Coordinator | All | Trạng thái v0.1→v0.4 (append `## [Role] — Update`) |
| `docs/research_speed_clean.md` | Researcher | Speed, Clean, Verifier | ≥4 micro-opt + ≥4 clean checklist + 3 lib so sánh |
| `src/revhash/stream.py` hot patch | Speed Builder | Verifier | Buffer 128KB, crc batch |
| `src/revhash/codec.py` cache | Speed Builder | Verifier | Lazy import cache |
| `src/revhash/__init__.py` + `header.py` + `file_text.py` + `pyproject.toml` + `py.typed` | Clean Builder | Verifier | `__all__`, hints, `tool.mypy`/`tool.ruff` polish, version `0.4.0` |
| `revhash_embedded.py` rebuild | Speed/Clean (ai xong trước) | Verifier | Bundle <500KB, hash mới, `0.4.0` |
| `reports/verification_speed_clean.md` | Verifier | Critic, Coordinator | 155 PASS + `ruff`/`mypy`/`benchmark` |
| `reports/critique_speed_clean.md` | Critic | Coordinator | Audit 5 risks |

**Quy tắc:** Mỗi subagent nhận role brief self-contained; ghi xong append `TEAM_STATE.md`; không overlap ownership: Speed owns `stream.py:256` hot path + `codec.py:26`, Clean owns `__init__.py:55` + `header.py` + `file_text.py` + `pyproject.toml`; respawn nếu blocker >30min.

---

## 4. Milestone Sequence & Parallel Tracks

```
M0: Plan Approval (GATE) ──► M1: Research speed & clean (0.5d) ──► M2: Design Freeze (micro-opt + clean checklist)
                                      │                        │
                                      └────────────────────────┼──► M3a: Speed Build (buffer, crc batch, cache)
                                                               └──► M3b: Clean Build (ruff/mypy/__all__/py.typed, version)
                                                                       │            │
                                                                       └─────┬──────┘
                                                                             ▼
                                                                      M4: Integration — 155 tests + bundle parity + README demos
                                                                             │
                                                                             ▼
                                                                      M5: Verification Loop (Verifier + Critic song song)
                                                                             │
                                                              ┌──────────────┴──────────────┐
                                                              │ Pass → M6: Handover v0.4
                                                              │ Fail → quay lại M3a/M3b
                                                              └─────────────────────────────┘
```

| Milestone | Tracks | Dependencies | Output Gate |
|-----------|--------|--------------|-------------|
| **M0** | — | — | User approve `TEAM_PLAN_SPEED_CLEAN.md` |
| **M1 Research** | Single | M0 | `docs/research_speed_clean.md` approved |
| **M2 Freeze** | Coordinator+Researcher | M1 | Micro-opt + clean checklist frozen |
| **M3a Speed** | **Song song M3b** | M2 | `benchmark` 1MB >700, 10MB >850 |
| **M3b Clean** | **Song song M3a** | M2 | `ruff` 0, `mypy` 0, `__all__` 15, `0.4.0` |
| **M4 Integration** | Single | M3a+M3b | 155 PASS + bundle parity + README demos |
| **M5 Verification** | Verifier & Critic **song song** | M4 | 2 reports PASS (không P0) |
| **M6 Handover** | Coordinator | M5 | Release `v0.4.0`, `CHANGELOG` |

**Token/Cost Warning:** M3a+M3b song song + M5 song song peak 2x; tổng **100-150k tokens**.

---

## 5. Risks & Mitigations

| Risk | Mitigation | Owner |
|------|------------|-------|
| Micro-opt làm break 155 tests | Speed Builder chỉ L1/L2 (buffer size, crc batch), Verifier chạy `pytest` sau mỗi patch | Speed + Verifier |
| `mypy` strict fail, `ruff` drift bundle | Clean Builder incremental `ignore_missing_imports`, `ruff format` + rebuild bundle `--check` | Clean + Speed |
| Over-polish thêm API L4 | Coordinator enforce L3 max, không thêm public API | Coordinator |

---

## 6. Approval Gate (BẮT BUỘC)

> **Bạn có Approve Team Plan Speed & Clean này không?**
> - Reply `yes` / `approve` / `go` để Coordinator launch team ngay.
> - Hoặc `modifications: ...` để điều chỉnh (ví dụ: chỉ cần speed, không cần clean; thêm `orjson` backend; đổi version `0.4.0`→`1.0.0`).

**Không proceed cho đến khi có explicit approval.**

---

## 7. Sau Approval — Cách Launch

- Coordinator spawn subagents qua `Task` (hoặc sequential) — mỗi subagent nhận role brief self-contained + artifact paths.
- Tiến độ cập nhật `TEAM_STATE.md`.
- Verification Loop non-negotiable trước khi synthesis.


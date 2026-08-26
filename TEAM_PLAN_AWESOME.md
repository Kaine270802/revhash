# TEAM PLAN — Làm revhash Tuyệt Vời Hơn Nữa (Polish v0.3)

> **Skill:** `e2e` + `teamwork-preview` — Coordinator-led team, inspired by Google Antigravity
> **Ngày:** 28-08-2026
> **Workspace:** `D:\data optimization`
> **Coordinator:** Muse Spark
> **Mode:** `FULL` / `L3 EXTEND` — cross-module polish, DX, docs, performance, không breaking API
> **Confidence:** `MEDIUM` — request vague "tuyệt vời hơn nữa", cần interpretation: polish toàn diện để library đạt production-grade awesome

---

## 1. Goal Summary (Một câu)

**Biến revhash hiện tại (v0.2.1-filetext: flexible file↔text, O1 streaming, bundle 101KB, nhưng đã clean tests) thành thư viện production-grade “tuyệt vời” — khôi phục test suite 150+ với coverage 90%+, bench & typecheck & lint CI, README/docs/examples polish, performance micro-opt, DX nhúng 1 dòng, và release chuẩn `pip` + `revhash_embedded.py` sync, được Verifier/Critic độc lập PASS.**

> **“Tuyệt vời” được cụ thể hóa:** Không thêm feature lớn mới, chỉ **polish** những gì đã có để đạt awesome: tests, docs, examples, benchmark, CI, type hints, CLI, error messages, và bundle.

### Success Criteria Tổng (Top-level) — Awesome Checklist

- [ ] **Tests khôi phục & nâng:** `tests/` 150+ cases (unit codec/header/stream/text/file_text, integration file↔text, fuzz 100, large 50MB O1) — `pytest tests -q` 150+ PASS, coverage ≥90% (nếu có `coverage`), không hardcode ratio, parity bundle vs pkg 10 cases byte-identical
- [ ] **Type & Lint:** `mypy src/revhash --ignore-missing-imports` hoặc `pyright` pass (hoặc ít nhất `ruff check` pass), `ruff format --check` pass, `python -m py_compile` pass
- [ ] **Benchmark & Perf:** `benchmarks/run_benchmark.py` 10KB/1MB/10MB/100MB 32× gzip giữ, `python -m revhash benchmark --size 100M` <10s encode, memory O1 <150MB cho 50MB stream (tracemalloc), không chậm >5% so v0.2.1
- [ ] **Docs polish:** `README.md` (quick start 5 ví dụ copy-paste file/text + CLI + benchmark table + limitations), `docs/api.md` + `docs/api_embedded.md` + `docs/api_filetext.md` không drift, `CHANGELOG.md` v0.1→v0.3, `examples/` 3 demos chạy `python examples/*.py` PASS
- [ ] **DX nhúng 1 dòng:** `pip install -e .` + `import revhash` + `cp revhash_embedded.py` → `import revhash_embedded as revhash` + `get_available_codecs()` fallback, `__version__` align `0.3.0-awesome` (bundle + pkg), `pyproject.toml` version bump + `python scripts/build_embedded.py --check` PASS
- [ ] **CLI polish:** `python -m revhash --help` 6 commands, `compress`/`decompress`/`info`/`verify`/`train-dict`/`benchmark` với messages rõ, `verify` Tamper detection 100% (decompress corrupt → `RevHashCorruptedError`)
- [ ] **Packaging chuẩn:** `pip install -e .` + `pip wheel` OK, `pyproject.toml` classifiers + `hatch` sdist includes, `LICENSE` MIT tồn tại, `revhash_embedded.py` <500KB (101KB hiện tại) + `__bundle_hash__` sync
- [ ] **Verifier + Critic độc lập PASS:** Không P0 blocker, không hardcode ratio, không silent utf-8 loss, không OOM `dst=None` guard, không bundle drift

---

## 2. Roles Table

| Role | Specialty | Owns | Inputs | Outputs | Success Criteria |
|------|-----------|------|--------|---------|------------------|
| **Coordinator / Orchestrator** | Quản lý team, tổng hợp | `TEAM_PLAN_AWESOME.md`, `TEAM_STATE.md`, `CHANGELOG.md`, `pyproject.toml` version bump, `README.md` patch, release `v0.3.0-awesome` | Yêu cầu user + Team Sheet + Evidence Brief | Team Sheet, milestones, final walkthrough, `docs/api` sync | All streams tích hợp, demo 1 dòng nhúng + file/text 6 cases + benchmark PASS, verification PASS |
| **Researcher / Explorer** | Prior-art awesome libs, polish checklist | Khảo sát awesome Python libs (requests, rich, pydantic), checklist polish | `src/revhash/*`, `README.md`, `pyproject.toml`, prior-art awesome libs | `docs/research_awesome.md` | Liệt kê ≥6 tiêu chí awesome (tests, type, lint, bench, docs, examples, CI, error msgs), so sánh 3 lib awesome, đề xuất polish list ưu tiên cho M3 builders |
| **Polish Builder** | Core polish, performance, type | `src/revhash/*.py` micro-opt, type hints, error msgs, `file_text.py` guard polish | `docs/research_awesome.md` + `src/revhash/*` | `src/revhash/*.py` patched (type hints, `__all__` align, `get_available_codecs` fallback polish), `revhash_embedded.py` rebuild | `mypy`/`ruff` pass, `compress_file`/`decompress_file` guards OOM strict (bytes+decompress header), `__version__` align, không regress 150+ |
| **Docs & Examples Builder** | Docs, README, examples, CLI | `README.md`, `docs/*.md`, `examples/*.py`, `CHANGELOG.md` | `docs/research_awesome.md` + `src/revhash/*` | `README.md` polish (5 ví dụ copy-paste), `examples/awesome_demo.py`, `CHANGELOG.md` v0.1→v0.3, CLI help polish | 5 ví dụ `README` copy-paste `python -c` PASS, `python examples/awesome_demo.py` PASS, `pyproject.toml` version `0.3.0` |
| **Verifier / QA** | Testing + benchmark + typecheck | Test suite, benchmark, typecheck, lint | Toàn bộ code + bundle + examples | `tests/` (restore 150+), `reports/verification_awesome.md`, `benchmarks/results_awesome.json` | 150+ PASS, coverage ≥80%, `mypy`/`ruff` PASS, `benchmark` 10MB 32× giữ, `build --check` PASS, `pytest` 150+ in 7s |
| **Critic / Auditor** | Adversarial, anti-cheat, security | Audit polish & awesome claims | Toàn bộ artifacts | `reports/critique_awesome.md` | Tìm ≥5 risks thực (hardcode awesome, missing coverage, type lie, benchmark inflate, bundle drift), đề xuất fix P0/P1 |

> **Team size: 6 (1 Coordinator + 5 Specialists)** — minimal sufficient cho polish cross-module: Researcher → 2 builders song song (Polish Core vs Docs/Examples) → Verifier + Critic song song. **Token/cost warning:** 2 builders + 2 verifiers song song peak 2x, tổng ước **100-150k tokens** (ít hơn v0.2 vì nhiều polish nhỏ). Offload sang file để tránh bloat context. Nếu cần tiết kiệm, gộp Polish+Docs thành 1 builder (giảm xuống 5 người).

**Adapted from `references/example-teams.md`:**
- Mẫu #3 Research+Implementation Pipeline → Researcher khảo sát awesome libs trước khi builders polish
- Mẫu #2 Systems Component → Polish Builder (core) + Docs Builder (DX) song song trên interface chung (`docs/api*.md`)
- Mẫu #1 Full-Stack Verifier/Critic → QA + Auditor độc lập cho awesome claims

---

## 3. Handoff Protocol (Shared Artifacts)

| Artifact | Owner ghi | Người đọc | Mô tả |
|----------|-----------|-----------|-------|
| `TEAM_PLAN_AWESOME.md` | Coordinator | All | Kế hoạch polish awesome này (frozen sau approve) |
| `TEAM_STATE.md` | Coordinator | All | Trạng thái milestones v0.1 + v0.2 + v0.2.1 + v0.3 (append `## [Role] — Update`) |
| `docs/research_awesome.md` | Researcher | Polish, Docs, Verifier | Checklist 6+ tiêu chí awesome + so sánh 3 lib + polish list ưu tiên |
| `src/revhash/*.py` (patch) | Polish Builder | Verifier, Critic | Core polish: type hints, `__version__` align, guards OOM polish, `get_available_codecs` |
| `revhash_embedded.py` (rebuild) | Polish Builder | Verifier | Bundle <500KB, `__bundle_hash__` sync, `<500KB` 101KB |
| `README.md` + `docs/api*.md` + `CHANGELOG.md` + `examples/awesome_demo.py` | Docs Builder | Verifier, User | Docs polish 5 ví dụ, changelog v0.1→v0.3, CLI help |
| `tests/` (restore 150+) | Verifier | Critic, Coordinator | `test_codec.py:35` ... `test_filetext_flex.py:12` + `test_embedded.py:18` |
| `reports/verification_awesome.md` | Verifier | Coordinator, Critic | 150+ PASS, `mypy`/`ruff`, `benchmark` 32×, `build --check` |
| `reports/critique_awesome.md` | Critic | Coordinator | Audit 5 risks + anti-cheat |

**Quy tắc:**
- Mỗi subagent nhận **role brief self-contained** (goal, Owns, Inputs, Outputs, Success Criteria + artifact paths) — không giả định thấy conversation này.
- Ghi file xong append `TEAM_STATE.md` với `## [Role] — Update YYYY-MM-DD HH:MM`.
- Không overlap ownership: Polish sở hữu `src/revhash/*.py` + bundle; Docs sở hữu `README.md` + `examples/`; Verifier sở hữu `tests/`; Critic chỉ đọc.
- Single responsibility: blocker >30min respawn.

---

## 4. Milestone Sequence & Parallel Tracks

```
M0: Plan Approval (GATE) ──► M1: Research awesome (0.5d) ──► M2: Design Freeze (polish checklist)
                                      │                        │
                                      └────────────────────────┼──► M3a: Polish Core Build (type, guards, version, bundle)
                                                               └──► M3b: Docs & Examples Build (README, CHANGELOG, awesome_demo)
                                                                       │            │
                                                                       └─────┬──────┘
                                                                             ▼
                                                                      M4: Integration — Tests restore + bundle parity + README demos
                                                                             │
                                                                             ▼
                                                                      M5: Verification Loop (Verifier + Critic song song, non-negotiable)
                                                                             │
                                                              ┌──────────────┴──────────────┐
                                                              │ Pass → M6: Synthesis & Handover v0.3-awesome
                                                              │ Fail → quay lại M3a/M3b với fix list
                                                              └─────────────────────────────┘
```

| Milestone | Tracks song song | Dependencies | Output Gate |
|-----------|------------------|--------------|-------------|
| **M0** | — | — | User approve `TEAM_PLAN_AWESOME.md` |
| **M1 Research** | Single | M0 | `docs/research_awesome.md` approved (≥6 tiêu chí awesome, 3 lib so sánh) |
| **M2 Design Freeze** | Coordinator+Researcher | M1 | Polish checklist frozen (type, guards, version, docs) |
| **M3a Polish Core** | **Song song M3b** | M2 | `src/revhash/*.py` patched + `revhash_embedded.py` rebuild (<500KB, `mypy` pass) |
| **M3b Docs & Examples** | **Song song M3a** | M2 | `README.md` polish + `examples/awesome_demo.py` + `CHANGELOG.md` 5 demos PASS |
| **M4 Integration** | Single (Coordinator) | M3a+M3b | `pytest tests -q` 150+ PASS, bundle parity, `build --check` PASS, `README` demos PASS |
| **M5 Verification** | Verifier & Critic **song song** | M4 | `reports/verification_awesome.md` 150+ PASS + type/lint + `reports/critique_awesome.md` PASS (không P0) |
| **M6 Handover** | Coordinator | M5 | Release `v0.3.0-awesome`, `README` 5 ví dụ, `CHANGELOG`, migration guide |

**Token/Cost Warning:** M3a+M3b song song + M5 Verifier+Critic song song peak 2x; tổng ước **100-150k tokens** cho polish FULL. Offload aggressively sang file; nếu host không support parallel subagents, run sequential focused sessions.

---

## 5. Risks & Mitigations

| Risk | Mitigation | Owner |
|------|------------|-------|
| Polish làm break 154 tests hiện tại (142+12) | Polish Builder chỉ tweak L1/L2 (5-20 lines), giữ backward compat; Verifier chạy `pytest` sau mỗi patch | Polish + Verifier |
| Type hints sai → `mypy` fail, bundle drift | Researcher chỉ rõ `src/revhash` type coverage hiện tại; Polish thêm hints incremental, không `strict` toàn bộ; `build --check` guard drift | Polish + Researcher |
| Docs/examples drift vs code (ví dụ copy-paste không chạy) | Docs Builder test từng snippet `python -c` + `python examples/awesome_demo.py` PASS trước khi commit | Docs + Verifier |
| Benchmark inflate (hardcode ratio 32×) | Critic check `grep ratio hardcode` 0, `benchmarks/results.json` recompute; Verifier chạy `run_benchmark.py` thực | Critic + Verifier |
| Over-polish (thêm feature lớn, L4) | Coordinator enforce L3 EXTEND max, `TEAM_PLAN_FILETEXT` contract giữ, không thêm public API mới ngoài polish | Coordinator |

---

## 6. Approval Gate (BẮT BUỘC)

> **Bạn có Approve Team Plan Awesome này không?**
> - Reply `yes` / `approve` / `go` để Coordinator launch team ngay.
> - Hoặc `modifications: ...` để điều chỉnh (ví dụ: không cần `mypy`, chỉ cần README polish; thêm CI `GitHub Actions`; đổi version `0.3.0` → `1.0.0`; v.v.)

**Không proceed cho đến khi có explicit approval.**

---

## 7. Sau Approval — Cách Launch

- Coordinator spawn subagents qua `Task` (hoặc simulate sequential) — mỗi subagent nhận role brief self-contained + artifact paths.
- Tiến độ cập nhật `TEAM_STATE.md` (append `## [Role] — Update ...`).
- Verification Loop non-negotiable trước khi synthesis; Critic phải tìm ≥5 risks thực.


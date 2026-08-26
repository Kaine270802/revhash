# TEAM PLAN — revhash v0.5: Decompress Performance + Header Integrity + CI

> **Skill:** `teamwork-preview` — Coordinator-led Agent Team
> **Ngày:** 28-08-2026
> **Workspace:** `D:\data optimization`
> **Coordinator:** Muse Spark
> **Base:** v0.4.0 (commit `fde360c`, 155 tests PASS, bundle `102337B` hash `54400620...`)
> **Nguồn:** Đánh giá có bằng chứng đo thực tế (không phải suy đoán) — xem §1.1

---

## 1. Goal Summary (một câu)

**Sửa 3 điểm yếu đã được đo bằng chứng của revhash v0.4.0 — (1) decompress chậm hơn zstd thuần 10× do buffer copy 3 lần khi tính CRC, (2) `verify()` không phủ header nên tamper `chunk_size`/`level` vẫn trả `True`, (3) không có CI/coverage nên mọi tuyên bố chất lượng đều thủ công — thành v0.5.0 với decompress ≥800 MB/s, header được xác thực (format v2 tương thích ngược đọc v1), và CI GitHub Actions đo coverage thật.**

### 1.1 Bằng chứng khởi tạo (đã đo, không phải giả định)

| Vấn đề | Đo thực tế | Vị trí |
|---|---|---|
| Decompress chậm 10× | `raw zstd 2388 MB/s` vs `revhash 241 MB/s` | `src/revhash/stream.py:876-889` `_proc` |
| Triple copy | `pending.extend` + `bytes(pending[:n])` + `del pending[:n]` | `stream.py:883-888` |
| Header tamper bypass | `chunk_size 1M→4M: verify=True`, `level 3→22: verify=True` | `header.py:150` + `stream.py` SHA chỉ phủ payload |
| Không CI | `.github/`, `tox.ini`, `.pre-commit-config.yaml` đều **không tồn tại** | root |
| Coverage chưa từng đo | `import coverage` → `ModuleNotFoundError` | — |
| Type safety yếu hơn vẻ ngoài | **75** `type: ignore` + 5 mã mypy bị tắt + `ignore_errors` cho `algorithms` | `pyproject.toml:58` |

### 1.2 Success Criteria

- [ ] **Decompress ≥800 MB/s** trên 10MB text_repeat (hiện 241) — đo **cold** (data object mới mỗi lần), median 5 lần
- [ ] **CRC per-chunk vẫn đúng byte-for-byte** — output byte-identical, tamper detection giữ 100%, không dùng buffer `pending`
- [ ] **Header được xác thực:** tamper `chunk_size`/`level`/`codec_id` → `verify()` trả `False`; test hồi quy cho từng field
- [ ] **Tương thích ngược:** blob v0.4 (header version 1) vẫn `decompress` + `verify` được bằng v0.5; blob mới ghi version 2
- [ ] **CI xanh:** `.github/workflows/ci.yml` chạy `pytest` + `ruff` + `mypy` + `build --check` trên Python 3.9/3.11/3.12
- [ ] **Coverage đo thật:** `pytest --cov=revhash --cov-report=term` có số liệu, ngưỡng `--cov-fail-under` đặt theo số đo thực (không bịa)
- [ ] **Không hồi quy:** 155 tests + N tests mới đều PASS, ratio 32.5× giữ, compress ≥850 MB/s, bundle `<500KB`, `pip wheel` PEP440

---

## 2. Roles Table

| Role | Specialty | Owns (ghi) | Inputs | Outputs | Success Criteria |
|------|-----------|------------|--------|---------|------------------|
| **Coordinator** | Điều phối, tổng hợp, quyết định phạm vi | `TEAM_PLAN_V05.md`, `TEAM_STATE.md`, `docs/api_v05.md`, `CHANGELOG.md`, `README.md`, version bump | Đánh giá §1.1 + output các role | Team Sheet, Design Freeze, tích hợp, bàn giao | Mọi track hợp nhất, không chồng lấn ownership, Verifier+Critic PASS trước khi tuyên bố |
| **Researcher / Explorer** *(read-only)* | Format migration + phương pháp đo | `docs/research_v05.md` **duy nhất** | `header.py`, `stream.py` parse paths, `tests/test_header.py`, lịch sử `reports/critique_*.md` | `docs/research_v05.md` | Đề xuất ≥2 phương án header v2 (dual-read vs strict) có phân tích tương thích; định nghĩa quy trình đo **cold** chống lặp lại lỗi warm-cache của v0.4 |
| **Core Stream Builder** | Hot path + binary format | `src/revhash/stream.py`, `src/revhash/header.py` | `docs/research_v05.md`, `docs/api_v05.md` | CRC lũy tiến (bỏ `pending`), header vào SHA + version 2, dual-read v1/v2 | Decompress ≥800 MB/s cold; tamper header phát hiện 100%; blob v1 vẫn đọc được; 155 tests PASS |
| **Infra Builder** | CI/CD, tooling, coverage | `.github/workflows/`, `tox.ini`, `.pre-commit-config.yaml`, `pyproject.toml` (mục `[tool.coverage]`/deps dev) | `pyproject.toml` hiện tại, `tests/` | CI matrix 3.9/3.11/3.12, coverage report, pre-commit | CI chạy xanh local (`act` hoặc mô phỏng lệnh); `pytest --cov` ra số thật; **không** đụng `src/revhash/*` |
| **Verifier / QA** | Kiểm chứng độc lập | `tests/test_header_mac.py`, `tests/test_decompress_perf.py`, `reports/verification_v05.md`, `benchmarks/results_v05.json` | Toàn bộ code sau M4 | Test hồi quy + số đo cold + bảng PASS/FAIL | Ghi **exact cwd + command + exit code + hash**; đo cold median 5 lần; không sửa `src/revhash/*` |
| **Critic / Auditor** | Đối kháng, chống nguỵ tạo | `reports/critique_v05.md` **duy nhất** | Toàn bộ artifacts | Audit ≥5 rủi ro thật kèm `python -c` tái hiện | Thách thức kết quả Verifier; kiểm CRC lũy tiến có sai lệch biên chunk không; kiểm benchmark có warm-cache artifact không; **không được sửa** |

> **Team size: 6 (1 Coordinator + 5 specialists)** — đúng khuyến nghị 3–6.

### 2.1 Vì sao chỉ 2 builder song song (không phải 4)

Ba hạng mục P0/P1 về code (CRC, header MAC, refactor) **đều ghi vào `stream.py`** → nếu tách 3 builder sẽ xung đột ownership. Theo quy tắc "một writer tại một thời điểm cho mỗi path", gộp thành **Core Stream Builder** làm tuần tự nội bộ. Chỉ `Infra Builder` có path rời rạc hoàn toàn (`.github/`, `tox.ini`) nên chạy song song an toàn.

### 2.2 Adapt từ `references/example-teams.md`

- Mẫu **#2 Systems/Low-Level Component** → Core Stream Builder (binary format + hot path, giống Scheduler/Allocator Worker nhưng gộp vì chung file)
- Mẫu **#3 Research + Implementation** → Researcher khảo sát format migration trước khi code
- Mẫu **#1 Full-Stack** → cặp Verifier + Critic độc lập chạy sau tích hợp

---

## 3. Handoff Protocol

| Artifact | Owner ghi | Người đọc | Nội dung |
|---|---|---|---|
| `TEAM_PLAN_V05.md` | Coordinator | All | Kế hoạch này (đóng băng sau approve) |
| `TEAM_STATE.md` | Coordinator + mọi role (append) | All | Mỗi role append `## [Role] — Update YYYY-MM-DD` |
| `docs/research_v05.md` | Researcher | Core Stream, Coordinator | Phương án header v2 + quy trình đo cold |
| `docs/api_v05.md` | Coordinator | Core Stream, Verifier | **Design Freeze**: spec header v2, thuật toán CRC lũy tiến, contract dual-read |
| `src/revhash/stream.py`, `header.py` | **Core Stream Builder** (độc quyền) | Verifier, Critic | Code |
| `.github/workflows/ci.yml`, `tox.ini`, `.pre-commit-config.yaml`, `pyproject.toml` | **Infra Builder** (độc quyền) | Verifier | CI |
| `tests/test_header_mac.py`, `tests/test_decompress_perf.py` | **Verifier** (độc quyền) | Critic | Test mới |
| `reports/verification_v05.md`, `benchmarks/results_v05.json` | Verifier | Critic, Coordinator | Bằng chứng |
| `reports/critique_v05.md` | Critic | Coordinator | Audit |
| `revhash_embedded.py` | **Coordinator** (chỉ ở M4, sau khi builder đóng) | Verifier | Bundle rebuild |

**Quy tắc bắt buộc:**
- Mỗi specialist nhận **role brief tự chứa** (goal, Owns, Inputs, Outputs, Success Criteria, đường dẫn artifact) — không giả định thấy hội thoại này.
- `pyproject.toml` do **Infra Builder** sở hữu; Core Stream Builder cần đổi gì trong đó phải **dừng và báo Coordinator**.
- `revhash_embedded.py` **không builder nào** được rebuild — chỉ Coordinator ở M4, tránh drift hash.
- Blocker >30 phút → Coordinator re-dispatch hoặc respawn role.

---

## 4. Milestones & Parallel Tracks

```
M0 Approval (GATE)
   │
   ▼
M1 Research (read-only, ~0.5d) ── docs/research_v05.md
   │
   ▼
M2 Design Freeze (Coordinator) ── docs/api_v05.md  [header v2 spec + CRC algo]
   │
   ├──────────────────────────────┬──────────────────────────────┐
   ▼                              ▼                              │
M3a Core Stream Builder      M3b Infra Builder            (SONG SONG —
   (tuần tự nội bộ:)            (.github/, tox.ini,        Owns rời rạc)
   1. CRC lũy tiến              pyproject dev deps,
   2. Header vào SHA + v2       coverage config)
   3. Dual-read v1/v2
   4. (tuỳ chọn) tách
      _decompress_core
   │                              │
   └──────────────┬───────────────┘
                  ▼
        M4 Integration (Coordinator)
        rebuild bundle + full suite + README/CHANGELOG
                  ▼
        M5 Verification Loop  ── Verifier ∥ Critic (SONG SONG, bắt buộc)
                  │
        ┌─────────┴─────────┐
        │ PASS → M6 Handover v0.5.0
        │ FAIL → quay lại M3a/M3b với fix list, chạy lại M5
        └───────────────────┘
```

| Milestone | Track | Phụ thuộc | Output Gate |
|---|---|---|---|
| **M0** | — | — | User approve |
| **M1** | Single (read-only) | M0 | `docs/research_v05.md`: ≥2 phương án header v2 + quy trình đo cold |
| **M2** | Coordinator | M1 | `docs/api_v05.md` đóng băng: header v2 layout, CRC lũy tiến pseudocode, dual-read contract |
| **M3a** | **∥ M3b** | M2 | Decompress ≥800 MB/s cold; header tamper → `verify=False`; blob v1 đọc được; 155 PASS |
| **M3b** | **∥ M3a** | M2 | CI yml hợp lệ; `pytest --cov` ra số; không chạm `src/revhash/*` |
| **M4** | Coordinator | M3a + M3b | Bundle rebuild `<500KB`; toàn bộ suite PASS; docs sync version |
| **M5** | Verifier **∥** Critic | M4 | 2 báo cáo, không P0 tồn đọng |
| **M6** | Coordinator | M5 | Release `v0.5.0` + walkthrough + rủi ro còn lại |

---

## 5. Risks & Mitigations

| Risk | Mức | Mitigation | Owner |
|---|---|---|---|
| CRC lũy tiến sai ở **biên chunk** → checksum sai âm thầm | **CRITICAL** | Test đối chiếu CRC cũ vs mới trên data không chia hết chunk (4M+123, 1B, 0B); Critic tái hiện độc lập | Core Stream + Critic |
| Header v2 phá blob v0.4 hiện có | **HIGH** | Dual-read bắt buộc: version 1 → verify payload-only (hành vi cũ), version 2 → verify header+payload; test blob v1 lưu sẵn | Researcher + Core Stream |
| Benchmark lặp lại **warm-cache artifact** như v0.4 | **HIGH** | Researcher định nghĩa quy trình cold (data object mới mỗi lần, median 5, không warm-up); Critic bắt buộc tái đo độc lập | Researcher + Critic |
| Hai builder cùng chạm `pyproject.toml` | MEDIUM | Infra Builder sở hữu độc quyền; Core Stream phải dừng + báo Coordinator | Coordinator |
| Bundle hash drift do rebuild nhiều nơi | MEDIUM | Chỉ Coordinator rebuild ở M4 | Coordinator |
| Refactor `_decompress_core` làm hỏng luồng non-seekable | MEDIUM | Đặt là **tuỳ chọn cuối** trong M3a; bỏ nếu M5 gần deadline | Core Stream |
| Coverage thấp hơn kỳ vọng → tuyên bố sai | LOW | Đặt `--cov-fail-under` **theo số đo thực**, không đặt trước | Infra + Verifier |

---

## 6. Token / Cost Warning

- M3a ∥ M3b: **~2× peak token** so với tuần tự.
- M5 Verifier ∥ Critic: bắt buộc, thêm ~2× ở giai đoạn kiểm chứng.
- **Ước tính tổng: 110.000–160.000 tokens** cho đủ 6 milestone.
- Giảm chi phí nếu cần: bỏ Researcher (Coordinator tự freeze từ §1.1) → còn 5 role, tiết kiệm ~20k; hoặc hoãn refactor `_decompress_core` sang v0.6.

---

## 7. Phạm vi loại trừ (Out of scope v0.5)

- Không thêm codec mới, không đổi public API (`__all__` giữ 15)
- Không tối ưu compress (đã 885/977 MB/s, đạt gate)
- Không xử lý non-seekable pipe >100MB (cần thêm field `compressed_len` — để v0.6)
- Không viết lại `cli.py` / `selector.py`

---

## 8. Approval Gate (BẮT BUỘC)

> **Approve team plan này? Trả lời `yes` / `approve` / `go`, hoặc đưa modifications.**
>
> Gợi ý các điều chỉnh bạn có thể muốn:
> - `modifications: bỏ header v2` → chỉ làm perf + CI, không đổi format (rủi ro thấp nhất)
> - `modifications: bỏ Researcher` → 5 role, Coordinator tự freeze
> - `modifications: thêm refactor bắt buộc` → nâng `_decompress_core` từ tuỳ chọn lên P0

**Sẽ không khởi chạy specialist nào cho đến khi có approve rõ ràng.**

---

*— Coordinator, 2026-08-28 — Team Sheet lập theo `teamwork-preview`, adapt từ `references/example-teams.md` mẫu #1/#2/#3.*

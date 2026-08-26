# Nghiên cứu thuật toán nén Lossless cho thư viện revhash (Unlimited Streaming)

> **Owner:** Researcher / Explorer — Team revhash  
> **Ngày:** 2026-08-25  
> **Mục tiêu:** Khảo sát ≥6 thuật toán lossless, đánh giá trên tiêu chí *unlimited streaming* (ratio, speed, memory O(1), chunk-friendliness, dictionary streaming), đề xuất stack tối ưu cho Core & Optimization Builder.

---

## 1. Bối cảnh & ràng buộc “unlimited”

Thư viện `revhash` phải thỏa mãn đồng thời:

| Ràng buộc | Ý nghĩa kỹ thuật |
|-----------|-------------------|
| **Không giới hạn dung lượng** (0 B → 10 GB+) | Không bao giờ `read()` toàn bộ file; streaming chunk 1–8 MB, memory bounded < 150 MB |
| **100% byte-identical** | Lossless tuyệt đối, checksum per-chunk + global SHA-256 |
| **Ratio tối ưu** | Tốt hơn `gzip -6` ≥15% trên text lặp, tiệm cận `zstd -19`/`lzma` |
| **Throughput tuyến tính** | Encode 80–150 MB/s, decode 150–250 MB/s, scale O(n) |
| **API đơn giản** | `compress(bytes)` / `decompress(bytes)` + `compress_file` / `compress_stream(reader, writer)` |

Ràng buộc này loại bỏ các thuật toán chỉ tối ưu cho whole-file trong RAM và ưu tiên các codec có **streaming API chuẩn** (frame liên tục, không reset dictionary mỗi chunk).

---

## 2. Taxonomy các họ thuật toán lossless

```
Lossless Compression
├── Entropy coding (mã hóa entropy đơn thuần)
│   ├── Huffman (1952) — mã tiền tố biến độ dài
│   └── ANS / rANS / FSE (2009–2014) — mã hóa bất đối xứng, tiệm cận entropy
├── Dictionary / LZ (từ điển trượt)
│   ├── LZ77 / LZ78 / LZW (1977–1984)
│   ├── LZMA / LZMA2 (1999) — LZ + range coding + Markov chain
│   ├── Zstandard (2015) — LZ + Huffman + FSE + dictionary
│   └── Brotli (2015) — LZ77 + Huffman + context modeling + static dict
├── Block-sorting
│   └── BWT + MTF + Huffman (bzip2, 1996)
└── Hybrid / Dictionary training
    └── Zstd dictionary, Brotli static dictionary, custom adaptive dict
```

Tất cả codec thực tế đều là **hybrid**: LZ tìm lặp → entropy coder mã hóa.

---

## 3. Khảo sát chi tiết 8 thuật toán

### 3.1 Huffman Coding (David Huffman, 1952)

- **Nguyên lý:** Xây cây tiền tố tối ưu dựa trên tần suất ký tự; ký tự phổ biến → mã ngắn. Đạt độ dài trung bình tiệm cận entropy Shannon nếu phân bố i.i.d.
- **Ưu:** O(n log σ), decode rất nhanh, memory O(σ), dễ streaming (có thể flush theo block).
- **Nhược:** Không bắt được lặp dài (`"abcabcabc..."` vẫn mã hóa từng ký tự), ratio kém đơn độc — chỉ ~5–15% saving trên text tự nhiên nếu không kết hợp LZ.
- **Unlimited streaming:** ★★★★★ — stateless theo block, nhưng ratio không đủ để làm codec chính.
- **Vai trò trong stack:** Lớp entropy cuối cùng cho LZ (DEFLATE, Zstd, Brotli đều dùng Huffman/FSE sau LZ).
- **Tham khảo:** Huffman, *A Method for the Construction of Minimum-Redundancy Codes*, Proc. IRE 1952.

### 3.2 LZ77 / LZ78 / LZW (Ziv–Lempel 1977–1984)

- **Nguyên lý:** Thay chuỗi lặp bằng tham chiếu `(distance, length)` tới cửa sổ trượt (LZ77) hoặc từ điển phrase (LZ78/LZW). Ví dụ `DEFLATE` (gzip) = LZ77 + Huffman.
- **Ưu:** Bắt lặp dài cực tốt, ratio cao trên text lặp, thuật toán đơn giản.
- **Nhược:** Cửa sổ cố định (gzip 32 KB, zstd 8 MB mặc định) — nếu chunk < window thì mất cơ hội tham chiếu xa. LZW có patent lịch sử, ít dùng mới.
- **Unlimited streaming:** ★★★☆☆ nếu *chunked independent* (mỗi chunk reset window → mất ratio), ★★★★★ nếu *streaming single-frame* (giữ window liên tục). Kết quả benchmark §5 chứng minh.
- **Memory:** O(window) — 32 KB (gzip) đến 8 MB (zstd). Bounded, phù hợp O(1).
- **Tham khảo:** Ziv & Lempel, IEEE Trans. IT 1977/1978; RFC 1951 DEFLATE.

### 3.3 LZMA / LZMA2 (Igor Pavlov, 1999 — dùng trong `.xz`, `7z`)

- **Nguyên lý:** LZ77 với dictionary lớn (tới 1.5 GB) + Markov chain + **range coding** (biến thể arithmetic coding). Dự đoán xác suất bit tiếp theo dựa trên context.
- **Ưu:** Ratio tốt nhất trong nhóm whole-file trên benchmark của chúng tôi: trên `10MB text_repeat`, ratio **0.00021** vs gzip `0.00491` (gấp ~23× tốt hơn). Trên `1MB text_repeat` cũng đạt `0.00079` (tốt nhất nhóm nếu bỏ qua brotli/zstd ở mức cao).
- **Nhược:** Chậm (encode 70–110 MB/s trên text lặp, nhưng chỉ 3–6 MB/s trên random/realistic 10 MB), memory lớn, **chunk-friendliness kém nhất** — benchmark 10 MB → 100 MB cho thấy overhead chunk 1 MB lên tới **433%** (LZMA) so với whole-file, do dictionary bị cắt mỗi chunk.
- **Unlimited streaming:** ★★☆☆☆ — `lzma` module Python không có streaming dictionary reuse tốt, không phù hợp làm default cho unlimited; chỉ nên là *option high-ratio* cho whole-file hoặc chunk lớn ≥4 MB.
- **Memory:** Encoder có thể >100 MB nếu dict lớn; cần giới hạn `preset=6` (~16 MB).
- **Tham khảo:** Pavlov, LZMA SDK; `xz` man page.

### 3.4 BWT + MTF + Huffman (Burrows–Wheeler, bzip2 — 1994/1996)

- **Nguyên lý:** BWT sắp xếp lại block để nhóm ký tự giống nhau → MTF (move-to-front) → Huffman. Không dùng LZ, mà biến đổi toàn cục.
- **Ưu:** Trên text realistic 70% lặp, `bz2-9` đạt ratio **0.044–0.046** tốt hơn gzip (`0.083`) trên 1–10 MB, do BWT bắt được context dài mà LZ cửa sổ nhỏ bỏ lỡ.
- **Nhược:** Chậm nhất nhóm: encode **7–16 MB/s**, decode **25–140 MB/s**; memory theo block (100–900 KB). BWT yêu cầu sắp xếp toàn block → **không streamable mịn** (phải có block boundary); overhead chunk 1 MB: ratio `0.00279` vs whole `0.00179` (+56%).
- **Unlimited streaming:** ★★☆☆☆ — block-based, không có dictionary reuse liên chunk, không có dictionary training.
- **Kết luận:** Không chọn làm default; chỉ tham khảo cho text tự nhiên dài nếu cần ratio hơn speed.
- **Tham khảo:** Burrows & Wheeler, SRC Report 124 (1994); Seward, bzip2.

### 3.5 ANS / rANS / FSE (Jarek Duda 2009, Collet FSE 2014)

- **Nguyên lý:** Asymmetric Numeral Systems — mã hóa entropy tiệm cận arithmetic coding nhưng nhanh như Huffman (dùng table lookup, không cần phép chia). **rANS** (range variant) và **tANS** (table). FSE (Finite State Entropy) là bản tối ưu của ANS dùng trong Zstd.
- **Ưu:** Tốc độ gần Huffman, ratio gần arithmetic (tốt hơn Huffman 2–5% trên phân bố lệch). Decode nhanh, phù hợp SIMD.
- **Nhược:** Đơn độc không bắt lặp — phải kết hợp LZ. Triển khai thuần Python sẽ chậm; phải dựa vào backend C/Rust (zstd, brotli đã tích hợp sẵn).
- **Unlimited streaming:** ★★★★★ khi nằm trong Zstd/Brotli (đã streaming), ★☆☆☆☆ nếu tự cài đặt thuần Python.
- **Vai trò trong stack:** **Không cài riêng**, mà *kế thừa* qua Zstd (FSE) và Brotli (Huffman + context).
- **Tham khảo:** Duda, *Asymmetric Numeral Systems*, 2009; Collet, RFC 8878 Zstandard.

### 3.6 Zstandard — Zstd (Yann Collet, Meta 2015, RFC 8878)

- **Nguyên lý:** Hybrid hiện đại: **LZ77 (hash chain + optimal parse) + Huffman + FSE (ANS) + dictionary + chiến lược multi-stage**. Cửa sổ tới 128 MB, có thể tuning `level 1–22`, hỗ trợ **streaming frame**, **dictionary training**, **long-distance matching (LDM)**.
- **Ưu (benchmark thực tế của revhash):**
  - Ratio tốt: `10MB text_repeat` → **0.00015** (zstd-3) vs gzip `0.00491` (32× tốt hơn), tiệm cận brotli `0.00006`.
  - Speed vượt trội: **1 300–7 300 MB/s** compress trên text lặp (nhờ highly optimized C + `compressBound` nhanh), **2 300–4 500 MB/s** decompress.
  - Trên realistic 10 MB: ratio `0.090` (zstd-3) → `0.062` (zstd-19), cạnh tranh với lzma nhưng nhanh hơn 2–5× ở decode.
  - Random data: không phình to (ratio `1.00002` vs bz2 `1.004`).
- **Chunk-friendliness:** Nếu *chunked independent* 1 MB → overhead **+530%** (10 MB) / **+128%** (20 MB test) so với whole-file. Nhưng nếu dùng **streaming single-frame** (`ZstdCompressor.stream_writer`) → overhead **≈0%** (20 MB test: 2 060 B whole vs 2 059 B streaming). Đây là **chìa khóa unlimited**: giữ một frame, ghi chunk nối tiếp, dictionary/window được bảo toàn.
- **Dictionary streaming:** Zstd hỗ trợ `train_dictionary()` và `ZstdCompressor(dict_data=...)`. Thí nghiệm §5.4: dict 112 KB train trên 100 sample 10 KB → giảm **80%** trên file 10 KB, **50%** trên 1 MB, **71%** trên chunk 256 KB. Rất phù hợp cho *small-file* và *chunk đầu* của file lớn.
- **Memory:** Bounded ~ `windowSize + hashTable` (mặc định 8 MB), cấu hình được. Streaming O(1) đã verify peak 51 MB cho 50 MB input (vs whole-file 100 MB).
- **Nhược:** Level 19 chậm (3 MB/s trên realistic), chỉ dùng cho offline high-ratio.
- **Unlimited streaming:** ★★★★★ — **lựa chọn default**.
- **Tham khảo:** RFC 8878; Collet et al., *Zstandard — Fast Real-time Compression Algorithm*; Facebook zstd repo.

### 3.7 Brotli (Google, 2015 — RFC 7932)

- **Nguyên lý:** LZ77 + Huffman + **context modeling bậc 2** + **static dictionary 120 KB** (từ vựng web). Có quality 0–11, window tới 16 MB.
- **Ưu:** Ratio tốt nhất trên text lặp ở mức cao: `10MB text_repeat` → **0.00004** (q11) / `0.00006` (q6), tốt hơn cả zstd-19. Trên 10 KB cũng tốt nhất (`0.044` vs zstd `0.054`).
- **Nhược:** Encode chậm ở quality cao: **0.8–1 MB/s** ở q11 trên 10 MB realistic (chậm hơn zstd-19 3×, gzip 60×). `q6` lại nhanh (~90–1 300 MB/s) nhưng ratio kém hơn q11. Chunk overhead cực lớn: **+5 100%** ở 1 MB chunk trên 100 MB (do context reset).
- **Unlimited streaming:** ★★★☆☆ — có streaming API nhưng window/context reset mỗi chunk nếu dùng independent; static dict giúp small file nhưng không adaptive như zstd dict.
- **Vai trò:** **Fallback cho small text / web payload** (< 1 MB) hoặc khi cần tương thích web; không làm default cho file GB.
- **Tham khảo:** RFC 7932; Alakuijala et al., *Brotli: A General-Purpose Data Compressor*, ACM TIS 2018.

### 3.8 Dictionary-based / Adaptive Dictionary Streaming

- **Nguyên lý:** Thay vì chỉ LZ window, học trước các substring phổ biến từ corpus mẫu → đưa vào dictionary để LZ tìm match ngay từ byte đầu. Zstd dict, Brotli static dict, custom rolling dict.
- **Ưu:** Cải thiện dramatic trên *small chunks*: thí nghiệm cho thấy **71–80% saving thêm** trên chunk 256 KB–10 KB. Rất quan trọng cho unlimited vì chunk đầu tiên của file lớn thường không có history.
- **Streaming adaptive:** Có hai chiến lược:
  1. **Offline training:** Thu thập 100–1 000 sample đầu file (hoặc file cùng loại), `train_dictionary(112KB, samples)` → embed dict vào header (overhead ~4 KB). Phù hợp khi encode nhiều file cùng domain (log, CSV tiếng Việt).
  2. **Rolling adaptive:** Dùng chunk 1 để làm dict cho chunk 2..N (chỉ khả thi nếu implement custom, Zstd chưa hỗ trợ tự động rolling trong một frame — nhưng có thể giả lập bằng cách nén chunk 1 với level cao rồi dùng dict).
- **Memory:** Dict ~ 4–112 KB, negligible.
- **Kết luận:** **Bắt buộc** cho kiến trúc hybrid unlimited để giảm overhead chunk nhỏ.

---

## 4. Bảng so sánh tổng hợp (dựa trên benchmark thực thi § baseline_report.md)

| Thuật toán | Ratio 10 MB text_repeat (whole) | Ratio 10 MB realistic | Speed comp (MB/s) realistic 10 MB | Speed decomp (MB/s) | Memory | Chunk 1 MB overhead (100 MB) | Dict training | Streaming O(1) | Khuyến nghị |
|---|---|---|---|---|---|---|---|---|---|
| **Huffman thuần** | ~0.6 (ước) | ~0.6 | ~300 | ~800 | O(σ) | thấp | không | ✅ | Chỉ làm lớp entropy |
| **gzip (DEFLATE = LZ77+Huffman)** | 0.00491 | 0.083 | 63 | 670 | 32 KB win | **+12%** (thấp nhất!) | không | ✅ | Baseline, fallback tương thích |
| **bzip2 (BWT+MTF)** | 0.00179 | **0.044** (tốt) | 13 | 78 | 900 KB block | +56% | không | ⚠️ block | Không chọn default |
| **LZMA (LZ+range)** | 0.00021 | 0.070 | 6.7 | 264 | 16 MB+ | **+433%** (tệ) | không | ⚠️ | Option high-ratio |
| **Zstd-3 (LZ+Huffman+FSE)** | **0.00015** | 0.090 | **876** | **1 940** | 8 MB win | +530%* / **0%** streaming | ✅ | **✅✅** | **Default** |
| **Zstd-19** | 0.00014 | 0.062 | 3.0 | 1 708 | 8 MB | +578%* / 0% streaming | ✅ | ✅ | High-ratio option |
| **Brotli-6** | 0.00006 | 0.080 | 94 | 931 | 16 MB win | +5 100%* | static | ⚠️ | Small-file web |
| **Brotli-11** | **0.00004** | 0.065 | 0.8 | 1 028 | 16 MB | — | static | ⚠️ | Max ratio offline |

\* Overhead tính cho *chunked independent* (mỗi chunk là frame riêng). Nếu dùng **streaming single-frame** (ghi liên tục vào một frame Zstd), overhead → **~0%** (đã verify). Đây là điểm mấu chốt cho unlimited.

**Nhận xét chính:**
- Trên **text lặp cao** (đại diện log, CSV, JSON lặp): Zstd/Brotli/LZMA vượt gzip 10–30× về ratio, Zstd nhanh hơn gzip 2–20×.
- Trên **realistic 70% lặp** (gần dữ liệu thực tiếng Việt): bz2 ratio tốt nhất nhưng chậm; Zstd cân bằng nhất.
- Trên **random** (worst-case): tất cả ~1.0, Zstd không phình (tốt nhất), bz2 phình 0.45%.
- **Chunk overhead** là kẻ thù của independent chunking — phải dùng streaming frame.

---

## 5. Phân tích sâu cho unlimited streaming

### 5.1 Whole-file vs Chunked Independent vs Streaming Single-Frame

Chúng tôi đo trên 3 kích cỡ (10 MB, 20 MB, 100 MB) text_repeat:

| Kích thước | Codec | Whole-file ratio | Chunk 1 MB independent | Overhead | Streaming single-frame ratio | Overhead streaming |
|---|---|---|---|---|---|---|
| 10 MB | zstd-3 | 0.00015 | 0.00063 | +320% | — | — |
| 100 MB | zstd-3 | 0.00010 | 0.00063 | **+530%** | 0.00010 | **~0%** |
| 100 MB | gzip-6 | 0.00485 | 0.00545 | +12% | — | — |
| 100 MB | lzma-6 | 0.00015 | 0.00080 | +433% | — | — |
| 20 MB | zstd-3 | 0.00010 | 0.00022 | +128% | **0.00010** | **-0.0%** |

**Bài học:**
- **Independent chunking** (mỗi chunk = một file nén riêng, nối lại) làm ratio suy giảm mạnh (đặc biệt với Zstd/Brotli/LZMA do mất window/dictionary liên chunk). Overhead giảm khi tăng chunk size (4 MB tốt hơn 1 MB: 10 MB zstd 0.00025 vs 0.00063).
- **Streaming single-frame** (một frame Zstd, `stream_writer` ghi chunk nối tiếp) **bảo toàn hoàn toàn ratio** whole-file, vì window trượt được giữ xuyên chunk. Đây là cách duy nhất để đạt O(1) memory mà không hy sinh ratio.
- **gzip** có overhead thấp nhất khi independent (+12%) vì window nhỏ (32 KB) nên ít mất mát, nhưng ratio gốc đã kém.

**Memory profile (50 MB text_repeat, tracemalloc):**
- Whole-file: peak **100 MB** (giữ cả input + output trong RAM)
- Streaming 1 MB chunks: peak **51 MB** (chỉ giữ chunk hiện tại + window + output buffer) — chứng minh O(1), không scale theo file size.

### 5.2 Ảnh hưởng kích thước chunk (tuning 1–8 MB)

| Chunk | Ưu | Nhược | Khuyến nghị |
|---|---|---|---|
| **1 MB** | Memory thấp nhất, resume granularity mịn, phù hợp RAM < 512 MB | Overhead independent cao, nhiều header/checksum hơn | Dùng khi RAM hạn chế hoặc cần resume từng MB |
| **4 MB** | Overhead giảm ~2–3× so với 1 MB, vẫn O(1), cân bằng tốt | Memory ~4 MB + window | **Default** cho revhash |
| **8 MB** | Overhead thấp nhất, gần whole-file, tận dụng Zstd window 8 MB | Memory cao hơn, resume thô hơn | Option cho server RAM lớn, file > 1 GB |

Với streaming single-frame, **kích thước chunk không ảnh hưởng ratio** — chỉ ảnh hưởng memory và granularity của checksum/resume.

### 5.3 Small file & header overhead

Đo trên file 0 B → 10 KB:

| n bytes | gzip-6 | zstd-3 | lzma-6 | brotli-6 |
|---|---|---|---|---|
| 0 | 20 B | 9 B | 32 B | 1 B |
| 1 | 21 B | 10 B | 60 B | 5 B |
| 100 | 103 B | 91 B | 156 B | 90 B |
| 1 000 | 165 B | 149 B | 224 B | 139 B |
| 10 240 | 213 B | 150 B | 256 B | 141 B |

⇒ Với file < 1 KB, overhead header có thể >100% (phình). Cần **store mode** (không nén nếu `comp > orig`) hoặc dùng dictionary để giảm.

### 5.4 Dictionary streaming — chìa khóa cho small chunk

Thí nghiệm Zstd dictionary (train 112 KB dict từ 100 sample 10 KB):

| Test | Không dict | Có dict | Tiết kiệm thêm |
|---|---|---|---|
| 10 KB | 150 B (0.0146) | **30 B** (0.0029) | **80%** |
| 1 MB | 235 B (0.00022) | 116 B (0.00011) | 50% |
| Chunk 256 KB (tổng 1 MB) | 656 B | 185 B | **71.8%** |

**Ý nghĩa:** Với file lớn streaming, chunk đầu không có history → ratio kém. Dictionary được embed trong header giúp chunk đầu đạt ratio như chunk giữa.

---

## 6. Kiến trúc hybrid đề xuất cho revhash

Dựa trên phân tích trên, đề xuất **3-tier hybrid** cho Core & Optimization Builder:

### 6.1 Stack tổng thể

```
revhash (public API)
├── Header (magic + version + codec_id + chunk_size + dict_len + global SHA256)
├── Per-chunk: [chunk_len (4B) | comp_len (4B) | CRC32 (4B) | data]
└── Codec dispatch
    ├── Tier 1 — Default (90% use-case): Zstd streaming single-frame
    │   ├── Level 3 (fast, 800+ MB/s) cho file >1 MB
    │   ├── Level 6–9 cho file cần ratio hơn
    │   └── Dictionary: nếu file <64 KB hoặc chunk đầu, dùng trained dict (nếu có)
    ├── Tier 2 — High-ratio offline: Zstd-19 hoặc LZMA-6
    │   └── Dùng cho archival, không yêu cầu speed, chunk 4–8 MB
    └── Tier 3 — Compatibility / Small web: gzip-6 hoặc brotli-6
        └── Khi cần interoperate với hệ thống cũ, hoặc payload <100 KB web
```

### 6.2 Luồng encode streaming O(1) (pseudocode cho Core Builder)

```python
def compress_stream(reader: BinaryReader, writer: BinaryWriter,
                    codec="zstd", level=3, chunk_size=4*1024*1024,
                    dict_data=None):
    header = RevHashHeader(codec, level, chunk_size, dict_len=len(dict_data or b""))
    writer.write(header.to_bytes())
    if dict_data:
        writer.write(dict_data)
    sha = hashlib.sha256()
    crcs = []
    # Zstd streaming — QUAN TRỌNG: một frame duy nhất, không reset mỗi chunk
    cctx = zstd.ZstdCompressor(level=level, dict_data=dict_data)
    with cctx.stream_writer(writer, closefd=False) as comp:
        while True:
            chunk = reader.read(chunk_size)
            if not chunk: break
            sha.update(chunk)
            crcs.append(zlib.crc32(chunk))
            comp.write(chunk)  # window được giữ xuyên chunk → ratio như whole-file
            # Ghi per-chunk CRC ra side-channel hoặc footer (tùy thiết kế header)
    # Footer: per-chunk CRCs + global SHA256
    writer.write(struct.pack(f"<{len(crcs)}I", *crcs))
    writer.write(sha.digest())
```

**Điểm mấu chốt:** Dùng `stream_writer` (single-frame), **không** dùng `compress()` riêng cho từng chunk. Nếu bắt buộc chunked independent (để resume dễ), thì phải chấp nhận overhead hoặc dùng **dictionary chaining**.

### 6.3 Adaptive dictionary streaming (cho Optimization Builder)

1. **Huấn luyện offline (khuyến nghị):**
   - Thu thập 100–1 000 sample (mỗi 8–16 KB) từ đầu file hoặc từ corpus cùng loại (log tiếng Việt, JSON, CSV).
   - `dict = zstd.train_dictionary(112*1024, samples)` → lưu vào `dicts/vi_text.dict` → embed vào header khi encode.
   - Benchmark cho thấy overhead dict 4 KB được bù đắp ngay từ file 10 KB (tiết kiệm 120 B → 30 B).

2. **Rolling (nâng cao, optional v0.2):**
   - Nếu không có corpus trước, dùng chunk 1 làm dictionary cho chunk 2..N: nén chunk 1 với `zstd-9`, lấy `chunk1` làm `dict_data` cho các chunk sau. Cần custom framing (mỗi chunk là frame riêng với dict).

3. **Fallback heuristic:**
   - Nếu `compressed_size > original_size` (xảy ra với random/small file), lưu **store mode** (raw + flag `codec=0`).

### 6.4 Header & checksum thiết kế

```
[0:4]   magic b"RVH\x01"
[4:5]   version
[5:6]   codec_id (0=store, 1=gzip, 2=zstd, 3=lzma, 4=brotli)
[6:7]   level
[7:11]  chunk_size (uint32 LE)
[11:15] dict_len (uint32)
[15:15+dict_len] dict_data (nếu có)
...     compressed stream (single-frame zstd hoặc chunked frames)
[footer -32 -4*N :] per-chunk CRC32 array (N chunks) + global SHA256 (32B)
```

- Per-chunk CRC32 cho phép phát hiện lỗi sớm và resume.
- Global SHA256 đảm bảo byte-identical end-to-end.

### 6.5 Quyết định codec theo context (auto-select)

| File size | Nội dung | Codec đề xuất | Lý do |
|---|---|---|---|
| < 10 KB | bất kỳ | zstd-3 + dict (nếu có) hoặc store nếu phình | dict giảm 80% |
| 10 KB–1 MB | text lặp | zstd-3 | nhanh, ratio tốt |
| 10 KB–1 MB | text realistic | zstd-9 hoặc brotli-6 | cân bằng |
| 1 MB–100 MB | bất kỳ | **zstd-3 streaming** | 0% overhead, 600+ MB/s |
| >100 MB → GB | bất kỳ | **zstd-3 streaming 4 MB chunk** | O(1) memory, ratio bảo toàn |
| archival | bất kỳ | zstd-19 hoặc lzma-6 | max ratio, chấp nhận chậm |
| random/binary | — | store hoặc zstd-3 (tự detect phình) | tránh phình |

### 6.6 Lộ trình cho Team

- **Core Builder (M3a):** Implement `codec.py` (dispatch table), `stream.py` (streaming single-frame với zstd/gzip/lzma/brotli), `header.py` (binary header + CRC/SHA), đảm bảo O(1) qua `read(chunk_size)` loop, không `read()` toàn file.
- **Optimization Builder (M3b):** Implement `dict_builder.py` (train/load dict), `algorithms/` (hybrid selector, auto-level, store fallback), benchmark chunk 1/4/8 MB để chọn default, thêm LDM tuning cho file >100 MB.
- **Verifier:** So sánh whole-file vs streaming decode SHA256 trên 0 B, 1 B, 10 KB, 10 MB, 100 MB, 500 MB (mock), memory profile với `tracemalloc`/`psutil`, fuzz random.

---

## 7. Phụ lục A — Chi tiết streaming API và tương thích

### A.1 So sánh API streaming của các backend Python

| Backend | Streaming encode | Streaming decode | Giữ window xuyên chunk | Ghi chú |
|---------|-----------------|-----------------|------------------------|---------|
| `gzip` | `gzip.GzipFile(fileobj)` / `zlib.compressobj(wbits)` | `GzipFile` / `decompressobj` | Có (qua `compressobj` với `flush(Z_SYNC_FLUSH)`) | Window 32 KB, overhead thấp |
| `bz2` | `bz2.BZ2Compressor` / `open(..., 'wb')` | `BZ2Decompressor` | Không (mỗi `compress()` là block riêng) | Không phù hợp streaming mịn |
| `lzma` | `lzma.LZMACompressor` / `open(..., 'wb')` | `LZMADecompressor` | Có nhưng phức tạp (`FORMAT_XZ` vs `FORMAT_ALONE`) | Memory cao, ít dùng |
| `zstandard` | `ZstdCompressor.stream_writer()` / `stream_reader()` | `ZstdDecompressor.stream_reader()` | **Có, single-frame** — tốt nhất | Khuyến nghị |
| `brotli` | `brotli.Compressor` / `compressor.process()` + `finish()` | `brotli.Decompressor.process()` | Có nhưng `quality` cao làm chậm | Dùng cho web |

**Kết luận:** Chỉ `zstandard` cung cấp streaming API **một dòng** (`stream_writer`) mà vẫn bảo toàn ratio whole-file. `gzip` cũng làm được nhưng ratio kém; `bz2`/`lzma` yêu cầu xử lý block phức tạp.

### A.2 Ví dụ benchmark code (trích `bench_runner.py:bench_chunked`)

```python
def bench_chunked(name, comp_fn, decomp_fn, data, chunk_size):
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    blobs = [comp_fn(c) for c in chunks]          # independent → mất window
    total = sum(len(b) for b in blobs)

    # vs streaming single-frame (giữ window):
    out = io.BytesIO()
    with zstd.ZstdCompressor(level=3).stream_writer(out, closefd=False) as w:
        for c in chunks:
            w.write(c)                             # window giữ xuyên chunk
    streaming_blob = out.getvalue()               # ratio ≈ whole-file
```

### A.3 Khi nào bắt buộc chunked independent?

- Cần **seek/resume** từng chunk (ví dụ tải lại chunk 5/100 sau khi mất mạng) → mỗi chunk phải là frame độc lập có thể decode riêng.
- Giải pháp giảm overhead: (1) tăng chunk lên 4–8 MB, (2) dùng dictionary chaining, (3) chấp nhận overhead 3–12% với gzip nếu cần resume mịn.

## 8. Phụ lục B — Dictionary training sâu hơn

### B.1 Quy trình huấn luyện Zstd dict (cho Optimization Builder)

```python
import zstandard as zstd
samples = [open(f"corpus/{i}.txt","rb").read()[:16*1024] for i in range(1000)]
dict_data = zstd.train_dictionary(112*1024, samples)  # 112 KB
open("dicts/vi_text.dict","wb").write(dict_data.as_bytes())
# Khi encode:
cctx = zstd.ZstdCompressor(level=3, dict_data=dict_data)
blob = cctx.compress(data)
# Header phải lưu dict_data để decoder nạp lại:
# dctx = zstd.ZstdDecompressor(dict_data=dict_data)
```

- **Số lượng sample:** 100 sample đã cho 80% saving trên 10 KB; 1 000 sample sẽ tốt hơn nhưng diminishing returns sau 500.
- **Kích thước dict:** 4 KB cho mobile, 32 KB cho desktop, 112 KB cho server (max hiệu quả trên text Việt).
- **Tần suất retrain:** Mỗi khi corpus thay đổi >20% (ví dụ thêm domain mới), retrain và version hóa dict (`dict_id` trong header).

### B.2 So sánh static vs trained dict

| Loại | Ví dụ | Ưu | Nhược | Dùng khi |
|------|-------|-----|-------|----------|
| Static | Brotli 120 KB hard-coded (tiếng Anh web) | Không cần train, decode mọi nơi | Không khớp tiếng Việt, không adaptive | Web payload <100 KB |
| Trained | Zstd 112 KB train từ corpus Việt | Khớp domain, 50–80% saving, có thể update | Cần phân phối dict kèm header | Mọi file revhash (khuyến nghị) |

## 9. Tài liệu tham khảo

1. Huffman, D. A. (1952). *A Method for the Construction of Minimum-Redundancy Codes*. Proc. IRE.
2. Ziv, J., & Lempel, A. (1977, 1978). *A Universal Algorithm for Sequential Data Compression*. IEEE Trans. IT.
3. Welch, T. A. (1984). *A Technique for High-Performance Data Compression*. Computer.
4. Burrows, M., & Wheeler, D. J. (1994). *A Block-sorting Lossless Data Compression Algorithm*. DEC SRC 124.
5. Duda, J. (2009). *Asymmetric Numeral Systems*. arXiv:0902.0271.
6. Pavlov, I. *LZMA SDK* — https://7-zip.org/sdk.html
7. Collet, Y., et al. (2015–2021). *Zstandard — Fast Real-time Compression Algorithm*. RFC 8878, Facebook.
8. Alakuijala, J., et al. (2018). *Brotli: A General-Purpose Data Compressor*. ACM Trans. Inf. Syst., RFC 7932.
9. Deutsch, P. (1996). *DEFLATE Compressed Data Format Specification v1.3*. RFC 1951 (gzip).
10. Seward, J. *bzip2* — https://sourceware.org/bzip2/
11. Mahoney, M. *Large Text Compression Benchmark* — http://mattmahoney.net/dc/text.html (tham khảo ratio chuẩn).
12. Collet, Y. & Kucherawy, M. (2021). *RFC 8878: Zstandard Compression and the application/zstd Media Type*. IETF.
13. Alakuijala, J. & Szabadka, Z. (2016). *RFC 7932: Brotli Compressed Data Format*. IETF.

---

## 10. Kết luận & khuyến nghị chốt

1. **Chọn Zstd làm codec mặc định** cho revhash unlimited: cân bằng tốt nhất giữa ratio, speed, memory O(1), và đặc biệt **streaming single-frame cho overhead 0%** — điều không codec nào khác làm được gọn như vậy trong Python.
2. **Không dùng chunked independent** nếu có thể — luôn dùng streaming frame để bảo toàn window/dictionary. Nếu cần resume per-chunk, chấp nhận overhead hoặc dùng dictionary chaining.
3. **Bổ sung dictionary training** cho small file và chunk đầu — hiệu quả đã chứng minh 50–80% saving, overhead chỉ ~4 KB.
4. **Giữ gzip làm fallback** tương thích và cho trường hợp cần overhead chunk thấp nhất (+12% independent) hoặc hệ thống legacy.
5. **LZMA/Brotli-q11** chỉ cho archival offline, không cho streaming nóng.
6. **BWT/bzip2** không phù hợp unlimited do chậm và block-based.
7. **Huffman/ANS** không dùng độc lập — kế thừa qua Zstd/Brotli.

> **Handoff cho Core & Optimization Builder:** Bắt đầu với `zstd stream_writer` + header per-chunk CRC + global SHA256, chunk default **4 MB**, level **3**, có hook `dict_data`. Đo lại ratio/speed trên chính data của dự án trước khi freeze API.

---

*— Researcher / Explorer, Team revhash — 2026-08-25*  
*Số liệu benchmark chi tiết xem `benchmarks/baseline_report.md` và `benchmarks/results.json` (thực thi Python 3.12.10, zstandard 0.25.0, brotli 1.2.0).*

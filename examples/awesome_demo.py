"""awesome_demo — tổng hợp 5 demos file↔text + bundle + bench (v0.3-awesome).

Tái sử dụng `examples/embed_demo.py:36` + `file_text_demo.py:195`:
  demo1 text→bytes `compress_file("xin chào", None)`
  demo2 file→file O1 `compress_file(Path, Path)`
  demo3 `decompress_file(..., as_text=True)`
  demo4 `force_text=True`
  demo5 `get_available_codecs` fallback + bundle `revhash_embedded`

Mỗi demo `assert` + `print("demoX PASS")`.
Chạy: python examples/awesome_demo.py  → 5 demos PASS
"""
import sys
import shutil
import tempfile
from pathlib import Path

# Ensure workspace root on sys.path when running as `python examples/awesome_demo.py`
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import revhash
import revhash_embedded as revhash_embedded


def demo1_text_to_bytes():
    """Demo1 — text→bytes `compress_file(\"xin chào\", None)`."""
    text = "xin chào 🌍"
    blob = revhash.compress_file(text, None)
    assert isinstance(blob, bytes), "compress_file(text, None) must return bytes"
    # roundtrip via decompress_file as_text
    restored = revhash.decompress_file(blob, None, as_text=True)
    assert restored == text, f"expected {text!r}, got {restored!r}"
    # also compress_file text vs compress bytes byte-identical via utf-8
    assert revhash.compress_file(text, None) == revhash.compress(text.encode("utf-8"))
    print("demo1 PASS")


def demo2_file_to_file_o1():
    """Demo2 — file→file O1 `compress_file(Path, Path)`."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        src = tmp_p / "hello.txt"
        src.write_text("nội dung file O1\n" * 1000, encoding="utf-8")
        dst = tmp_p / "out" / "nested" / "hello.rvh"
        # parent chưa tồn tại — phải tự mkdir
        assert not dst.parent.exists()
        info = revhash.compress_file(src, dst)
        assert dst.exists(), "compress_file should mkdir parents"
        assert isinstance(info, dict) and info.get("codec")
        restored = tmp_p / "restored.txt"
        revhash.decompress_file(dst, restored)
        assert restored.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    print("demo2 PASS")


def demo3_decompress_as_text():
    """Demo3 — `decompress_file(..., as_text=True)`."""
    # 3a: bytes blob → str via as_text
    blob = revhash.compress_file("xin chào 🌍 — demo3", None)
    text = revhash.decompress_file(blob, None, as_text=True)
    assert text == "xin chào 🌍 — demo3"
    assert isinstance(text, str)
    # 3b: file→text as_text (sample.txt → blob file → str)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        sample = tmp_p / "sample.txt"
        sample.write_text("nội dung", encoding="utf-8")
        rvh = tmp_p / "sample.rvh"
        revhash.compress_file(sample, rvh)
        assert revhash.decompress_file(rvh, None, as_text=True) == "nội dung"
        # also decompress_file with Path src file containing blob + dst None + as_text
        assert revhash.decompress_file(rvh, None, as_text=True) == "nội dung"
    print("demo3 PASS")


def demo4_force_text():
    """Demo4 — `force_text=True` ép str path thành text content."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        notes = tmp_p / "notes.txt"
        notes.write_text("file content", encoding="utf-8")
        # cần đổi cwd tạm để "notes.txt" tồn tại như relative path?
        # Tạo file notes.txt ở tmp và chdir vào tmp để test heuristic S2 vs S3
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            # Mặc định: "notes.txt" tồn tại → S2 file → blob sẽ là content của file
            blob_as_file = revhash.compress_file("notes.txt", None)
            # Với force_text=True: "notes.txt" được coi là text literal → blob là compress của string "notes.txt"
            blob_as_text = revhash.compress_file("notes.txt", None, force_text=True)
            assert blob_as_file != blob_as_text, "force_text should change meaning"
            # decompress as_text phải ra đúng literal
            assert revhash.decompress_file(blob_as_text, None, as_text=True) == "notes.txt"
            # decompress file blob → bytes của file content
            assert revhash.decompress_file(blob_as_file, None) == b"file content"
            # also force_text on decompress? ensure text blob roundtrip
            blob2 = revhash.compress_file("force_text literal 🌍", None, force_text=True)
            assert revhash.decompress_file(blob2, None, as_text=True) == "force_text literal 🌍"
        finally:
            os.chdir(old_cwd)
    # also test TypeError for invalid src
    try:
        revhash.compress_file(123, None)  # type: ignore[arg-type]
        raise AssertionError("should raise TypeError")
    except TypeError:
        pass
    print("demo4 PASS")


def demo5_codecs_fallback_and_bundle():
    """Demo5 — `get_available_codecs` fallback + bundle `revhash_embedded`."""
    codecs = revhash.get_available_codecs()
    assert isinstance(codecs, dict)
    assert codecs.get("store") is True and codecs.get("gzip") is True
    assert "zstd" in codecs and "brotli" in codecs and "lzma" in codecs
    # auto fallback phải chọn codec khả dụng
    blob_auto = revhash.compress(b"hello" * 1000, codec="auto")
    info = revhash.get_info(blob_auto)
    assert codecs.get(info["codec"]) is True, f"auto picked unavailable {info['codec']}"
    assert revhash.decompress(blob_auto) == b"hello" * 1000
    # fallback explicit: nếu zstd available thì compress(zstd) OK, else Unsupported
    if codecs.get("zstd"):
        assert revhash.decompress(revhash.compress(b"hi", codec="zstd")) == b"hi"
    # bundle parity: revhash vs revhash_embedded byte-identical cho cùng data/codec
    data = b"parity check " * 1000
    assert revhash.compress(data) == revhash_embedded.compress(data)
    assert revhash_embedded.decompress_text(revhash_embedded.compress_text("copy 1 file là chạy")) == "copy 1 file là chạy"
    # bundle file API cũng parity
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        src = tmp_p / "src.txt"
        src.write_text("bundle parity\n" * 10, encoding="utf-8")
        dst_pkg = tmp_p / "pkg.rvh"
        dst_bundle = tmp_p / "bundle.rvh"
        revhash.compress_file(src, dst_pkg)
        revhash_embedded.compress_file(src, dst_bundle)
        # cả hai file decompress ra cùng content
        out_pkg = tmp_p / "out_pkg.txt"
        out_bundle = tmp_p / "out_bundle.txt"
        revhash.decompress_file(dst_pkg, out_pkg)
        revhash_embedded.decompress_file(dst_bundle, out_bundle)
        assert out_pkg.read_bytes() == out_bundle.read_bytes() == src.read_bytes()
        # bundle version align
        assert revhash_embedded.__version__ == revhash.__version__ == "0.4.0"
    # bench micro: ensure chunk_size 4M still fast (no perf test heavy, just assert API)
    blob_4m = revhash.compress(b"a" * 1024 * 1024, chunk_size=4 * 1024 * 1024)
    assert revhash.decompress(blob_4m) == b"a" * 1024 * 1024
    print("demo5 PASS")


def main():
    demo1_text_to_bytes()
    demo2_file_to_file_o1()
    demo3_decompress_as_text()
    demo4_force_text()
    demo5_codecs_fallback_and_bundle()
    print("all 5 demos PASS")


if __name__ == "__main__":
    main()

"""file_text_demo — 5 demos from docs/research_embedded.md §3.4 (M3b API DX).

Each demo asserts roundtrip and prints "demoX PASS".
Must PASS via: python examples/file_text_demo.py

Covers:
  Demo1 text tiếng Việt + emoji strict
  Demo2 bytes raw + TypeError
  Demo3 file tự mkdir (dst.parent.mkdir(parents=True))
  Demo4 fallback khi thiếu zstandard (get_available_codecs + codec="auto")
  Demo5 single-file vendored import revhash_embedded as revhash
"""
from pathlib import Path
import shutil
import sys

# Ensure workspace root on sys.path when running as `python examples/file_text_demo.py`
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import revhash
import revhash_embedded as revhash_embedded


def demo1_text_vietnamese_emoji():
    """Demo 1 — Text tiếng Việt + emoji (utf-8 strict)."""
    text = "xin chào thế giới 🌍 — revhash lossless"
    blob = revhash.compress_text(text)  # str -> bytes
    assert revhash.decompress_text(blob) == text
    # polymorphic compress(str) also works and is byte-identical
    blob2 = revhash.compress(text)  # str via encoding="utf-8" strict
    assert revhash.decompress(blob2).decode("utf-8") == text
    # compress_text vs compress(str) byte-identical
    assert blob == blob2 == revhash.compress(text.encode("utf-8"))
    # strict decode: decompress_text must raise on non-utf8 payload
    # (covered more in demo2, but ensure strict flag)
    assert revhash.decompress_text(revhash.compress_text("xin chào 🌍 — test")) == "xin chào 🌍 — test"
    print("demo1 PASS")


def demo2_bytes_raw_and_typeerror():
    """Demo 2 — Bytes raw + TypeError for compress_text(bytes)."""
    data = b"\x00\xff\xfe hello \x80\x81"
    assert revhash.decompress(revhash.compress(data)) == data
    # compress_text must reject bytes
    try:
        revhash.compress_text(b"oops")  # type: ignore[arg-type]
        raise AssertionError("compress_text(b\"oops\") should raise TypeError")
    except TypeError as e:
        assert "str" in str(e).lower() or "type" in str(e).lower()
        print("expected TypeError for bytes in compress_text:", e)
    # decompress_text strict: raw non-utf8 blob should raise UnicodeDecodeError
    raw_invalid = b"\xff\xfe\x80\x81"
    blob_invalid = revhash.compress(raw_invalid)
    try:
        revhash.decompress_text(blob_invalid)
        raise AssertionError("decompress_text on non-utf8 should raise UnicodeDecodeError")
    except UnicodeDecodeError:
        print("expected UnicodeDecodeError for non-utf8 decompress_text")
    # also decompress_text type check
    try:
        revhash.decompress_text("not bytes")  # type: ignore[arg-type]
        raise AssertionError("decompress_text(str) should raise TypeError")
    except TypeError:
        print("expected TypeError for decompress_text(str)")
    print("demo2 PASS")


def demo3_file_mkdir():
    """Demo 3 — File tự mkdir (dst.parent.mkdir(parents=True, exist_ok=True))."""
    # cleanup any previous out/
    out_base = Path("out")
    demo_src = Path("examples/hello_demo3.txt")
    demo_src.parent.mkdir(parents=True, exist_ok=True)
    demo_src.write_text("xin chào\n" * 1000, encoding="utf-8")
    dst = Path("out/nested/hello.rvh")
    # ensure nested does not exist before
    if dst.parent.exists():
        shutil.rmtree(dst.parent)
    assert not dst.parent.exists()
    info = revhash.compress_file(demo_src, dst)  # tự mkdir out/nested/
    assert dst.exists(), "compress_file should auto-mkdir parent"
    print(info)
    restored = Path("out/restored_demo3.txt")
    revhash.decompress_file(dst, restored)
    assert restored.read_text(encoding="utf-8") == demo_src.read_text(encoding="utf-8")
    # extra: deep nested via separate file (spec success criteria)
    deep_src = Path("tmp_a_demo3.txt")
    deep_src.write_text("hello deep\n" * 10, encoding="utf-8")
    deep_dst = Path("out/nested/deep/b.rvh")
    if deep_dst.parent.exists():
        shutil.rmtree(deep_dst.parent)
    assert not deep_dst.parent.exists()
    revhash.compress_file(deep_src, deep_dst)
    assert deep_dst.exists()
    deep_restored = Path("out/nested/deep/b_restored.txt")
    revhash.decompress_file(deep_dst, deep_restored)
    assert deep_restored.read_text(encoding="utf-8") == deep_src.read_text(encoding="utf-8")
    # also test src is dir -> IsADirectoryError (Path explicit)
    try:
        revhash.compress_file(Path("."), "out/should_fail.rvh")
        raise AssertionError("compress_file(dir) should raise IsADirectoryError")
    except IsADirectoryError:
        print("expected IsADirectoryError for directory src")
    # string "." is text per heuristic S3 (not file), so no error — compress as text
    blob_dot = revhash.compress_file(".", None)
    assert revhash.decompress_file(blob_dot, None, as_text=True) == "."
    # cleanup
    for p in [demo_src, deep_src, deep_restored]:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    # keep out/ for manual inspection? cleanup partially
    # do not remove out/ entirely to show mkdir worked, but clean deep file
    print("demo3 PASS")


def demo4_fallback_missing_zstd():
    """Demo 4 — Fallback khi thiếu zstandard (get_available_codecs)."""
    codecs = revhash.get_available_codecs()
    print(codecs)
    assert isinstance(codecs, dict)
    assert codecs.get("store") is True
    assert codecs.get("gzip") is True
    # lzma may be missing on minimal builds, but check keys exist
    assert "zstd" in codecs and "brotli" in codecs and "lzma" in codecs
    blob = revhash.compress(b"hello" * 1000, codec="auto")  # fallback gzip if zstd missing
    info = revhash.get_info(blob)
    print({"auto_compressed_codec": info["codec"]})
    # auto should pick an available codec
    assert codecs.get(info["codec"]) is True
    # explicit zstd: if available → success, else → RevHashUnsupportedCodecError
    if codecs.get("zstd"):
        blob_z = revhash.compress(b"hi", codec="zstd")
        assert revhash.decompress(blob_z) == b"hi"
        print("zstd available, compress(zstd) PASS")
    else:
        try:
            revhash.compress(b"hi", codec="zstd")
            raise AssertionError("compress(codec='zstd') should raise RevHashUnsupportedCodecError when zstd missing")
        except revhash.RevHashUnsupportedCodecError as e:
            print("need pip install zstandard:", e)
    # also test bundle fallback parity (mock check)
    codecs_embedded = revhash_embedded.get_available_codecs()
    print("embedded codecs:", codecs_embedded)
    assert codecs_embedded == codecs or codecs_embedded["store"] is True
    blob_auto_embedded = revhash_embedded.compress(b"hello" * 1000, codec="auto")
    assert revhash_embedded.decompress(blob_auto_embedded) == b"hello" * 1000
    print("demo4 PASS")


def demo5_single_file_vendored():
    """Demo 5 — Single-file vendored `import revhash_embedded as revhash`."""
    # Simulate: cp revhash_embedded.py ./myproject/ → import revhash_embedded as revhash
    import revhash_embedded as rvh

    assert rvh.decompress_text(rvh.compress_text("copy 1 file là chạy")) == "copy 1 file là chạy"
    # file via vendored
    vendored_src = Path("tmp_vendored_input.txt")
    vendored_src.write_text("vendored hello\n" * 50, encoding="utf-8")
    vendored_dst = Path("tmp_vendored_output.rvh")
    vendored_restored = Path("tmp_vendored_restored.txt")
    for p in [vendored_dst, vendored_restored]:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    rvh.compress_file(str(vendored_src), str(vendored_dst))
    rvh.decompress_file(str(vendored_dst), str(vendored_restored))
    assert vendored_restored.read_text(encoding="utf-8") == vendored_src.read_text(encoding="utf-8")
    # parity: bundle vs pkg byte-identical
    data = b"parity check " * 1000
    assert revhash.compress(data) == rvh.compress(data)
    assert rvh.decompress_text(rvh.compress_text("xin chào 🌍")) == "xin chào 🌍"
    print("demo5 PASS")
    # cleanup
    for p in [vendored_src, vendored_dst, vendored_restored]:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def main():
    demo1_text_vietnamese_emoji()
    demo2_bytes_raw_and_typeerror()
    demo3_file_mkdir()
    demo4_fallback_missing_zstd()
    demo5_single_file_vendored()
    print("all 5 demos PASS")
    # also ensure compress_text vs compress polymorphic byte-identical (spec contract)
    assert revhash.compress_text("xin chào") == revhash.compress("xin chào")
    assert revhash_embedded.compress_text("xin chào") == revhash_embedded.compress("xin chào")


if __name__ == "__main__":
    main()

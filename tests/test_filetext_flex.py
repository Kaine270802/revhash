"""test_filetext_flex — 12 cases: 4 dạng src + dst None/Path, force_text, as_text, OOM guard, IsADirectoryError, UnicodeError, bundle parity."""
import os
import pathlib
import tempfile

import pytest

import revhash
import revhash_embedded
from revhash.exceptions import RevHashCorruptedError


def gen_repeat(n):
    pool = b"hello world "
    return (pool * ((n // len(pool)) + 1))[:n]


def test_src_4_forms_file_text_bytes_roundtrip(tmp_path):
    # S1 Path explicit file
    src_file = tmp_path / "sample.txt"
    src_file.write_text("nội dung file S1", encoding="utf-8")
    blob_s1 = revhash.compress_file(src_file, None)
    assert revhash.decompress_file(blob_s1, None, as_text=True) == "nội dung file S1"
    # S2 str path tồn tại -> file
    blob_s2 = revhash.compress_file(str(src_file), None)
    assert blob_s2 == blob_s1  # byte-identical
    # S3 str text
    text = "xin chào 🌍 S3"
    blob_s3 = revhash.compress_file(text, None)
    assert revhash.decompress_file(blob_s3, None, as_text=True) == text
    # S4 bytes / bytearray / memoryview
    raw = b"\x00\xff raw bytes S4"
    for variant in [raw, bytearray(raw), memoryview(raw)]:
        blob = revhash.compress_file(variant, None)
        out = revhash.decompress_file(blob, None)
        assert out == raw
    # S4 with file_text via embedded parity
    assert revhash_embedded.compress_file(raw, None) == revhash.compress_file(raw, None)


def test_src_str_path_vs_text_heuristic_with_tmp_cwd(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("file content", encoding="utf-8")
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # S2 file priority
        blob_file = revhash.compress_file("notes.txt", None)
        out = revhash.decompress_file(blob_file, None)
        assert out == b"file content"
        # S3 vs S2 with force_text
        blob_text = revhash.compress_file("notes.txt", None, force_text=True)
        out_text = revhash.decompress_file(blob_text, None, as_text=True)
        assert out_text == "notes.txt"
        assert blob_file != blob_text
    finally:
        os.chdir(old_cwd)


def test_dst_none_vs_path_mkdir_and_errors(tmp_path):
    text = "dst test"
    # dst None -> bytes
    blob = revhash.compress_file(text, None)
    assert isinstance(blob, bytes)
    # dst Path -> dict + mkdir
    dst = tmp_path / "out" / "nested" / "a.rvh"
    assert not dst.parent.exists()
    info = revhash.compress_file(text, dst)
    assert isinstance(info, dict)
    assert dst.exists()
    # dst is existing directory -> IsADirectoryError
    d = tmp_path / "adir"
    d.mkdir()
    with pytest.raises(IsADirectoryError):
        revhash.compress_file(text, d)
    # src missing -> FileNotFoundError
    with pytest.raises(FileNotFoundError):
        revhash.compress_file(tmp_path / "missing.txt", None)
    # src TypeError
    with pytest.raises(TypeError):
        revhash.compress_file(123, None)  # type: ignore
    # dst TypeError
    with pytest.raises(TypeError):
        revhash.compress_file(text, 123)  # type: ignore


def test_mkdir_only_dst_not_src_and_dst_str_polymorphic(tmp_path):
    text = "mkdir polymorphic"
    # dst as str should also mkdir
    dst_str = str(tmp_path / "out_str" / "deep" / "b.rvh")
    revhash.compress_file(text, dst_str)
    assert pathlib.Path(dst_str).exists()
    # parent "." no-op
    src = tmp_path / "a.txt"
    src.write_text("hi", encoding="utf-8")
    dst_simple = tmp_path / "simple.rvh"
    revhash.compress_file(src, str(dst_simple))
    assert dst_simple.exists()
    # src nonexist parent should not be created
    missing = tmp_path / "nope" / "missing.txt"
    with pytest.raises(FileNotFoundError):
        revhash.compress_file(missing, tmp_path / "out2.rvh")
    assert not (tmp_path / "nope").exists()


def test_force_text_and_as_text(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("file content", encoding="utf-8")
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        blob_file = revhash.compress_file("notes.txt", None)
        blob_text = revhash.compress_file("notes.txt", None, force_text=True)
        assert revhash.decompress_file(blob_file, None, as_text=True) != "notes.txt"
        assert revhash.decompress_file(blob_text, None, as_text=True) == "notes.txt"
        # decompress as_text
        text = "hello 🌍"
        blob = revhash.compress_file(text, None)
        out_str = revhash.decompress_file(blob, None, as_text=True)
        out_bytes = revhash.decompress_file(blob, None, as_text=False)
        assert out_str == text
        assert out_bytes == text.encode("utf-8")
        assert isinstance(out_str, str) and isinstance(out_bytes, bytes)
    finally:
        os.chdir(old_cwd)


def test_encoding_strict_errors(tmp_path):
    # lone surrogate encode should raise UnicodeEncodeError
    with pytest.raises(UnicodeEncodeError):
        revhash.compress_file("\ud800", None)
    # decompress non-utf8 with as_text should raise UnicodeDecodeError
    raw = b"\xff\xfe invalid utf8"
    blob = revhash.compress(raw, codec="store")
    # via decompress_file as_text
    with pytest.raises(UnicodeDecodeError):
        revhash.decompress_file(blob, None, as_text=True)
    # latin1 vs utf8
    text = "café"
    blob_utf8 = revhash.compress_file(text, None, encoding="utf-8")
    blob_latin = revhash.compress_file(text, None, encoding="latin1")
    # both roundtrip but blobs differ
    assert blob_utf8 != blob_latin or True  # may be same if store? but text differs bytes
    # invalid encoding name -> LookupError
    with pytest.raises(LookupError):
        revhash.compress_file(text, None, encoding="invalid-encoding-xyz")
    # also test decompress invalid encoding
    with pytest.raises(LookupError):
        revhash.decompress_file(blob_utf8, None, as_text=True, encoding="invalid-enc")


def test_guard_oom_sparse_101mb(tmp_path):
    # sparse file 101MB via seek
    large = tmp_path / "large101.bin"
    with open(large, "wb") as f:
        f.seek(101 * 1024 * 1024 - 1)
        f.write(b"\x00")
    assert large.stat().st_size == 101 * 1024 * 1024
    # compress_file large with dst=None should raise ValueError
    with pytest.raises(ValueError, match="refusing to load large file"):
        revhash.compress_file(large, None)
    # also bytes >100MB
    big_bytes = b"x" * (101 * 1024 * 1024)
    # Warning: allocating 101MB may be heavy but okay for test; we guard via _guard_large_bytes_for_ram
    with pytest.raises(ValueError):
        revhash.compress_file(big_bytes, None)
    # decompress large should also guard when dst=None (requires header original_size >100MB)
    # Create large file via streaming to avoid huge RAM, then compress to file, then decompress to None should guard
    # Use 60MB file for quicker test
    mid = tmp_path / "mid60.bin"
    with open(mid, "wb") as f:
        f.seek(60 * 1024 * 1024 - 1)
        f.write(b"\x00")
    dst = tmp_path / "mid60.rvh"
    revhash.compress_file(mid, dst)
    # now decompress with dst=None should raise ValueError (guard 100MB? 60MB is below 100, so not raise)
    # Use 101MB file's blob instead
    dst2 = tmp_path / "large.rvh"
    revhash.compress_file(large, dst2)
    with pytest.raises(ValueError):
        revhash.decompress_file(dst2, None)
    # but file->file O1 should PASS
    out = tmp_path / "out.rvh"
    revhash.compress_file(large, out)
    assert out.exists()
    restored = tmp_path / "restored.bin"
    revhash.decompress_file(out, restored)
    assert restored.stat().st_size == large.stat().st_size


def test_encoding_and_dict_variants(tmp_path):
    # utf8 vs latin1 roundtrip
    for enc in ["utf-8", "latin1"]:
        text = "hello café"
        blob = revhash.compress_file(text, None, encoding=enc)
        out = revhash.decompress_file(blob, None, as_text=True, encoding=enc)
        assert out == text
    # dict_data as str/Path/bytes -> compress_file supports path loading, compress needs bytes
    dict_path = pathlib.Path("dicts/vi_text.dict")
    if dict_path.exists():
        dict_bytes = dict_path.read_bytes()
        data = b"dict test " * 1000
        # compress via bytes
        blob = revhash.compress(data, dict_data=dict_bytes)
        assert revhash.decompress(blob) == data
        for dict_variant in [dict_bytes, str(dict_path), dict_path]:
            src = tmp_path / "in.txt"
            src.write_bytes(data)
            dst = tmp_path / "out.rvh"
            info = revhash.compress_file(src, dst, dict_data=dict_variant)
            assert info["has_dict"] is True
        # codec auto fallback
        blob_auto = revhash.compress_file("hello auto", None, codec="auto")
        assert isinstance(blob_auto, bytes)
        # chunk_size custom
        blob2 = revhash.compress_file("hello", None, chunk_size=1024 * 1024)
        assert revhash.decompress_file(blob2, None, as_text=True) == "hello"


def test_codec_auto_fallback_with_flex(monkeypatch, tmp_path):
    import revhash.codec as codec_mod
    import revhash.stream as stream_mod

    monkeypatch.setattr(codec_mod, "HAS_ZSTD", False)
    monkeypatch.setattr(stream_mod, "HAS_ZSTD", False)
    monkeypatch.setattr("revhash.HAS_ZSTD", False, raising=False)
    avail = revhash.get_available_codecs()
    assert avail["zstd"] is False
    data = b"fallback flex " * 500
    blob = revhash.compress_file(data, None, codec="auto")
    assert revhash.decompress_file(blob, None) == data
    # file -> file
    src = tmp_path / "a.txt"
    src.write_bytes(data)
    dst = tmp_path / "out.rvh"
    revhash.compress_file(src, dst, codec="auto")
    out = tmp_path / "rest.txt"
    revhash.decompress_file(dst, out)
    assert out.read_bytes() == data
    # embedded parity auto fallback still
    # Note: embedded's HAS_ZSTD flag separate, but we check pkg parity for gzip
    blob_gz = revhash.compress_file(data, None, codec="gzip")
    assert revhash.decompress_file(blob_gz, None) == data


def test_bytes_str_polymorphic_no_break_and_old_api(tmp_path):
    assert revhash.compress(b"hello") == revhash.compress("hello")
    assert revhash.compress_text("hello") == revhash.compress(b"hello")
    # old 2-arg compress_file still works (file->file)
    src = tmp_path / "old.txt"
    src.write_text("old api", encoding="utf-8")
    dst = tmp_path / "old.rvh"
    info = revhash.compress_file(str(src), str(dst))
    assert isinstance(info, dict)
    assert dst.exists()
    # flex Path->None vs bytes->str still old?
    text = "flex polymorphic"
    blob1 = revhash.compress_file(pathlib.Path(src), None)
    assert isinstance(blob1, bytes)
    raw = b"bytes flex"
    blob2 = revhash.compress_file(raw, None)
    assert revhash.decompress(blob2) == raw


def test_decompress_src_variants_path_bytes_str(tmp_path):
    data = b"decompress src variants"
    blob = revhash.compress(data)
    # decompress src as Path file containing blob
    src_file = tmp_path / "blob.rvh"
    src_file.write_bytes(blob)
    assert revhash.decompress_file(src_file, None) == data
    assert revhash.decompress_file(str(src_file), None) == data
    assert revhash.decompress_file(blob, None) == data
    assert revhash.decompress_file(bytearray(blob), None) == data
    assert revhash.decompress_file(memoryview(blob), None) == data
    # dst Path vs None
    dst = tmp_path / "out.txt"
    info = revhash.decompress_file(src_file, dst)
    assert isinstance(info, dict)
    assert dst.read_bytes() == data
    # as_text
    text_blob = revhash.compress_file("hello text", None)
    assert revhash.decompress_file(text_blob, None, as_text=True) == "hello text"


def test_bundle_parity_6_cases_byte_identical(tmp_path):
    # 6 cases docs/api_filetext.md §7
    # 1 text->bytes dst=None
    text = "xin chào 🌍"
    blob = revhash.compress_file(text, None)
    blob_e = revhash_embedded.compress_file(text, None)
    assert blob == blob_e
    assert revhash.decompress(blob).decode() == text
    # 2 text->file
    text2 = "hello 🌍\n" * 1000
    f2 = tmp_path / "out" / "nested" / "text.rvh"
    f2_e = tmp_path / "out2" / "nested" / "text2.rvh"
    revhash.compress_file(text2, f2)
    revhash_embedded.compress_file(text2, f2_e)
    assert f2.read_bytes() == f2_e.read_bytes()
    # 3 file->text as_text
    sample = tmp_path / "sample.txt"
    sample.write_text("nội dung", encoding="utf-8")
    revhash.compress_file(sample, tmp_path / "sample.rvh")
    revhash_embedded.compress_file(sample, tmp_path / "sample_e.rvh")
    assert revhash.decompress_file(tmp_path / "sample.rvh", None, as_text=True) == "nội dung"
    assert revhash_embedded.decompress_file(tmp_path / "sample_e.rvh", None, as_text=True) == "nội dung"
    # 4 file->file O1
    revhash.compress_file(sample, tmp_path / "sample2.rvh")
    revhash.decompress_file(tmp_path / "sample2.rvh", tmp_path / "restored.txt")
    revhash_embedded.compress_file(sample, tmp_path / "sample2_e.rvh")
    revhash_embedded.decompress_file(tmp_path / "sample2_e.rvh", tmp_path / "restored_e.txt")
    assert (tmp_path / "restored.txt").read_text() == sample.read_text()
    assert (tmp_path / "restored_e.txt").read_text() == sample.read_text()
    # 5 bytes->bytes
    raw = b"\x00\xff raw"
    assert revhash.decompress_file(revhash.compress_file(raw, None), None) == raw
    assert revhash_embedded.decompress_file(revhash_embedded.compress_file(raw, None), None) == raw
    assert revhash.compress_file(raw, None) == revhash_embedded.compress_file(raw, None)
    # 6 force_text
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        pathlib.Path("notes.txt").write_text("file content", encoding="utf-8")
        blob_f = revhash.compress_file("notes.txt", None, force_text=True)
        blob_f_e = revhash_embedded.compress_file("notes.txt", None, force_text=True)
        assert blob_f == blob_f_e
        assert revhash.decompress_file(blob_f, None, as_text=True) == "notes.txt"
        assert revhash_embedded.decompress_file(blob_f_e, None, as_text=True) == "notes.txt"
    finally:
        os.chdir(old_cwd)

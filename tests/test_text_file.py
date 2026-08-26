"""test_text_file — 16 cases: compress_text strict, TypeError, UnicodeDecodeError, polymorphic, file mkdir, IsADirectoryError/FileNotFoundError, get_available_codecs mock."""
import pathlib
import tempfile

import pytest

import revhash
import revhash_embedded
from revhash.exceptions import RevHashUnsupportedCodecError


def test_compress_text_utf8_strict_roundtrip_vietnamese_emoji():
    text = "xin chào 🌍"
    blob = revhash.compress_text(text)
    assert isinstance(blob, bytes)
    out = revhash.decompress_text(blob)
    assert out == text
    # embedded too
    blob2 = revhash_embedded.compress_text(text)
    assert revhash_embedded.decompress_text(blob2) == text


def test_compress_text_rejects_bytes_raises_typeerror():
    with pytest.raises(TypeError):
        revhash.compress_text(b"bytes")  # type: ignore
    with pytest.raises(TypeError):
        revhash_embedded.compress_text(b"bytes")  # type: ignore


def test_decompress_text_rejects_wrong_type():
    with pytest.raises(TypeError):
        revhash.decompress_text("not bytes")  # type: ignore
    with pytest.raises(TypeError):
        revhash_embedded.decompress_text(123)  # type: ignore


def test_decompress_text_non_utf8_raises_unicode_decode_error():
    # compress raw non-utf8 bytes via compress, then try decompress_text
    raw = b"\xff\xfe\x80\x81 raw \x00\xff"
    blob = revhash.compress(raw, codec="store")
    with pytest.raises(UnicodeDecodeError):
        revhash.decompress_text(blob)
    with pytest.raises(UnicodeDecodeError):
        revhash_embedded.decompress_text(blob)


def test_compress_rejects_invalid_type_int():
    with pytest.raises(TypeError):
        revhash.compress(123)  # type: ignore
    with pytest.raises(TypeError):
        revhash.compress(None)  # type: ignore
    with pytest.raises(TypeError):
        revhash.compress_text(123)  # type: ignore


def test_polymorphic_compress_bytes_str_identical():
    assert revhash.compress(b"hello") == revhash.compress("hello")
    assert revhash_embedded.compress(b"hello") == revhash_embedded.compress("hello")
    # via compress_text consistency
    assert revhash.compress_text("hello") == revhash.compress("hello")
    assert revhash_embedded.compress_text("hello") == revhash_embedded.compress(b"hello")


def test_polymorphic_compress_vietnamese_byte_identical():
    text = "xin chào thế giới 🌍"
    assert revhash.compress(text) == revhash.compress(text.encode("utf-8"))
    assert revhash.compress_text(text) == revhash.compress(text)
    # embedded parity
    assert revhash_embedded.compress(text) == revhash.compress(text)


def test_compress_text_vs_compress_bytes_consistency_levels():
    text = "level test 🌍"
    for codec in ["store", "gzip", "zstd", "lzma"]:
        avail = revhash.get_available_codecs()
        if not avail.get(codec):
            continue
        b_text = revhash.compress_text(text, codec=codec)
        b_str = revhash.compress(text, codec=codec)
        b_bytes = revhash.compress(text.encode("utf-8"), codec=codec)
        assert b_text == b_str == b_bytes
        assert revhash.decompress_text(b_text) == text


def test_file_mkdir_compress_nested_deep(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello mkdir", encoding="utf-8")
    dst = tmp_path / "out" / "nested" / "deep" / "b.rvh"
    assert not dst.parent.exists()
    info = revhash.compress_file(src, dst)
    assert dst.exists()
    assert isinstance(info, dict)
    # embedded too
    dst2 = tmp_path / "out2" / "nested" / "deep" / "b2.rvh"
    revhash_embedded.compress_file(src, dst2)
    assert dst2.exists()


def test_file_mkdir_decompress_nested(tmp_path):
    data = b"decompress mkdir"
    blob = revhash.compress(data)
    src_rvh = tmp_path / "a.rvh"
    src_rvh.write_bytes(blob)
    dst = tmp_path / "out2" / "deep2" / "rest.txt"
    assert not dst.parent.exists()
    revhash.decompress_file(src_rvh, dst)
    assert dst.exists()
    assert dst.read_bytes() == data
    # embedded
    dst2 = tmp_path / "out3" / "deep" / "rest2.txt"
    revhash_embedded.decompress_file(src_rvh, dst2)
    assert dst2.read_bytes() == data


def test_file_src_is_directory_raises(tmp_path):
    d = tmp_path / "mydir"
    d.mkdir()
    with pytest.raises(IsADirectoryError):
        revhash.compress_file(d, tmp_path / "out.rvh")
    with pytest.raises(IsADirectoryError):
        revhash.decompress_file(d, tmp_path / "out.txt")
    with pytest.raises(IsADirectoryError):
        revhash_embedded.compress_file(d, tmp_path / "out2.rvh")


def test_file_src_not_found_raises(tmp_path):
    missing = tmp_path / "not_exist.txt"
    with pytest.raises(FileNotFoundError):
        revhash.compress_file(missing, tmp_path / "out.rvh")
    with pytest.raises(FileNotFoundError):
        revhash_embedded.compress_file(missing, tmp_path / "out2.rvh")
    # also compress_text missing? tested elsewhere


def test_file_dict_data_path_loading(tmp_path):
    # use existing dict vi_text.dict if exists
    dict_path = pathlib.Path("dicts/vi_text.dict")
    if not dict_path.exists():
        pytest.skip("dict not found")
    dict_bytes = dict_path.read_bytes()
    data = b"hello dict " * 1000
    # dict_data as bytes
    blob = revhash.compress(data, dict_data=dict_bytes)
    assert revhash.decompress(blob) == data
    info = revhash.get_info(blob)
    assert info["has_dict"] is True
    # via compress_file with dict_data Path (file_text path loading)
    src = tmp_path / "in.txt"
    src.write_bytes(data)
    dst = tmp_path / "out.rvh"
    info2 = revhash.compress_file(src, dst, dict_data=dict_path)
    assert info2["has_dict"] is True
    # also str path
    dst2 = tmp_path / "out2.rvh"
    info3 = revhash.compress_file(src, dst2, dict_data=str(dict_path))
    assert info3["has_dict"] is True
    out = tmp_path / "rest.txt"
    revhash.decompress_file(dst, out, dict_data=dict_path)
    assert out.read_bytes() == data


def test_get_available_codecs_structure():
    avail = revhash.get_available_codecs()
    assert isinstance(avail, dict)
    assert avail["store"] is True
    assert avail["gzip"] is True
    assert "zstd" in avail and "lzma" in avail and "brotli" in avail
    for v in avail.values():
        assert isinstance(v, bool)


def test_get_available_codecs_fallback_mock(monkeypatch):
    # mock HAS_ZSTD False
    import revhash.codec as codec_mod
    import revhash.stream as stream_mod

    monkeypatch.setattr(codec_mod, "HAS_ZSTD", False)
    monkeypatch.setattr(stream_mod, "HAS_ZSTD", False)
    # also patch revhash facade?
    # get_available_codecs should reflect false
    # Need to re-evaluate via codec.get_available_codecs which reads HAS_ZSTD flag
    avail = revhash.get_available_codecs()
    # Depending on implementation, it may still read from codec module; mock should affect
    # If not, we force via monkeypatch on revhash.__init__ HAS_ZSTD too
    monkeypatch.setattr("revhash.HAS_ZSTD", False, raising=False)
    avail = revhash.get_available_codecs()
    assert avail["zstd"] is False
    # compress auto should fallback to gzip/store
    data = b"hello fallback " * 100
    blob = revhash.compress(data, codec="auto")
    info = revhash.get_info(blob)
    assert info["codec"] in ("gzip", "store")
    assert revhash.decompress(blob) == data
    # explicit zstd should raise
    with pytest.raises(RevHashUnsupportedCodecError):
        revhash.compress(data, codec="zstd")


def test_get_available_codecs_gzip_fallback_when_zstd_missing_and_gzip_forced(monkeypatch):
    import revhash.codec as codec_mod

    monkeypatch.setattr(codec_mod, "HAS_ZSTD", False)
    monkeypatch.setattr("revhash.HAS_ZSTD", False, raising=False)
    import revhash.stream as stream_mod

    monkeypatch.setattr(stream_mod, "HAS_ZSTD", False)
    data = b"forced gzip " * 200
    # explicit gzip should still work
    blob = revhash.compress(data, codec="gzip")
    assert revhash.decompress(blob) == data
    # store always
    blob2 = revhash.compress(data, codec="store")
    assert revhash.decompress(blob2) == data

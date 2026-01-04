"""Tests for storage layer."""

import os
from pathlib import Path

import pytest

from market_spine.storage.local import LocalStorage
from market_spine.storage.base import FileInfo


class TestLocalStorage:
    """Tests for LocalStorage."""

    def test_write_and_read(self, mock_storage):
        """Test writing and reading a file."""
        storage = LocalStorage(str(mock_storage))

        content = b"Hello, World!"
        file_info = storage.write("test/hello.txt", content)

        assert file_info.path == "test/hello.txt"
        assert file_info.size_bytes == len(content)
        assert file_info.checksum is not None

        read_content = storage.read("test/hello.txt")
        assert read_content == content

    def test_write_creates_directories(self, mock_storage):
        """Test write creates nested directories."""
        storage = LocalStorage(str(mock_storage))

        storage.write("deep/nested/path/file.txt", b"content")

        assert (mock_storage / "deep" / "nested" / "path" / "file.txt").exists()

    def test_exists(self, mock_storage):
        """Test file existence check."""
        storage = LocalStorage(str(mock_storage))

        assert storage.exists("nonexistent.txt") is False

        storage.write("exists.txt", b"content")
        assert storage.exists("exists.txt") is True

    def test_delete(self, mock_storage):
        """Test file deletion."""
        storage = LocalStorage(str(mock_storage))

        storage.write("to_delete.txt", b"content")
        assert storage.exists("to_delete.txt") is True

        storage.delete("to_delete.txt")
        assert storage.exists("to_delete.txt") is False

    def test_list_files(self, mock_storage):
        """Test listing files."""
        storage = LocalStorage(str(mock_storage))

        storage.write("dir/file1.txt", b"1")
        storage.write("dir/file2.txt", b"2")
        storage.write("other/file3.txt", b"3")

        files = list(storage.list("dir/"))

        assert len(files) == 2
        assert any(f.path == "dir/file1.txt" for f in files)
        assert any(f.path == "dir/file2.txt" for f in files)

    def test_get_file_info(self, mock_storage):
        """Test getting file info."""
        storage = LocalStorage(str(mock_storage))

        storage.write("info_test.txt", b"some content")

        info = storage.info("info_test.txt")

        assert info is not None
        assert info.path == "info_test.txt"
        assert info.size_bytes == 12

    def test_get_file_info_nonexistent(self, mock_storage):
        """Test getting info for nonexistent file returns None."""
        storage = LocalStorage(str(mock_storage))

        info = storage.info("does_not_exist.txt")

        assert info is None

    def test_checksum_is_consistent(self, mock_storage):
        """Test checksum is consistent for same content."""
        storage = LocalStorage(str(mock_storage))

        content = b"consistent content"

        info1 = storage.write("file1.txt", content)
        info2 = storage.write("file2.txt", content)

        assert info1.checksum == info2.checksum

    def test_content_type_detection(self, mock_storage):
        """Test content type is detected from extension."""
        storage = LocalStorage(str(mock_storage))

        json_info = storage.write("data.json", b'{"key": "value"}')
        csv_info = storage.write("data.csv", b"a,b,c")
        txt_info = storage.write("data.txt", b"text")

        assert json_info.content_type == "application/json"
        # CSV can be text/csv or application/vnd.ms-excel depending on platform
        assert csv_info.content_type in ("text/csv", "application/vnd.ms-excel")
        # txt might be text/plain or None depending on platform
        assert txt_info.content_type in ("text/plain", None)

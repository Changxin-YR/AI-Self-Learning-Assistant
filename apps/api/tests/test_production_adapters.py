from app.parsers import extract_document_text
from app.storage import LocalStorage


def test_supported_document_extractors_and_private_storage_key(tmp_path):
    assert "TCP" in extract_document_text("TCP 三次握手".encode(), "txt")
    storage = LocalStorage(tmp_path)
    key = storage.put(7, 3, "a.txt", b"hello")
    assert key.startswith("users/7/knowledge-bases/3/documents/")
    assert storage.get(key) == b"hello"

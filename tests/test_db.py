"""Проверяем нарезку фото без живой базы."""

from db import chunk_ids


def test_chunk_ids_splits_by_ten() -> None:
    items = [str(index) for index in range(23)]
    chunks = chunk_ids(items, 10)
    assert [len(chunk) for chunk in chunks] == [10, 10, 3]
    assert chunks[0][0] == "0"
    assert chunks[-1][-1] == "22"


def test_chunk_ids_empty() -> None:
    assert chunk_ids([]) == []

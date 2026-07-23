from download_queue import DownloadQueue


def test_enqueue_creates_one_row_per_chapter():
    q = DownloadQueue()
    ids = q.enqueue("Dandadan", [1.0, 2.0, 3.0], source="mangadex", language="pt-br")
    assert len(ids) == 3
    items = q.list_items()
    chapters = sorted(i["chapter_number"] for i in items if i["series"] == "Dandadan")
    assert chapters == [1.0, 2.0, 3.0]
    assert all(i["status"] == "queued" for i in items)


def test_enqueue_none_creates_single_series_row():
    q = DownloadQueue()
    ids = q.enqueue("One Piece", None)
    assert len(ids) == 1
    item = [i for i in q.list_items() if i["id"] == ids[0]][0]
    assert item["chapter_number"] is None


def test_next_queued_is_fifo_and_mark_advances():
    q = DownloadQueue()
    a, b = q.enqueue("S", [1.0, 2.0])
    nxt = q.next_queued()
    assert nxt["id"] == a
    q.mark(a, "done")
    assert q.next_queued()["id"] == b


def test_cancel_retry_remove_clear():
    q = DownloadQueue()
    a, b = q.enqueue("S", [1.0, 2.0])
    q.cancel_item(a)
    assert [i for i in q.list_items() if i["id"] == a][0]["status"] == "cancelled"
    q.retry_item(a)
    assert [i for i in q.list_items() if i["id"] == a][0]["status"] == "queued"
    q.mark(b, "done")
    q.clear_finished()
    remaining = {i["id"] for i in q.list_items()}
    assert b not in remaining and a in remaining
    q.remove_item(a)
    assert not q.list_items()


def test_requeue_stale_resets_downloading():
    q = DownloadQueue()
    (a,) = q.enqueue("S", [1.0])
    q.mark(a, "downloading")
    q.requeue_stale()
    assert q.next_queued()["id"] == a

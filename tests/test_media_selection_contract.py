import os

os.environ["DISABLE_QUEUE_WORKER"] = "1"

from app import app
from app.process_manager import downloader
from app.utils import normalize_media_item


def test_normalize_media_categories_use_structural_fields():
    album = normalize_media_item({
        "id": "a1",
        "type": "albums",
        "attributes": {"name": "Video in the title", "albumType": "single"},
    })
    video = normalize_media_item({
        "id": "v1",
        "type": "music-videos",
        "attributes": {"name": "A normal title"},
    })
    unknown = normalize_media_item({"id": "u1", "type": "relationships"})

    assert album["category"] == "single"
    assert album["isVideo"] is False
    assert video["category"] == "music_video"
    assert video["isVideo"] is True
    assert unknown["category"] == "unknown"
    assert unknown["selectable"] is False


def test_submit_selection_returns_explicit_success_contract(monkeypatch):
    downloader.needs_input = True
    downloader.selection_id = "selection-test"
    downloader.input_options = [{"id": "1", "category": "album", "selectable": True}]
    monkeypatch.setattr(downloader, "write_input", lambda value: True)

    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    response = app.test_client().post(
        "/submit_selection",
        data={"selection": "1", "selection_id": "selection-test"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "accepted": True,
        "request_id": "selection-test",
        "task_ids": [],
        "message": "Seleção adicionada à fila",
    }


def test_submit_selection_rejects_stale_or_unknown_ids(monkeypatch):
    downloader.needs_input = True
    downloader.selection_id = "selection-current"
    downloader.input_options = [{"id": "1", "category": "album", "selectable": True}]
    monkeypatch.setattr(downloader, "write_input", lambda value: True)

    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    client = app.test_client()
    stale = client.post(
        "/submit_selection",
        data={"selection": "1", "selection_id": "selection-old"},
    )
    unknown = client.post(
        "/submit_selection",
        data={"selection": "9", "selection_id": "selection-current"},
    )

    assert stale.status_code == 409
    assert stale.get_json()["error_code"] == "STALE_SELECTION"
    assert unknown.status_code == 400
    assert unknown.get_json()["error_code"] == "INVALID_SELECTION"

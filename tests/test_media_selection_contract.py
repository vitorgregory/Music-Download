import os

os.environ["DISABLE_QUEUE_WORKER"] = "1"

from app import app
from app.process_manager import downloader
from app.utils import normalize_media_item, normalize_release_type


def test_normalize_release_type_uses_track_count_and_duration():
    assert normalize_release_type("album", track_count=3, total_duration_sec=900) == "single"
    assert normalize_release_type("album", track_count=4, total_duration_sec=1500) == "ep"
    assert normalize_release_type("album", track_count=7, total_duration_sec=1500) == "album"
    assert normalize_release_type("album", track_count=3, total_duration_sec=1800) == "album"
    assert normalize_release_type("music-video", track_count=1, total_duration_sec=240) == "music_video"
    assert normalize_release_type("album") == "unknown"


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
    assert album["kind"] == "single"
    assert album["isVideo"] is False
    assert video["category"] == "music_video"
    assert video["isVideo"] is True
    assert unknown["category"] == "unknown"
    assert unknown["selectable"] is True


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
        "selection_id": "selection-test",
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

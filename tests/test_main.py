import json
import pytest
from unittest.mock import AsyncMock, patch
from starlette.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from apps.server.main import app, room_manager


@pytest.fixture(autouse=True)
def reset_room_manager():
    room_manager._rooms.clear()
    room_manager._ws_to_room.clear()
    yield
    room_manager._rooms.clear()
    room_manager._ws_to_room.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _patch_gemini():
    return patch("apps.server.main.start_gemini_sessions", new_callable=AsyncMock)


# --- HTTP ---

async def test_index_serves_html():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/")
        assert resp.status_code == 200
        assert "html" in resp.headers.get("content-type", "").lower()


async def test_languages_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/languages")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 50
        codes = {l["code"] for l in data}
        assert "en" in codes
        assert "ja" in codes
        # Check structure
        entry = data[0]
        assert "code" in entry
        assert "name" in entry
        assert "native_name" in entry
        assert "flag" in entry
        assert "bcp47" in entry
        assert "recommended" in entry


# --- Create Room ---

def test_create_room(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "create_room", "language": "en"}))
        data = json.loads(ws.receive_text())
        assert data["type"] == "room_created"
        assert len(data["room"]) == 6


def test_create_room_any_language(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "create_room", "language": "fr"}))
        data = json.loads(ws.receive_text())
        assert data["type"] == "room_created"


# --- Join Room ---

def test_join_room(client):
    with _patch_gemini():
        with client.websocket_connect("/ws") as ws_a:
            ws_a.send_text(json.dumps({"type": "create_room", "language": "en"}))
            create_data = json.loads(ws_a.receive_text())
            room_code = create_data["room"]

            with client.websocket_connect("/ws") as ws_b:
                ws_b.send_text(json.dumps({"type": "join_room", "room": room_code, "language": "ja"}))
                b_data = json.loads(ws_b.receive_text())
                assert b_data["type"] == "room_joined"
                assert b_data["participants"] == 2

                a_data = json.loads(ws_a.receive_text())
                assert a_data["type"] == "room_joined"

                b_started = json.loads(ws_b.receive_text())
                assert b_started["type"] == "call_started"
                a_started = json.loads(ws_a.receive_text())
                assert a_started["type"] == "call_started"

                # Graceful leave to avoid deadlock on disconnect
                ws_b.send_text(json.dumps({"type": "leave"}))
                peer_msg = json.loads(ws_a.receive_text())
                assert peer_msg["type"] == "peer_disconnected"


def test_join_room_not_found(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join_room", "room": "XXXXXX", "language": "ja"}))
        data = json.loads(ws.receive_text())
        assert data["type"] == "error"
        assert "not found" in data["message"]


def test_join_room_full(client):
    with _patch_gemini():
        with client.websocket_connect("/ws") as ws1:
            ws1.send_text(json.dumps({"type": "create_room", "language": "en"}))
            data = json.loads(ws1.receive_text())
            room_code = data["room"]

            with client.websocket_connect("/ws") as ws2:
                ws2.send_text(json.dumps({"type": "join_room", "room": room_code, "language": "ja"}))
                ws2.receive_text()  # room_joined
                ws1.receive_text()  # room_joined
                ws2.receive_text()  # call_started
                ws1.receive_text()  # call_started

                with client.websocket_connect("/ws") as ws3:
                    ws3.send_text(json.dumps({"type": "join_room", "room": room_code, "language": "en"}))
                    err = json.loads(ws3.receive_text())
                    assert err["type"] == "error"
                    assert "full" in err["message"]

                # Graceful leave
                ws2.send_text(json.dumps({"type": "leave"}))
                ws1.receive_text()  # peer_disconnected


def test_join_room_any_language_pair(client):
    """Any two languages can be paired in a room."""
    with _patch_gemini():
        with client.websocket_connect("/ws") as ws1:
            ws1.send_text(json.dumps({"type": "create_room", "language": "fr"}))
            data = json.loads(ws1.receive_text())
            room_code = data["room"]

            with client.websocket_connect("/ws") as ws2:
                ws2.send_text(json.dumps({"type": "join_room", "room": room_code, "language": "de"}))
                b_data = json.loads(ws2.receive_text())
                assert b_data["type"] == "room_joined"
                assert b_data["language"] == "de"
                assert b_data["peer_language"] == "fr"

                ws1.receive_text()  # room_joined
                ws2.receive_text()  # call_started
                ws1.receive_text()  # call_started

                ws2.send_text(json.dumps({"type": "leave"}))
                ws1.receive_text()  # peer_disconnected


# --- Audio routing ---

def test_audio_routing(client):
    with _patch_gemini():
        with client.websocket_connect("/ws") as ws_a:
            ws_a.send_text(json.dumps({"type": "create_room", "language": "en"}))
            data = json.loads(ws_a.receive_text())
            room_code = data["room"]

            with client.websocket_connect("/ws") as ws_b:
                ws_b.send_text(json.dumps({"type": "join_room", "room": room_code, "language": "ja"}))
                ws_b.receive_text()  # room_joined
                ws_a.receive_text()  # room_joined
                ws_b.receive_text()  # call_started
                ws_a.receive_text()  # call_started

                room = list(room_manager._rooms.values())[0]
                mock_session = AsyncMock()
                room.session_a_to_b = mock_session

                ws_a.send_bytes(b'\x00' * 3200)

                # Graceful cleanup
                ws_b.send_text(json.dumps({"type": "leave"}))
                ws_a.receive_text()  # peer_disconnected


def test_audio_before_room_ignored(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_bytes(b'\x00' * 3200)
        ws.send_text(json.dumps({"type": "create_room", "language": "en"}))
        data = json.loads(ws.receive_text())
        assert data["type"] == "room_created"


# --- Signaling ---

def test_unknown_message_type(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "unknown_thing"}))
        data = json.loads(ws.receive_text())
        assert data["type"] == "error"
        assert "Unknown" in data["message"]


# --- Leave / Disconnect ---

def test_leave_message(client):
    with _patch_gemini():
        with client.websocket_connect("/ws") as ws_a:
            ws_a.send_text(json.dumps({"type": "create_room", "language": "en"}))
            data = json.loads(ws_a.receive_text())
            room_code = data["room"]

            with client.websocket_connect("/ws") as ws_b:
                ws_b.send_text(json.dumps({"type": "join_room", "room": room_code, "language": "ja"}))
                ws_b.receive_text()  # room_joined
                ws_a.receive_text()  # room_joined
                ws_b.receive_text()  # call_started
                ws_a.receive_text()  # call_started

                ws_b.send_text(json.dumps({"type": "leave"}))
                peer_msg = json.loads(ws_a.receive_text())
                assert peer_msg["type"] == "peer_disconnected"


def test_disconnect_cleanup(client):
    with client.websocket_connect("/ws") as ws_a:
        ws_a.send_text(json.dumps({"type": "create_room", "language": "en"}))
        data = json.loads(ws_a.receive_text())
        room_code = data["room"]
        assert room_code in room_manager._rooms

    # After disconnect, room should be cleaned up
    assert room_code not in room_manager._rooms


# --- Full lifecycle ---

def test_full_lifecycle(client):
    with _patch_gemini():
        with client.websocket_connect("/ws") as ws_a:
            ws_a.send_text(json.dumps({"type": "create_room", "language": "en"}))
            create_data = json.loads(ws_a.receive_text())
            assert create_data["type"] == "room_created"
            room_code = create_data["room"]

            with client.websocket_connect("/ws") as ws_b:
                ws_b.send_text(json.dumps({"type": "join_room", "room": room_code, "language": "ja"}))
                b_joined = json.loads(ws_b.receive_text())
                assert b_joined["type"] == "room_joined"
                a_joined = json.loads(ws_a.receive_text())
                assert a_joined["type"] == "room_joined"

                b_started = json.loads(ws_b.receive_text())
                assert b_started["type"] == "call_started"
                a_started = json.loads(ws_a.receive_text())
                assert a_started["type"] == "call_started"

                # Leave gracefully
                ws_b.send_text(json.dumps({"type": "leave"}))
                peer_msg = json.loads(ws_a.receive_text())
                assert peer_msg["type"] == "peer_disconnected"

            assert len(room_manager._rooms) == 0

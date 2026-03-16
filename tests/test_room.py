import time
import pytest
from unittest.mock import AsyncMock
from apps.server.room import Room, RoomManager, _generate_code


@pytest.fixture
def manager():
    return RoomManager()


@pytest.fixture
def ws_a():
    return AsyncMock()


@pytest.fixture
def ws_b():
    return AsyncMock()


# --- Code generation ---

def test_generate_code_length():
    code = _generate_code()
    assert len(code) == 6


def test_generate_code_alphanumeric():
    code = _generate_code()
    assert code.isalnum()
    assert code == code.upper()


# --- Room properties ---

def test_room_empty():
    room = Room(code="ABC123")
    assert room.participant_count == 0
    assert not room.is_full


def test_room_one_user():
    ws = AsyncMock()
    room = Room(code="ABC123", user_a=ws, lang_a="en")
    assert room.participant_count == 1
    assert not room.is_full


def test_room_full():
    room = Room(code="ABC123", user_a=AsyncMock(), user_b=AsyncMock(), lang_a="en", lang_b="ja")
    assert room.participant_count == 2
    assert room.is_full


# --- Room methods ---

def test_get_peer(ws_a, ws_b):
    room = Room(code="ABC123", user_a=ws_a, user_b=ws_b, lang_a="en", lang_b="ja")
    assert room.get_peer(ws_a) is ws_b
    assert room.get_peer(ws_b) is ws_a
    assert room.get_peer(AsyncMock()) is None


def test_get_language(ws_a, ws_b):
    room = Room(code="ABC123", user_a=ws_a, user_b=ws_b, lang_a="en", lang_b="ja")
    assert room.get_language(ws_a) == "en"
    assert room.get_language(ws_b) == "ja"
    assert room.get_language(AsyncMock()) is None


def test_get_peer_language(ws_a, ws_b):
    room = Room(code="ABC123", user_a=ws_a, user_b=ws_b, lang_a="en", lang_b="ja")
    assert room.get_peer_language(ws_a) == "ja"
    assert room.get_peer_language(ws_b) == "en"


def test_get_session_for_user(ws_a, ws_b):
    room = Room(code="ABC123", user_a=ws_a, user_b=ws_b, lang_a="en", lang_b="ja")
    mock_session_ab = AsyncMock()
    mock_session_ba = AsyncMock()
    room.session_a_to_b = mock_session_ab
    room.session_b_to_a = mock_session_ba
    assert room.get_session_for_user(ws_a) is mock_session_ab
    assert room.get_session_for_user(ws_b) is mock_session_ba
    assert room.get_session_for_user(AsyncMock()) is None


def test_touch():
    room = Room(code="ABC123")
    old = room.last_activity
    time.sleep(0.01)
    room.touch()
    assert room.last_activity > old


# --- RoomManager create ---

def test_create_room(manager, ws_a):
    room = manager.create_room(ws_a, "en")
    assert len(room.code) == 6
    assert room.user_a is ws_a
    assert room.lang_a == "en"
    assert room.user_b is None
    assert room.lang_b is None


def test_create_room_any_language(manager, ws_a):
    room = manager.create_room(ws_a, "fr")
    assert room.user_a is ws_a
    assert room.lang_a == "fr"


# --- RoomManager join ---

def test_join_room(manager, ws_a, ws_b):
    room = manager.create_room(ws_a, "en")
    joined, assigned = manager.join_room(room.code, ws_b, "ja")
    assert joined.is_full
    assert joined.user_b is ws_b
    assert joined.lang_b == "ja"
    assert assigned == "ja"


def test_join_room_not_found(manager, ws_b):
    with pytest.raises(ValueError, match="not found"):
        manager.join_room("XXXXXX", ws_b, "ja")


def test_join_room_full(manager, ws_a, ws_b):
    room = manager.create_room(ws_a, "en")
    manager.join_room(room.code, ws_b, "ja")
    with pytest.raises(ValueError, match="full"):
        manager.join_room(room.code, AsyncMock(), "en")


def test_join_room_any_language_pair(manager, ws_a, ws_b):
    """Any two languages can be paired."""
    room = manager.create_room(ws_a, "fr")
    joined, assigned = manager.join_room(room.code, ws_b, "de")
    assert joined.is_full
    assert joined.lang_a == "fr"
    assert joined.lang_b == "de"


# --- RoomManager lookup and remove ---

def test_get_room_for_ws(manager, ws_a):
    room = manager.create_room(ws_a, "en")
    found = manager.get_room_for_ws(ws_a)
    assert found is room
    assert manager.get_room_for_ws(AsyncMock()) is None


def test_remove_user(manager, ws_a, ws_b):
    room = manager.create_room(ws_a, "en")
    manager.join_room(room.code, ws_b, "ja")
    removed_room = manager.remove_user(ws_a)
    assert removed_room is room
    assert room.user_a is None
    assert room.lang_a is None
    assert room.user_b is ws_b
    assert manager.get_room_for_ws(ws_a) is None


# --- Stale cleanup ---

def test_cleanup_stale_rooms(manager, ws_a):
    room = manager.create_room(ws_a, "en")
    room.last_activity = time.time() - 1000
    stale = manager.cleanup_stale_rooms(max_age=500)
    assert room.code in stale
    assert manager.get_room_for_ws(ws_a) is None

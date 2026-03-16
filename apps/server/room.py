import random
import string
import time
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class Room:
    code: str
    user_a: Any = None
    user_b: Any = None
    lang_a: Optional[str] = None
    lang_b: Optional[str] = None
    session_a_to_b: Any = None
    session_b_to_a: Any = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    @property
    def is_full(self) -> bool:
        return self.user_a is not None and self.user_b is not None

    @property
    def participant_count(self) -> int:
        count = 0
        if self.user_a is not None:
            count += 1
        if self.user_b is not None:
            count += 1
        return count

    def get_peer(self, ws) -> Optional[Any]:
        if ws is self.user_a:
            return self.user_b
        if ws is self.user_b:
            return self.user_a
        return None

    def get_language(self, ws) -> Optional[str]:
        if ws is self.user_a:
            return self.lang_a
        if ws is self.user_b:
            return self.lang_b
        return None

    def get_peer_language(self, ws) -> Optional[str]:
        if ws is self.user_a:
            return self.lang_b
        if ws is self.user_b:
            return self.lang_a
        return None

    def get_session_for_user(self, ws) -> Optional[Any]:
        """Get the translation session for this user's audio (their lang -> peer's lang)."""
        if ws is self.user_a:
            return self.session_a_to_b
        if ws is self.user_b:
            return self.session_b_to_a
        return None

    def touch(self):
        self.last_activity = time.time()


def _generate_code(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


class RoomManager:
    def __init__(self):
        self._rooms: dict[str, Room] = {}
        self._ws_to_room: dict[Any, str] = {}

    def create_room(self, ws, language: str) -> Room:
        code = _generate_code()
        while code in self._rooms:
            code = _generate_code()

        room = Room(code=code, user_a=ws, lang_a=language)
        self._rooms[code] = room
        self._ws_to_room[id(ws)] = code
        return room

    def join_room(self, code: str, ws, language: str) -> tuple[Room, str]:
        """Join a room. Returns (room, assigned_language)."""
        room = self._rooms.get(code)
        if room is None:
            raise ValueError(f"Room '{code}' not found.")
        if room.is_full:
            raise ValueError(f"Room '{code}' is full.")

        room.user_b = ws
        room.lang_b = language

        self._ws_to_room[id(ws)] = code
        room.touch()
        return room, language

    def get_room_for_ws(self, ws) -> Optional[Room]:
        code = self._ws_to_room.get(id(ws))
        if code is None:
            return None
        return self._rooms.get(code)

    def remove_user(self, ws) -> Optional[Room]:
        code = self._ws_to_room.pop(id(ws), None)
        if code is None:
            return None
        room = self._rooms.get(code)
        if room is None:
            return None

        if ws is room.user_a:
            room.user_a = None
            room.lang_a = None
        elif ws is room.user_b:
            room.user_b = None
            room.lang_b = None

        return room

    def delete_room(self, code: str):
        room = self._rooms.pop(code, None)
        if room is None:
            return
        for ws in [room.user_a, room.user_b]:
            if ws is not None:
                self._ws_to_room.pop(id(ws), None)

    def cleanup_stale_rooms(self, max_age: float) -> list[str]:
        now = time.time()
        stale = [code for code, room in self._rooms.items()
                 if now - room.last_activity > max_age]
        for code in stale:
            self.delete_room(code)
        return stale

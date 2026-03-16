import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.server.room import RoomManager
from apps.server.config import get_languages_list, get_language_name
from apps.server.gemini_session import GeminiSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
room_manager = RoomManager()

app.mount("/static", StaticFiles(directory="apps/web"), name="static")


@app.get("/")
async def index():
    return FileResponse("apps/web/index.html")


@app.get("/api/languages")
async def languages():
    return JSONResponse(get_languages_list())


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket connected")

    try:
        while True:
            message = await ws.receive()

            if "bytes" in message and message["bytes"]:
                await handle_audio(ws, message["bytes"])
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                await handle_signaling(ws, data)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        if "disconnect" in str(e).lower():
            logger.info("WebSocket disconnected")
        else:
            logger.error(f"WebSocket error: {e}")
    finally:
        await handle_disconnect(ws)


async def handle_signaling(ws: WebSocket, data: dict):
    msg_type = data.get("type")

    if msg_type == "create_room":
        await handle_create_room(ws, data)
    elif msg_type == "join_room":
        await handle_join_room(ws, data)
    elif msg_type == "leave":
        await handle_disconnect(ws)
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


async def handle_create_room(ws: WebSocket, data: dict):
    language = data.get("language", "en")
    try:
        room = room_manager.create_room(ws, language)
        await ws.send_json({"type": "room_created", "room": room.code})
        logger.info(f"Room {room.code} created by {get_language_name(language)} speaker")
    except Exception as e:
        await ws.send_json({"type": "error", "message": str(e)})


async def handle_join_room(ws: WebSocket, data: dict):
    code = data.get("room", "").upper()
    language = data.get("language", "en")
    try:
        room, assigned_language = room_manager.join_room(code, ws, language)
        await ws.send_json({
            "type": "room_joined",
            "room": room.code,
            "participants": room.participant_count,
            "language": assigned_language,
            "peer_language": room.lang_a,
        })

        # Notify the other user
        peer = room.get_peer(ws)
        if peer:
            try:
                await peer.send_json({
                    "type": "room_joined",
                    "room": room.code,
                    "participants": room.participant_count,
                    "peer_language": room.lang_b,
                })
            except Exception:
                pass

        # Start Gemini sessions if room is full
        if room.is_full:
            try:
                await start_gemini_sessions(room)
            except Exception as e:
                logger.error(f"Failed to start Gemini sessions for room {room.code}: {e}")
                for user in [room.user_a, room.user_b]:
                    if user:
                        try:
                            await user.send_json({"type": "error", "message": f"Could not start translation: {e}"})
                        except Exception:
                            pass
                return
            for user in [room.user_a, room.user_b]:
                if user:
                    try:
                        await user.send_json({"type": "call_started"})
                    except Exception:
                        pass
            logger.info(f"Call started in room {room.code}: {room.lang_a} <-> {room.lang_b}")
    except Exception as e:
        await ws.send_json({"type": "error", "message": str(e)})


async def start_gemini_sessions(room):
    """Create and start two Gemini translation sessions for the room."""

    # A→B: user_a's audio (lang_a) → translated to lang_b → sent to user_b
    async def a_to_b_on_audio(data: bytes):
        try:
            await room.user_b.send_bytes(data)
        except Exception:
            pass

    async def a_to_b_on_transcript(direction: str, text: str):
        for user in [room.user_a, room.user_b]:
            try:
                await user.send_json({"type": "transcript", "direction": direction, "text": text})
            except Exception:
                pass

    async def a_to_b_on_turn_complete():
        for user in [room.user_a, room.user_b]:
            try:
                await user.send_json({"type": "turn_complete"})
            except Exception:
                pass

    async def a_to_b_on_error(e: Exception):
        logger.error(f"{room.lang_a}→{room.lang_b} Gemini error: {e}")

    # B→A: user_b's audio (lang_b) → translated to lang_a → sent to user_a
    async def b_to_a_on_audio(data: bytes):
        try:
            await room.user_a.send_bytes(data)
        except Exception:
            pass

    async def b_to_a_on_transcript(direction: str, text: str):
        for user in [room.user_b, room.user_a]:
            try:
                await user.send_json({"type": "transcript", "direction": direction, "text": text})
            except Exception:
                pass

    async def b_to_a_on_turn_complete():
        for user in [room.user_a, room.user_b]:
            try:
                await user.send_json({"type": "turn_complete"})
            except Exception:
                pass

    async def b_to_a_on_error(e: Exception):
        logger.error(f"{room.lang_b}→{room.lang_a} Gemini error: {e}")

    room.session_a_to_b = GeminiSession(
        source_lang=room.lang_a,
        target_lang=room.lang_b,
        on_audio=a_to_b_on_audio,
        on_transcript=a_to_b_on_transcript,
        on_turn_complete=a_to_b_on_turn_complete,
        on_error=a_to_b_on_error,
    )
    room.session_b_to_a = GeminiSession(
        source_lang=room.lang_b,
        target_lang=room.lang_a,
        on_audio=b_to_a_on_audio,
        on_transcript=b_to_a_on_transcript,
        on_turn_complete=b_to_a_on_turn_complete,
        on_error=b_to_a_on_error,
    )

    await room.session_a_to_b.start()
    await room.session_b_to_a.start()


_audio_log_counter = 0
_audio_no_room_logged = set()  # track ws ids that already logged "no room"

async def handle_audio(ws: WebSocket, data: bytes):
    global _audio_log_counter
    room = room_manager.get_room_for_ws(ws)
    if room is None:
        ws_id = id(ws)
        if ws_id not in _audio_no_room_logged:
            _audio_no_room_logged.add(ws_id)
            logger.warning("Audio received but no room found for ws (suppressing further)")
        return

    language = room.get_language(ws)
    _audio_log_counter += 1
    if _audio_log_counter <= 5 or _audio_log_counter % 100 == 0:
        logger.info(f"Audio from {language} speaker: {len(data)} bytes (msg #{_audio_log_counter})")

    session = room.get_session_for_user(ws)
    if session:
        await session.send_audio(data)

    room.touch()


async def handle_disconnect(ws: WebSocket):
    room = room_manager.remove_user(ws)
    if room is None:
        return

    # Close Gemini sessions
    for session in [room.session_a_to_b, room.session_b_to_a]:
        if session:
            try:
                await session.close()
            except Exception:
                pass

    # Notify peer
    peer = room.user_a or room.user_b
    if peer:
        try:
            await peer.send_json({"type": "peer_disconnected"})
        except Exception:
            pass

    room_manager.delete_room(room.code)
    logger.info(f"Room {room.code} cleaned up")

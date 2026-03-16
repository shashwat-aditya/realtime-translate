import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


class FakeGeminiLiveSession:
    def __init__(self):
        self.sent_audio = []
        self._responses = asyncio.Queue()

    async def send_realtime_input(self, **kwargs):
        self.sent_audio.append(kwargs)

    async def receive(self):
        while True:
            resp = await self._responses.get()
            if resp is None:
                return
            yield resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def fake_session():
    return FakeGeminiLiveSession()


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()
    return ws


@pytest.fixture
def fake_gemini_response():
    def make(data=None, input_transcript=None, output_transcript=None, turn_complete=False):
        response = MagicMock()
        response.data = data
        has_server_content = input_transcript or output_transcript or turn_complete
        if has_server_content:
            sc = MagicMock()
            if input_transcript:
                sc.input_transcription = MagicMock(text=input_transcript)
            else:
                sc.input_transcription = None
            if output_transcript:
                sc.output_transcription = MagicMock(text=output_transcript)
            else:
                sc.output_transcription = None
            sc.turn_complete = turn_complete
            response.server_content = sc
        else:
            response.server_content = None
        return response
    return make


@pytest.fixture
def room_manager():
    from apps.server.room import RoomManager
    return RoomManager()

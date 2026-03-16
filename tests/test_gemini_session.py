import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from apps.server.gemini_session import GeminiSession
from tests.conftest import FakeGeminiLiveSession


def _make_session(fake_live_session, **callback_overrides):
    """Helper to create a GeminiSession with a patched Gemini client."""
    callbacks = {
        "on_audio": AsyncMock(),
        "on_transcript": AsyncMock(),
        "on_turn_complete": AsyncMock(),
        "on_error": AsyncMock(),
    }
    callbacks.update(callback_overrides)
    session = GeminiSession(source_lang="en", target_lang="ja", **callbacks)
    return session, callbacks, fake_live_session


def _patch_client(fake_live_session):
    """Return a patch context that makes genai.Client return our fake session."""
    mock_client = MagicMock()
    # client.aio.live.connect() returns an async context manager
    connect_cm = MagicMock()
    connect_cm.__aenter__ = AsyncMock(return_value=fake_live_session)
    connect_cm.__aexit__ = AsyncMock(return_value=None)
    mock_client.aio.live.connect.return_value = connect_cm
    return patch("apps.server.gemini_session.genai.Client", return_value=mock_client)


@pytest.fixture
def fake_live():
    return FakeGeminiLiveSession()


# --- Unit tests ---

async def test_start_connects(fake_live):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()
    assert session._session is fake_live
    assert session._running is True
    await session.close()


async def test_start_spawns_receive_task(fake_live):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()
    assert session._receive_task is not None
    assert not session._receive_task.done()
    await session.close()


async def test_send_audio_forwards(fake_live):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()
    audio_data = b'\x00' * 3200
    await session.send_audio(audio_data)
    assert len(fake_live.sent_audio) == 1
    assert fake_live.sent_audio[0]["media"].data == audio_data
    await session.close()


async def test_send_audio_noop_when_closed(fake_live):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()
    await session.close()
    await session.send_audio(b'\x00' * 3200)
    assert len(fake_live.sent_audio) == 0


async def test_receive_dispatches_audio(fake_live, fake_gemini_response):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()

    audio_bytes = b'\x01\x02\x03'
    await fake_live._responses.put(fake_gemini_response(data=audio_bytes))
    await fake_live._responses.put(None)  # end stream
    await asyncio.sleep(0.05)

    callbacks["on_audio"].assert_awaited_with(audio_bytes)
    await session.close()


async def test_receive_dispatches_input_transcript(fake_live, fake_gemini_response):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()

    await fake_live._responses.put(fake_gemini_response(input_transcript="Hello"))
    await fake_live._responses.put(None)
    await asyncio.sleep(0.05)

    callbacks["on_transcript"].assert_awaited_with("input", "Hello")
    await session.close()


async def test_receive_dispatches_output_transcript(fake_live, fake_gemini_response):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()

    await fake_live._responses.put(fake_gemini_response(output_transcript="こんにちは"))
    await fake_live._responses.put(None)
    await asyncio.sleep(0.05)

    callbacks["on_transcript"].assert_awaited_with("output", "こんにちは")
    await session.close()


async def test_receive_dispatches_turn_complete(fake_live, fake_gemini_response):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()

    await fake_live._responses.put(fake_gemini_response(turn_complete=True))
    await fake_live._responses.put(None)
    await asyncio.sleep(0.05)

    callbacks["on_turn_complete"].assert_awaited()
    await session.close()


async def test_error_calls_on_error(fake_live):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()

    # Simulate an error by making receive raise
    error = RuntimeError("connection lost")

    async def bad_receive():
        raise error
        yield  # make it a generator

    fake_live.receive = bad_receive
    # Cancel current task and re-enter
    session._receive_task.cancel()
    try:
        await session._receive_task
    except asyncio.CancelledError:
        pass
    session._running = True
    session._closed = False
    # Patch _reconnect to also fail so retries exhaust quickly
    async def fail_reconnect():
        raise RuntimeError("reconnect failed")
    session._reconnect = fail_reconnect
    session._receive_task = asyncio.create_task(session._receive_loop())
    # Wait for reconnect attempts to exhaust (1s sleep between each, 3 max)
    await asyncio.sleep(3.5)

    callbacks["on_error"].assert_awaited()
    await session.close()


async def test_close_cancels_task(fake_live):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()
    task = session._receive_task
    await session.close()
    assert task.done()


async def test_close_is_idempotent(fake_live):
    session, callbacks, _ = _make_session(fake_live)
    with _patch_client(fake_live):
        await session.start()
    await session.close()
    await session.close()  # Should not raise
    assert session._closed is True

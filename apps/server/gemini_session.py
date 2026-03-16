import asyncio
import logging
from typing import Callable, Optional

from google import genai
from google.genai import types

from apps.server.config import get_gemini_config, get_api_key, MODEL, INPUT_MIME_TYPE

logger = logging.getLogger(__name__)


class GeminiSession:
    def __init__(
        self,
        source_lang: str,
        target_lang: str,
        on_audio: Callable[[bytes], None],
        on_transcript: Callable[[str, str], None],
        on_turn_complete: Callable[[], None],
        on_error: Callable[[Exception], None],
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.direction = f"{source_lang}_to_{target_lang}"
        self.on_audio = on_audio
        self.on_transcript = on_transcript
        self.on_turn_complete = on_turn_complete
        self.on_error = on_error

        self._config = get_gemini_config(source_lang, target_lang)
        self._client = None
        self._connect_cm = None
        self._session = None
        self._receive_task: Optional[asyncio.Task] = None
        self._running = False
        self._closed = False
        self._send_error_logged = False
        self._send_count = 0

    async def start(self):
        self._client = genai.Client(api_key=get_api_key())
        self._connect_cm = self._client.aio.live.connect(
            model=MODEL, config=self._config
        )
        self._session = await self._connect_cm.__aenter__()
        self._running = True
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info(f"GeminiSession started: {self.direction}")

    async def send_audio(self, pcm_data: bytes):
        if self._closed or self._session is None:
            return
        self._send_count += 1
        if self._send_count <= 3 or self._send_count % 100 == 0:
            logger.info(f"[{self.direction}] send_audio #{self._send_count}: {len(pcm_data)} bytes")
        try:
            await self._session.send_realtime_input(
                media=types.Blob(data=pcm_data, mime_type=INPUT_MIME_TYPE)
            )
        except Exception as e:
            if not self._send_error_logged:
                self._send_error_logged = True
                logger.error(f"[{self.direction}] Error sending audio (suppressing further): {e}")
            self._closed = True

    async def _reconnect(self):
        """Tear down the old connection and establish a new one."""
        if self._connect_cm:
            try:
                await self._connect_cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._client = genai.Client(api_key=get_api_key())
        self._connect_cm = self._client.aio.live.connect(
            model=MODEL, config=self._config
        )
        self._session = await self._connect_cm.__aenter__()
        self._send_error_logged = False
        self._send_count = 0
        self._closed = False

    async def _receive_loop(self):
        audio_chunk_count = 0
        reconnect_attempts = 0
        max_reconnects = 3
        try:
            logger.info(f"Receive loop started: {self.direction}")
            while self._running:
                logger.info(f"[{self.direction}] Waiting for Gemini responses...")
                try:
                    async for response in self._session.receive():
                        if not self._running:
                            break
                        reconnect_attempts = 0  # reset on successful response

                        # Log raw response for debugging
                        has_data = response.data is not None
                        has_sc = response.server_content is not None
                        if has_data or has_sc:
                            logger.info(f"[{self.direction}] Response: data={has_data}, server_content={has_sc}")

                        if response.server_content:
                            sc = response.server_content

                            # Audio comes via model_turn.parts[].inline_data
                            if hasattr(sc, 'model_turn') and sc.model_turn:
                                for part in sc.model_turn.parts:
                                    if hasattr(part, 'inline_data') and part.inline_data:
                                        audio_chunk_count += 1
                                        if audio_chunk_count <= 3 or audio_chunk_count % 50 == 0:
                                            logger.info(f"[{self.direction}] Audio #{audio_chunk_count}: {len(part.inline_data.data)} bytes")
                                        try:
                                            await self.on_audio(part.inline_data.data)
                                        except Exception as e:
                                            logger.warning(f"on_audio callback failed: {e}")

                        elif response.data:
                            # Fallback: some SDK versions put audio here
                            audio_chunk_count += 1
                            try:
                                await self.on_audio(response.data)
                            except Exception as e:
                                logger.warning(f"on_audio callback failed: {e}")

                        if response.server_content:
                            sc = response.server_content

                            if sc.input_transcription and sc.input_transcription.text:
                                logger.info(f"[{self.direction}] Input transcript: {sc.input_transcription.text}")
                                try:
                                    await self.on_transcript("input", sc.input_transcription.text)
                                except Exception:
                                    logger.warning("on_transcript callback failed")

                            if sc.output_transcription and sc.output_transcription.text:
                                logger.info(f"[{self.direction}] Output transcript: {sc.output_transcription.text}")
                                try:
                                    await self.on_transcript("output", sc.output_transcription.text)
                                except Exception:
                                    logger.warning("on_transcript callback failed")

                            if sc.turn_complete:
                                logger.info(f"[{self.direction}] Turn complete")
                                try:
                                    await self.on_turn_complete()
                                except Exception:
                                    logger.warning("on_turn_complete callback failed")

                    logger.info(f"[{self.direction}] session.receive() exhausted, looping back")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if not self._running:
                        break
                    reconnect_attempts += 1
                    if reconnect_attempts > max_reconnects:
                        logger.error(f"[{self.direction}] Max reconnects ({max_reconnects}) exceeded, giving up: {e}")
                        self._closed = True
                        try:
                            await self.on_error(e)
                        except Exception:
                            pass
                        break
                    logger.warning(f"[{self.direction}] Session error (attempt {reconnect_attempts}/{max_reconnects}), reconnecting: {e}")
                    self._closed = True  # stop send_audio during reconnect
                    try:
                        await asyncio.sleep(1)
                        await self._reconnect()
                        logger.info(f"[{self.direction}] Reconnected successfully")
                    except Exception as re:
                        logger.error(f"[{self.direction}] Reconnect failed: {re}")
                        try:
                            await self.on_error(re)
                        except Exception:
                            pass
                        break
        except asyncio.CancelledError:
            logger.info(f"[{self.direction}] Receive loop cancelled")

    async def close(self):
        if not self._running and self._closed:
            return
        self._closed = True
        self._running = False
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._connect_cm:
            try:
                await self._connect_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._connect_cm = None
            self._session = None

"""
Minimal feasibility test for Gemini Live API translation.
Speak English into your mic → hear Japanese from your speaker.

Usage:
  pip install google-genai pyaudio
  export GEMINI_API_KEY=your_key
  python feasibility_test.py [--to-english]

Default: EN → JA (you speak English, hear Japanese)
With --to-english: JA → EN (you speak Japanese, hear English)
"""

import sys
import os
import time
import threading
import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- Config ---
load_dotenv()
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("Set GEMINI_API_KEY environment variable")
    sys.exit(1)

TO_ENGLISH = "--to-english" in sys.argv

if TO_ENGLISH:
    SYSTEM = """You are a strict speech translator. Your ONLY function is translation.

RULES:
- You receive audio in Japanese.
- You output the EXACT same meaning in English. Nothing more.
- NEVER answer questions. NEVER have a conversation. NEVER add your own words.
- NEVER say things like "sure", "okay", "here's the translation".
- If someone says "こんにちは、予約したいのですが", you say "Hello, I'd like to make a reservation." and NOTHING else.
- You are a transparent translation layer. Act as if you don't exist."""
    OUTPUT_LANG = "en-US"
    print("Mode: Japanese → English")
    print("Speak Japanese into your mic...")
else:
    SYSTEM = """You are a strict speech translator. Your ONLY function is translation.

RULES:
- You receive audio in English.
- You output the EXACT same meaning in Japanese. Nothing more.
- NEVER answer questions. NEVER have a conversation. NEVER add your own words.
- NEVER say things like "sure", "okay", "here's the translation".
- If someone says "I'd like to book a table for two on Friday at 7pm", you say "金曜日の午後7時に2名で予約したいのですが" and NOTHING else.
- You are a transparent translation layer. Act as if you don't exist."""
    OUTPUT_LANG = "ja-JP"
    print("Mode: English → Japanese")
    print("Speak English into your mic...")

MODEL = "gemini-2.5-flash-native-audio-latest"

# Audio settings
INPUT_RATE = 16000
INPUT_CHANNELS = 1
INPUT_FORMAT = pyaudio.paInt16
INPUT_CHUNK = 1600  # 100ms chunks

OUTPUT_RATE = 24000
OUTPUT_CHANNELS = 1
OUTPUT_FORMAT = pyaudio.paInt16

# --- Audio setup ---
pa = pyaudio.PyAudio()

output_stream = pa.open(
    format=OUTPUT_FORMAT,
    channels=OUTPUT_CHANNELS,
    rate=OUTPUT_RATE,
    output=True,
    frames_per_buffer=4800,
)

input_stream = pa.open(
    format=INPUT_FORMAT,
    channels=INPUT_CHANNELS,
    rate=INPUT_RATE,
    input=True,
    frames_per_buffer=INPUT_CHUNK,
)

# --- Gemini client ---
client = genai.Client(api_key=API_KEY)

config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=types.Content(
        parts=[types.Part(text=SYSTEM)]
    ),
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
        ),
        language_code=OUTPUT_LANG,
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(),
    output_audio_transcription=types.AudioTranscriptionConfig(),
)


async def run():
    import asyncio

    print(f"\nConnecting to {MODEL}...")

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("Connected! Start speaking. Press Ctrl+C to stop.\n")

        got_first_audio = False
        turn_start_time = None
        is_speaking = True

        async def send_audio():
            nonlocal is_speaking
            while True:
                data = await asyncio.to_thread(input_stream.read, INPUT_CHUNK, exception_on_overflow=False)
                is_speaking = True
                await session.send_realtime_input(
                    media=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                )

        async def receive_audio():
            nonlocal got_first_audio, turn_start_time, is_speaking
            turn_count = 0
            while True:
                async for response in session.receive():
                    # Detect when model starts processing (input transcription complete)
                    if response.server_content and response.server_content.input_transcription:
                        transcript = response.server_content.input_transcription.text
                        if transcript:
                            turn_start_time = time.time()
                            is_speaking = False
                            print(f"  [heard]: {transcript}")

                    if response.data:
                        if not got_first_audio and turn_start_time is not None:
                            got_first_audio = True
                            latency = time.time() - turn_start_time
                            print(f"  ⏱  Translation latency: {latency:.2f}s")
                        await asyncio.to_thread(output_stream.write, response.data)

                    if response.server_content and response.server_content.output_transcription:
                        transcript = response.server_content.output_transcription.text
                        if transcript:
                            print(f"  [said]: {transcript}")

                    if response.server_content and response.server_content.turn_complete:
                        turn_count += 1
                        print(f"  --- turn {turn_count} complete ---\n")
                        got_first_audio = False
                        turn_start_time = None

        sender = asyncio.create_task(send_audio())
        receiver = asyncio.create_task(receive_audio())

        try:
            await asyncio.gather(sender, receiver)
        except (KeyboardInterrupt, asyncio.CancelledError):
            sender.cancel()
            receiver.cancel()
            print("\nStopped.")


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        pa.terminate()

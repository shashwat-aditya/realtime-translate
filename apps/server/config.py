import os
from dotenv import load_dotenv
from google.genai import types

load_dotenv()

# Model
MODEL = "gemini-2.5-flash-native-audio-latest"
VOICE = "Kore"

# Audio format constants (fixed by Gemini Live API)
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
INPUT_CHANNELS = 1
OUTPUT_CHANNELS = 1
BIT_DEPTH = 16
BYTES_PER_SAMPLE = BIT_DEPTH // 8
INPUT_CHUNK_SAMPLES = 1600  # 100ms at 16kHz
INPUT_CHUNK_BYTES = INPUT_CHUNK_SAMPLES * BYTES_PER_SAMPLE  # 3200
INPUT_CHUNK_DURATION_MS = 100
INPUT_MIME_TYPE = "audio/pcm;rate=16000"

# All Gemini-supported languages: code -> (name, native_name, flag_emoji, bcp47_code)
LANGUAGES = {
    "af": ("Afrikaans", "Afrikaans", "\U0001F1FF\U0001F1E6", "af-ZA"),
    "am": ("Amharic", "\u12A0\u121B\u122D\u129B", "\U0001F1EA\U0001F1F9", "am-ET"),
    "ar": ("Arabic", "\u0627\u0644\u0639\u0631\u0628\u064A\u0629", "\U0001F1F8\U0001F1E6", "ar-SA"),
    "az": ("Azerbaijani", "Az\u0259rbaycanca", "\U0001F1E6\U0001F1FF", "az-AZ"),
    "bg": ("Bulgarian", "\u0411\u044A\u043B\u0433\u0430\u0440\u0441\u043A\u0438", "\U0001F1E7\U0001F1EC", "bg-BG"),
    "bn": ("Bengali", "\u09AC\u09BE\u0982\u09B2\u09BE", "\U0001F1E7\U0001F1E9", "bn-BD"),
    "bs": ("Bosnian", "Bosanski", "\U0001F1E7\U0001F1E6", "bs-BA"),
    "ca": ("Catalan", "Catal\u00E0", "\U0001F1EA\U0001F1F8", "ca-ES"),
    "cs": ("Czech", "\u010Ce\u0161tina", "\U0001F1E8\U0001F1FF", "cs-CZ"),
    "cy": ("Welsh", "Cymraeg", "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F", "cy-GB"),
    "da": ("Danish", "Dansk", "\U0001F1E9\U0001F1F0", "da-DK"),
    "de": ("German", "Deutsch", "\U0001F1E9\U0001F1EA", "de-DE"),
    "el": ("Greek", "\u0395\u03BB\u03BB\u03B7\u03BD\u03B9\u03BA\u03AC", "\U0001F1EC\U0001F1F7", "el-GR"),
    "en": ("English", "English", "\U0001F1FA\U0001F1F8", "en-US"),
    "es": ("Spanish", "Espa\u00F1ol", "\U0001F1EA\U0001F1F8", "es-ES"),
    "et": ("Estonian", "Eesti", "\U0001F1EA\U0001F1EA", "et-EE"),
    "eu": ("Basque", "Euskara", "\U0001F1EA\U0001F1F8", "eu-ES"),
    "fa": ("Persian", "\u0641\u0627\u0631\u0633\u06CC", "\U0001F1EE\U0001F1F7", "fa-IR"),
    "fi": ("Finnish", "Suomi", "\U0001F1EB\U0001F1EE", "fi-FI"),
    "fr": ("French", "Fran\u00E7ais", "\U0001F1EB\U0001F1F7", "fr-FR"),
    "ga": ("Irish", "Gaeilge", "\U0001F1EE\U0001F1EA", "ga-IE"),
    "gl": ("Galician", "Galego", "\U0001F1EA\U0001F1F8", "gl-ES"),
    "gu": ("Gujarati", "\u0A97\u0AC1\u0A9C\u0AB0\u0ABE\u0AA4\u0AC0", "\U0001F1EE\U0001F1F3", "gu-IN"),
    "he": ("Hebrew", "\u05E2\u05D1\u05E8\u05D9\u05EA", "\U0001F1EE\U0001F1F1", "he-IL"),
    "hi": ("Hindi", "\u0939\u093F\u0928\u094D\u0926\u0940", "\U0001F1EE\U0001F1F3", "hi-IN"),
    "hr": ("Croatian", "Hrvatski", "\U0001F1ED\U0001F1F7", "hr-HR"),
    "hu": ("Hungarian", "Magyar", "\U0001F1ED\U0001F1FA", "hu-HU"),
    "hy": ("Armenian", "\u0540\u0561\u0575\u0565\u0580\u0565\u0576", "\U0001F1E6\U0001F1F2", "hy-AM"),
    "id": ("Indonesian", "Bahasa Indonesia", "\U0001F1EE\U0001F1E9", "id-ID"),
    "is": ("Icelandic", "\u00CDslenska", "\U0001F1EE\U0001F1F8", "is-IS"),
    "it": ("Italian", "Italiano", "\U0001F1EE\U0001F1F9", "it-IT"),
    "ja": ("Japanese", "\u65E5\u672C\u8A9E", "\U0001F1EF\U0001F1F5", "ja-JP"),
    "jv": ("Javanese", "Basa Jawa", "\U0001F1EE\U0001F1E9", "jv-ID"),
    "ka": ("Georgian", "\u10E5\u10D0\u10E0\u10D7\u10E3\u10DA\u10D8", "\U0001F1EC\U0001F1EA", "ka-GE"),
    "kk": ("Kazakh", "\u049A\u0430\u0437\u0430\u049B", "\U0001F1F0\U0001F1FF", "kk-KZ"),
    "km": ("Khmer", "\u1797\u17B6\u179F\u17B6\u1781\u17D2\u1798\u17C2\u179A", "\U0001F1F0\U0001F1ED", "km-KH"),
    "kn": ("Kannada", "\u0C95\u0CA8\u0CCD\u0CA8\u0CA1", "\U0001F1EE\U0001F1F3", "kn-IN"),
    "ko": ("Korean", "\uD55C\uAD6D\uC5B4", "\U0001F1F0\U0001F1F7", "ko-KR"),
    "lo": ("Lao", "\u0EA5\u0EB2\u0EA7", "\U0001F1F1\U0001F1E6", "lo-LA"),
    "lt": ("Lithuanian", "Lietuvi\u0173", "\U0001F1F1\U0001F1F9", "lt-LT"),
    "lv": ("Latvian", "Latvie\u0161u", "\U0001F1F1\U0001F1FB", "lv-LV"),
    "mk": ("Macedonian", "\u041C\u0430\u043A\u0435\u0434\u043E\u043D\u0441\u043A\u0438", "\U0001F1F2\U0001F1F0", "mk-MK"),
    "ml": ("Malayalam", "\u0D2E\u0D32\u0D2F\u0D3E\u0D33\u0D02", "\U0001F1EE\U0001F1F3", "ml-IN"),
    "mn": ("Mongolian", "\u041C\u043E\u043D\u0433\u043E\u043B", "\U0001F1F2\U0001F1F3", "mn-MN"),
    "mr": ("Marathi", "\u092E\u0930\u093E\u0920\u0940", "\U0001F1EE\U0001F1F3", "mr-IN"),
    "ms": ("Malay", "Bahasa Melayu", "\U0001F1F2\U0001F1FE", "ms-MY"),
    "mt": ("Maltese", "Malti", "\U0001F1F2\U0001F1F9", "mt-MT"),
    "my": ("Burmese", "\u1019\u103C\u1014\u103A\u1019\u102C", "\U0001F1F2\U0001F1F2", "my-MM"),
    "ne": ("Nepali", "\u0928\u0947\u092A\u093E\u0932\u0940", "\U0001F1F3\U0001F1F5", "ne-NP"),
    "nl": ("Dutch", "Nederlands", "\U0001F1F3\U0001F1F1", "nl-NL"),
    "no": ("Norwegian", "Norsk", "\U0001F1F3\U0001F1F4", "no-NO"),
    "pa": ("Punjabi", "\u0A2A\u0A70\u0A1C\u0A3E\u0A2C\u0A40", "\U0001F1EE\U0001F1F3", "pa-IN"),
    "pl": ("Polish", "Polski", "\U0001F1F5\U0001F1F1", "pl-PL"),
    "pt": ("Portuguese", "Portugu\u00EAs", "\U0001F1E7\U0001F1F7", "pt-BR"),
    "ro": ("Romanian", "Rom\u00E2n\u0103", "\U0001F1F7\U0001F1F4", "ro-RO"),
    "ru": ("Russian", "\u0420\u0443\u0441\u0441\u043A\u0438\u0439", "\U0001F1F7\U0001F1FA", "ru-RU"),
    "si": ("Sinhala", "\u0DC3\u0DD2\u0D82\u0DC4\u0DBD", "\U0001F1F1\U0001F1F0", "si-LK"),
    "sk": ("Slovak", "Sloven\u010Dina", "\U0001F1F8\U0001F1F0", "sk-SK"),
    "sl": ("Slovenian", "Sloven\u0161\u010Dina", "\U0001F1F8\U0001F1EE", "sl-SI"),
    "so": ("Somali", "Soomaali", "\U0001F1F8\U0001F1F4", "so-SO"),
    "sq": ("Albanian", "Shqip", "\U0001F1E6\U0001F1F1", "sq-AL"),
    "sr": ("Serbian", "\u0421\u0440\u043F\u0441\u043A\u0438", "\U0001F1F7\U0001F1F8", "sr-RS"),
    "su": ("Sundanese", "Basa Sunda", "\U0001F1EE\U0001F1E9", "su-ID"),
    "sv": ("Swedish", "Svenska", "\U0001F1F8\U0001F1EA", "sv-SE"),
    "sw": ("Swahili", "Kiswahili", "\U0001F1F0\U0001F1EA", "sw-KE"),
    "ta": ("Tamil", "\u0BA4\u0BAE\u0BBF\u0BB4\u0BCD", "\U0001F1EE\U0001F1F3", "ta-IN"),
    "te": ("Telugu", "\u0C24\u0C46\u0C32\u0C41\u0C17\u0C41", "\U0001F1EE\U0001F1F3", "te-IN"),
    "th": ("Thai", "\u0E44\u0E17\u0E22", "\U0001F1F9\U0001F1ED", "th-TH"),
    "tl": ("Filipino", "Filipino", "\U0001F1F5\U0001F1ED", "tl-PH"),
    "tr": ("Turkish", "T\u00FCrk\u00E7e", "\U0001F1F9\U0001F1F7", "tr-TR"),
    "uk": ("Ukrainian", "\u0423\u043A\u0440\u0430\u0457\u043D\u0441\u044C\u043A\u0430", "\U0001F1FA\U0001F1E6", "uk-UA"),
    "ur": ("Urdu", "\u0627\u0631\u062F\u0648", "\U0001F1F5\U0001F1F0", "ur-PK"),
    "uz": ("Uzbek", "O\u02BBzbekcha", "\U0001F1FA\U0001F1FF", "uz-UZ"),
    "vi": ("Vietnamese", "Ti\u1EBFng Vi\u1EC7t", "\U0001F1FB\U0001F1F3", "vi-VN"),
    "zh": ("Chinese", "\u4E2D\u6587", "\U0001F1E8\U0001F1F3", "zh-CN"),
    "zu": ("Zulu", "isiZulu", "\U0001F1FF\U0001F1E6", "zu-ZA"),
}

# Languages that have been tested and work well
RECOMMENDED_LANGUAGES = [
    "en", "ja", "es", "fr", "de", "it", "pt", "ko", "zh",
    "ar", "hi", "ru", "nl", "pl", "sv", "th", "tr", "vi",
]


def get_language_name(code: str) -> str:
    """Get the English name for a language code."""
    lang = LANGUAGES.get(code)
    if lang is None:
        return code.upper()
    return lang[0]


def get_language_info(code: str) -> dict | None:
    """Get full language info dict for a language code."""
    lang = LANGUAGES.get(code)
    if lang is None:
        return None
    return {
        "code": code,
        "name": lang[0],
        "native_name": lang[1],
        "flag": lang[2],
        "bcp47": lang[3],
    }


def get_languages_list() -> list[dict]:
    """Return all supported languages as a list of dicts for the API."""
    result = []
    for code, (name, native_name, flag, bcp47) in LANGUAGES.items():
        result.append({
            "code": code,
            "name": name,
            "native_name": native_name,
            "flag": flag,
            "bcp47": bcp47,
            "recommended": code in RECOMMENDED_LANGUAGES,
        })
    return result


def get_translation_prompt(source_lang: str, target_lang: str) -> str:
    """Generate a strict translator system prompt for any language pair."""
    source_name = get_language_name(source_lang)
    target_name = get_language_name(target_lang)
    return f"""You are a strict speech translator. Your ONLY function is translation.

RULES:
- You receive audio in {source_name}.
- You output the EXACT same meaning in {target_name}. Nothing more.
- NEVER answer questions. NEVER have a conversation. NEVER add your own words.
- NEVER say things like "sure", "okay", "here's the translation".
- You are a transparent translation layer. Act as if you don't exist."""


def get_gemini_config(source_lang: str, target_lang: str) -> types.LiveConnectConfig:
    """Return a LiveConnectConfig for translating from source_lang to target_lang.

    Args:
        source_lang: Language code of the input audio (e.g. "en", "ja").
        target_lang: Language code of the output audio (e.g. "ja", "en").

    Raises:
        ValueError: If either language code is not recognized.
    """
    if source_lang not in LANGUAGES:
        raise ValueError(f"Unsupported source language: {source_lang}")
    if target_lang not in LANGUAGES:
        raise ValueError(f"Unsupported target language: {target_lang}")

    system_prompt = get_translation_prompt(source_lang, target_lang)
    target_bcp47 = LANGUAGES[target_lang][3]

    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part(text=system_prompt)]
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            ),
            language_code=target_bcp47,
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


def get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    return key

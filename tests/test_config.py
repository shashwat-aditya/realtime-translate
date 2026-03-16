import pytest
from apps.server.config import (
    MODEL, VOICE, INPUT_SAMPLE_RATE, OUTPUT_SAMPLE_RATE,
    INPUT_CHUNK_BYTES, INPUT_CHUNK_SAMPLES, INPUT_CHUNK_DURATION_MS,
    BYTES_PER_SAMPLE, LANGUAGES, RECOMMENDED_LANGUAGES,
    get_gemini_config, get_translation_prompt, get_language_name,
    get_language_info, get_languages_list,
)


def test_default_constants():
    assert MODEL == "gemini-2.5-flash-native-audio-latest"
    assert VOICE == "Kore"
    assert INPUT_SAMPLE_RATE == 16000
    assert OUTPUT_SAMPLE_RATE == 24000
    assert INPUT_CHUNK_BYTES == 3200
    assert INPUT_CHUNK_SAMPLES == 1600


def test_languages_dict_has_entries():
    assert len(LANGUAGES) > 50
    assert "en" in LANGUAGES
    assert "ja" in LANGUAGES
    assert "es" in LANGUAGES


def test_language_tuple_format():
    for code, entry in LANGUAGES.items():
        assert len(entry) == 4, f"Language {code} should have 4 fields"
        name, native_name, flag, bcp47 = entry
        assert isinstance(name, str) and len(name) > 0
        assert isinstance(native_name, str) and len(native_name) > 0
        assert isinstance(flag, str)
        assert "-" in bcp47, f"BCP-47 code {bcp47} should contain a hyphen"


def test_recommended_languages_are_valid():
    for code in RECOMMENDED_LANGUAGES:
        assert code in LANGUAGES, f"Recommended language {code} not in LANGUAGES"


def test_get_language_name():
    assert get_language_name("en") == "English"
    assert get_language_name("ja") == "Japanese"
    assert get_language_name("zz") == "ZZ"  # unknown code


def test_get_language_info():
    info = get_language_info("en")
    assert info is not None
    assert info["code"] == "en"
    assert info["name"] == "English"
    assert info["bcp47"] == "en-US"
    assert get_language_info("zz") is None


def test_get_languages_list():
    langs = get_languages_list()
    assert len(langs) == len(LANGUAGES)
    codes = {l["code"] for l in langs}
    assert "en" in codes
    assert "ja" in codes
    # Check recommended flag
    en_entry = next(l for l in langs if l["code"] == "en")
    assert en_entry["recommended"] is True


def test_get_translation_prompt():
    prompt = get_translation_prompt("en", "ja")
    assert "English" in prompt
    assert "Japanese" in prompt
    assert "translator" in prompt.lower()


def test_get_gemini_config_en_to_ja():
    config = get_gemini_config("en", "ja")
    assert config.speech_config.language_code == "ja-JP"
    system_text = config.system_instruction.parts[0].text
    assert "English" in system_text
    assert "Japanese" in system_text


def test_get_gemini_config_ja_to_en():
    config = get_gemini_config("ja", "en")
    assert config.speech_config.language_code == "en-US"
    system_text = config.system_instruction.parts[0].text
    assert "Japanese" in system_text
    assert "English" in system_text


def test_get_gemini_config_any_pair():
    config = get_gemini_config("fr", "de")
    assert config.speech_config.language_code == "de-DE"
    system_text = config.system_instruction.parts[0].text
    assert "French" in system_text
    assert "German" in system_text


def test_get_gemini_config_invalid_source():
    with pytest.raises(ValueError, match="Unsupported source"):
        get_gemini_config("zz", "en")


def test_get_gemini_config_invalid_target():
    with pytest.raises(ValueError, match="Unsupported target"):
        get_gemini_config("en", "zz")


def test_input_chunk_math():
    assert INPUT_CHUNK_SAMPLES * BYTES_PER_SAMPLE == INPUT_CHUNK_BYTES
    assert INPUT_CHUNK_BYTES == 3200
    duration_ms = (INPUT_CHUNK_SAMPLES / INPUT_SAMPLE_RATE) * 1000
    assert duration_ms == INPUT_CHUNK_DURATION_MS == 100

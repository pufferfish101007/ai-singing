from typing import Dict, List, TypedDict
import os
from dotenv import load_dotenv
import base64
import csv
import requests
from util import error, strip_word
import json
from time import sleep

load_dotenv()

XI_API_KEY = os.getenv("XI_API_KEY")
VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel; see https://api.elevenlabs.io/v1/voices

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream/with-timestamps"

headers = {
    "Content-Type": "application/json",
    "xi-api-key": XI_API_KEY,
}

if not os.path.isdir(f'audio-cache-{VOICE_ID}'):
    os.mkdir(f'audio-cache-{VOICE_ID}')

class WordInfo(TypedDict):
    character_start_times: List[float]
    character_end_times: List[float]
    characters: List[str]
    audio_bytes: bytes

def cache_path(word: str) -> str:
    return f"audio-cache-{VOICE_ID}/{word}"

def get_cache(word: str) -> WordInfo | None:
    file = cache_path(word)
    if os.path.isfile(f"{file}.mp3"):
        info: WordInfo = { 'audio_bytes': b'', 'character_end_times': [], 'character_start_times': [], 'characters': [] }
        with open(f"{file}.mp3", "rb") as f:
            info["audio_bytes"] = base64.b64encode(f.read())
            f.seek(0)
        with open(f"{file}.csv", "r") as f:
            reader = csv.reader(f)
            info["character_start_times"] = list(map(float, reader.__next__()))
            info["character_end_times"] = list(map(float, reader.__next__()))
            info["characters"] = reader.__next__()
        return info
    else:
        return None


def streaming_tts(word: str, previous: str | None, next: str | None) -> WordInfo:
    response = requests.post(
        url,
        json={
            "text": word,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            "previous_text": previous,
            "next_words": next,
        },
        headers=headers,
        stream=True,
    )
    if response.status_code != 200:
        error(
            f"Error encountered, status: {response.status_code}, "
            f"content: {response.text}"
        )

    audio_bytes: bytes = b""
    character_start_times = []
    character_end_times = []
    characters = []

    for line in response.iter_lines():
        if line:  # filter out keep-alive new line
            # convert the response which contains bytes into a JSON string from utf-8 encoding
            json_string = line.decode("utf-8")

            # parse the JSON string and load the data as a dictionary
            response_dict = json.loads(json_string)

            # the "audio_base64" entry in the dictionary contains the audio as a base64 encoded string,
            # we need to decode it into bytes in order to save the audio as a file
            audio_bytes_chunk = base64.b64decode(response_dict["audio_base64"])
            audio_bytes += audio_bytes_chunk

            if response_dict["alignment"] is not None:
                character_start_times.extend(
                    response_dict["alignment"][
                        "character_start_times_seconds"
                    ]
                )
                character_end_times.extend(
                    response_dict["alignment"]["character_end_times_seconds"]
                )
                characters.extend(
                    response_dict["alignment"]["characters"]
                )
    return {
        "audio_bytes": audio_bytes,
        "character_start_times": character_start_times,
        "character_end_times": character_end_times,
        'characters': characters
    }


def tts(full_texts: Dict[str, List[str]]) -> Dict[str, WordInfo]:
    words_map: Dict[str, WordInfo] = {}

    for words in full_texts.values():
        for i, word in enumerate(words):
            stripped_word = strip_word(word)
            if stripped_word in words_map:
                continue
            cache = get_cache(stripped_word)
            if cache is not None:
                words_map[stripped_word] = cache
                continue

            word_info = streaming_tts(
                stripped_word,
                None if i == 0 else " ".join(words[:i]),
                " ".join(words[i + 1 :]) if i + 1 < len(words) else None,
            )

            words_map[stripped_word] = word_info

            with open(f"audio-cache-{VOICE_ID}/{stripped_word}.mp3", "wb") as f:
                f.write(word_info["audio_bytes"])
            with open(f"audio-cache-{VOICE_ID}/{stripped_word}.csv", "w") as f:
                writer = csv.writer(f)
                writer.writerow(word_info["character_start_times"])
                writer.writerow(word_info["character_end_times"])
                writer.writerow(word_info["characters"])

            sleep(0.2)  # try to avoid rate limits and be nice to elevenlabs' servers

    return words_map


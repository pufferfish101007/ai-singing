from sys import argv
from typing import List, cast
from util import error, s_to_ms, strip_word
from parse_mxml import events_from_mxml, Note, Pitch
from tts import tts, cache_path
import os
import audio
import librosa
import numpy as np

if len(argv) < 2:
    error("input xml file name needed")
if len(argv) < 3:
    error("you need to specify at least 1 part name to generate for")

file_name = argv[1]
part_names = argv[2:]

try:
    with open(f"{file_name}.musicxml") as file:
        xml_txt = file.read()
except:
    error(f"couldn't read file {file_name}.musicxml")

events = events_from_mxml(xml_txt, part_names, file_name)


def join_lyrics(evs: List[Note]) -> List[str]:
    words: List[str] = []
    curr_word_start_idx = 0
    prev_ev_idx = 0
    for i, event in enumerate(evs):
        if isinstance(event, Pitch):
            if event.lyric is not None:
                lyric = strip_word(event.lyric)
                match event.lyric_pos:
                    case 0:
                        words.append(lyric)
                        curr_word_start_idx = i
                        event.lyric_start_pos = 0
                        event.lyric_end_pos = len(lyric) - 1
                    case 3:
                        words.append(lyric)
                        event.lyric_word = lyric
                        event.lyric_start_pos = 0
                        event.lyric_end_pos = len(lyric) - 1
                    case 1:
                        words[-1] += lyric
                        event.lyric_start_pos = (
                            cast(Pitch, evs[prev_ev_idx]).lyric_end_pos + 1
                        )
                        event.lyric_end_pos = len(lyric) + event.lyric_start_pos - 1
                    case 2:
                        words[-1] += lyric
                        event.lyric_start_pos = (
                            cast(Pitch, evs[prev_ev_idx]).lyric_end_pos + 1
                        )
                        event.lyric_end_pos = len(lyric) + event.lyric_start_pos - 1
                        for j in range(curr_word_start_idx, i + 1):
                            cast(Pitch, evs[j]).lyric_word = words[-1]
            prev_ev_idx = i
    return words


for evs in events.values():
    for i in range(len(evs) - 1, -1, -1):
        ev = evs[i]
        if isinstance(ev, Pitch) and (ev.lyric is None or ev.lyric == ""):
            error("empty lyric")

full_texts = {part: join_lyrics(evs) for part, evs in events.items()}

print(full_texts)

words_map = tts(full_texts)

whole_audio = audio.AudioSegment.empty()

if not os.path.isdir("stretched"):
    os.mkdir("stretched")

target_sr = 44100

try:
    for i, evs in enumerate(events.values()):
        print(i)
        part_y = np.array([])
        for j, event in enumerate(evs):
            print(sum(event.duration))
            if isinstance(event, Pitch):
                print(event.lyric_word)
                if (word := strip_word(event.lyric_word)) not in words_map:
                    error(f'"{word}" not registered')

                word_info = words_map[word]

                word_audio = audio.load_audio(f"{cache_path(word)}.mp3")

                word_audio = audio.strip_silence(
                    audio.crop_audio(
                        word_audio,
                        s_to_ms(
                            word_info["character_start_times"][event.lyric_start_pos]
                        ),
                        s_to_ms(word_info["character_end_times"][event.lyric_end_pos]),
                    )
                )

                word_audio.export("tmp.wav", format="wav")

                y, sr = librosa.load("tmp.wav", sr=None)
                y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)

                stretched_y, sr = audio.stretch_audio(
                    y, float(target_sr), sum(event.duration) * 0.001
                )
                stretched_y = librosa.resample(
                    stretched_y, orig_sr=sr, target_sr=target_sr
                )

                tuned_y = np.array([])
                for i in range(len(event.duration)):
                    this_y = stretched_y[
                        int(sum(event.duration[:i]) * 0.001 * target_sr) : int(
                            sum(event.duration[: i + 1]) * 0.001 * target_sr
                        )
                    ]
                    # print(len(stretched_y), len(this_y), event.duration)
                    current_pitch = audio.detect_average_pitch(this_y, target_sr)
                    target_note = [
                        "A",
                        "Bb",
                        "B",
                        "C",
                        "C#",
                        "D",
                        "Eb",
                        "E",
                        "F",
                        "F#",
                        "G",
                        "Ab",
                    ][event.degree[i]]
                    target_pitch = librosa.note_to_hz(f"{target_note}{event.octave[i]}")
                    this_tuned_y, sr = audio.adjust_pitch(
                        this_y, float(target_sr), cast(float, target_pitch)
                    )
                    this_tuned_y = librosa.resample(
                        this_tuned_y, orig_sr=sr, target_sr=target_sr
                    )
                    tuned_y = np.append(tuned_y, this_tuned_y)

                # print('autotuned')

                # audio.save_audio(tuned_y, sr, 'tmp.wav')

                part_y = np.append(part_y, tuned_y)
            else:
                print("rest")
                silence = audio.AudioSegment.silent(duration=int(sum(event.duration)))
                silence.export("tmp.wav", format="wav")
                silence_y, sr = librosa.load("tmp.wav", sr=None)
                silence_y = librosa.resample(silence_y, orig_sr=sr, target_sr=target_sr)
                part_y = np.append(part_y, silence_y)
        audio.save_audio(part_y, target_sr, "tmp.wav")
        part_audio = audio.AudioSegment.from_file("tmp.wav", format="wav")
        if part_audio.duration_seconds > whole_audio.duration_seconds:
            whole_audio = part_audio.overlay(whole_audio)
        else:
            whole_audio = whole_audio.overlay(part_audio)
finally:
    whole_audio.export(f"{file_name}.wav", format="wav")

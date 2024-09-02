# with thanks to Mrs GPT for assisting with code generation for this file
from pydub import AudioSegment
import librosa
import numpy as np
from scipy.io.wavfile import write
from typing import Tuple
from pydub.silence import detect_leading_silence
import math

trim_leading_silence = lambda x: x[detect_leading_silence(x) :]
trim_trailing_silence = lambda x: trim_leading_silence(x.reverse()).reverse()
strip_silence = lambda x: trim_trailing_silence(trim_leading_silence(x))


def load_audio(mp3_path: str) -> AudioSegment:
    return AudioSegment.from_mp3(mp3_path)


def crop_audio(audio: AudioSegment, start_ms: int, end_ms: int) -> AudioSegment:
    return audio[start_ms:end_ms]


def stretch_audio(
    audio: np.ndarray, sr: float, target_duration: float
) -> Tuple[np.ndarray, float]:
    original_duration = librosa.get_duration(y=audio, sr=sr)
    rate = original_duration / target_duration
    y_stretched = librosa.effects.time_stretch(audio, rate=rate)
    return y_stretched, sr


def detect_average_pitch(audio: np.ndarray, sr: float) -> float:
    f0, voiced_flag, voiced_probs = librosa.pyin(
        audio, fmin=float(librosa.note_to_hz("C2")), fmax=float(librosa.note_to_hz("C7"))
    )
    f0 = f0[voiced_flag]  # Keep only voiced frames
    avg_pitch = np.nanmedian(f0)  # Compute the median of detected pitches, ignoring NaNs
    return avg_pitch


def adjust_pitch(y: np.ndarray, sr: float, target_pitch: float) -> Tuple[np.ndarray, float]:
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    # analyse in 0.1s chunks
    h_chunks = [y[i:i + int(0.1 * sr)] for i in range(0, len(y), int(0.1 * sr))]
    h_shifted = np.array([])
    for chunk in h_chunks:
        current_pitch = detect_average_pitch(chunk, sr)
        if math.isnan(current_pitch):
            #print('nan')
            h_shifted = np.append(h_shifted, chunk)
            continue
        n_steps = np.log2(target_pitch / current_pitch) * 12
        _shifted = librosa.effects.pitch_shift(chunk, sr=sr, n_steps=n_steps)
        h_shifted = np.append(h_shifted, _shifted)
    # save_audio(h_shifted, sr, 'tmp.wav')
    # save_audio(y_percussive, sr, 'tmp2.wav')
    # pd_shifted = AudioSegment.from_file('tmp.wav')
    # pd_percussive = AudioSegment.from_file('tmp2.wav')
    # pd_combined = pd_shifted.overlay(pd_percussive)
    # pd_combined.export("tmp.wav", format="wav")
    # new_y, new_sr = librosa.load("tmp.wav", sr=None)
    return h_shifted, float(sr)


def save_audio(y: np.ndarray, sr: int | float, file_name: str) -> None:
    write(file_name, int(sr), y.astype(np.float32))


def concatenate_audio(
    existing_audio_path: str, new_audio_path: str, output_path: str
) -> None:
    existing_audio = AudioSegment.from_file(existing_audio_path)
    new_audio = AudioSegment.from_file(new_audio_path)
    combined = existing_audio + new_audio
    combined.export(output_path, format="mp3")

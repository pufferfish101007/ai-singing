from sys import argv
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from os import getenv
import requests
import json
import base64
from audiostretchy.stretch import AudioStretch
from pydub import AudioSegment
from typing import Dict, List, cast, NoReturn
from io import BytesIO

load_dotenv()

def error(err: str) -> NoReturn:
  print(f"error: {err}")
  exit(1)

if len(argv) < 2:
  error('input xml file name needed')
if len(argv) < 3:
  error('you need to specify at least 1 part name to generate for')

file_name = argv[1]
part_names = argv[2:]

try:
  with open(file_name) as file:
    xml_txt = file.read()
except:
  error(f'couldn\'t read file {file_name}')

try:
  xml = ET.fromstring(xml_txt)
except:
  error(f'couldn\'t parse {file_name} as XML')

if xml.tag != 'score-partwise':
  error('expected root element to be score-partwise')
if xml.get('version') != '4.0':
  error('expected version to be 4.0')
part_list = xml.find('part-list')
if part_list is None:
  error('couldn\'t find part-list')
part_ids = list(map(lambda p: p.get('id'), filter(lambda p: (n := p.find('part-name')) is not None and n.text in part_names, part_list.iter("score-part"))))
if len(part_names) != len(part_ids):
  error('couldn\'t find some parts - make sure they are spelled correctly, unabbreviated, using correct capitalisation, and enclosed in "quotation marks" if needed')
print(part_ids)

class Note:
  def __init__(self, *, duration):
    # duration, in milliseconds
    self.duration: float = duration

class Rest(Note):
  def __init__(self, *, duration):
    super().__init__(duration=duration)

class Pitch(Note):
  def __init__(self, *, duration, degree, octave, lyric, lyric_pos):
    super().__init__(duration=duration)
    # degree of the chromatuc scale (A=0, Bb=11)
    self.degree: int = degree
    # octave (middle C is C4)
    self.octave: int = octave
    # one syllable of lyric
    self.lyric: str = lyric
    # position of lyric: 0=begin, 1=middle, 2=end, 3=single
    self.lyric_pos: int = lyric_pos
    # the following properties are updated once we've generated the speech
    self.lyric_word: str = '' # the full word this syllable is a part of
    self.lyric_start_pos: int = 0 # the character in the word this syllable starts at
    self.lyric_end_pos: int = 0 # the character in the word this syllable ends at
    self.lyric_start_time: float = 0 # this syllable's start time within the word audio
    self.lyric_end_time: float = 0 # this syllable's end time within the word audio
  def __str__(self):
    pitch = ['A', 'Bb', 'B', 'C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab'][self.degree]
    return f'"{"-" if self.lyric_pos in [0, 1] else ""}{self.lyric if self.lyric else "_"}"{"-" if self.lyric_pos in [1, 2] else ""} @ {pitch}{self.octave} for {self.duration}ms'

events: Dict[str, List[Note]] = {}

# note represented as { degree: int, octave: int }; degree is from 0 (A) to 11 (Bb)
for part in filter(lambda p: p.get('id') in part_ids, xml.iter('part')):
  part_id = part.get('id') or error('couldn\'t find part id')
  events[cast(str, part_id)] = []
  divisions = None
  tempo = 120 # in bpm
  for measure in part.iter('measure'):
    attrs = measure.find("attributes")
    division = attrs.find('divisions') if attrs is not None else None
    if divisions is not None and division is not None:
      error('divisions redefined for a part')
    if divisions is None:
      if division is None:
        error('missing divisions for a part')
      divisions = int(division.text or error('missing divisions'))
    for direction in measure.iter('direction'):
      sound = direction.find('sound')
      if sound is not None:
        tempo_val = sound.get('tempo')
        if tempo_val is not None:
          tempo = int(tempo_val)
    for note in measure.iter('note'):
      duration = int((note.find('duration') or error('couldn\'t find duration')).text or error('text is None')) / divisions * 60000 / tempo
      if note.find('rest') is not None:
        events[part_id].append(Rest(duration=duration))
      elif (pitch := note.find('pitch')) is not None:
        alter = int(cast(str, a.text)) if (a := pitch.find('alter')) is not None else 0
        degree = ({'A': 0, 'B': 2, 'C': 3, 'D': 5, 'E': 7, 'F': 8, 'G': 10 }[cast(str, (pitch.find('step') or error('coudldn\'t find step')).text)] + alter) % 12
        octave = int((pitch.find('octave') or error('couldn\'t find octave')).text or error('no octave text'))
        lyrics = note.find('lyric')
        if lyrics is not None:
          lyric: str | None = (lyrics.find('text') or error('no lyrics text')).text
          lyric_pos: int | None = ['begin', 'middle', 'end', 'single'].index((lyrics.find('syllabic') or error('couldn\'t find syllabic')).text or error('no syllabic text'))
        else:
          lyric, lyric_pos = None, None
        events[part_id].append(Pitch(degree=degree, octave=octave, lyric=lyric, lyric_pos=lyric_pos, duration=duration))

def join_lyrics(evs: List[Note]) -> List[str]:
  words: List[str] = []
  curr_word_start_idx = 0
  for (i, event) in enumerate(evs):
    if isinstance(event, Pitch):
      if event.lyric is not None:
        match event.lyric_pos:
          case 0:
            words.append(event.lyric)
            curr_word_start_idx = i
            event.lyric_start_pos = 0
            event.lyric_end_pos = len(event.lyric)
          case 3:
            words.append(event.lyric)
            event.lyric_word = event.lyric
            event.lyric_start_pos = 0
            event.lyric_end_pos = len(event.lyric)
          case 1:
            words[-1] += event.lyric
            event.lyric_start_pos = len(words[-1])
            event.lyric_end_pos = len(event.lyric) + len(words[-1])
          case 2:
            words[-1] += event.lyric
            event.lyric_start_pos = len(words[-1])
            event.lyric_end_pos = len(event.lyric) + len(words[-1])
            for j in range(curr_word_start_idx, i + 1):
              cast(Pitch, evs[j]).lyric = words[-1]
  return words

full_texts = { part: join_lyrics(evs) for part, evs in events.items() }

XI_API_KEY = getenv('XI_API_KEY')
VOICE_ID = 'ErXwobaYiN019PkySvjV' # Antoni; see https://api.elevenlabs.io/v1/voices

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"

headers = {
  "Content-Type": "application/json",
  "xi-api-key": XI_API_KEY
}

data = {
  "text": full_texts['P1'],
  "model_id": "eleven_multilingual_v2",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75
  }
}

words_map = {}

for words in full_texts.values():
  for word in words:
    if word.lower() in words_map:
      continue
    response = requests.post(
        url,
        json=data,
        headers=headers,
    )
    if response.status_code != 200:
      error(f"Error encountered, status: {response.status_code}, "
              f"content: {response.text}")

    json_string = response.content.decode("utf-8")
    response_dict = json.loads(json_string)
    audio_bytes = base64.b64decode(response_dict["audio_base64"])
    words_map[word.lower()] = {
      'audio_bytes': audio_bytes,
      'character_start_times': response_dict['character_start_times_seconds'],
      'character_end_times': response_dict['character_end_times_seconds'],
    }

whole_audio = AudioSegment.empty()

for evs in events.values():
  part_audio = AudioSegment.empty()
  for event in evs:
    if isinstance(event, Pitch):
      word_info = words_map[event.lyric_word]
      word_audio = AudioSegment(data=word_info['audio_bytes'])[word_info['character_start_times'][event.lyric_start_pos]:word_info['character_start_times'][event.lyric_end_pos]]
      whole_audio += word_audio
      wav_io = BytesIO()
      word_audio.export(wav_io, format="wav")
      wav_io.seek(0)
      audio_stretcher = AudioStretch().open_wav(wav_io)
    else:
      part_audio += AudioSegment.silent(duration=event.duration)
  if part_audio.duration_seconds() > whole_audio.duration_seconds():
    whole_audio = part_audio.overlay(whole_audio)
  else:
    whole_audio = whole_audio.overlay(part_audio)
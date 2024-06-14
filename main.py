from sys import argv
import xml.etree.ElementTree as ET

def error(err):
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
    self.duration = duration

class Rest(Note):
  def __init__(self, *, duration):
    super().__init__(duration=duration)

class Pitch(Note):
  def __init__(self, *, duration, degree, octave, lyric, lyric_pos):
    super().__init__(duration=duration)
    # degree of the chromatuc scale (A=0, Bb=11)
    self.degree = degree
    # octave (middle C is C4)
    self.octave = octave
    # one syllable of lyric
    self.lyric = lyric
    # position of lyric: 0=begin, 1=middle, 2=end, 3=single
    self.lyric_pos = lyric_pos
  def __str__(self):
    pitch = ['A', 'Bb', 'B', 'C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab'][self.degree]
    return f'"{"-" if self.lyric_pos in [0, 1] else ""}{self.lyric if self.lyric else "_"}"{"-" if self.lyric_pos in [1, 2] else ""} @ {pitch}{self.octave} for {self.duration}ms'

# note represented as { degree: int, octave: int }; degree is from 0 (A) to 11 (Bb)
for part in filter(lambda p: p.get('id') in part_ids, xml.iter('part')):
  events = [];
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
      divisions = int(division.text)
    for direction in measure.iter('direction'):
      sound = direction.find('sound')
      if sound is not None:
        tempo_val = sound.get('tempo')
        if tempo_val is not None:
          tempo = int(tempo_val)
    for note in measure.iter('note'):
      duration = int(note.find('duration').text) / divisions * 60000 / tempo
      if note.find('rest') is not None:
        events.append(Rest(duration=duration))
      elif (pitch := note.find('pitch')) is not None:
        alter = int(a.text) if (a := pitch.find('alter')) else 0
        degree = ({'A': 0, 'B': 2, 'C': 3, 'D': 5, 'E': 7, 'F': 8, 'G': 10 }[pitch.find('step').text] + alter) % 12
        octave = int(pitch.find('octave').text)
        lyrics = note.find('lyric')
        if lyrics is not None:
          lyric = lyrics.find('text').text
          lyric_pos = ['begin', 'middle', 'end', 'single'].index(lyrics.find('syllabic').text)
        events.append(Pitch(degree=degree, octave=octave, lyric=lyric, lyric_pos=lyric_pos, duration=duration))
print('\n'.join(map(str, events)))
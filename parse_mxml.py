from util import not_none, error
from typing import Dict, List, cast
import xml.etree.ElementTree as ET

"""Some sort of note event"""


class Note:
    def __init__(self, *, duration: List[float]):
        self.duration: List[float] = duration
        """durations, in milliseconds"""


class Rest(Note):
    """A rest; silence"""

    def __init__(self, *, duration: float):
        super().__init__(duration=[duration])

    def __str__(self):
        return f"rest for {self.duration[0]}ms"


class Pitch(Note):
    """A pitched note, with a lyric"""
    
    def __init__(
        self,
        *,
        duration: List[float],
        degree: List[int],
        octave: List[int],
        lyric: str | None,
        lyric_pos: int | None,
    ):
        super().__init__(duration=duration)

        self.degree: List[int] = degree
        """degree of the chromatuc scale (A=0, Bb=11)"""

        self.octave: List[int] = octave
        """octave (middle C is C4)"""

        self.lyric: str | None = lyric
        """one syllable of lyric"""

        self.lyric_pos: int | None = lyric_pos
        """position of lyric: 0=begin, 1=middle, 2=end, 3=single"""

        # the following properties are updated once we've generated the speech

        self.lyric_word: str = ""
        """the full word this syllable is a part of"""

        self.lyric_start_pos: int = 0
        """the character in the word this syllable starts at"""

        self.lyric_end_pos: int = 0
        """the character in the word this syllable ends at"""

        self.lyric_start_time: float = 0
        """this syllable's start time within the word audio"""

        self.lyric_end_time: float = 0
        """this syllable's end time within the word audio"""

    def __str__(self):
        pitch = ["A", "Bb", "B", "C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab"][
            self.degree
        ]
        return f'\'{"-" if self.lyric_pos in [1, 2] else ""}{self.lyric if self.lyric else "_"}\'{"-" if self.lyric_pos in [0, 1] else ""} @ {pitch}{self.octave} for {self.duration}ms'


def events_from_mxml(
    xml_txt: str, part_names: List[str], file_name: str
) -> Dict[str, List[Note]]:
    try:
        xml = ET.fromstring(xml_txt)
    except:
        error(f"couldn't parse {file_name} as XML")

    if xml.tag != "score-partwise":
        error("expected root element to be score-partwise")
    if xml.get("version") != "4.0":
        error("expected version to be 4.0")
    part_list = xml.find("part-list")
    if part_list is None:
        error("couldn't find part-list")
    part_ids = list(
        map(
            lambda p: p.get("id"),
            filter(
                lambda p: (n := p.find("part-name")) is not None
                and n.text in part_names,
                part_list.iter("score-part"),
            ),
        )
    )
    if len(part_names) != len(part_ids):
        error(
            "couldn't find some parts - make sure they are spelled correctly, unabbreviated, using correct capitalisation, and enclosed in 'quotation marks' if needed"
        )
    print(part_ids)

    events: Dict[str, List[Note]] = {}

    tempo = 126  # in bpm

    # note represented as { degree: int, octave: int }; degree is from 0 (A) to 11 (Bb)
    for part in filter(lambda p: p.get("id") in part_ids, xml.iter("part")):
        part_id = part.get("id") or error("couldn't find part id")
        events[cast(str, part_id)] = []
        divisions = None
        octave_change = -1
        for measure in part.iter("measure"):
            attrs = measure.find("attributes")
            division = attrs.find("divisions") if attrs is not None else None
            clef = attrs.find('clef') if attrs is not None else None
            octave_change_el = clef.find('clef-octave-change') if clef is not None else None
            # if octave_change_el is not None:
            #     octave_change_text = octave_change_el.text
            #     if octave_change_text == '':
            #         octave_change = 0
            #     elif octave_change_text is not None:
            #         octave_change = int(octave_change_text)
            if divisions is not None and division is not None:
                error("divisions redefined for a part")
            if divisions is None and division is None:
                error("missing divisions for a part")
            if division is not None:
                divisions = int(division.text or error("missing divisions"))
            # " The <divisions> element indicates how many divisions per quarter note [crotchet] are used to indicate a note's duration."
            for direction in measure.iter("direction"):
                sound = direction.find("sound")
                if sound is not None:
                    tempo_val = sound.get("tempo")
                    if tempo_val is not None:
                        tempo = int(tempo_val)
            for note in measure.iter("note"):
                duration = (
                    int(not_none((note.find("duration"))).text or error("text is None"))
                    / divisions
                    * 60000
                    / tempo
                )
                if note.find("rest") is not None:
                    events[part_id].append(Rest(duration=duration))
                elif (pitch := note.find("pitch")) is not None:
                    alter = (
                        int(cast(str, a.text))
                        if (a := pitch.find("alter")) is not None
                        else 0
                    )
                    degree = (
                        {"A": 0, "B": 2, "C": 3, "D": 5, "E": 7, "F": 8, "G": 10}[
                            cast(str, not_none(pitch.find("step")).text)
                        ]
                        + alter
                    ) % 12
                    octave = int(
                        not_none(pitch.find("octave")).text or error("no octave text")
                    ) + octave_change
                    lyrics = note.find("lyric")
                    if lyrics is not None:
                        lyric: str = not_none((not_none(lyrics.find("text"))).text)
                        lyric_pos: int = not_none([
                            "begin",
                            "middle",
                            "end",
                            "single",
                        ].index(
                            not_none((lyrics.find("syllabic"))).text
                            or error("no syllabic text")
                        ))
                        events[part_id].append(
                            Pitch(
                                degree=[degree],
                                octave=[octave],
                                lyric=lyric,
                                lyric_pos=lyric_pos,
                                duration=[duration],
                            )
                        )
                    else:
                        prev_event = events[part_id][-1]
                        if not isinstance(prev_event, Pitch):
                            error(f"previous event wasn't a pitch (in measure {measure.get('number')})")
                        prev_event.duration.append(duration)
                        prev_event.degree.append(degree)
                        prev_event.octave.append(octave)

    return events

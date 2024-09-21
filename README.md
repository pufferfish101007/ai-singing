# ai-singing

## prerequisits

- Python 3 (probably 3.10 or later?)
- [rubberband](https://breakfastquay.com/rubberband/)
- `pip install -r reqirements.txt`

## usage 

```sh
python3 main.py score-name "Part 1" ... "Part n"
```

Outputs to `score-name.wav`.

Requires an uncompressed MusicXML file (with a `.musicxml` extension). `.mxml` files must be unzipped first.

[`baa.musicxml`](./baa.musicxml) is a short arrangement of Baa Baa Black Sheep for TTB for testing purposes; [`baa.wav`](./baa.wav) is the output.

## feature completion (or, lack of)

This has been tested on files created using musescore 4. Any notatational errors will probably lead to an error and may be difficult to spot. Error output is very unhelpful at the moment. Tempo changes may or may not be supported; anything beyond basic notes and rests is probably not supported (e.g. ornamentation, dynamics etc.). Divisi is also not currently supported - but writing things in separate systems is fine. If you give the name of a part which is not actually a voice part, it will still attempt to produce audio for it.

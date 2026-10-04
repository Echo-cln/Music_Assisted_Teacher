"""不依赖付费音源的轻量乐谱导入与规则编曲核心。

它输出标准化 MIDI 音高/时值 JSON；浏览器负责即时试听，之后可接 FluidSynth
或学校已有音源服务导出高保真音频。
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET

PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _pitch(step: str, octave: int, alter: int = 0) -> int:
    return max(24, min(108, 12 * (octave + 1) + PITCH.get(step.upper(), 0) + alter))


def parse_note_text(value: str, tempo: int) -> list[dict]:
    """将 C4 D4 E4 G4 这类最适合课堂的输入转为四分音符旋律。"""
    notes, start, beat = [], 0.0, 60 / tempo
    for token in value.replace("，", " ").replace(",", " ").split():
        token = token.strip().upper()
        if token in {"R", "REST", "-"}:
            start += beat
            continue
        step, octave, alter = token[:1], 4, 0
        if step not in PITCH:
            continue
        remain = token[1:]
        if remain.startswith(('#', 'B')):
            alter = 1 if remain[0] == '#' else -1
            remain = remain[1:]
        if remain and remain.lstrip('-').isdigit():
            octave = int(remain)
        notes.append({"pitch": _pitch(step, octave, alter), "start": round(start, 3), "duration": round(beat, 3), "velocity": 92})
        start += beat
    return notes


def parse_musicxml(raw: bytes, tempo: int = 96) -> list[dict]:
    root = ET.fromstring(raw)
    divisions, cursor, last_start, notes = 1, 0.0, 0.0, []
    beat = 60 / tempo
    for elem in root.iter():
        if elem.tag.rsplit('}', 1)[-1] == 'sound' and elem.get('tempo'):
            tempo = max(40, min(220, int(float(elem.get('tempo')))))
            beat = 60 / tempo
    for measure in root.iter():
        if measure.tag.rsplit('}', 1)[-1] != 'measure':
            continue
        for child in measure:
            tag = child.tag.rsplit('}', 1)[-1]
            if tag == 'attributes':
                for item in child:
                    if item.tag.rsplit('}', 1)[-1] == 'divisions' and item.text:
                        divisions = max(1, int(item.text))
            if tag != 'note':
                continue
            data = {n.tag.rsplit('}', 1)[-1]: n for n in child}
            duration = float(data.get('duration').text) / divisions if data.get('duration') is not None else 1
            is_chord = 'chord' in data
            note_start = last_start if is_chord else cursor
            if 'rest' not in data and data.get('pitch') is not None:
                p = {n.tag.rsplit('}', 1)[-1]: n.text for n in data['pitch']}
                notes.append({"pitch": _pitch(p.get('step', 'C'), int(p.get('octave', 4)), int(p.get('alter', 0))), "start": round(note_start * beat, 3), "duration": round(duration * beat, 3), "velocity": 90})
            if not is_chord:
                last_start = cursor
                cursor += duration
    return notes


def _vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            break
    return value, pos


def parse_midi(raw: bytes) -> tuple[list[dict], int]:
    if raw[:4] != b'MThd':
        raise ValueError('不是标准 MIDI 文件')
    _, _, division = struct.unpack('>HHH', raw[8:14])
    division = max(1, division)
    pos, tempo, tick, active, notes = 14, 500000, 0, {}, []
    while pos + 8 <= len(raw):
        if raw[pos:pos + 4] != b'MTrk': break
        size = struct.unpack('>I', raw[pos + 4:pos + 8])[0]; end = pos + 8 + size; pos += 8
        running = None
        while pos < end:
            delta, pos = _vlq(raw, pos); tick += delta
            status = raw[pos]
            if status < 0x80:
                status = running
            else:
                pos += 1; running = status
            if status == 0xFF:
                meta = raw[pos]; pos += 1; n, pos = _vlq(raw, pos); payload = raw[pos:pos+n]; pos += n
                if meta == 0x51 and len(payload) == 3: tempo = int.from_bytes(payload, 'big')
                continue
            if status in (0xF0, 0xF7):
                n, pos = _vlq(raw, pos); pos += n; continue
            kind, channel = status & 0xF0, status & 0x0F
            key = raw[pos]; velocity = raw[pos + 1] if kind != 0xC0 and kind != 0xD0 else 0
            pos += 1 if kind in (0xC0, 0xD0) else 2
            token = (channel, key)
            if kind == 0x90 and velocity:
                active[token] = (tick, velocity)
            elif kind == 0x80 or (kind == 0x90 and not velocity):
                if token in active:
                    begin, vel = active.pop(token)
                    seconds = tempo / 1_000_000 / division
                    notes.append({"pitch": key, "start": round(begin * seconds, 3), "duration": round(max(1, tick-begin) * seconds, 3), "velocity": vel})
        pos = end
    return sorted(notes, key=lambda n: n['start']), max(40, min(220, round(60_000_000 / tempo)))


def arrange(melody: list[dict], tempo: int, style: str, instruments: list[str]) -> dict:
    """按实际旋律推断调性、逐小节选和弦，并为每个选中的乐器建立独立轨道。"""
    melody = sorted(melody, key=lambda n: n["start"])
    if not melody:
        return {"style": style, "tracks": []}
    beat, end = 60 / tempo, max(n["start"] + n["duration"] for n in melody)
    instruments = list(dict.fromkeys(instruments or ["piano"]))
    tracks = [{"id": "melody", "name": "主旋律（钢琴键位）", "instrument": "piano", "notes": melody}]
    pcs = [int(n["pitch"]) % 12 for n in melody]
    major, minor = {0, 2, 4, 5, 7, 9, 11}, {0, 2, 3, 5, 7, 8, 10}
    candidates = []
    for tonic in range(12):
        for mode, scale in (("major", major), ("minor", minor)):
            allowed = {(tonic + p) % 12 for p in scale}
            score = sum(2 for p in pcs if p in allowed) + sum(3 for p in pcs[-3:] if p == tonic) + (10 if pcs[-1] == tonic else 0)
            candidates.append((score, tonic, mode))
    _, tonic, mode = max(candidates)
    steps = [0, 2, 4, 5, 7, 9, 11] if mode == "major" else [0, 2, 3, 5, 7, 8, 10]
    recipes = {
        "乡土抒情": ([0, 5, 3, 4], "broken"),
        "欢快律动": ([0, 3, 4, 0], "pulse"),
        "童谣清新": ([0, 3, 0, 4], "simple"),
        "器乐合奏": ([0, 1, 4, 0], "sustain"),
    }
    preferred, texture = recipes.get(style, recipes["乡土抒情"])
    bars = max(1, int(end / (beat * 4)) + 1)
    chords = []
    for bar in range(bars):
        bar_pcs = [n["pitch"] % 12 for n in melody if bar * 4 * beat <= n["start"] < (bar + 1) * 4 * beat]
        def quality(degree: int):
            root = (tonic + steps[degree]) % 12
            triad = {root, (tonic + steps[(degree + 2) % 7]) % 12, (tonic + steps[(degree + 4) % 7]) % 12}
            return sum(5 for p in bar_pcs if p in triad) + (2 if degree == preferred[bar % len(preferred)] else 0)
        degree = max(range(7), key=quality)
        root = 48 + ((tonic + steps[degree]) % 12)
        third = 3 if ((tonic + steps[(degree + 2) % 7]) - (tonic + steps[degree])) % 12 == 3 else 4
        chords.append((root, third, 7))

    for instrument in [i for i in instruments if i in {"piano", "guzheng", "violin", "guitar", "erhu"}]:
        notes = []
        for bar, (root, third, fifth) in enumerate(chords):
            start_at = bar * 4 * beat
            if instrument == "guzheng":
                for index, offset in enumerate((0, third, fifth, third)):
                    notes.append({"pitch": root + offset + 12, "start": round(start_at + index * beat, 3), "duration": round(.82 * beat, 3), "velocity": 58})
            elif instrument == "guitar":
                for pulse in ((0, 2) if texture == "pulse" else (0,)):
                    for offset in (0, third, fifth): notes.append({"pitch": root + offset, "start": round(start_at + pulse * beat, 3), "duration": round((1.5 if texture == "pulse" else 3.4) * beat, 3), "velocity": 56})
            elif instrument == "violin":
                notes.append({"pitch": root + fifth + 12, "start": round(start_at, 3), "duration": round(3.7 * beat, 3), "velocity": 52})
            elif instrument == "erhu":
                for pulse in (0, 2): notes.append({"pitch": root - 12, "start": round(start_at + pulse * beat, 3), "duration": round(1.7 * beat, 3), "velocity": 64})
            else:
                for offset in (0, third, fifth): notes.append({"pitch": root + offset, "start": round(start_at, 3), "duration": round(3.55 * beat, 3), "velocity": 50})
        tracks.append({"id": instrument, "name": {"piano": "钢琴和声", "guzheng": "古筝分解和弦", "violin": "小提琴长音", "guitar": "吉他和弦", "erhu": "二胡低音"}[instrument], "instrument": instrument, "notes": notes})
    if "drum" in instruments:
        drum = [{"pitch": 36 if i % 4 == 0 else 42, "start": round(i * beat, 3), "duration": .12, "velocity": 76} for i in range(bars * 4)]
        tracks.append({"id": "drum", "name": "非洲鼓节奏", "instrument": "drum", "notes": drum})
    names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
    roots = [root for root, _, _ in chords]
    return {"style": style, "key": f"{names[tonic]}{'大调' if mode == 'major' else '小调'}", "chord_roots": roots, "instruments": instruments, "tracks": tracks, "tips": f"已按主旋律推断 {names[tonic]}{'大调' if mode == 'major' else '小调'}，逐小节匹配和弦；{style}使用 {texture} 织体。"}

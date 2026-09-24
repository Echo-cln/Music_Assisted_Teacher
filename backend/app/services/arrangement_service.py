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
    """把旋律转成可继续修改的低音、和声与节奏轨，不覆盖原旋律。"""
    melody = sorted(melody, key=lambda n: n['start'])
    if not melody:
        return {"style": style, "tracks": []}
    beat, end = 60 / tempo, max(n['start'] + n['duration'] for n in melody)
    tracks = [{"id": "melody", "name": "主旋律", "instrument": "piano", "notes": melody}]
    roots = [48, 53, 55, 48]
    bars = max(1, int(end / (beat * 4)) + 1)
    if any(i in instruments for i in ('piano', 'guzheng', 'erhu', 'violin')):
        instrument = next((i for i in instruments if i in ('guzheng', 'piano', 'erhu', 'violin')), 'piano')
        harmony = []
        for bar in range(bars):
            root = roots[bar % len(roots)]
            for offset in (0, 4, 7): harmony.append({"pitch": root+offset, "start": round(bar*4*beat, 3), "duration": round(3.6*beat, 3), "velocity": 54})
        tracks.append({"id": "harmony", "name": "和声织体", "instrument": instrument, "notes": harmony})
    bass = [{"pitch": roots[int(t['start']/(beat*4)) % len(roots)]-12, "start": round(t['start'],3), "duration": round(1.8*beat,3), "velocity": 68} for t in melody[::2]]
    tracks.append({"id": "bass", "name": "低音声部", "instrument": "erhu" if 'erhu' in instruments else "piano", "notes": bass})
    if 'drum' in instruments:
        drum = []
        for i in range(bars * 4):
            drum.append({"pitch": 36 if i % 2 == 0 else 42, "start": round(i*beat,3), "duration": .12, "velocity": 76})
        tracks.append({"id": "drum", "name": "非洲鼓节奏", "instrument": "drum", "notes": drum})
    return {"style": style, "tracks": tracks, "tips": "已生成可编辑的主旋律、和声、低音与节奏轨。课堂上可静音任一轨，再让学生分声部进入。"}


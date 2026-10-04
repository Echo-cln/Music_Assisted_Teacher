"""不依赖付费音源的轻量乐谱导入与规则编曲核心。

它输出标准化 MIDI 音高/时值 JSON；浏览器负责即时试听，之后可接 FluidSynth
或学校已有音源服务导出高保真音频。
"""
from __future__ import annotations

import math
import struct
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

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
    # .mxl 是压缩版 MusicXML。很多记谱软件和 Audiveris 都会导出它，
    # 因此不能把它当成普通 XML 直接喂给 ElementTree。
    if raw[:2] == b"PK":
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith((".musicxml", ".xml")) and not name.startswith("META-INF/")]
            if not names:
                raise ValueError("压缩 MusicXML 中没有可读取的乐谱 XML")
            raw = archive.read(names[0])
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
    """根据旋律逐小节选择和弦，并以不同织体生成可试听的独立轨道。

    规则的目标是“可解释的课堂伴奏”，不是把一个固定 I–IV–V–I 套到每首旋律：
    每个小节都记录所选和弦，前端会将其展示给教师核验。
    """
    melody = sorted(melody, key=lambda n: n['start'])
    if not melody:
        return {"style": style, "tracks": []}
    beat, end = 60 / tempo, max(n['start'] + n['duration'] for n in melody)
    bar_seconds = beat * 4
    instruments = list(dict.fromkeys(instruments or ["piano"]))
    tracks = [{"id": "melody", "name": "主旋律（钢琴键位）", "instrument": "piano", "notes": melody}]
    pcs = [int(n["pitch"]) % 12 for n in melody]
    major, minor = {0, 2, 4, 5, 7, 9, 11}, {0, 2, 3, 5, 7, 8, 10}
    candidates = []
    for tonic in range(12):
        for mode, scale in (("major", major), ("minor", minor)):
            allowed = {(tonic + p) % 12 for p in scale}
            # 终止音优先，避免 C–E–G–C 与多个平行调并列。
            # 全曲音阶覆盖比最后一个音更可靠；终止音只用于解决接近的候选调。
            score = sum(3 for p in pcs if p in allowed) + sum(2 for p in pcs[-3:] if p == tonic) + (6 if pcs[-1] == tonic else 0)
            candidates.append((score, tonic, mode))
    _, tonic, mode = max(candidates)
    steps = [0, 2, 4, 5, 7, 9, 11] if mode == "major" else [0, 2, 3, 5, 7, 8, 10]
    recipes = {
        "乡土抒情": {"degrees": [0, 5, 3, 4], "texture": "分解琶音与长音", "kind": "lyric"},
        "欢快律动": {"degrees": [0, 4, 5, 3], "texture": "切分扫弦与强弱鼓点", "kind": "rhythm"},
        "童谣清新": {"degrees": [0, 3, 0, 4], "texture": "简洁对答与轻拍节奏", "kind": "nursery"},
        "器乐合奏": {"degrees": [0, 1, 4, 0], "texture": "声部对位与延展和声", "kind": "ensemble"},
    }
    recipe = recipes.get(style, recipes["乡土抒情"])
    bars = max(1, math.ceil(end / bar_seconds))
    names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
    roots, chords, chord_labels = [], [], []
    for bar in range(bars):
        bar_pcs = [n["pitch"] % 12 for n in melody if bar * bar_seconds <= n["start"] < (bar + 1) * bar_seconds]

        def chord_for(degree: int) -> tuple[int, int, int, str]:
            root_pc = (tonic + steps[degree]) % 12
            third_pc = (tonic + steps[(degree + 2) % 7]) % 12
            fifth_pc = (tonic + steps[(degree + 4) % 7]) % 12
            third = 3 if (third_pc - root_pc) % 12 == 3 else 4
            fifth = (fifth_pc - root_pc) % 12
            suffix = "m" if third == 3 and fifth == 7 else "dim" if fifth == 6 else ""
            return root_pc, third, fifth, f"{names[root_pc]}{suffix}"

        def compatibility(degree: int) -> tuple[int, int]:
            root_pc, third, fifth, _ = chord_for(degree)
            triad = {root_pc, (root_pc + third) % 12, (root_pc + fifth) % 12}
            # 旋律音的归属优先；同分时才使用各主题的和弦偏好。
            support = sum(6 for p in bar_pcs if p in triad)
            anchor = sum(2 for p in set(bar_pcs) if p in triad)
            preference = 1 if degree == recipe["degrees"][bar % len(recipe["degrees"])] else 0
            return support + anchor, preference

        degree = max(range(7), key=compatibility)
        root_pc, third, fifth, label = chord_for(degree)
        root = 48 + root_pc
        roots.append(root)
        chords.append((root, third, fifth))
        chord_labels.append(label)

    def put(notes: list[dict], pitch: int, start: float, duration: float, velocity: int) -> None:
        notes.append({"pitch": max(24, min(108, pitch)), "start": round(start, 3), "duration": round(max(.06, duration), 3), "velocity": velocity})

    def add_track(instrument: str, name: str, notes: list[dict]):
        if notes:
            tracks.append({"id": instrument, "name": name, "instrument": instrument, "notes": notes})

    for instrument in [i for i in instruments if i in {"piano", "guzheng", "violin", "guitar", "erhu"}]:
        notes = []
        for bar, (root, third, fifth) in enumerate(chords):
            start, tone_kind = bar * bar_seconds, recipe["kind"]
            chord = (root, root + third, root + fifth)
            if instrument == "piano":
                if tone_kind == "lyric":
                    for idx, offset in enumerate((0, third, fifth, third)):
                        put(notes, root + offset + 12, start + idx * beat, .84 * beat, 58)
                elif tone_kind == "rhythm":
                    for pulse in (0, 1, 2, 3):
                        for pitch in chord: put(notes, pitch + 12, start + pulse * beat, .58 * beat, 54 if pulse % 2 else 68)
                elif tone_kind == "nursery":
                    put(notes, root, start, 1.7 * beat, 58)
                    for pitch in (root + third + 12, root + fifth + 12): put(notes, pitch, start + 2 * beat, 1.55 * beat, 50)
                else:
                    for pitch in chord: put(notes, pitch + 12, start, 3.75 * beat, 48)
            elif instrument == "guzheng":
                sequence = (0, third, fifth, third) if tone_kind == "lyric" else (0, fifth, third, fifth, 0, fifth, third, fifth) if tone_kind == "rhythm" else (0, fifth) if tone_kind == "nursery" else (0, fifth, third, fifth)
                spacing = 4 / len(sequence)
                for idx, offset in enumerate(sequence): put(notes, root + offset + 12, start + idx * spacing * beat, (.72 if tone_kind == "rhythm" else 1.25) * beat, 54)
            elif instrument == "guitar":
                pulses = (0, 2) if tone_kind == "lyric" else (0, .5, 1.5, 2, 2.5, 3.5) if tone_kind == "rhythm" else (0, 2) if tone_kind == "nursery" else (0, 1, 2, 3)
                duration = 1.45 * beat if tone_kind in {"lyric", "nursery"} else .62 * beat if tone_kind == "rhythm" else .9 * beat
                for pulse in pulses:
                    for pitch in chord: put(notes, pitch, start + pulse * beat, duration, 52 + int(pulse % 2 == 0) * 10)
            elif instrument == "violin":
                if tone_kind == "rhythm":
                    for pulse in (.5, 1.5, 2.5, 3.5): put(notes, root + fifth + 12, start + pulse * beat, .38 * beat, 48)
                elif tone_kind == "nursery":
                    put(notes, root + third + 12, start + 2 * beat, 1.6 * beat, 50)
                elif tone_kind == "ensemble":
                    put(notes, root + third + 12, start, 1.85 * beat, 48)
                    put(notes, root + fifth + 12, start + 2 * beat, 1.65 * beat, 52)
                else:
                    put(notes, root + fifth + 12, start, 3.7 * beat, 52)
            elif instrument == "erhu":
                if tone_kind == "ensemble":
                    for pulse, offset in ((.5, third + 12), (1.5, fifth + 12), (2.5, third + 12), (3.25, root + 12)): put(notes, root + offset, start + pulse * beat, .6 * beat, 54)
                elif tone_kind == "rhythm":
                    for pulse in (1, 3): put(notes, root + 12, start + pulse * beat, .72 * beat, 60)
                else:
                    put(notes, root - 12, start, 1.7 * beat, 62)
                    put(notes, root - 12, start + 2 * beat, 1.55 * beat, 58)
        add_track(instrument, {"piano": "钢琴伴奏", "guzheng": "古筝织体", "violin": "小提琴声部", "guitar": "原声吉他节奏", "erhu": "二胡声部"}[instrument], notes)
    if "drum" in instruments:
        drum = []
        for bar in range(bars):
            start, kind = bar * bar_seconds, recipe["kind"]
            pattern = ((0, 36, 88), (1, 42, 45), (2, 38, 68), (3, 42, 45)) if kind == "lyric" else ((0, 36, 90), (.5, 42, 45), (1, 38, 72), (1.5, 42, 45), (2, 36, 84), (2.5, 42, 45), (3, 38, 75), (3.5, 42, 50)) if kind == "rhythm" else ((0, 36, 70), (2, 38, 58)) if kind == "nursery" else ((0, 36, 76), (1.5, 42, 42), (2, 38, 70), (3, 42, 42))
            for pulse, pitch, velocity in pattern: put(drum, pitch, start + pulse * beat, .11, velocity)
        tracks.append({"id": "drum", "name": "课堂打击乐节奏", "instrument": "drum", "notes": drum})
    return {"style": style, "key": f"{names[tonic]}{'大调' if mode == 'major' else '小调'}", "chord_roots": roots, "chord_labels": chord_labels, "instruments": instruments, "tracks": tracks, "tips": f"已根据主旋律推断 {names[tonic]}{'大调' if mode == 'major' else '小调'}；和弦走向为 {' – '.join(chord_labels)}；{style}使用{recipe['texture']}。"}

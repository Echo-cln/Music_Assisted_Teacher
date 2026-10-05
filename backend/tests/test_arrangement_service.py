from app.services.arrangement_service import arrange, parse_note_text


def _arrange(notes: str, style: str = "乡土抒情"):
    return arrange(
        parse_note_text(notes, 96),
        96,
        style,
        ["piano", "guzheng", "violin", "guitar", "erhu", "drum"],
    )


def test_chords_follow_a_four_bar_c_major_melody():
    # 每四个四分音符是一小节：C、Am、F、G、C（最后回到主音，调性不歧义）。
    result = _arrange("C4 E4 G4 E4 A4 C5 E5 C5 F4 A4 C5 A4 G4 B4 D5 B4 C4 E4 G4 C5")
    assert result["key"] == "C大调"
    assert result["chord_labels"] == ["C", "Am", "F", "G", "C"]
    assert "C – Am – F – G – C" in result["tips"]


def test_styles_produce_different_rhythm_content_not_just_a_new_label():
    melody = "C4 E4 G4 E4 A4 C5 E5 C5 F4 A4 C5 A4 G4 B4 D5 B4 C4 E4 G4 C5"
    lyrical = _arrange(melody, "乡土抒情")
    rhythm = _arrange(melody, "欢快律动")
    nursery = _arrange(melody, "童谣清新")
    ensemble = _arrange(melody, "器乐合奏")

    def track(result, track_id):
        # 主旋律在任何主题下都必须原样保留；比较的是实际编曲伴奏轨，而非钢琴键位主旋律。
        return next(item for item in result["tracks"] if item["id"] == track_id)["notes"]

    # 吉他、鼓和钢琴伴奏的时值/起点必须随主题真实变化。
    assert track(lyrical, "guitar") != track(rhythm, "guitar")
    assert track(rhythm, "drum") != track(nursery, "drum")
    assert track(nursery, "piano") != track(ensemble, "piano")


def test_key_changes_with_melody_terminal_and_pitch_set():
    assert _arrange("G4 B4 D5 G5 C5 E5 D5 G5")["key"] == "G大调"
    assert _arrange("A4 C5 E5 A5 D5 F5 E5 A5")["key"] == "A小调"

from app.services.omr_service import _command_parts, _export_file


def test_missing_audiveris_configuration_has_actionable_message():
    try:
        _command_parts("")
    except RuntimeError as error:
        assert "AUDIVERIS_COMMAND" in str(error)
    else:
        raise AssertionError("未配置 Audiveris 时不能静默成功")


def test_export_file_only_accepts_musicxml(tmp_path):
    (tmp_path / "page.omr").write_text("intermediate")
    assert _export_file(tmp_path) is None
    exported = tmp_path / "page.mxl"
    exported.write_bytes(b"PK")
    assert _export_file(tmp_path) == exported

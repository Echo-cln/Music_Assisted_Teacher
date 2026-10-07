from types import SimpleNamespace

from app.services import audio_service


def test_audio_separator_cli_returns_vocal_stem(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_service, "_audio_separator_executable", lambda: ["audio-separator"])
    monkeypatch.setattr(audio_service, "get_settings", lambda: SimpleNamespace(audio_separator_model="test-model.ckpt"))

    def run(command, **kwargs):
        assert command[0] == "audio-separator"
        assert "--model_filename" in command
        assert "test-model.ckpt" in command
        assert "--single_stem" in command
        output_dir = tmp_path / "out"
        output_dir.mkdir(exist_ok=True)
        (output_dir / "song_(Vocals).wav").write_bytes(b"valid audio stem" * 500)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(audio_service.subprocess, "run", run)
    stem, _ = audio_service._separate_with_audio_separator(tmp_path / "song.mp3", tmp_path / "out")
    assert stem is not None
    assert stem.name == "song_(Vocals).wav"


def test_audio_separator_failure_does_not_return_a_fake_stem(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_service, "_audio_separator_executable", lambda: ["audio-separator"])
    monkeypatch.setattr(audio_service, "get_settings", lambda: SimpleNamespace(audio_separator_model="test-model.ckpt"))
    monkeypatch.setattr(audio_service.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="model download failed"))
    stem, detail = audio_service._separate_with_audio_separator(tmp_path / "song.mp3", tmp_path / "out")
    assert stem is None
    assert "model download failed" in detail

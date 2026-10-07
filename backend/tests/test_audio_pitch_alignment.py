import unittest

import numpy as np

from app.services.audio_service import PitchTrack, _voiced_sequence


class VoicedSequenceTests(unittest.TestCase):
    def test_silence_frames_are_removed_without_interpolation(self):
        track = PitchTrack(
            values=np.array([440.0, 440.0, np.nan, np.nan, np.nan, 493.88]),
            times=np.arange(6, dtype=float) * 0.02,
            confidence=np.array([0.9, 0.8, 0.0, 0.0, 0.0, 0.9]),
            voiced_ratio=0.5,
            backend="test",
        )

        midi, frame_indices, confidence = _voiced_sequence(track)

        self.assertEqual(frame_indices.tolist(), [0, 1, 5])
        self.assertEqual(np.rint(midi).astype(int).tolist(), [69, 69, 71])
        self.assertEqual(confidence.tolist(), [0.9, 0.8, 0.9])

    def test_low_confidence_pitch_is_not_treated_as_voice(self):
        track = PitchTrack(
            values=np.array([440.0, 440.0, 440.0]),
            times=np.arange(3, dtype=float),
            confidence=np.array([0.9, 0.24, 0.9]),
            voiced_ratio=2 / 3,
            backend="test",
        )

        _, frame_indices, _ = _voiced_sequence(track)

        self.assertEqual(frame_indices.tolist(), [0, 2])

    def test_too_few_trusted_frames_is_reported(self):
        track = PitchTrack(
            values=np.array([np.nan, 440.0]),
            times=np.arange(2, dtype=float),
            confidence=np.array([0.0, 0.2]),
            voiced_ratio=0.0,
            backend="test",
        )

        with self.assertRaisesRegex(ValueError, "可用的人声音高帧不足"):
            _voiced_sequence(track)


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.lesson_run_service import (
    apply_lesson_run_event,
    build_run_stages,
    interrupt_stale_lesson_run,
    serialize_lesson_run,
)


class LessonRunServiceTests(unittest.TestCase):
    def make_run(self, now=None):
        now = now or datetime(2026, 10, 7, 10, 0, 0)
        stages = build_run_stages([
            {"stage": "听辨", "minutes": 5},
            {"stage": "学唱", "minutes": 10},
        ])
        stages[0]["status"] = "running"
        stages[0]["started_at"] = now.isoformat()
        return SimpleNamespace(
            id=1,
            lesson_plan_id=8,
            mode="actual",
            status="running",
            plan_snapshot_json=json.dumps({"content": {"title": "测试课"}}),
            stages_json=json.dumps(stages, ensure_ascii=False),
            current_stage_index=0,
            total_active_seconds=0,
            total_paused_seconds=0,
            reflection="",
            active_since=now,
            paused_since=None,
            last_heartbeat_at=now,
            started_at=now,
            ended_at=None,
        )

    def test_pause_time_is_excluded_from_active_lesson_time(self):
        start = datetime(2026, 10, 7, 10, 0, 0)
        run = self.make_run(start)
        apply_lesson_run_event(run, "heartbeat", start + timedelta(minutes=5))
        apply_lesson_run_event(run, "pause", start + timedelta(minutes=5))
        apply_lesson_run_event(run, "resume", start + timedelta(minutes=7))
        apply_lesson_run_event(run, "finish", start + timedelta(minutes=10))

        result = serialize_lesson_run(run, start + timedelta(minutes=10))

        self.assertEqual(result["total_active_seconds"], 8 * 60)
        self.assertEqual(result["total_paused_seconds"], 2 * 60)
        self.assertEqual(result["stages"][0]["active_seconds"], 8 * 60)
        self.assertEqual(result["status"], "completed")

    def test_next_stage_closes_previous_and_starts_next(self):
        start = datetime(2026, 10, 7, 10, 0, 0)
        run = self.make_run(start)
        apply_lesson_run_event(run, "next", start + timedelta(minutes=3))
        result = serialize_lesson_run(run, start + timedelta(minutes=3))

        self.assertEqual(result["current_stage_index"], 1)
        self.assertEqual(result["stages"][0]["active_seconds"], 180)
        self.assertEqual(result["stages"][0]["status"], "completed")
        self.assertEqual(result["stages"][1]["status"], "running")

    def test_stage_notes_and_overall_reflection_are_saved(self):
        start = datetime(2026, 10, 7, 10, 0, 0)
        run = self.make_run(start)
        apply_lesson_run_event(run, "note", start + timedelta(seconds=20), stage_index=0, note="学生能跟唱，设备音量偏低")
        apply_lesson_run_event(run, "reflection", start + timedelta(seconds=30), reflection="下次缩短示范并增加分组练习")
        result = serialize_lesson_run(run, start + timedelta(seconds=30))

        self.assertEqual(result["stages"][0]["note"], "学生能跟唱，设备音量偏低")
        self.assertEqual(result["reflection"], "下次缩短示范并增加分组练习")

    def test_finish_while_paused_counts_pause_but_not_active_time(self):
        start = datetime(2026, 10, 7, 10, 0, 0)
        run = self.make_run(start)
        apply_lesson_run_event(run, "pause", start + timedelta(minutes=2))
        apply_lesson_run_event(run, "finish", start + timedelta(minutes=7))
        result = serialize_lesson_run(run, start + timedelta(minutes=7))

        self.assertEqual(result["total_active_seconds"], 2 * 60)
        self.assertEqual(result["total_paused_seconds"], 5 * 60)
        self.assertEqual(result["status"], "completed")

    def test_stale_browser_time_is_not_counted_after_last_heartbeat(self):
        start = datetime(2026, 10, 7, 10, 0, 0)
        run = self.make_run(start)
        apply_lesson_run_event(run, "heartbeat", start + timedelta(seconds=15))
        changed = interrupt_stale_lesson_run(run, start + timedelta(seconds=200), stale_seconds=120)
        result = serialize_lesson_run(run, start + timedelta(seconds=200))

        self.assertTrue(changed)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(result["total_active_seconds"], 15)


if __name__ == "__main__":
    unittest.main()

"""Kiểm thử trình dựng (EditorCore, cắt theo beat, xuất video, cổng MCP, bảo mật).

Chạy bằng unittest (không cần cài pytest):
    .venv\\Scripts\\python -m unittest tests.test_editor -v
Dữ liệu thử nằm trong thư mục tạm, không đụng tới data/ thật.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile

# Đặt TRƯỚC khi import backend: mọi dữ liệu của bài thử nằm trong thư mục tạm, không đụng data/ thật.
os.environ["CML_DATA_DIR"] = tempfile.mkdtemp(prefix="cml-data-test-")
import time
import unittest
from pathlib import Path

from backend import media
from backend.editor import mcp_server
from backend.editor.core import CommandError, EditorCore, Locked, VersionConflict
from backend.editor.service import EditorService, plan_cuts
from backend.editor.store import Store
from backend.jobs import JobQueue

HAS_FFMPEG = bool(media.FFMPEG)


def make_video(path: Path, seconds: float = 4, size: str = "640x360", audio: bool = True) -> Path:
    args = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:d={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=330:d={seconds}"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-shortest", str(path)]
    media.run_ffmpeg(args)
    return path


def make_music(path: Path, bpm: float = 120, seconds: float = 6) -> Path:
    period = 60 / bpm
    expr = f"if(lt(mod(t\\,{period})\\,0.03)\\,0.9*sin(2*PI*900*t)\\,0)+0.05*sin(2*PI*220*t)"
    media.run_ffmpeg(["-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d={seconds}", "-c:a", "pcm_s16le", str(path)])
    return path


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cml-test-"))
        self.core = EditorCore(Store(self.tmp / "e.db"), lock_ttl=0.5)
        self.p = self.core.create_project("thu")
        self.tid = self.core.apply(self.p.id, {"type": "add_track", "kind": "video"})["result"]["track_id"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, start=0.0, length=2.0):
        return self.core.apply(self.p.id, {"type": "add_clip", "track_id": self.tid, "clip": {
            "media_id": "m", "start": start, "in_point": 0.0, "out_point": length}})["result"]["clip_id"]

    def clips(self):
        return self.core.get(self.p.id)[0].tracks[0].clips

    def test_undo_redo(self):
        self.add(); self.add(2)
        self.core.undo(self.p.id)
        self.assertEqual(len(self.clips()), 1)
        self.core.redo(self.p.id)
        self.assertEqual(len(self.clips()), 2)

    def test_split(self):
        cid = self.add(1, 4)
        r = self.core.apply(self.p.id, {"type": "split_clip", "clip_id": cid, "at": 2.5})["result"]
        p, _ = self.core.get(self.p.id)
        self.assertAlmostEqual(p.find_clip(r["left_id"])[1].out_point, 1.5)
        self.assertAlmostEqual(p.find_clip(r["right_id"])[1].in_point, 1.5)

    def test_batch_is_one_undo_step(self):
        self.core.apply(self.p.id, {"type": "batch", "commands": [
            {"type": "add_track", "kind": "audio", "id": "trk_nhac"},
            {"type": "add_clip", "track_id": "trk_nhac", "clip": {"media_id": "m", "start": 0, "out_point": 3}}]})
        self.core.undo(self.p.id)
        self.assertEqual(len(self.core.get(self.p.id)[0].tracks), 1)

    def test_stale_copy_is_refused(self):
        # Agent cầm bản cũ không được ghi đè chỗ người dùng vừa sửa (Vidlab P1).
        _, v = self.core.get(self.p.id)
        self.add()
        with self.assertRaises(VersionConflict):
            self.core.apply(self.p.id, {"type": "add_track", "kind": "text"}, "agent", expected_version=v)

    def test_lock_expires_and_user_can_always_edit(self):
        # Agent chết giữa chừng không được khóa project mãi (Vidlab P8).
        self.assertTrue(self.core.lock(self.p.id, "agent-a"))
        with self.assertRaises(Locked):
            self.core.apply(self.p.id, {"type": "add_track", "kind": "text"}, "agent-b")
        self.core.apply(self.p.id, {"type": "add_track", "kind": "text"}, "user")
        time.sleep(0.6)
        self.assertTrue(self.core.lock(self.p.id, "agent-b"))

    def test_mute_track(self):
        self.core.apply(self.p.id, {"type": "update_track", "track_id": self.tid, "fields": {"muted": True}})
        self.assertTrue(self.core.get(self.p.id)[0].tracks[0].muted)
        with self.assertRaises(CommandError):
            self.core.apply(self.p.id, {"type": "update_track", "track_id": self.tid, "fields": {"kind": "audio"}})

    def test_bad_clip(self):
        with self.assertRaises(CommandError):
            self.core.apply(self.p.id, {"type": "add_clip", "track_id": self.tid,
                                        "clip": {"start": 0, "in_point": 3, "out_point": 1}})


class PlanCutsTest(unittest.TestCase):
    def test_covers_song_and_rotates(self):
        clips = plan_cuts([i * 0.5 for i in range(1, 20)], [{"media_id": "a", "duration": 6},
                                                            {"media_id": "b", "duration": 6}], 2, 0.3, 10)
        self.assertEqual([c["media_id"] for c in clips[:4]], ["a", "b", "a", "b"])
        for x, y in zip(clips, clips[1:]):
            self.assertAlmostEqual(x["start"] + x["out_point"] - x["in_point"], y["start"], places=3)
        last = clips[-1]
        self.assertAlmostEqual(last["start"] + last["out_point"] - last["in_point"], 10, places=3)

    def test_short_tail_is_merged(self):
        clips = plan_cuts([1.0, 2.0, 2.9], [{"media_id": "a", "duration": 9}], 1, 0.3, 3.0)
        self.assertGreaterEqual(min(c["out_point"] - c["in_point"] for c in clips), 0.3)


class FfmpegVersionTest(unittest.TestCase):
    # Lỗi thật trên Windows 19/11/2026: FFmpeg mới không còn -filter_complex_script.
    def test_option_by_version(self):
        from backend.editor.render import filter_script_option
        self.assertEqual(filter_script_option("ffmpeg version 6.1.1-3ubuntu5 Copyright"), "-filter_complex_script")
        self.assertEqual(filter_script_option("ffmpeg version 7.1-full_build-www.gyan.dev"), "-/filter_complex")
        self.assertEqual(filter_script_option("ffmpeg version 8.0-essentials_build"), "-/filter_complex")
        self.assertEqual(filter_script_option("ffmpeg version 2025-11-10-git-abc-full_build"), "-/filter_complex")
        self.assertEqual(filter_script_option("ffmpeg version n6.0"), "-filter_complex_script")


class McpTest(unittest.TestCase):
    def test_initialize_and_list(self):
        init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "creative-motion-lab")
        self.assertIsNone(mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertTrue({"edit", "beat_cut", "auto_captions", "export_video", "undo"} <= names)
        json.dumps(tools)

    def test_server_down_is_reported_not_crash(self):
        old = mcp_server.BASE
        mcp_server.BASE = "http://127.0.0.1:9"
        try:
            r = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                   "params": {"name": "list_media", "arguments": {}}})
        finally:
            mcp_server.BASE = old
        self.assertTrue(r["result"]["isError"])


@unittest.skipUnless(HAS_FFMPEG, "cần FFmpeg")
class EndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="cml-e2e-"))
        cls.jobs = JobQueue(db_path=cls.tmp / "jobs.db", jobs_dir=cls.tmp / "jobs")
        cls.svc = EditorService(cls.jobs, data_dir=cls.tmp / "editor")
        cls.jobs.register("render", cls.svc.render_job)
        src = cls.tmp / "src"
        src.mkdir()
        cls.v1 = cls.svc.import_file(make_video(src / "clip một.mp4", 5), "clip một.mp4")
        cls.v2 = cls.svc.import_file(make_video(src / "b.mp4", 5, "1280x720", audio=False))
        cls.song = cls.svc.import_file(make_music(src / "nhac.wav"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def export(self, pid):
        job_id, _ = self.jobs.new_job_dir()
        self.jobs.submit(job_id, "render", {"project_id": pid})
        self.jobs.run_once(job_id)
        job = self.jobs.get(job_id)
        self.assertEqual(job["status"], "done", job["error"])
        return job

    def test_thumbnail(self):
        self.assertGreater(self.svc.thumbnail(self.v1.id).stat().st_size, 1000)

    def test_media_file_supports_seeking(self):
        try:
            from backend.editor.api import ranged_file
        except ImportError:
            self.skipTest("thiếu FastAPI")
        r = ranged_file(Path(self.v1.path), "bytes=100-199")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r.headers["content-length"], "100")

    def test_import_uses_ascii_path(self):
        self.assertTrue(self.v1.path.isascii())
        self.assertEqual(self.v1.original_name, "clip một.mp4")

    def test_beat_cut_captions_export(self):
        p = self.svc.core.create_project("beat", 540, 960, 30)
        r = self.svc.beat_cut(p.id, self.song.id, [self.v1.id, self.v2.id], 2, look="teal-orange")
        self.assertGreaterEqual(r["clips"], 3)
        tid = self.svc.core.apply(p.id, {"type": "add_track", "kind": "text"})["result"]["track_id"]
        self.svc.core.apply(p.id, {"type": "add_clip", "track_id": tid, "clip": {
            "start": 0.5, "out_point": 2, "text": "Xin chào Việt Nam"}})
        job = self.export(p.id)
        self.assertTrue(job["extra"]["ok"], job["extra"])
        self.assertAlmostEqual(job["extra"]["duration"], 6, delta=0.25)

    def test_gap_becomes_black(self):
        p = self.svc.core.create_project("gap", 640, 360, 30)
        v = self.svc.core.apply(p.id, {"type": "add_track", "kind": "video"})["result"]["track_id"]
        self.svc.core.apply(p.id, {"type": "add_clip", "track_id": v, "clip": {
            "media_id": self.v1.id, "start": 1.5, "in_point": 1, "out_point": 3, "look": "vintage"}})
        job = self.export(p.id)
        self.assertGreaterEqual(job["extra"]["black_seconds"], 1.0)

    def test_captions_from_subtitle_job(self):
        p = self.svc.core.create_project("pd")
        job_id, _ = self.jobs.new_job_dir()
        self.jobs.register("fake_sub", lambda ctx: {"file": None, "extra": {
            "original": [[0.0, 1.2, "Xin chào"], [1.5, 2.5, "Tạm biệt"]], "source_lang": "vi",
            "tracks": {"en": [[0.0, 1.2, "Hello"], [1.5, 2.5, "Goodbye"]]}}})
        self.jobs.submit(job_id, "fake_sub", {})
        self.jobs.run_once(job_id)
        r = self.svc.captions_from_job(p.id, job_id, lang="en", offset=2.0)
        clips = self.svc.core.get(p.id)[0].find_track(r["track_id"]).clips
        self.assertEqual([c.text for c in clips], ["Hello", "Goodbye"])
        self.assertAlmostEqual(clips[0].start, 2.0)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient
            from backend.main import app
        except ImportError as e:
            raise unittest.SkipTest(f"thiếu thư viện: {e}")
        cls.c = TestClient(app, base_url="http://localhost:8000")

    def test_foreign_host_gets_403(self):
        self.assertEqual(self.c.get("/api/editor/looks").status_code, 200)
        self.assertEqual(self.c.get("/api/editor/looks", headers={"host": "evil.example"}).status_code, 403)

    def test_write_needs_header(self):
        self.assertEqual(self.c.post("/api/editor/projects", json={"name": "x"}).status_code, 403)

    def test_editor_page_is_served(self):
        r = self.c.get("/editor.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Creative Motion Lab", r.text)

    def test_project_roundtrip(self):
        h = {"X-CML": "1"}
        pid = self.c.post("/api/editor/projects", json={"name": "api-test"}, headers=h).json()["project"]["id"]
        r = self.c.post(f"/api/editor/projects/{pid}/commands", headers=h,
                        json={"command": {"type": "add_track", "kind": "video"}})
        self.assertEqual(r.json()["version"], 2)
        self.assertFalse(self.c.get(f"/api/editor/projects/{pid}?since_version=2").json()["changed"])
        self.assertEqual(self.c.post(f"/api/editor/projects/{pid}/undo", headers=h).json()["version"], 1)


if __name__ == "__main__":
    unittest.main()

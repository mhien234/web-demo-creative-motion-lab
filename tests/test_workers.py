"""Kiểm thử các worker bằng video và nhạc tự tạo bằng FFmpeg (không cần file thật).

Chạy:  python -m pytest tests -q
"""
from __future__ import annotations

import time

import pytest

from backend import media
from backend.jobs import JobQueue
from backend.workers import HANDLERS
from backend.workers.beat_sync import cut_points, detect_beats, SR

pytestmark = pytest.mark.skipif(not media.FFMPEG, reason="cần FFmpeg")


def make_music(path, bpm=120, seconds=10):
    period = 60 / bpm
    expr = f"if(lt(mod(t\\,{period})\\,0.03)\\,0.9*sin(2*PI*900*t)\\,0)+0.05*sin(2*PI*220*t)"
    media.run_ffmpeg(["-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d={seconds}", "-c:a", "pcm_s16le", str(path)])


def make_video(path, seconds=8, size="640x360"):
    media.run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:d={seconds}",
                      "-f", "lavfi", "-i", f"sine=frequency=330:d={seconds}",
                      "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:a=0.08",
                      "-filter_complex", "[1][2]amix=inputs=2[a]", "-map", "0:v", "-map", "[a]",
                      "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                      "-shortest", str(path)])


@pytest.fixture()
def q(tmp_path):
    jq = JobQueue(db_path=tmp_path / "jobs.db", jobs_dir=tmp_path / "jobs")
    for k, h in HANDLERS.items():
        jq.register(k, h)
    return jq


def submit(q, kind, params, videos=(), music=None):
    job_id, d = q.new_job_dir()
    for i, v in enumerate(videos):
        (d / f"video_{i:02d}_{v.name}").write_bytes(v.read_bytes())
    if music:
        (d / f"music_{music.name}").write_bytes(music.read_bytes())
    q.submit(job_id, kind, params)
    q.run_once(job_id)
    return q.get(job_id)


def test_detect_beats_finds_120_bpm(tmp_path):
    m = tmp_path / "click.wav"
    make_music(m, bpm=120, seconds=12)
    info = detect_beats(media.decode_mono(m, SR), sensitivity=100)
    assert abs(info["bpm"] - 120) < 3 or abs(info["bpm"] - 60) < 2, info["bpm"]
    gaps = [b - a for a, b in zip(info["beats"], info["beats"][1:])]
    assert gaps and abs(sum(gaps) / len(gaps) - 0.5) < 0.05


def test_cut_points_every_two_beats():
    beats = [0.5 * i for i in range(1, 20)]
    pts = cut_points(beats, 10.0, every=2)
    assert pts[0] == 0 and pts[-1] == 10.0
    assert all(b > a for a, b in zip(pts, pts[1:]))


def test_beat_sync_job(tmp_path, q):
    m, v1, v2 = tmp_path / "beat.wav", tmp_path / "a.mp4", tmp_path / "b.mp4"
    make_music(m, seconds=6)
    make_video(v1, seconds=5)
    make_video(v2, seconds=4, size="360x640")
    t0 = time.time()
    job = submit(q, "beat_sync", {"every": 2, "sensitivity": 70, "fx": ["flash", "zoom"],
                                  "quality": "720p", "ratio": "16:9"}, [v1, v2], m)
    assert job["status"] == "done", job["error"]
    out = q.jobs_dir / job["id"] / job["result_file"]
    assert abs(media.duration_of(out) - 6) < 0.4
    assert media.has_stream(out, "audio") and media.has_stream(out, "video")
    assert job["extra"]["cuts"] >= 3
    print(f"beat_sync: {job['extra']} trong {time.time() - t0:.1f}s")


def test_beat_sync_without_music_fails_nicely(tmp_path, q):
    v = tmp_path / "a.mp4"
    make_video(v, seconds=2)
    job = submit(q, "beat_sync", {}, [v])
    assert job["status"] == "failed" and "nhạc" in job["error"]


def test_denoise_job(tmp_path, q):
    v = tmp_path / "noisy.mp4"
    make_video(v, seconds=4)
    job = submit(q, "denoise", {"level": 2}, [v])
    assert job["status"] == "done", job["error"]
    out = q.jobs_dir / job["id"] / job["result_file"]
    assert abs(media.duration_of(out) - 4) < 0.3


def test_subtitles_apply_burn(tmp_path, q):
    v = tmp_path / "talk.mp4"
    make_video(v, seconds=4)
    segs = [[0.5, 2.0, "Chào mừng đến với Creative Motion Lab!"], [2.0, 3.5, "Bắt đầu ngay nào!"]]
    job = submit(q, "subtitles", {"mode": "apply", "segments": segs, "burn": True}, [v])
    assert job["status"] == "done", job["error"]
    srt = (q.jobs_dir / job["id"] / "subs.srt").read_text(encoding="utf-8")
    assert "00:00:00,500 --> 00:00:02,000" in srt and "Bắt đầu ngay nào!" in srt


def test_transcribe_without_whisper_reports_install_hint(tmp_path, q):
    pytest.importorskip("numpy")
    try:
        import faster_whisper  # noqa: F401
        pytest.skip("faster-whisper đã được cài")
    except ImportError:
        pass
    v = tmp_path / "talk.mp4"
    make_video(v, seconds=2)
    job = submit(q, "subtitles", {"mode": "transcribe", "lang": "vi"}, [v])
    assert job["status"] == "failed" and "Cài ngay" in job["error"]


def test_beat_sync_uses_cut_times_from_website(tmp_path, q):
    m, v = tmp_path / "beat.wav", tmp_path / "a.mp4"
    make_music(m, seconds=5)
    make_video(v, seconds=5)
    job = submit(q, "beat_sync", {"cut_times": [1.0, 2.5, 4.0], "quality": "720p"}, [v], m)
    assert job["status"] == "done", job["error"]
    assert job["extra"]["cut_times"] == [1.0, 2.5, 4.0]


def test_translate_falls_back_to_original_text_without_tools(monkeypatch):
    from backend.workers import subtitles
    monkeypatch.setattr(subtitles, "_has", lambda m: False)
    monkeypatch.setattr(subtitles, "_translate_gtx", lambda *a: (_ for _ in ()).throw(OSError("offline")))
    out, note = subtitles._translate(["Hello"], "en", "vi")
    assert out == ["Hello"] and note


def test_translate_skips_same_language():
    from backend.workers import subtitles
    assert subtitles._translate(["Xin chào"], "vi", "vi") == (["Xin chào"], None)


def test_translate_job_many_languages(q, monkeypatch):
    from backend.workers import subtitles
    monkeypatch.setattr(subtitles, "_translate_argos", lambda *a: None)
    monkeypatch.setattr(subtitles, "_translate_gtx", lambda texts, src, dst: [f"[{dst}] {t}" for t in texts])
    segs = [[0.5, 2.0, "Hello"], [2.0, 3.5, "Let's go"]]
    job = submit(q, "subtitles", {"mode": "translate", "segments": segs, "source": "en",
                                  "targets": ["vi", "ja", "zh-CN", "en"]})
    assert job["status"] == "done", job["error"]
    tr = job["extra"]["tracks"]
    assert tr["vi"] == [[0.5, 2.0, "[vi] Hello"], [2.0, 3.5, "[vi] Let's go"]]
    assert tr["zh-CN"][0][2] == "[zh-CN] Hello"
    assert tr["en"][1][2] == "Let's go"            # cùng ngôn ngữ gốc -> giữ nguyên


def test_translate_job_reports_network_error(q, monkeypatch):
    from backend.workers import subtitles
    monkeypatch.setattr(subtitles, "_translate_argos", lambda *a: None)

    def boom(*a):
        raise ConnectionError("offline")
    monkeypatch.setattr(subtitles, "_translate_google", boom)
    monkeypatch.setattr(subtitles, "_translate_gtx", boom)
    job = submit(q, "subtitles", {"mode": "translate", "segments": [[0, 1, "Hi"]], "source": "en", "targets": ["vi"]})
    assert job["status"] == "failed" and "mạng" in job["error"]


def test_gtx_batches_lines_and_falls_back_when_line_count_differs(monkeypatch):
    from backend.workers import subtitles
    calls = []

    def fake(text, src, dst):
        calls.append(text)
        return "ONE LINE ONLY" if "\n" in text else text.upper()
    monkeypatch.setattr(subtitles, "_gtx_request", fake)
    assert subtitles._translate_gtx(["a", "b", "c"], "en", "vi") == ["A", "B", "C"]
    assert calls[0] == "a\nb\nc"


# ---------------------------------------------------------------- giọng đọc AI
class FakeEngine:
    """Thay Edge TTS khi kiểm thử: mỗi câu là một tiếng bíp dài theo số chữ."""
    name = "fake"

    def __init__(self):
        self.calls = []

    def synth(self, text, voice, out):
        self.calls.append((text, voice))
        secs = 0.4 + 0.08 * len(text)
        media.run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=500:d={secs:.2f}", "-c:a", "libmp3lame", str(out)])


@pytest.fixture()
def fake_tts(monkeypatch):
    from backend.workers import voiceover
    eng = FakeEngine()
    monkeypatch.setattr(voiceover, "get_engine", lambda name=None: eng)
    return eng


def test_voiceover_into_video(tmp_path, q, fake_tts):
    from backend.media import duration_of
    v = tmp_path / "in.mp4"; make_video(v, seconds=8)
    segs = [[0.5, 2.0, "Xin chào"], [2.2, 3.0, "Câu này rất dài nên phải đọc nhanh hơn một chút"],
            [5.0, 7.0, "gốc\nbản dịch song ngữ"]]
    job = submit(q, "voiceover", {"lang": "vi", "voice": "vi-VN-NamMinhNeural", "segments": segs,
                                  "orig_volume": 0.3}, videos=[v])
    assert job["status"] == "done", job.get("error")
    x = job["extra"]
    assert x["voice"] == "vi-VN-NamMinhNeural" and x["spoken"] == 3 and x["sped_up"] >= 1
    assert fake_tts.calls[2][0] == "bản dịch song ngữ"       # chỉ đọc dòng dịch
    out = q.jobs_dir / job["id"] / "long-tieng.mp4"
    assert media.has_stream(out, "video") and media.has_stream(out, "audio")
    assert abs(duration_of(out) - 8) < 0.6


def test_voiceover_audio_only_and_all_ten_languages(tmp_path, q, fake_tts):
    from backend.workers.voiceover import VOICES, pick_voice
    assert len(VOICES) == 10 and all(len(v) == 2 for v in VOICES.values())
    assert pick_voice("zh", None) == "zh-CN-XiaoxiaoNeural"
    assert pick_voice("ja", "khong-co") == "ja-JP-NanamiNeural"
    job = submit(q, "voiceover", {"lang": "ru", "segments": [[0, 1.5, "Привет"]]})
    assert job["status"] == "done", job.get("error")
    assert (q.jobs_dir / job["id"] / "giong-doc.m4a").exists()


def test_voiceover_unsupported_language(q, fake_tts):
    job = submit(q, "voiceover", {"lang": "id", "segments": [[0, 1, "Halo"]]})
    assert job["status"] == "failed" and "chưa hỗ trợ" in job["error"]


def test_voiceover_without_edge_tts_gives_install_hint(q, monkeypatch):
    import builtins
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__",
                        lambda n, *a, **k: (_ for _ in ()).throw(ImportError(n)) if n == "edge_tts" else real(n, *a, **k))
    job = submit(q, "voiceover", {"lang": "vi", "segments": [[0, 1, "Xin chào"]]})
    assert job["status"] == "failed" and "Cài giọng đọc" in job["error"]


def test_voiceover_skips_a_line_the_service_drops(tmp_path, q, monkeypatch):
    from backend.workers import voiceover
    from backend.media import MediaError

    class Flaky(FakeEngine):
        def synth(self, text, voice, out):
            if "lỗi" in text:
                out.write_bytes(b"")
                raise MediaError("No audio was received")
            super().synth(text, voice, out)

    monkeypatch.setattr(voiceover, "get_engine", lambda name=None: Flaky())
    v = tmp_path / "in.mp4"; make_video(v, seconds=8)
    segs = [[0.5, 2, "một"], [2, 3.5, "câu lỗi"], [3.5, 5, "ba"], [5, 6.5, "bốn"]]
    job = submit(q, "voiceover", {"lang": "vi", "segments": segs}, videos=[v])
    assert job["status"] == "done", job.get("error")
    assert job["extra"]["spoken"] == 3 and job["extra"]["skipped"] == [[2.0, "câu lỗi"]]

    monkeypatch.setattr(voiceover, "get_engine", lambda name=None: Flaky())
    job = submit(q, "voiceover", {"lang": "vi", "segments": [[0, 1, "lỗi"], [1, 2, "lỗi nữa"], [2, 3, "ok"]]})
    assert job["status"] == "failed" and "2/3" in job["error"]

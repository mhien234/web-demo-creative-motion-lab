"""Chạy thử worker Xóa nền ngoài máy chủ web, trên clip mẫu của dự án.

Dùng:  .venv\\Scripts\\python thu-xoa-nen.py
Kết quả nằm trong data/jobs/thu-xoa-nen/.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

# Console Windows mac dinh dung bang ma cp1252/cp437, khong in duoc chu Viet co dau:
# print() se nem UnicodeEncodeError giua chung. Ep stdout sang UTF-8 truoc moi thu khac.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.jobs import JobContext  # noqa: E402
from backend.media import run_ffmpeg  # noqa: E402
from backend.workers import remove_bg  # noqa: E402

SRC = ROOT / "test-media" / "clip-game-1.mp4"
JOB = ROOT / "data" / "jobs" / "thu-xoa-nen"


def main() -> int:
    print("Trang thai:", remove_bg.rembg_status())
    model = remove_bg.find_model()
    print("Model:", model or "KHONG TIM THAY")
    if model is None:
        print("Dat file rvm_resnet50_fp32.onnx vao thu muc models/ roi chay lai.")
        return 1
    if not SRC.is_file():
        print("Khong thay clip mau:", SRC)
        return 1

    shutil.rmtree(JOB, ignore_errors=True)
    JOB.mkdir(parents=True, exist_ok=True)
    # Cat 2 giay dau cho nhanh
    run_ffmpeg(["-i", str(SRC), "-t", "2", "-c", "copy", str(JOB / "video_00_clip.mp4")])

    last = [""]

    def report(p: float, m: str) -> None:
        if m != last[0]:
            last[0] = m
            print(f"   [{p * 100:5.1f}%] {m}")

    ok = True
    for mode in ("color", "blur", "transparent"):
        print(f"\n--- kieu nen: {mode} ---")
        ctx = JobContext("thu-xoa-nen", JOB, {"mode": mode, "max_width": 854}, report)
        t = time.time()
        try:
            out = remove_bg.run(ctx)
            f = out["file"]
            keep = JOB / f"ket-qua-{mode}{f.suffix}"
            shutil.move(str(f), str(keep))
            print(f"   OK sau {time.time() - t:.1f}s -> {keep.name}")
            print("   thong tin:", out["extra"])
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"   THAT BAI: {type(e).__name__}: {e}")

    print("\nFile ket qua nam o:", JOB)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

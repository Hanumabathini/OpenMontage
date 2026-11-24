"""Tests for the WanGP local video tool, using a fake WanGP install (no GPU needed)."""

from __future__ import annotations

import json
import shutil
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe required",
)

FAKE_WGP = textwrap.dedent(
    '''
    import json, subprocess, sys
    from pathlib import Path

    MODE = {mode!r}
    args = sys.argv[1:]
    job = json.loads(Path(args[args.index("--process") + 1]).read_text(encoding="utf-8"))
    out = Path(args[args.index("--output-dir") + 1])
    out.mkdir(parents=True, exist_ok=True)
    print("fake wgp processing", job.get("model_type"))

    def write(src):
        w, h = (int(v) for v in job["resolution"].split("x"))
        frames = int(job.get("video_length", 121))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"{{src}}=size=320x{{int(320 * h / w) // 2 * 2}}:rate=24",
                        "-frames:v", str(frames), "-pix_fmt", "yuv420p",
                        str(out / "clip.mp4")], check=True)

    if MODE == "moving":
        write("testsrc2")
    elif MODE == "static":
        write("color=c=gray")
    elif MODE == "oom":
        if job.get("model_type") == "ti2v_2_2_fastwan":
            write("testsrc2")
        else:
            print("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB")
    # MODE == "none": print only, produce nothing
    '''
)


@pytest.fixture
def fake_wangp(tmp_path, monkeypatch):
    """Create a fake WanGP folder (with a space in its path) whose wgp.py obeys `mode`."""

    def make(mode: str = "moving") -> Path:
        root = tmp_path / "Wan GP"
        root.mkdir(exist_ok=True)
        (root / "wgp.py").write_text(FAKE_WGP.format(mode=mode), encoding="utf-8")
        monkeypatch.setenv("WANGP_DIR", str(root))
        monkeypatch.setenv("WANGP_PYTHON", sys.executable)
        return root

    return make


# ---------------------------------------------------------------- Task 1: runner helpers


def test_resolve_uses_env_python(fake_wangp):
    from tools.video._wangp_runner import resolve_wangp

    root = fake_wangp()
    wdir, python, reason = resolve_wangp()
    assert wdir == root
    assert python == sys.executable
    assert reason == ""


def test_resolve_detects_env_venv(tmp_path, monkeypatch):
    from tools.video._wangp_runner import resolve_wangp

    root = tmp_path / "WanGP"
    (root).mkdir()
    (root / "wgp.py").write_text("", encoding="utf-8")
    exe = root / "env_venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("WANGP_DIR", str(root))
    monkeypatch.delenv("WANGP_PYTHON", raising=False)
    _, python, reason = resolve_wangp()
    assert python == str(exe)
    assert reason == ""


def test_resolve_reports_missing(tmp_path, monkeypatch):
    from tools.video._wangp_runner import resolve_wangp

    monkeypatch.setenv("WANGP_DIR", str(tmp_path / "nowhere"))
    monkeypatch.delenv("WANGP_PYTHON", raising=False)
    wdir, python, reason = resolve_wangp()
    assert wdir is None and python is None
    assert "wgp.py" in reason


def test_build_job_text():
    from tools.video._wangp_runner import build_job

    job = build_job("a robot arm", "text, watermark", model_type="ti2v_2_2", resolution="1280x720",
                    frames=121, steps=40, seed=7)
    assert job["model_type"] == "ti2v_2_2"
    assert job["prompt"] == "a robot arm"
    assert job["negative_prompt"] == "text, watermark"
    assert job["resolution"] == "1280x720"
    assert job["video_length"] == 121
    assert job["num_inference_steps"] == 40
    assert job["seed"] == 7
    assert "image_start" not in job


def test_build_job_image(tmp_path):
    from tools.video._wangp_runner import build_job

    img = tmp_path / "hero.png"
    img.write_bytes(b"x")
    job = build_job("hero waves", "", model_type="ti2v_2_2", resolution="720x1280", frames=121,
                    steps=40, seed=1, image_start=img)
    assert job["image_prompt_type"] == "S"
    assert Path(job["image_start"]).is_absolute()


def test_snap_frames():
    from tools.video._wangp_runner import snap_frames

    assert snap_frames(120) == 121
    assert snap_frames(121) == 121
    assert snap_frames(3) == 5


def test_run_and_motion_moving(fake_wangp, tmp_path):
    from tools.video._wangp_runner import build_job, motion_score, probe_clip, resolve_wangp, run_wangp

    fake_wangp("moving")
    wdir, python, _ = resolve_wangp()
    job = build_job("x", "", model_type="ti2v_2_2", resolution="1280x720", frames=49, steps=4, seed=1)
    work = tmp_path / "work dir"
    clip, log = run_wangp(python, wdir, job, work, timeout_s=120)
    assert clip is not None and clip.exists()
    assert (work / "job.json").exists() and (work / "wangp.log").exists()
    assert "fake wgp processing" in log
    info = probe_clip(clip)
    assert info["fps"] == pytest.approx(24, abs=0.5)
    assert info["duration"] == pytest.approx(49 / 24, abs=0.2)
    score, frozen = motion_score(clip)
    assert score > 0.5 and frozen < 0.5


def test_motion_static(fake_wangp, tmp_path):
    from tools.video._wangp_runner import build_job, motion_score, resolve_wangp, run_wangp

    fake_wangp("static")
    wdir, python, _ = resolve_wangp()
    job = build_job("x", "", model_type="ti2v_2_2", resolution="1280x720", frames=25, steps=4, seed=1)
    clip, _ = run_wangp(python, wdir, job, tmp_path / "w", timeout_s=120)
    score, frozen = motion_score(clip)
    assert score < 0.5
    assert frozen >= 0.5

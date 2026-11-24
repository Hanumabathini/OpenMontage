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
                        f"{{src}}{{':' if '=' in src else '='}}size=320x{{int(320 * h / w) // 2 * 2}}:rate=24",
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
    assert clip is not None
    score, frozen = motion_score(clip)
    assert score < 0.5
    assert frozen >= 0.5


# ---------------------------------------------------------------- Task 2: wangp_video tool


def _tool():
    from tools.video.wangp_video import WanGPVideo

    return WanGPVideo()


def test_status_unavailable_without_wangp(tmp_path, monkeypatch):
    from tools.base_tool import ToolStatus

    monkeypatch.setenv("WANGP_DIR", str(tmp_path / "missing"))
    monkeypatch.delenv("WANGP_PYTHON", raising=False)
    tool = _tool()
    assert tool.get_status() == ToolStatus.UNAVAILABLE
    result = tool.execute({"prompt": "x", "output_path": str(tmp_path / "o.mp4")})
    assert result.success is False
    assert "WANGP_DIR" in result.error


def test_execute_moving_writes_output(fake_wangp, tmp_path):
    from tools.base_tool import ToolStatus

    fake_wangp("moving")
    tool = _tool()
    assert tool.get_status() == ToolStatus.AVAILABLE
    out = tmp_path / "shots dir" / "shot01.mp4"
    result = tool.execute({"prompt": "robot arm", "output_path": str(out), "duration_seconds": 2, "seed": 3})
    assert result.success, result.error
    assert out.exists()
    assert result.artifacts == [str(out)]
    assert result.cost_usd == 0.0
    assert result.data["rung"] == 0
    assert result.data["model_type"] == "ti2v_2_2"
    assert result.data["resolution"] == "1280x720"
    assert result.data["steps"] == 40
    assert result.data["motion_score"] > 0.5
    assert Path(result.data["log_path"]).exists()


def test_execute_vertical_and_draft(fake_wangp, tmp_path):
    fake_wangp("moving")
    out = tmp_path / "v.mp4"
    result = _tool().execute({"prompt": "x", "output_path": str(out), "aspect": "9:16",
                              "quality": "draft", "duration_seconds": 1})
    assert result.success, result.error
    assert result.data["resolution"] == "720x1280"
    assert result.data["model_type"] == "ti2v_2_2_fastwan"
    assert result.data["steps"] == 3
    job = json.loads((Path(result.data["log_path"]).parent / "job.json").read_text())
    assert job["guidance_scale"] == 1


def test_execute_static_rejected(fake_wangp, tmp_path):
    fake_wangp("static")
    out = tmp_path / "s.mp4"
    result = _tool().execute({"prompt": "x", "output_path": str(out), "duration_seconds": 1})
    assert result.success is False
    assert "motion" in result.error.lower()
    assert not out.exists()


def test_execute_no_output_returns_log_tail(fake_wangp, tmp_path):
    fake_wangp("none")
    result = _tool().execute({"prompt": "x", "output_path": str(tmp_path / "n.mp4"), "duration_seconds": 1})
    assert result.success is False
    assert "fake wgp processing" in result.error


def test_execute_oom_steps_ladder(fake_wangp, tmp_path):
    fake_wangp("oom")
    out = tmp_path / "o.mp4"
    result = _tool().execute({"prompt": "x", "output_path": str(out), "duration_seconds": 1})
    assert result.success, result.error
    assert result.data["rung"] >= 1
    assert result.data["model_type"] == "ti2v_2_2_fastwan"
    assert out.exists()


def test_image_to_video_requires_image(fake_wangp, tmp_path):
    fake_wangp("moving")
    result = _tool().execute({"prompt": "x", "operation": "image_to_video",
                              "output_path": str(tmp_path / "i.mp4")})
    assert result.success is False
    assert "reference_image_path" in result.error


def test_image_to_video_passes_start_image(fake_wangp, tmp_path):
    fake_wangp("moving")
    img = tmp_path / "hero.png"
    img.write_bytes(b"png")
    result = _tool().execute({"prompt": "hero waves", "operation": "image_to_video",
                              "reference_image_path": str(img), "output_path": str(tmp_path / "i.mp4"),
                              "duration_seconds": 1})
    assert result.success, result.error
    job = json.loads((Path(result.data["log_path"]).parent / "job.json").read_text())
    assert job["image_prompt_type"] == "S"
    assert job["image_start"] == str(img.resolve())


def test_registry_discovers_tool():
    from tools.tool_registry import registry

    registry.ensure_discovered()
    tool = registry.get("wangp_video")
    assert tool is not None
    assert tool.capability == "video_generation"
    assert tool.provider == "wangp"

"""Helpers for driving a local WanGP (Wan2GP) install in headless mode.

WanGP is run as its own process with its own Python environment:

    <python> wgp.py --process <job.json> --output-dir <dir>      (cwd = WANGP_DIR)

so OpenMontage never imports torch or WanGP code. Configuration comes from the
environment (``.env`` is loaded by the tool registry):

    WANGP_DIR             WanGP folder containing wgp.py (alias: WANGP_HOME; default ~/WanGP)
    WANGP_PYTHON          optional, or "auto"; otherwise env_uv / env_venv / venv / .venv / env is detected
    WANGP_ENABLED         set to false/0/no to switch the provider off
    WANGP_TEMPLATE        optional settings JSON exported from the WanGP UI, used as the base of every job
    WANGP_TIMEOUT_SECONDS default per-job timeout (7200)

Only one GPU job runs at a time: a lock file in the WanGP folder serialises jobs
from every OpenMontage process on the machine.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ENV_FOLDERS = ("env_uv", "env_venv", "venv", ".venv", "env")
# Only genuine GPU memory exhaustion steps the fallback ladder; other CUDA errors are reported as-is.
REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_NAME = ".openmontage_gpu.lock"
STALE_LOCK_SECONDS = 24 * 3600
# Template keys that must never carry over between shots (per-shot text, seeds and media inputs).
TEMPLATE_DROP_KEYS = {
    "prompt", "negative_prompt", "seed", "image_start", "image_end", "image_refs", "image_guide",
    "image_mask", "image_prompt_type", "video_source", "video_guide", "video_mask", "audio_guide",
    "audio_guide2", "audio_source", "client_id", "state",
}
OOM_PATTERN = re.compile(r"out of memory|OutOfMemoryError|CUBLAS_STATUS_ALLOC_FAILED", re.IGNORECASE)


def _env_python(env_dir: Path) -> Path:
    if os.name == "nt":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def resolve_wangp() -> tuple[Path | None, str | None, str]:
    """Return ``(wangp_dir, python, reason)``; ``reason`` is empty when usable."""
    if os.environ.get("WANGP_ENABLED", "").strip().lower() in {"false", "0", "no", "off"}:
        return None, None, "WanGP is switched off (WANGP_ENABLED=false in .env)."
    raw_dir = os.environ.get("WANGP_DIR") or os.environ.get("WANGP_HOME") or str(Path.home() / "WanGP")
    wangp_dir = Path(raw_dir).expanduser()
    if not (wangp_dir / "wgp.py").is_file():
        return None, None, (
            f"WanGP not found: {wangp_dir / 'wgp.py'} does not exist. Install WanGP "
            "(https://github.com/deepbeepmeep/Wan2GP) and set WANGP_DIR in .env."
        )
    python = (os.environ.get("WANGP_PYTHON") or "").strip()
    if python and python.lower() != "auto":
        if Path(python).is_file():
            return wangp_dir, python, ""
        found = shutil.which(python)
        if found:
            return wangp_dir, found, ""
        return None, None, f"WANGP_PYTHON is neither a file nor a command on PATH: {python}"
    for name in ENV_FOLDERS:
        exe = _env_python(wangp_dir / name)
        if exe.is_file():
            return wangp_dir, str(exe), ""
    return None, None, (
        f"No WanGP Python environment found in {wangp_dir} "
        f"(looked for {', '.join(ENV_FOLDERS)}). Set WANGP_PYTHON in .env."
    )


def snap_frames(n: int) -> int:
    """Wan clip lengths are 4n+1 frames; round up, minimum 5."""
    n = max(5, int(n))
    return n if (n - 1) % 4 == 0 else ((n - 1) // 4 + 1) * 4 + 1


def build_job(
    prompt: str,
    negative_prompt: str,
    *,
    model_type: str,
    resolution: str,
    frames: int,
    steps: int,
    seed: int,
    guidance_scale: float | None = None,
    image_start: Path | str | None = None,
) -> dict[str, Any]:
    job: dict[str, Any] = {
        "model_type": model_type,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "resolution": resolution,
        "video_length": snap_frames(frames),
        "num_inference_steps": int(steps),
        "seed": int(seed),
    }
    if guidance_scale is not None:
        job["guidance_scale"] = guidance_scale
    if image_start is not None:
        job["image_prompt_type"] = "S"
        job["image_start"] = str(Path(image_start).resolve())
    return job


def run_wangp(python: str, wangp_dir: Path, job: dict, work_dir: Path, timeout_s: int) -> tuple[Path | None, str]:
    """Run one WanGP job; return the newest mp4 it wrote (or None) and the log text."""
    work_dir.mkdir(parents=True, exist_ok=True)
    job_path = work_dir / "job.json"
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    log_path = work_dir / "wangp.log"
    before = {p.resolve() for p in work_dir.glob("*.mp4")}
    cmd = [python, "wgp.py", "--process", str(job_path), "--output-dir", str(work_dir)]
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        if os.name == "nt":
            proc = subprocess.Popen(cmd, cwd=str(wangp_dir), stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            proc = subprocess.Popen(cmd, cwd=str(wangp_dir), stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            log.write(f"\n[wangp_video] timed out after {timeout_s}s; WanGP process tree stopped\n")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    new = [p for p in work_dir.glob("*.mp4") if p.resolve() not in before]
    clip = max(new, key=lambda p: p.stat().st_mtime) if new else None
    return clip, text


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop WanGP and its children (a Windows venv python.exe is a launcher with a child)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, check=False, timeout=60)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        proc.kill()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def default_timeout() -> int:
    try:
        return int(os.environ.get("WANGP_TIMEOUT_SECONDS") or 7200)
    except ValueError:
        return 7200


def load_template() -> dict[str, Any]:
    """Settings exported from the WanGP UI (WANGP_TEMPLATE), minus per-shot keys. Empty if unset."""
    raw = (os.environ.get("WANGP_TEMPLATE") or "").strip()
    if not raw:
        return {}
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"WANGP_TEMPLATE must be a JSON object: {path}")
    return {k: v for k, v in data.items() if k not in TEMPLATE_DROP_KEYS}


class GpuBusyError(TimeoutError):
    """Another WanGP job held the GPU lock for longer than the caller would wait."""


@contextmanager
def gpu_lock(wangp_dir: Path, wait_s: float, stale_s: float = STALE_LOCK_SECONDS) -> Iterator[None]:
    """Hold the machine-wide WanGP GPU lock; raise TimeoutError if another job keeps it past wait_s."""
    lock = Path(wangp_dir) / LOCK_NAME
    deadline = time.time() + max(wait_s, 0)
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale_s:
                    lock.unlink(missing_ok=True)  # abandoned by a crashed run
                    continue
            except FileNotFoundError:
                continue
            if time.time() >= deadline:
                raise GpuBusyError(
                    f"another WanGP job is using the GPU (lock {lock}). Wait for it to finish, "
                    "or delete the lock file if no WanGP job is running."
                ) from None
            time.sleep(min(5.0, max(deadline - time.time(), 0.1)))
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def probe_clip(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    data = json.loads(out.stdout)
    stream = data["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": round(int(num) / max(int(den), 1), 3),
        "duration": round(float(data["format"]["duration"]), 3),
    }


def motion_score(path: Path) -> tuple[float, float]:
    """Mean absolute luma change between consecutive frames (0-255) and share of frozen frames."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vf",
         "scale=320:-2,format=gray,tblend=all_mode=difference,signalstats,"
         "metadata=print:key=lavfi.signalstats.YAVG",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=600,
    )
    values = [float(v) for v in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", proc.stderr)]
    if not values:
        return 0.0, 1.0
    frozen = sum(v < 0.15 for v in values) / len(values)
    return round(sum(values) / len(values), 3), round(frozen, 3)

"""WanGP local video generation.

Generates shots with a local WanGP (Wan2GP) install, which runs Wan 2.2 on
low-VRAM GPUs (8 GB is enough for the 5B TI2V model). WanGP runs in its own
process and Python environment via its headless mode; see
``tools/video/_wangp_runner.py`` for configuration (``WANGP_DIR``,
``WANGP_PYTHON``).

Output is never faked: a clip that WanGP did not produce, or that has no real
motion, is returned as a failure.
"""

from __future__ import annotations

import random
import shutil
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from tools.video._wangp_runner import (
    OOM_PATTERN,
    build_job,
    motion_score,
    probe_clip,
    resolve_wangp,
    run_wangp,
    snap_frames,
)

NATIVE_FPS = 24
DEFAULT_NEGATIVE_PROMPT = (
    "text, letters, captions, subtitles, watermark, logo, static image, still frame, frozen, "
    "blurry, low quality, distorted, deformed hands, extra limbs"
)
PRESETS: dict[str, dict[str, Any]] = {
    "full": {"model_type": "ti2v_2_2", "steps": 40, "guidance_scale": None, "seconds_per_clip": 720},
    "fast": {"model_type": "ti2v_2_2", "steps": 30, "guidance_scale": None, "seconds_per_clip": 540},
    "draft": {"model_type": "ti2v_2_2_fastwan", "steps": 3, "guidance_scale": 1, "seconds_per_clip": 120},
}
RESOLUTIONS = {"16:9": ("1280x720", "960x544"), "9:16": ("720x1280", "544x960")}
MIN_MOTION = 0.5
MAX_FROZEN = 0.5


def _ladder(quality: str) -> list[tuple[str, bool]]:
    """(preset, low_res) rungs, stepped only on out-of-memory failures."""
    order = {"full": ["full", "fast", "draft"], "fast": ["fast", "draft"], "draft": ["draft"]}[quality]
    return [(name, False) for name in order] + [("draft", True)]


def _log_tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


class WanGPVideo(BaseTool):
    name = "wangp_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "wangp"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.LOCAL_GPU

    install_instructions = (
        "Install WanGP (https://github.com/deepbeepmeep/Wan2GP) and point OpenMontage at it in .env: "
        "WANGP_DIR=<folder containing wgp.py>, and optionally WANGP_PYTHON=<WanGP env python>."
    )
    fallback = "wan_video"
    fallback_tools = ["wan_video", "ltx_video_local", "image_selector"]
    agent_skills = ["wangp"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "reference_image": True,
        "offline": True,
        "native_audio": False,
        "local_gpu": True,
        "low_vram": True,
    }
    best_for = [
        "free local Wan 2.2 shots on 8 GB laptop GPUs (WanGP memory management)",
        "image-to-video from a character or start image for consistent characters",
        "overnight batch rendering of many 5-second shots",
    ]
    not_good_for = [
        "fast iteration (about 12 minutes per full-quality 5 s clip on an 8 GB laptop)",
        "shots that need readable on-screen text (add text in composition instead)",
        "native audio (Wan clips are silent)",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "negative_prompt": {"type": "string", "default": DEFAULT_NEGATIVE_PROMPT},
            "operation": {"type": "string", "enum": ["text_to_video", "image_to_video"], "default": "text_to_video"},
            "reference_image_path": {"type": "string", "description": "Start image for image_to_video"},
            "aspect": {"type": "string", "enum": sorted(RESOLUTIONS), "default": "16:9"},
            "quality": {"type": "string", "enum": sorted(PRESETS), "default": "full",
                        "description": "full = Wan2.2 5B 40 steps; fast = 30 steps; draft = FastWan 3 steps"},
            "duration_seconds": {"type": "number", "default": 5, "description": "About 5 s is Wan's native clip length"},
            "seed": {"type": "integer"},
            "output_path": {"type": "string"},
            "timeout_seconds": {"type": "integer", "default": 7200},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=4, ram_mb=24000, vram_mb=6000, disk_mb=30000, network_required=False)
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = ["prompt", "operation", "aspect", "quality", "seed", "duration_seconds", "reference_image_path"]
    side_effects = ["writes video file to output_path", "WanGP may download model weights on first use"]
    user_visible_verification = [
        "Watch the clip: the subject and camera should move as the prompt describes",
        "Check for warped hands, faces or garbled text",
    ]

    def get_status(self) -> ToolStatus:
        wangp_dir, _, _ = resolve_wangp()
        return ToolStatus.AVAILABLE if wangp_dir else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        preset = PRESETS.get(str(inputs.get("quality", "full")), PRESETS["full"])
        seconds = float(inputs.get("duration_seconds") or 5)
        return preset["seconds_per_clip"] * max(seconds, 1.0) / 5.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.time()
        wangp_dir, python, reason = resolve_wangp()
        if not wangp_dir:
            return ToolResult(success=False, error=f"{reason} ({self.install_instructions})")

        operation = inputs.get("operation", "text_to_video")
        image = None
        if operation == "image_to_video":
            if not inputs.get("reference_image_path"):
                return ToolResult(success=False, error="image_to_video needs reference_image_path (a local image file).")
            image = Path(str(inputs["reference_image_path"]))
            if not image.is_file():
                return ToolResult(success=False, error=f"reference_image_path not found: {image}")

        aspect = inputs.get("aspect", "16:9")
        quality = inputs.get("quality", "full")
        if aspect not in RESOLUTIONS or quality not in PRESETS:
            return ToolResult(success=False, error=f"aspect must be one of {sorted(RESOLUTIONS)}; quality one of {sorted(PRESETS)}")
        seconds = float(inputs.get("duration_seconds") or 5)
        frames = snap_frames(round(seconds * NATIVE_FPS) + 1)
        seed = int(inputs["seed"]) if inputs.get("seed") is not None else random.randint(0, 2**31 - 1)
        output_path = Path(str(inputs.get("output_path") or f"wangp_video_{seed}.mp4"))
        work_root = output_path.parent / f".wangp_{output_path.stem}"

        last_text = ""
        for rung, (preset_name, low_res) in enumerate(_ladder(quality)):
            preset = PRESETS[preset_name]
            resolution = RESOLUTIONS[aspect][1 if low_res else 0]
            job = build_job(
                str(inputs["prompt"]),
                str(inputs.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT),
                model_type=preset["model_type"],
                resolution=resolution,
                frames=frames,
                steps=preset["steps"],
                seed=seed,
                guidance_scale=preset["guidance_scale"],
                image_start=image,
            )
            work_dir = work_root / f"attempt_{rung + 1}"
            clip, last_text = run_wangp(python, wangp_dir, job, work_dir, int(inputs.get("timeout_seconds") or 7200))
            log_path = str(work_dir / "wangp.log")
            if clip is None:
                if OOM_PATTERN.search(last_text):
                    continue  # out of GPU memory: next rung
                return ToolResult(
                    success=False,
                    error=f"WanGP produced no video (log: {log_path}). Last log lines:\n{_log_tail(last_text)}",
                    duration_seconds=round(time.time() - start, 2),
                )

            info = probe_clip(clip)
            score, frozen = motion_score(clip)
            expected = (frames - 1) / NATIVE_FPS
            if score < MIN_MOTION or frozen >= MAX_FROZEN or info["duration"] < 0.8 * expected:
                return ToolResult(
                    success=False,
                    error=(f"WanGP clip rejected: motion score {score} (min {MIN_MOTION}), frozen share {frozen}, "
                           f"duration {info['duration']}s (expected ~{expected:.1f}s). Clip kept at {clip}. "
                           "Retry with a new seed or a prompt with one clear action."),
                    duration_seconds=round(time.time() - start, 2),
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(clip), str(output_path))
            return ToolResult(
                success=True,
                data={
                    "rung": rung,
                    "quality": preset_name,
                    "model_type": preset["model_type"],
                    "resolution": resolution,
                    "steps": preset["steps"],
                    "seed": seed,
                    "motion_score": score,
                    "frozen_fraction": frozen,
                    "duration": info["duration"],
                    "fps": info["fps"],
                    "width": info["width"],
                    "height": info["height"],
                    "operation": operation,
                    "log_path": log_path,
                },
                artifacts=[str(output_path)],
                cost_usd=0.0,
                duration_seconds=round(time.time() - start, 2),
                seed=seed,
                model=preset["model_type"],
            )

        return ToolResult(
            success=False,
            error=("WanGP ran out of GPU memory on every setting, including the low-resolution draft. "
                   f"Close other GPU apps (or the WanGP web app) and retry. Last log lines:\n{_log_tail(last_text)}"),
            duration_seconds=round(time.time() - start, 2),
        )

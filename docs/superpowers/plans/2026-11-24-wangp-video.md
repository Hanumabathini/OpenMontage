# WanGP Video Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `wangp_video` registry tool so OpenMontage generates video shots through a local WanGP install, via `wgp.py --process`.

**Architecture:** There are two modules. The first, `tools/video/_wangp_runner.py`, holds pure helpers: config resolution, job building, the subprocess run, and clip probing and motion scoring. The second, `tools/video/wangp_video.py`, holds the `BaseTool` subclass that wires the helpers to the registry contract and the fallback ladder. Tests use a fake WanGP folder whose `wgp.py` writes an ffmpeg test clip.

**Tech Stack:** Python 3.10+, stdlib `subprocess`/`json`/`pathlib`, ffmpeg/ffprobe, pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-wangp-video-design.md`

## Global Constraints
- Env vars: `WANGP_DIR` (default `~/WanGP`) and `WANGP_PYTHON` (optional). Env folders are auto-detected in this order: `env_uv`, `env_venv`, `venv`, `.venv`, `env`. The Python is `Scripts/python.exe` on Windows and `bin/python` elsewhere.
- The invocation is `[python, "wgp.py", "--process", <job.json>, "--output-dir", <dir>]` with `cwd=WANGP_DIR`.
- Quality presets:
  - `full` = `ti2v_2_2`, 40 steps
  - `fast` = `ti2v_2_2`, 30 steps
  - `draft` = `ti2v_2_2_fastwan`, 3 steps, `guidance_scale` 1
- Resolutions:
  - 16:9 → `1280x720`, low-memory rung `960x544`
  - 9:16 → `720x1280`, low-memory rung `544x960`
- The default `video_length` is 121 frames. It is snapped to 4n+1.
- Image start: `image_prompt_type` `"S"`, and `image_start` set to the absolute path.
- Acceptance: motion score ≥ 0.5, frozen fraction < 0.5, and duration ≥ 0.8 × the requested seconds.
- Never fabricate a clip from stills. A failure returns `ToolResult(success=False, ...)`.

## Review Focus
- WanGP missing or misconfigured: the tool shows UNAVAILABLE with instructions, never a traceback. Test in Task 2.
- WanGP exits 0 but writes no mp4: the result is a failure that includes the log tail. Test in Task 2.
- A static (frozen) output clip: rejected, no file is placed at `output_path`. Test in Task 2.
- OOM text in the log: the next ladder rung is tried and reported in `data["rung"]`. Test in Task 2.
- A Windows path with spaces in `WANGP_DIR` or `output_path`: an argv list (no shell) keeps it intact. Test in Task 1 (a path with a space).

---

### Task 1: Runner helpers

**Files:**
- Create: `tools/video/_wangp_runner.py`
- Test: `tests/tools/test_wangp_video.py` (shared fixture `fake_wangp(tmp_path, mode)` that writes a fake `wgp.py`. Modes: `"moving"` (testsrc2), `"static"` (color source), `"none"` (no output), `"oom"` (prints "CUDA out of memory", no output))

**Interfaces — Produces:**
- `resolve_wangp() -> tuple[Path | None, str | None, str]` returns `(dir, python, reason)`
- `build_job(prompt, negative_prompt, *, model_type, resolution, frames, steps, seed, guidance_scale=None, image_start=None) -> dict`
- `snap_frames(n: int) -> int` (4n+1, minimum 5)
- `run_wangp(python: str, wangp_dir: Path, job: dict, work_dir: Path, timeout_s: int) -> tuple[Path | None, str]` returns `(newest_mp4_or_None, log_text)`, and writes `job.json` and `wangp.log` into `work_dir`
- `probe_clip(path: Path) -> dict` with keys `width, height, fps, duration`
- `motion_score(path: Path) -> tuple[float, float]` returns `(mean_abs_luma_diff, frozen_fraction)`, using the ffmpeg `tblend=all_mode=difference,signalstats` YAVG method

- [ ] **Step 1: Write failing tests**
  - `test_resolve_uses_env_python` (a `WANGP_DIR` with a space in its name, plus `WANGP_PYTHON`)
  - `test_resolve_detects_env_venv`
  - `test_resolve_reports_missing`, with the reason containing `"wgp.py"`
  - `test_build_job_text` checks the keys `model_type, prompt, negative_prompt, resolution, video_length, num_inference_steps, seed`, and that there is no `image_start`
  - `test_build_job_image` checks `image_prompt_type == "S"` and an absolute `image_start`
  - `test_snap_frames`: 120→121, 121→121, 3→5
  - `test_run_and_motion_moving`: score > 0.5, frozen < 0.5
  - `test_motion_static`: score < 0.5
- [ ] **Step 2:** `pytest tests/tools/test_wangp_video.py -v` → FAIL (module missing)
- [ ] **Step 3:** Implement the helpers above.
- [ ] **Step 4:** `pytest tests/tools/test_wangp_video.py -v` → PASS
- [ ] **Step 5:** Commit: `feat(video): add WanGP runner helpers`

### Task 2: `wangp_video` tool

**Files:**
- Create: `tools/video/wangp_video.py`
- Test: `tests/tools/test_wangp_video.py` (add to it)

**Interfaces — Consumes:** everything from Task 1. **Produces:** `class WanGPVideo(BaseTool)`. It is discovered by the registry.
- Contract fields:
  - `name="wangp_video"`, `provider="wangp"`, `capability="video_generation"`, `runtime=LOCAL_GPU`, `tier=GENERATE`, `stability=EXPERIMENTAL`
  - `capabilities=["text_to_video","image_to_video"]`, `agent_skills=["wangp"]`
  - `fallback_tools=["wan_video","ltx_video_local","image_selector"]`
  - `resource_profile` with `vram_mb=6000`, `ram_mb=24000`
- Input schema:
  - `prompt` (required), `negative_prompt`, `operation`, `reference_image_path`
  - `aspect` (`"16:9"` or `"9:16"`, default `"16:9"`), `quality` (`full`, `fast` or `draft`, default `full`)
  - `duration_seconds` (default 5), `seed`, `output_path`, `timeout_seconds` (default 7200)
- `execute` data keys: `rung, model_type, resolution, steps, seed, motion_score, frozen_fraction, duration, fps, width, height, log_path`. Artifacts: `[output_path]`. `cost_usd=0.0`.
- Ladder = [requested preset] → [`fast` if requested full] → [`draft`] → [`draft` at the low-memory resolution]. The next rung is used only when there's no output and the log matches `out of memory|CUDA error|OutOfMemory`.

- [ ] **Step 1: Write failing tests**
  - `test_status_unavailable_without_wangp`
  - `test_execute_moving_writes_output` (the file exists, `data["rung"]==0`, `cost_usd==0`)
  - `test_execute_static_rejected` (`success is False`, the output is not created)
  - `test_execute_no_output_returns_log_tail`
  - `test_execute_oom_steps_ladder` (the fake writes output only when `job["model_type"]=="ti2v_2_2_fastwan"`, so it expects `data["rung"]>=1`)
  - `test_image_to_video_requires_image`
  - `test_registry_discovers_tool`
- [ ] **Step 2:** Run → FAIL
- [ ] **Step 3:** Implement `WanGPVideo` (`get_status`, `estimate_cost`=0, `estimate_runtime` = 720 s per 5 s clip at full, 540 at fast, 120 at draft, `execute`).
- [ ] **Step 4:** Run → PASS. Also run `pytest tests/contracts -q`, which must stay green.
- [ ] **Step 5:** Commit: `feat(video): add wangp_video tool for local WanGP generation`

### Task 3: Agent skill and docs

**Files:**
- Create: `.agents/skills/wangp/SKILL.md`. Front matter is `name: wangp` plus a description. Sections:
  - Setup: `.env` with `WANGP_DIR`, `WANGP_PYTHON`
  - Prompting: one clear action per 5 s shot, camera move, lighting, no on-screen text
  - Quality presets and timing (about 12 min per full clip on an 8 GB laptop)
  - Image-to-video for consistent characters
  - Licences: Wan2.2 is Apache-2.0
  - Never substitute stills on failure
- Modify: `.env.example` (add commented `WANGP_DIR=` and `WANGP_PYTHON=`), and `docs/PROVIDERS.md` (one row for WanGP local, $0 + GPU).
- [ ] **Step 1:** Add a test, `test_agent_skill_exists`, that checks `.agents/skills/wangp/SKILL.md` exists and contains `WANGP_DIR`. Run it → FAIL.
- [ ] **Step 2:** Write the files. Run → PASS. Also run any skill-index or contract tests that cover `.agents/skills`.
- [ ] **Step 3:** Commit: `docs: add WanGP agent skill and provider docs`

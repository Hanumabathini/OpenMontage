# WanGP ↔ OpenMontage integration

**Status:** built and unit-tested in the cloud; the laptop test is pending (see below). This is not yet a verified integration.

## What exists

- **Tool:** `tools/video/wangp_video.py`, discovered automatically as `wangp_video` (provider `wangp`, capability `video_generation`, runtime `LOCAL_GPU`, cost $0).
- **Runner:** `tools/video/_wangp_runner.py`. It runs `<WanGP python> wgp.py --process <job.json> --output-dir <unique per-shot dir>` with `cwd = WANGP_DIR`. This is the syntax verified on WanGP 20.12 on the laptop.
- **Agent guide:** `.agents/skills/wangp/SKILL.md`, the required Layer-3 reading for agents.
- **Tests:** `tests/tools/test_wangp_video.py` has 31 tests. They use a fake `wgp.py`, so no GPU is needed.

## Directive §25 requirements

| Requirement | Implementation |
|---|---|
| Explicit Python path / discovery | `WANGP_PYTHON` (a path, a command on PATH, or `auto`). Otherwise it detects `env_uv`, `env_venv`, `venv`, `.venv` or `env`. |
| Home / enable flag | `WANGP_DIR` (alias `WANGP_HOME`), `WANGP_ENABLED=false` |
| Exported settings template | `WANGP_TEMPLATE`. Per-shot prompt, seed and media are never inherited. |
| Text-to-video, image-to-video | `operation` = `text_to_video` or `image_to_video` (`reference_image_path` → `image_prompt_type: "S"`, `image_start`) |
| Seed / negative prompt | `seed` (random if unset; reported back), `negative_prompt` (default blocks text, watermarks and frozen frames) |
| Duration / resolution validation | 0 < `duration_seconds` ≤ 10, snapped to 4n+1 frames at 24 fps. `aspect` 16:9 → 1280×720, 9:16 → 720×1280. |
| Unique per-job output dirs | `<output dir>/.wangp_<shot>/attempt_N/` holding `job.json` and `wangp.log` |
| Logs and progress | Full WanGP log per attempt. Failures return the last 25 lines. |
| Timeouts / cancellation | `timeout_seconds` (default `WANGP_TIMEOUT_SECONDS` or 7200). Kills the **whole process tree** (`taskkill /T /F` on Windows). |
| Failure detection / retry | Out-of-memory errors step down the ladder: full → fast → FastWan draft → low-res draft. Other errors fail fast with the log. |
| Output validation | ffprobe size, fps and duration, plus a motion score (frame-difference). Frozen or static clips are **rejected, never substituted**. |
| One GPU job at a time | Machine-wide lock `WANGP_DIR/.openmontage_gpu.lock`. Waits up to `lock_wait_seconds` (default 6 h). A stale lock (>24 h) is reclaimed. |
| Checkpoint / resume | Pinned-seed calls are cacheable (`Determinism.SEEDED`), so a rerun reuses identical clips. Pipelines checkpoint per stage. |
| No paid fallback | `fallback_tools` are only local tools (`wan_video`, `ltx_video_local`, `image_selector`), and OpenMontage must ask the owner before switching provider (AGENT_GUIDE, "Ask Before Major Changes"). |

Not implemented, intentionally: GPU telemetry inside the tool. Use `nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv -l 30` during benchmarks. A WanGP-API/MCP path is also left out, because the headless CLI is proven and the API is not.

## Laptop test (Assignment 2, steps 1–5)

Run these in cmd, with the WanGP web app **stopped**:

```cmd
cd C:\Users\hanum\OpenMontage
.venv\Scripts\activate.bat
git remote add mine https://github.com/Hanumabathini/OpenMontage.git
git fetch mine claude/wangp-video-instagram-youtube-7vzwv0
git checkout -b wangp mine/claude/wangp-video-instagram-youtube-7vzwv0
echo WANGP_DIR=C:\Users\hanum\WanGP>> .env
python -c "from tools.tool_registry import registry; registry.discover(); print(registry.get('wangp_video').get_status())"
python -c "from tools.tool_registry import registry; registry.discover(); r=registry.get('wangp_video').execute({'prompt':'aerial drone shot slowly flying over a futuristic chip factory at sunrise, cranes rotating, trucks moving','quality':'draft','duration_seconds':5,'output_path':'test_wangp.mp4'}); print(r.success, r.error or r.data)"
```

Expected results:
- The first `python` line prints `ToolStatus.AVAILABLE`.
- The second prints `True {... 'motion_score': ..., 'rung': 0 ...}`.
- `test_wangp.mp4` plays and shows motion.

Record the results in SYSTEM-AUDIT.md.

## Benchmarks still needed (directive §30)

| Profile | Settings | Measured time per 5 s | Peak VRAM | Temp | Quality notes |
|---|---|---|---|---|---|
| Fast preview | `quality: draft` (FastWan, 3 steps, 720p) | — | — | — | — |
| Balanced | `quality: fast` (30 steps, 720p) | — | — | — | — |
| Hero | `quality: full` (40 steps, 720p) | first run 78 min (cold); warm run pending | — | — | s01a: excellent night aerial, motion 8.2 |

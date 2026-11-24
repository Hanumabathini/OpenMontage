# WanGP video tool: design

## Intent
The owner makes YouTube and social-media videos on a Windows laptop with an RTX 5070 Laptop GPU (8 GB VRAM) and 32 GB RAM.
WanGP (Wan2GP) is already installed and verified there: a headless `wgp.py --process` run produced a 5 s, 1280×704 Wan2.2 TI2V-5B clip with real motion.
OpenMontage's own `wan_video` tool runs Wan through diffusers and is sized for about 12 GB of VRAM, so on this laptop it is not a usable path.
The goal is for OpenMontage's pipelines to generate video shots through the owner's WanGP install, so that "one prompt → whole video" works locally and costs nothing.

## Goals
- A new registry tool `wangp_video` (capability `video_generation`, provider `wangp`, runtime `LOCAL_GPU`), discovered automatically like the other tools.
- Text-to-video, and image-to-video from a start image (for consistent characters).
- 16:9 and 9:16 output; selectable quality (full, faster, FastWan draft).
- The same proven invocation used on the laptop: `<WanGP python> wgp.py --process <job.json> --output-dir <dir>`.
- A motion check, so frozen or still output is reported as a failure, not a clip.
- A VRAM fallback ladder (lower steps, then FastWan, then a lower resolution), stepped only on out-of-memory errors.
- A Layer-3 agent skill (`.agents/skills/wangp/SKILL.md`) with prompting guidance and limits for 8 GB.
- Tests that run without a GPU, using a fake `wgp.py`.

## Non-goals
- Replacing or changing `wan_video`, ComfyUI or any other existing tool.
- Long-clip chaining inside the tool. Pipelines already cut and stitch shots.
- Installing WanGP. The tool reports clear install or config instructions when WanGP is missing.

## Anti-goals
- The tool never substitutes a still image or a Ken Burns move when generation fails.
- The tool never silently changes the model family. Fallback rungs are reported in the result.

## Constraints
- Config comes from `.env` or the environment: `WANGP_DIR` (default `~/WanGP`) and optional `WANGP_PYTHON`. Without `WANGP_PYTHON`, the tool auto-detects `env_uv`, `env_venv`, `venv`, `.venv` or `env` under `WANGP_DIR`.
- WanGP settings keys (verified against WanGP 20.x source):
  - `model_type`, `prompt`, `negative_prompt`, `resolution` ("WxH"), `video_length` (frames, 4n+1)
  - `num_inference_steps`, `seed`, `guidance_scale`
  - image start: `image_prompt_type: "S"` plus `image_start` (an absolute path)
- Wan2.2 5B renders at 24 fps. 121 frames is about 5 s. WanGP may round 720 to 704.
- Contract fields and style follow `PROJECT_CONTEXT.md` ("When Building New Tools").
- AGPL-3.0 project: the new files are contributed under the project licence.

## Approaches considered
1. **Subprocess tool calling `wgp.py --process`** (chosen). This exact path is proven on the target laptop, needs no running server, works from any pipeline, and is simple to test with a fake `wgp.py`.
2. **WanGP's MCP / web API.** WanGP must already be running in the background, the API surface is larger, and it isn't verified on the laptop. It's a possible later addition.
3. **ComfyUI with Wan workflows.** This means a second install, more VRAM tuning, and moving away from the working WanGP setup.

## Behaviour
- `get_status()` is AVAILABLE when `WANGP_DIR/wgp.py` exists and a Python is found. Otherwise it's UNAVAILABLE, with instructions.
- `execute()`:
  1. Builds `job.json` in a work folder beside `output_path`.
  2. Runs WanGP with a timeout and captures the log to `wangp.log`.
  3. Picks the newest `.mp4`, probes it with ffprobe, and measures motion (mean absolute luma difference between frames, plus the frozen-frame share).
  4. Accepts the clip if the motion score is at least 0.5 and less than half the frames are frozen.
  5. Moves the clip to `output_path` and returns a `ToolResult` with data on the rung, resolution, steps, seed, motion score, duration, fps and log path.
- On an out-of-memory error with no output, it steps down the ladder. Other failures return an error with the tail of the log.
- Quality presets:
  - `quality: "full"` = ti2v_2_2, 40 steps
  - `"fast"` = ti2v_2_2, 30 steps
  - `"draft"` = ti2v_2_2_fastwan, 3 steps, guidance 1
- Aspect: 16:9 → 1280x720, 9:16 → 720x1280. The low-memory rung uses 960x544 or 544x960.
- `estimate_runtime()` uses about 12 minutes per full-quality 5 s clip on the target laptop (WanGP's own estimate). It is documented as approximate.

## Left to the builder
- Exact `ToolResult.data` field names (they follow neighbouring tools).
- Test layout under `tests/tools/`.

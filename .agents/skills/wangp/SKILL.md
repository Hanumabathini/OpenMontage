---
name: wangp
description: Local Wan 2.2 video generation through a WanGP (Wan2GP) install with the wangp_video tool. Use when generating free, offline video shots on a low-VRAM NVIDIA GPU (8 GB and up), animating a character or start image, or planning overnight batches of 5-second clips. Triggers include wangp, wan2gp, local wan, free local video, 8GB GPU video, image-to-video character shot.
---

# WanGP local video (`wangp_video`)

`wangp_video` sends one shot at a time to a local WanGP install, which runs
**Wan2.2 TI2V 5B** (Apache-2.0 weights) with memory management that fits 8 GB GPUs.
WanGP runs as its own process; OpenMontage never loads torch for it.

## Setup (one time)

In `.env`:

```
WANGP_DIR=C:\Users\<you>\WanGP          # folder that contains wgp.py
WANGP_PYTHON=                           # optional; auto-detects env_uv, env_venv, venv, .venv, env
```

Optional settings: `WANGP_ENABLED=false` switches it off, `WANGP_HOME` is an alias of `WANGP_DIR`,
`WANGP_TEMPLATE` points to a settings JSON exported from the WanGP UI (used as the base of every
job; per-shot prompt, seed and media are never inherited), and `WANGP_TIMEOUT_SECONDS` sets the
per-attempt limit (default 7200).

**One GPU job at a time:** a lock file (`.openmontage_gpu.lock` in the WanGP folder) serialises all
WanGP jobs on the machine. A second call waits up to `lock_wait_seconds` (default 6 h) and then
fails with "another WanGP job is using the GPU". Plan batches sequentially.

`get_status()` is AVAILABLE only when `WANGP_DIR/wgp.py` and a Python are found.
The first render downloads the model weights (about 10–20 GB) and tunes kernels,
so the first clip can take an hour. Later clips are much faster.

**Only one thing may use the GPU at a time.** Stop the WanGP web app (or WanGP
Manager's running instance) before rendering through OpenMontage.

## Choosing settings

| Input | Values | Notes |
|---|---|---|
| `quality` | `full` (40 steps), `fast` (30), `draft` (FastWan, 3 steps) | Use `draft` for storyboard samples and `full` for the final render |
| `aspect` | `16:9` (1280x720), `9:16` (720x1280) | WanGP may output 1280x704. Composition crops and scales. |
| `duration_seconds` | default 5 | About 5 s is Wan's native length. Plan longer moments as several shots. |
| `operation` | `text_to_video`, `image_to_video` | `image_to_video` needs `reference_image_path` (a local file) |
| `seed` | integer | Reuse a seed to re-render a shot the same way |

**Timing on an 8 GB laptop (approximate):** `full` is about 12 min per 5 s clip,
`fast` about 9 min, and `draft` about 1–2 min. Announce the total to the user
before a batch: a 3-minute video is 36 shots, about 7 hours at `full`. Suggest
overnight rendering, or `draft` samples first.

## Writing prompts that work with Wan 2.2 5B

- **One clear main action per 5-second shot**, plus a camera move. For example:
  "robotic arm swings across the frame carrying a thin mirror-like silicon disc,
  camera tracks alongside". Multi-step actions ("picks up, places, spins,
  retracts") usually collapse into small, vague motion.
- Describe the subject, the action, the camera, the lighting and the style, in
  that order.
- **No readable text, logos or UI in the shot.** Wan garbles text. Add titles,
  labels and numbers in composition (Remotion or HyperFrames).
- Atmosphere, landscapes, industrial and B-roll scenes, and stylised animation
  work well. Talking presenters with lip-sync, long fights and exact hand
  actions are weak.
- Keep the default negative prompt. It already blocks text, watermarks,
  frozen frames and deformed hands.

## Consistent characters

Use `operation: "image_to_video"` with an image of the character as the first
frame. For variety, prepare one start image per scene (the character in
different places and poses) instead of reusing one image. Only use characters
and faces the user owns or has permission to use. Never use copyrighted
characters or real people's likeness without consent.

## Failure handling (never fake a shot)

- **No video, out of memory:** the tool steps down automatically (full → fast →
  draft → low-resolution draft) and reports the step used in `data["rung"]`.
  Tell the user if the result came from a lower setting.
- **Rejected for low motion or frozen frames:** retry with a new `seed`, or
  simplify the prompt to one action. **Do not** substitute a still image, a Ken
  Burns pan or a slideshow unless the user explicitly approves that change of
  treatment.
- **Other errors:** the result includes the last WanGP log lines and the
  `wangp.log` path. Show them to the user.

## Licensing

Wan2.2 weights are Apache-2.0, so commercial use is fine. WanGP's own licence
lets users sell or monetize what they create with it. Label AI-generated
footage that looks realistic as a concept or AI visualization, and tell the
user to use YouTube's altered or synthetic content disclosure.

# System audit

**Date:** 24 November 2026 · **Auditor:** Claude Code (cloud session)

**How this was done:** most checks were made with the owner pasting command output from the laptop.
This cloud session has **no direct access to the laptop**. Remote Control folders were offered, but none could be used from a cloud session.
So every "verified" item below cites the evidence the owner pasted or uploaded. Anything not shown that way is marked untested.

Status legend:
- ✅ verified working
- 🟡 installed, but not yet tested
- ⛔ missing
- ❌ broken
- ⚪ optional or not needed

## Hardware and OS

| Component | Status | Evidence | Notes |
|---|---|---|---|
| GPU: NVIDIA GeForce RTX 5070 Laptop, 8151 MiB | ✅ | `nvidia-smi` output, 23 Nov 2026 | Driver 591.97, CUDA 13.1. At idle, 238 MiB used, P8 state, 52 °C. |
| Windows build | ✅ | `Microsoft Windows [Version 10.0.26300.10075]` | Assumed to be Windows 11 (build 26300); not confirmed via `winver`. |
| RAM: 32 GB | 🟡 | Owner statement | Not measured. Run `scripts\check_system.bat` from the git-github repo. |
| Free disk: about 600 GB | 🟡 | Owner statement | Not measured. Same command. |
| CPU: AMD Ryzen | 🟡 | Owner statement | Model not recorded. |
| Thermals under 8-hour load | 🟡 | — | Benchmark needed. See WANGP-INTEGRATION.md. |

## Software on the laptop

| Component | Status | Evidence | Notes |
|---|---|---|---|
| Python 3.11.9 (system) | ✅ | `python --version` | |
| Python 3.12 (OpenMontage .venv) | ✅ | pip installed cp312 wheels | `py -3` picked 3.12. That's fine. |
| Node.js v26.13.0 | ✅ | `node --version` | Very new. If Remotion has problems, Node 22 LTS is the fallback. |
| npm, esbuild install script | ✅ | `npm install-scripts approve esbuild` + `npm rebuild esbuild` succeeded | 11 npm audit warnings in dev dependencies. **Do not** run `npm audit fix --force`. |
| FFmpeg / FFprobe 9.1 (gyan.dev full) | ✅ | `ffmpeg -version` | Built with nvenc, cuvid, libx264, libass and whisper. |
| Git | ✅ | clones and pulls succeeded | |
| WanGP 20.12, `C:\Users\hanum\WanGP` | ✅ | WanGP Manager screenshot: "Registered Python 3.11.9, PyTorch 2.10.0+cu130, CUDA 13.0, port 7860" | Env folder: `env_venv`. Managed by WanGP Manager 0.1.20 (experimental). |
| WanGP headless `wgp.py --process job.json --output-dir DIR` | ✅ | Two real renders: motion test, and Terafab shot s01a | Syntax confirmed against the installed version. |
| Wan2.2 TI2V 5B weights | ✅ | Downloaded on first render | Apache-2.0. |
| First render (cold start) | ✅ | 4,660 s ≈ 78 min, 1280×704, 24 fps, 5.04 s, motion 2.91 | Includes the download, Triton compile and autotuning. |
| Warm render time (s01a) | 🟡 | Clip received: 1280×704, 24 fps, 5.04 s, motion 8.21, 0% frozen | **Timing line not yet received.** WanGP's own estimate was about 11 min 42 s (rung 0, 40 steps). |
| OpenMontage (upstream clone at `C:\Users\hanum\OpenMontage`) | ✅ | `registry.discover()` found 164 tools | It is a clone of calesthio/OpenMontage. The owner's fork, with `wangp_video`, still needs fetching. |
| Remotion composer | 🟡 | `npm install` OK | `render_demo.py` not yet run. |
| Piper TTS | 🟡 | `pip install piper-tts` OK | Not yet benchmarked. Each voice model has its own licence. |
| `wangp_video` provider (this fork, branch `claude/wangp-video-instagram-youtube-7vzwv0`) | 🟡 | 31 unit tests and 2,254 repo tests pass in the cloud, using a fake WanGP | **Not yet run on the laptop.** See the steps in WANGP-INTEGRATION.md. |
| Kokoro TTS (Apache-2.0) | ✅ (cloud) | Generated the Terafab narration: 18 clips, all ≤ 9.1 s | Runs on CPU through kokoro-onnx. Not installed on the laptop. |
| Claude Code / Codex on the laptop | ⛔ | — | Needed for unattended OpenMontage runs. Uses the owner's plan, not an API key. |
| Blender | ⛔ | — | The directive asks for technical 3D at 20%. Install is optional; the free path uses HyperFrames and Remotion diagrams. |
| Windows Task Scheduler jobs | ⛔ | — | Not set up. Must be tested before promising unattended operation. |
| Laptop power settings | 🟡 | Commands given (`powercfg /change standby-timeout-ac 0`) | Not confirmed applied. |
| Armoury Crate | 🟡 | Owner has it | Recommended: Battery Health Charging Balanced (80%), Performance mode. Not confirmed. |

## Repositories in the directive

| Repository | Status | Licence | Verdict |
|---|---|---|---|
| Hanumabathini/OpenMontage | ✅ audited, extended | AGPL-3.0 | **Production controller.** The `wangp_video` provider was added here. Private use for the channel is fine. Changes must be shared if the software is distributed or offered as a network service. |
| deepbeepmeep/Wan2GP (WanGP) | ✅ verified on laptop | WanGP Community License 2.0 | Outputs may be sold or monetized. Credit WanGP if you sell an output directly. |
| Hanumabathini/git-github (`shorts-kit`, `terafab`) | ✅ | (owner's code) | Terafab 3-minute package: narration, music, captions, render and assembly scripts. Proven on the laptop. |
| Hanumabathini/social-media-research-skills | ✅ audited | MIT | Needs a **paid** ScrapeCreators key. Not active, because the $0 budget applies. |
| Hanumabathini/autoclip | ✅ audited | MIT | Long video to Shorts/Reels clipper. Analysis needs a cloud LLM key or local Ollama. Use only on the channel's own videos. |
| Hanumabathini/last30days-skill | ✅ audited (read-only) | MIT | Reddit, Hacker News, Polymarket and GitHub work with **no key**, so it's a good free trend source. Not run in the cloud because the run was blocked by session permissions. Run it on the laptop, and pass `--no-browser-cookies`. |
| Hanumabathini/chatterbox | ✅ audited | MIT | Candidate narrator. Chatterbox-Turbo (350M, English) is a strong fit. Benchmark it against Kokoro. |
| Hanumabathini/ACE-Step-1.5 | ✅ audited | MIT | Candidate music model. The developers say outputs are commercially usable. Benchmark on 8 GB. |
| Hanumabathini/hyperframes | ✅ audited | Apache-2.0 | Already used inside OpenMontage for motion graphics. No separate install needed. |
| Hanumabathini/AI-Youtube-Shorts-Generator | ✅ audited | MIT | Overlaps with autoclip. Its default `--mode api` uses the paid MuAPI. Its `--mode local` uses yt-dlp and faster-whisper but still needs an LLM. **Not needed**, since autoclip or OpenMontage clip-factory cover it. |
| Hanumabathini/short-video-factory | ✅ audited | AGPL-3.0 | A Chinese-language desktop app for product-marketing shorts. **Low fit**, so skip it. |
| Hanumabathini/social-media-agent | ⛔ not audited | ? | Attaching it to this session was refused, so it couldn't be read. The owner should confirm it's wanted. |
| Hanumabathini/OpenCreator | ⛔ not audited | ? | Same as above. |
| Hanumabathini/local-deep-research | ⛔ not audited | ? | Same as above. |

## Accounts and keys (never stored in git)

| Item | Status | Needed for |
|---|---|---|
| YouTube channel | ⛔ unknown | Everything. The owner should confirm the channel exists, and its handle. |
| YouTube Data API v3 key (free, from a Google Cloud project) | ⛔ | Legitimate public-data research: competitor uploads, view counts, outlier baselines. **This is the most important missing input for the intelligence work.** |
| YouTube Analytics (OAuth, owner's channel) | ⛔ | First-party metrics, once videos are live. |
| ScrapeCreators key | ⛔ (paid) | Not authorized under the $0 budget. |
| AdSense / YPP | ⛔ | Owner-led, after the channel is eligible. |

## Bottlenecks and risks

1. **GPU time.** At about 12 min per full-quality 5 s clip, a 15-minute episode with 25% WanGP footage (about 45 clips) needs about 9 GPU-hours. That is one night per episode at most, so roughly 2 episodes a week at the very most. This is an unconfirmed planning figure until the s01a timing arrives.
2. **No first-party or YouTube public-data access yet.** The viral-intelligence work is limited to news and industry demand. See the daily report.
3. **Nothing can run unattended from the cloud session.** Production runs on the laptop, through Claude Code or Codex there, or through the scripts.
4. **The licensed real-footage share (40%)** needs a rights workflow: Pexels, Pixabay, NASA, Wikimedia and company press kits, with each licence recorded in COPYRIGHT-REGISTRY.json.

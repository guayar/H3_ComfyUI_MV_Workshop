# MiniMax H3 workflow: partial research (round 1)

Status: PARTIAL. Several claims in the brief could not be verified, and the official Comfy docs page was unreachable (docs.comfy.org does not resolve from this session).

## Verified (at least one source found)

- MiniMax H3 exists in ComfyUI with separate checkpoints per mode: Ref2VA (`minimax_h3_ref2va_pruned_int8_convrot.safetensors`) and FL2VA. Weights live in `Comfy-Org/MiniMax-H3` on Hugging Face. Ref2VA also needs the Qwen3-VL 32B text encoder and H3 video and audio VAEs.
  - Source: https://www.runcomfy.com/comfyui-workflows/minimax-h3-ref-to-video-in-comfyui-native-stereo-audio
  - Source: https://www.digitalcreativeai.net/en/post/minimax-h3-comfyui-reference-to-video
- Official template file: `video_minimax_h3_r2v.json` (ComfyUI Browse Templates > Video). Recommended ComfyUI 0.30.0 or later (the brief says 0.40.0; not checked).
- Ref2VA reference limit: up to 9 images (third-party guide, model card not read).
- Fun ControlNet Union patch conditions H3 on Canny, Depth, HED, MLSD and Pose control videos, plus mask-based video inpainting. Works with both fl2va and ref2va transformer files.
  - Source: https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fun-controlnet (listed by search; FETCH FAILED, only the search snippet was seen)
- Target frame grid 17n+5 at 24 fps, 5 to 15 s. A control video longer than the target is trimmed; a shorter one holds its last frame (per search snippet).
- Turbo/Lightning 4-step LoRA exists, with a small loss in audio and motion quality (per the same docs snippet).
- Extender repo found: `tritant/ComfyUI_MiniMax_H3_Extender` (Apache-2.0, Python, ~149 stars per Trendshift). Nodes include an extender node and "MiniMax H3 Tail From Latent" for chaining clips. Source: https://trendshift.io/repositories/157037. README NOT read.
- Camera motion LoRA (orbit, dolly, elevation) exists, hosted by a community author. Third-party claim only (https://www.runcomfy.com/de/comfyui-workflows/minimax-h3-camera-control-comfyui-orbit-dolly-elevation).

## NOT verified (brief claims that the search did not confirm)

- `kat3ri/ComfyUI-MiniMax-H3-Extend`, `ref_decay`, `ref_ramp`: no results. Treat as unknown.
- "HybridWindows" repo: not checked.
- "ComfyUI-MiniMax-H3-LongMedia": not checked.
- Native node names (ReferenceToVideo, AddGuide, FunControlNetApply, PlantExtendPrefix, ExtendStitch), LMS sharpness LoRA, H3 latent upscaler, Director (DirectorCS): not confirmed.
- Speech/lip silencing method: no source yet.
- Camera-control accuracy numbers: none found.
- Any long-video drift or join-consistency results for H3: none found.
- Release date claim (open-sourced 2026-08-03): one Korean guide only.
- AMD ROCm compatibility of any H3 node: not checked.

## Open questions still to research

1. ControlNet per clip across joins in the Extender path, with strength and start/end percent values (needs the tritant README).
2. Speech suppression for H3 Ref2VA.
3. Physical effects (tile flaps, scenery change) via mask/control video.
4. Faster sharpness restorer than the LMS LoRA.
5. ROCm: any open issues for H3 on gfx1201.

## Needed from the user

- Approval to read and install `tritant/ComfyUI_MiniMax_H3_Extender` (third-party code, needs approval per the brief).
- Allow `docs.comfy.org` in the session network settings if the official ControlNet and H3 docs are required.
- The target repo `owner/repo` for the workflow.

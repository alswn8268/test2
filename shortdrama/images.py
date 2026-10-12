"""컷마다 쓸 그림 준비.

- folder     : assets/<에피소드id>/ 에서 shot_01.png → <화자id>.png → background.png 순으로 찾음
               (인물 사진 한 장만 만들어 두면 그 인물의 모든 컷에 재사용 → 얼굴이 안 바뀜)
- sdwebui    : 로컬 Stable Diffusion WebUI/Forge API로 생성 (화자별 고정 seed로 얼굴 일관성 유지)
- placeholder: 색 배경 + 이름 카드 (테스트용)
"""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config
from .schema import CAPTION, Episode, Role, Shot

EXTS = (".png", ".jpg", ".jpeg", ".webp")
ROLE_COLORS = {
    Role.villain: ((120, 20, 20), (30, 5, 5)),
    Role.hero: ((20, 60, 130), (5, 15, 40)),
    Role.helper: ((70, 70, 70), (20, 20, 20)),
    None: ((60, 50, 30), (15, 12, 8)),
}


def _find(folder: Path, stem: str) -> Path | None:
    for ext in EXTS:
        p = folder / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def font(cfg: Config, size: int) -> ImageFont.FreeTypeFont:
    path = cfg.resolve("subtitle.font_file")
    for candidate in (path, Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def placeholder(cfg: Config, ep: Episode, shot: Shot, out: Path) -> Path:
    w, h = cfg.get_path("video.width"), cfg.get_path("video.height")
    ch = ep.character(shot.speaker)
    top, bottom = ROLE_COLORS[ch.role if ch else None]
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):  # 세로 그라데이션
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    label = ch.name if ch else "(자막)"
    sub = f"{ch.age}세 · {ep.location}" if ch else ep.location
    for text, size, y in ((label, 150, h * 0.22), (sub, 60, h * 0.32), (shot.emotion.value, 70, h * 0.38)):
        f = font(cfg, size)
        tw = draw.textlength(text, font=f)
        draw.text(((w - tw) / 2, y), text, font=f, fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def _seed(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def sdwebui(cfg: Config, ep: Episode, shot: Shot, out: Path) -> Path:
    ch = ep.character(shot.speaker)
    prompt = ", ".join(filter(None, [
        "photorealistic, cinematic Korean drama still, vertical portrait, close-up",
        ch.look_prompt if ch else None, shot.visual, ep.background_prompt,
    ]))
    body = {
        "prompt": prompt,
        "negative_prompt": cfg.get_path("images.negative_prompt", ""),
        "width": 768, "height": 1344,  # 9:16 근사, 렌더 때 1080x1920으로 확대
        "steps": cfg.get_path("images.steps", 28),
        "seed": _seed(ep.id + shot.speaker),  # 같은 인물 = 같은 seed
    }
    url = cfg.get_path("images.sdwebui_url").rstrip("/") + "/sdapi/v1/txt2img"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.load(resp)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(data["images"][0]))
    return out


def image_for_shot(cfg: Config, ep: Episode, idx: int, shot: Shot, work: Path) -> Path:
    provider = cfg.get_path("images.provider", "folder")
    stem = f"shot_{idx + 1:02d}"
    asset_dir = cfg.resolve("paths.assets") / ep.id

    if provider == "folder":
        speaker = shot.speaker if shot.speaker != CAPTION else None
        for name in filter(None, (stem, speaker, "background")):
            found = _find(asset_dir, name)
            if found:
                return found
        return placeholder(cfg, ep, shot, work / "images" / f"{stem}.png")

    if provider == "sdwebui":
        cached = _find(asset_dir / "generated", stem)
        return cached or sdwebui(cfg, ep, shot, asset_dir / "generated" / f"{stem}.png")

    if provider == "placeholder":
        return placeholder(cfg, ep, shot, work / "images" / f"{stem}.png")

    raise ValueError(f"알 수 없는 images.provider: {provider}")

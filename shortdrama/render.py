"""ffmpeg 렌더링: 컷별 클립(천천히 다가가는 줌 + 음성) → 이어붙이기 → 자막·배경음악 입히기."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from .config import Config
from .images import font
from .media import run
from .subtitles import wrap


def shot_clip(cfg: Config, image: Path, audio: Path | None, seconds: float,
              emphasis: bool, out: Path) -> None:
    w, h, fps = cfg.get_path("video.width"), cfg.get_path("video.height"), cfg.get_path("video.fps")
    frames = max(1, round(seconds * fps))
    # 1.5배로 키운 뒤 줌 → 떨림 감소. 강조 컷은 빠르게 확 다가가는 '펀치 줌'
    zoom = "min(1+on*0.012,1.22)" if emphasis else "1+on*0.0007"
    vf = (f"scale={int(w * 1.5)}:{int(h * 1.5)}:force_original_aspect_ratio=increase,"
          f"crop={int(w * 1.5)}:{int(h * 1.5)},"
          f"zoompan=z='{zoom}':d={frames}:s={w}x{h}:fps={fps}"
          f":x='iw/2-(iw/zoom/2)':y='ih/3-(ih/zoom/3)',format=yuv420p")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(image)]
    if audio:
        cmd += ["-i", str(audio)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-vf", vf, "-af", "apad,aresample=48000", "-ac", "2", "-t", f"{seconds:.3f}",
            "-map", "0:v", "-map", "1:a", "-r", str(fps),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", str(out)]
    run(cmd)


def concat(clips: list[Path], out: Path) -> None:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", listing.name, "-c", "copy", out.name], cwd=out.parent)


def burn(cfg: Config, video: Path, ass: Path, out: Path) -> None:
    """자막을 입히고, 배경음악이 설정돼 있으면 대사 아래로 깔아준다."""
    fonts_dir = cfg.resolve("subtitle.font_file").parent
    local_fonts = video.parent / "fonts"  # 필터 경로 이스케이프 문제를 피하려고 작업 폴더로 복사
    if fonts_dir.exists() and not local_fonts.exists():
        shutil.copytree(fonts_dir, local_fonts)
    vf = f"ass={ass.name}" + (":fontsdir=fonts" if local_fonts.exists() else "")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video.name]
    bgm = cfg.get_path("video.bgm")
    if bgm:
        bgm_path = cfg.resolve("video.bgm")
        db = cfg.get_path("video.bgm_volume_db", -20)
        cmd += ["-stream_loop", "-1", "-i", str(bgm_path),
                "-filter_complex",
                f"[0:v]{vf}[v];[1:a]volume={db}dB[b];[0:a][b]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf, "-c:a", "copy"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-movflags", "+faststart", str(out.resolve())]
    run(cmd, cwd=video.parent)


def end_card_image(src: Path, out: Path) -> Path:
    """마지막 컷 그림을 어둡게 해서 댓글 유도 자막 배경으로 사용."""
    img = Image.open(src).convert("RGB")
    ImageEnhance.Brightness(img).enhance(0.35).save(out)
    return out


def thumbnail(cfg: Config, image: Path, text: str, out: Path) -> None:
    """썸네일: 첫 컷 그림 + 노란 큰 글씨."""
    w, h = cfg.get_path("video.width"), cfg.get_path("video.height")
    img = ImageOps.fit(Image.open(image).convert("RGB"), (w, h))
    img = ImageEnhance.Brightness(img).enhance(0.8)
    draw = ImageDraw.Draw(img)
    f = font(cfg, int(h * 0.075))
    lines = wrap(text, 8)
    y = h * 0.62
    for line in lines:
        tw = draw.textlength(line, font=f)
        draw.text(((w - tw) / 2, y), line, font=f, fill=(255, 229, 0),
                  stroke_width=12, stroke_fill=(0, 0, 0))
        y += h * 0.09
    img.save(out, quality=92)

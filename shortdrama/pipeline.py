"""전체 흐름: 대본 → 더빙 → 원칙 검사 → 그림 → 컷 렌더 → 이어붙이기 → 자막 → 완성본.

각 단계 결과는 output/<id>/work/ 에 캐시된다. 대사 한 줄만 고치면 그 컷의 음성만 다시 만든다.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from .config import Config
from .images import image_for_shot
from .media import require_ffmpeg
from .render import burn, concat, end_card_image, shot_clip, thumbnail
from .schema import CAPTION, Episode
from .subtitles import build_ass
from .tts import estimate_seconds, synthesize
from .validator import Issue, append_history, check, load_history


class ValidationFailed(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))


def _audio_key(cfg: Config, ep: Episode, idx: int) -> str:
    """대사·화자·음성 설정이 같으면 같은 키 → 음성 재사용."""
    s = ep.shots[idx]
    ch = ep.character(s.speaker)
    raw = "|".join([cfg.get_path("tts.provider"), s.line, ch.model_dump_json() if ch else ""])
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def estimate_durations(cfg: Config, ep: Episode) -> list[float]:
    """음성을 만들지 않고 대략적인 컷 길이만 계산 (check 명령용)."""
    pad = cfg.get_path("video.shot_padding", 0.25)
    return [cfg.get_path("video.caption_shot_seconds", 2.2) if s.speaker == CAPTION
            else estimate_seconds(s.line) + pad for s in ep.shots]


def metadata_text(ep: Episode, total: float) -> str:
    tags = ["#숏드라마", "#사이다", "#참교육", "#진상", f"#{ep.location.split()[-1]}"]
    return (f"제목: {ep.title}\n\n"
            f"설명:\n{ep.end_caption}\n\n{' '.join(tags)}\n\n"
            f"길이: {total:.1f}초 / 반전: {ep.twist_type.value} / 장소: {ep.location}\n")


def produce(cfg: Config, ep: Episode, force: bool = False, log=print) -> Path:
    require_ffmpeg()
    out_dir = cfg.resolve("paths.output") / ep.id
    work = out_dir / "work"
    (work / "audio").mkdir(parents=True, exist_ok=True)
    (work / "clips").mkdir(parents=True, exist_ok=True)

    # 1) 더빙
    log(f"[1/5] 더빙 ({cfg.get_path('tts.provider')}) - {len(ep.shots)}컷")
    pad = cfg.get_path("video.shot_padding", 0.25)
    audios: list[Path | None] = []
    durations: list[float] = []
    for i, s in enumerate(ep.shots):
        if s.speaker == CAPTION:
            audios.append(None)
            durations.append(cfg.get_path("video.caption_shot_seconds", 2.2))
            continue
        a = work / "audio" / f"shot_{i + 1:02d}_{_audio_key(cfg, ep, i)}.mp3"
        durations.append(synthesize(cfg, s.line, ep.character(s.speaker), a) + pad)
        audios.append(a)

    # 2) 원칙 검사
    log("[2/5] 7대 원칙 검사")
    issues = check(cfg, ep, durations, load_history(cfg))
    for issue in issues:
        log("   " + str(issue))
    if any(i.level == "ERROR" for i in issues) and not force:
        raise ValidationFailed([i for i in issues if i.level == "ERROR"])

    # 3) 그림 + 컷 클립
    log(f"[3/5] 그림 준비 + 컷 렌더 ({cfg.get_path('images.provider')})")
    clips, timeline, t, last_image = [], [], 0.0, None
    for i, (s, a, d) in enumerate(zip(ep.shots, audios, durations)):
        img = image_for_shot(cfg, ep, i, s, work)
        clip = work / "clips" / f"{i + 1:02d}.mp4"
        shot_clip(cfg, img, a, d, s.emphasis, clip)
        clips.append(clip)
        timeline.append((t, t + d))
        t += d
        last_image = img
        log(f"   {i + 1:02d}  {d:4.1f}초  {s.emotion.value:<6} {s.line}")
    end_sec = cfg.get_path("video.end_card_seconds", 2.5)
    end_img = end_card_image(last_image, work / "end_card.png")
    end_clip = work / "clips" / "99_end.mp4"
    shot_clip(cfg, end_img, None, end_sec, False, end_clip)
    clips.append(end_clip)
    total = t + end_sec

    # 4) 이어붙이기 + 자막
    log("[4/5] 이어붙이기 + 자막")
    joined = work / "clips" / "joined.mp4"
    concat(clips, joined)
    ass = work / "clips" / "subtitles.ass"
    ass.write_text(build_ass(cfg, ep, timeline, total), encoding="utf-8")
    final = out_dir / f"{ep.id}.mp4"
    burn(cfg, joined, ass, final)

    # 5) 업로드용 부속물
    log("[5/5] 썸네일 + 업로드 정보")
    thumbnail(cfg, image_for_shot(cfg, ep, 0, ep.shots[0], work), ep.thumbnail_text, out_dir / "thumbnail.jpg")
    (out_dir / "upload.txt").write_text(metadata_text(ep, total), encoding="utf-8")
    append_history(cfg, {"id": ep.id, "twist_type": ep.twist_type.value, "location": ep.location,
                         "seconds": round(total, 1), "made_at": datetime.now().isoformat(timespec="seconds")})
    log(f"완성: {final} ({total:.1f}초)")
    return final

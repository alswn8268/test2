"""대사 → 음성 파일. 기본은 무료 edge-tts, 테스트용 silent 제공."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .config import Config
from .media import make_silence, probe_duration
from .schema import Character, Role


def voice_settings(cfg: Config, ch: Character) -> tuple[str, str, str]:
    """캐릭터 → (음성, 빠르기, 높낮이). YAML에 직접 적은 값이 항상 우선."""
    voice = ch.voice or cfg.get_path(f"tts.voices.{ch.gender.value}")
    rate, pitch = "+0%", "+0Hz"
    if ch.age >= cfg.get_path("tts.senior_age", 60):
        rate = cfg.get_path("tts.senior_rate", rate)
        pitch = cfg.get_path("tts.senior_pitch", pitch)
    elif ch.role == Role.villain:
        rate = cfg.get_path("tts.villain_rate", rate)
    return voice, ch.voice_rate or rate, ch.voice_pitch or pitch


def estimate_seconds(text: str) -> float:
    """한국어 낭독 속도(초당 약 6자)로 대략 길이 추정."""
    return max(1.2, len(text.replace(" ", "")) / 6.0 + 0.4)


def synthesize(cfg: Config, text: str, ch: Character, out: Path) -> float:
    """음성을 out(mp3)에 저장하고 길이(초)를 돌려준다. 이미 있으면 재사용."""
    if out.exists() and out.stat().st_size > 0:
        return probe_duration(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    provider = cfg.get_path("tts.provider", "edge")

    if provider == "silent":
        make_silence(out, estimate_seconds(text))
    elif provider == "edge":
        import edge_tts

        voice, rate, pitch = voice_settings(cfg, ch)
        tmp = out.with_suffix(".part.mp3")
        asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(tmp)))
        tmp.rename(out)
    else:
        raise ValueError(f"알 수 없는 tts.provider: {provider}")
    return probe_duration(out)

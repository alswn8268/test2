"""7대 원칙 자동 검사.

ERROR가 하나라도 있으면 렌더링을 멈춘다(--force로 무시 가능). WARN은 알려만 준다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .schema import CAPTION, Emotion, Episode, Role
from .subtitles import chunk

EMOTION_ORDER = [Emotion.anger, Emotion.curiosity, Emotion.bigger_anger, Emotion.cider, Emotion.laugh]


@dataclass
class Issue:
    level: str  # "ERROR" | "WARN"
    rule: str
    message: str

    def __str__(self) -> str:
        icon = "❌" if self.level == "ERROR" else "⚠️"
        return f"{icon} [{self.rule}] {self.message}"


def check(cfg: Config, ep: Episode, durations: list[float] | None = None,
          history: list[dict] | None = None) -> list[Issue]:
    """durations를 주면 시간 관련 규칙(3초 훅, 10초 규칙, 전체 길이)까지 검사한다."""
    r = cfg.get_path
    issues: list[Issue] = []
    err = lambda rule, msg: issues.append(Issue("ERROR", rule, msg))
    warn = lambda rule, msg: issues.append(Issue("WARN", rule, msg))

    if not ep.shots:
        err("구조", "컷이 하나도 없습니다.")
        return issues

    # 원칙 3: 인물 수, 화자 정의
    if len(ep.characters) > r("rules.max_characters", 3):
        err("원칙3 쉬운 이해", f"등장인물이 {len(ep.characters)}명입니다. 3명 이하로 줄이세요.")
    ids = {c.id for c in ep.characters}
    for i, s in enumerate(ep.shots, 1):
        if s.speaker != CAPTION and s.speaker not in ids:
            err("구조", f"{i}번 컷 화자 '{s.speaker}'가 characters에 없습니다.")
    roles = {c.role for c in ep.characters}
    if Role.villain not in roles or Role.hero not in roles:
        err("원칙3 쉬운 이해", "진상(villain)과 주인공(hero)이 모두 있어야 선악이 바로 보입니다.")

    # 원칙 1: 첫 컷
    first = ep.shots[0]
    if first.speaker == CAPTION:
        err("원칙1 3초 훅", "첫 컷이 자막입니다. 진상의 고성 대사로 시작하세요.")
    elif ep.character(first.speaker) and ep.character(first.speaker).role != Role.villain:
        warn("원칙1 3초 훅", "첫 대사를 진상이 하면 분노가 더 빨리 터집니다.")
    if not first.line.rstrip().endswith(("!", "?", "!?", "?!")):
        warn("원칙1 3초 훅", f"첫 대사에 감정(!/?)이 없습니다: \"{first.line}\"")

    # 원칙 5: 감정 순서
    seq = [s.emotion for s in ep.shots]
    if seq[0] != Emotion.anger:
        err("원칙5 감정 설계", "첫 감정은 '분노'여야 합니다.")
    if seq[-1] != Emotion.laugh:
        err("원칙5 감정 설계", "마지막 컷 감정은 '웃음'이어야 합니다.")
    for need in EMOTION_ORDER:
        if need not in seq:
            err("원칙5 감정 설계", f"'{need.value}' 구간이 없습니다.")
    ranks = [EMOTION_ORDER.index(e) for e in seq]
    for i in range(1, len(ranks)):
        if ranks[i] < ranks[i - 1] - 1:
            warn("원칙5 감정 설계", f"{i + 1}번 컷에서 감정이 '{seq[i - 1].value}' → '{seq[i].value}'로 크게 되돌아갑니다.")

    # 원칙 4: 반복 제거
    seen = set()
    for i, s in enumerate(ep.shots, 1):
        key = s.line.replace(" ", "")
        if key in seen:
            warn("원칙4 10초 새 정보", f"{i}번 컷 대사가 앞과 똑같습니다.")
        seen.add(key)
    for i in range(2, len(ep.shots)):
        if ep.shots[i].speaker == ep.shots[i - 1].speaker == ep.shots[i - 2].speaker != CAPTION:
            warn("원칙4 10초 새 정보", f"{i - 1}~{i + 1}번 컷을 한 사람이 연달아 말합니다. 대화를 주고받게 하세요.")

    # 원칙 6: 자막 길이
    max_chars, max_lines = r("subtitle.max_chars_per_line", 11), r("subtitle.max_lines", 2)
    for i, s in enumerate(ep.shots, 1):
        cards = chunk(s.line, max_chars, max_lines)
        if len(cards) > 2:
            warn("원칙6 가독성", f"{i}번 컷 대사가 자막 {len(cards)}장으로 나뉩니다. 더 짧게: \"{s.line}\"")
    if len(ep.thumbnail_text) > 12:
        warn("원칙6 가독성", f"상단 문구가 {len(ep.thumbnail_text)}자입니다. 12자 이내 권장.")

    # 시간 규칙
    if durations:
        total = sum(durations)
        if durations[0] > r("rules.first_hook_seconds", 3.0) * 1.6:
            warn("원칙1 3초 훅", f"첫 컷이 {durations[0]:.1f}초입니다. 3초 안에 끝나게 줄이세요.")
        for i, d in enumerate(durations, 1):
            if d > r("rules.max_shot_seconds", 10.0):
                err("원칙4 10초 새 정보", f"{i}번 컷이 {d:.1f}초입니다. 10초 넘게 새 정보가 없습니다.")
        if not r("rules.min_total_seconds", 45) <= total <= r("rules.max_total_seconds", 95):
            warn("길이", f"전체 {total:.0f}초입니다. 권장 {r('rules.min_total_seconds')}~{r('rules.max_total_seconds')}초.")

    # 원칙 7: 최근 영상과 중복
    recent = [h for h in (history or []) if h.get("id") != ep.id][-r("rules.history_window", 3):]
    if any(h.get("twist_type") == ep.twist_type.value for h in recent):
        warn("원칙7 복제 금지", f"최근 {len(recent)}편 안에 같은 반전 유형('{ep.twist_type.value}')이 있습니다.")
    if any(h.get("location") == ep.location for h in recent):
        warn("원칙7 복제 금지", f"최근 {len(recent)}편 안에 같은 장소('{ep.location}')가 있습니다.")

    return issues


def load_history(cfg: Config) -> list[dict]:
    p = cfg.resolve("paths.output") / "history.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


def append_history(cfg: Config, entry: dict) -> None:
    p = cfg.resolve("paths.output") / "history.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    hist = [h for h in load_history(cfg) if h.get("id") != entry["id"]] + [entry]
    p.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

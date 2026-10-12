"""에피소드 데이터 구조.

대본 YAML 한 개 = Episode 한 개. Claude가 대본을 쓸 때도 이 구조로 출력하고,
렌더러도 이 구조만 읽는다. 사람이 YAML을 직접 고쳐도 그대로 다시 렌더링된다.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class Role(str, Enum):
    villain = "villain"  # 진상 (빨간 이름표)
    hero = "hero"  # 주인공 (파란 이름표)
    helper = "helper"  # 조력자 (회색 이름표)


class Gender(str, Enum):
    male = "male"
    female = "female"


class Emotion(str, Enum):
    anger = "분노"
    curiosity = "궁금증"
    bigger_anger = "더 큰 분노"
    cider = "사이다"
    laugh = "웃음"


class TwistType(str, Enum):
    evidence = "증거"
    relation = "관계"
    karma = "자업자득"
    identity = "신분"
    rule = "규칙"
    time = "시간"


# 화자 id 대신 쓸 수 있는 예약어: 목소리 없이 자막만 띄우는 컷
CAPTION = "caption"


class Character(BaseModel):
    id: str = Field(description="영문 소문자 id. 예: mansu")
    name: str = Field(description="화면 이름표에 표시될 한글 이름")
    role: Role
    gender: Gender
    age: int = Field(description="대략적인 나이")
    look_prompt: str = Field(description="AI 이미지용 영어 외형 묘사. 모든 컷에 동일하게 붙는다")
    voice: Optional[str] = Field(default=None, description="edge-tts 음성 이름. 비우면 자동 선택")
    voice_rate: Optional[str] = Field(default=None, description='말 빠르기. 예: "+10%"')
    voice_pitch: Optional[str] = Field(default=None, description='목소리 높낮이. 예: "-20Hz"')


class Shot(BaseModel):
    speaker: str = Field(description=f'Character.id 또는 "{CAPTION}"(목소리 없이 자막만)')
    line: str = Field(description="대사(=자막). 짧고 명확하게, 30자 이내 권장")
    emotion: Emotion
    beat: str = Field(description="이 컷이 주는 새 정보. 예: 사건 폭발, 떡밥, 반전, 참교육")
    visual: str = Field(description="AI 이미지용 영어 장면 묘사 (클로즈업 위주)")
    emphasis: bool = Field(default=False, description="노란 강조 자막 + 펀치 줌")


class Episode(BaseModel):
    id: str = Field(description="파일명으로 쓰일 영문 id. 예: ep04_market")
    title: str = Field(description="업로드용 제목")
    thumbnail_text: str = Field(description="화면 상단 고정 문구, 12자 이내")
    location: str = Field(description="장소 1곳")
    twist_type: TwistType
    background_prompt: str = Field(description="AI 이미지용 영어 배경 묘사")
    characters: list[Character]
    shots: list[Shot]
    end_caption: str = Field(description="마지막 댓글 유도 자막")

    def character(self, cid: str) -> Optional[Character]:
        return next((c for c in self.characters if c.id == cid), None)


def load_episode(path: str | Path) -> Episode:
    with open(path, encoding="utf-8") as f:
        return Episode.model_validate(yaml.safe_load(f))


def save_episode(ep: Episode, path: str | Path) -> None:
    data = ep.model_dump(mode="json", exclude_none=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=1000)

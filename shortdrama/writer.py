"""주제 한 줄 → 대본(Episode) 자동 작성. Claude API 구조화 출력 사용."""
from __future__ import annotations

import anthropic

from .config import Config
from .schema import Episode

SYSTEM_PROMPT = """당신은 중장년층(50~70대) 시청자를 위한 60~80초 세로 숏드라마 작가입니다.
반드시 아래 7가지 원칙을 지켜 대본을 씁니다.

1. 첫 3초 안에 사건을 터뜨린다. 첫 컷은 진상의 고성·막말 대사로 시작한다. 배경 설명으로 시작하지 않는다.
   나쁜 예: "어느 날 한 남자가 식당에 들어왔습니다." 좋은 예: "내가 여기서 돈을 얼마나 썼는데! 사장 나오라고 해!"
2. 진상짓 → 갈등 확대 → 반전 → 참교육 순서로 결말이 궁금하게 만든다. 중반에 "저 사람 뭔가 있다" 싶은 떡밥을 1~2개 깐다.
3. 등장인물은 2~3명, 장소는 1곳. 누가 잘못했는지 첫 10초 안에 분명해야 한다.
4. 모든 컷이 새 정보(새 대사, 갈등, 반전, 감정 변화)를 준다. 같은 말 반복, 의미 없는 동작 금지.
5. 감정 순서: 분노 → 궁금증 → 더 큰 분노 → 사이다 → 웃음. 마지막 컷은 웃음으로 끝난다.
6. 대사는 짧고 명확하게. 한 컷 대사는 30자 이내, 가능하면 15자 안팎. 어려운 단어와 외래어를 피한다.
   어르신 말투(예: "~했는디", "~여")는 자연스럽게 쓰되 알아듣기 쉽게.
7. 반전 방식은 사용자가 지정한 유형을 따른다. 매번 "알고 보니 회장님"으로 끝내지 않는다.

출력 규칙:
- 컷은 12~16개. 한 컷 = 한 사람의 대사 한 번 (또는 speaker가 "caption"인 자막 전용 컷).
- 자막 전용 컷은 2개 이하. 상황을 짚어주는 짧은 질문형 문장으로 쓴다. 예: "할머니가 12잔이나…?"
- 반전 컷과 첫 컷은 emphasis=true.
- visual, look_prompt, background_prompt는 이미지 생성용이므로 영어로, 얼굴 클로즈업 위주로 쓴다.
- 실존 인물·기업·브랜드 이름을 쓰지 않는다. 폭력은 밀치는 정도까지만, 혐오 표현은 쓰지 않는다.
- 진상도 마지막에는 망신을 당할 뿐 과도하게 처벌하지 않는다. 시청자가 웃으며 끝나야 한다.
"""


def write_episode(cfg: Config, topic: str, twist_type: str | None = None,
                  avoid: list[str] | None = None) -> Episode:
    """topic(주제/상황 한 줄)으로 대본을 만든다. avoid에는 최근 쓴 장소·반전을 넣어 중복을 피한다."""
    client = anthropic.Anthropic()

    request = f"주제: {topic}\n"
    if twist_type:
        request += f"반전 유형: {twist_type}\n"
    if avoid:
        request += "최근 영상과 겹치면 안 되는 것(장소/반전): " + ", ".join(avoid) + "\n"
    request += "위 주제로 숏드라마 대본 한 편을 작성하세요."

    response = client.beta.messages.parse(
        model=cfg.get_path("writer.model", "claude-opus-5-5"),
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": cfg.get_path("writer.effort", "high")},
        # 안전 분류기가 거절하면 서버가 자동으로 다른 모델로 이어서 처리
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": request}],
        output_format=Episode,
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"대본 작성이 거절되었습니다. 주제를 바꿔 주세요: {topic}")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise RuntimeError("대본이 중간에 끊겼습니다. 다시 실행해 주세요.")
    return response.parsed_output

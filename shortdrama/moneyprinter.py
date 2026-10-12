"""MoneyPrinterTurbo 연동 (선택).

MoneyPrinterTurbo는 '나레이션 + 무료 스톡 영상' 형식에 특화된 도구라,
인물이 대화하는 숏드라마보다는 "사연 읽어주는 숏츠" 같은 나레이션형 영상에 맞다.
docker로 MoneyPrinterTurbo를 따로 띄운 뒤 이 모듈로 작업을 넘긴다.
"""
from __future__ import annotations

import json
import time
import urllib.request

from .config import Config
from .schema import CAPTION, Episode


def _call(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def narration_script(ep: Episode) -> str:
    """대화형 대본 → 나레이션 한 덩어리 ("박만수가 외칩니다. ...")."""
    parts = []
    for s in ep.shots:
        ch = ep.character(s.speaker)
        parts.append(s.line if s.speaker == CAPTION or not ch else f"{ch.name}: {s.line}")
    return " ".join(parts + [ep.end_caption])


def submit(cfg: Config, subject: str, script: str = "", wait: bool = True, log=print) -> dict:
    base = cfg.get_path("moneyprinter.api_url").rstrip("/")
    body = {
        "video_subject": subject,
        "video_script": script,
        "video_language": "ko-KR",
        "video_aspect": "9:16",
        "voice_name": cfg.get_path("moneyprinter.voice_name"),
        "subtitle_enabled": True,
        "subtitle_position": "bottom",
        "font_size": 90,  # 중장년용 큰 자막
        "stroke_width": 3.0,
        "video_count": 1,
    }
    task_id = _call(f"{base}/videos", body)["data"]["task_id"]
    log(f"MoneyPrinterTurbo 작업 접수: {task_id}")
    if not wait:
        return {"task_id": task_id}
    while True:
        data = _call(f"{base}/tasks/{task_id}")["data"]
        log(f"  진행률 {data.get('progress', 0)}%")
        if data.get("videos") or data.get("state") == 1:
            return data
        if data.get("state") == -1 or data.get("error"):
            raise RuntimeError(f"MoneyPrinterTurbo 실패: {data.get('error') or data}")
        time.sleep(10)

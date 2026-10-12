"""ASS 자막 생성: 크고 굵은 자막, 역할별 색 이름표, 상단 고정 제목.

원칙 6(중장년 가독성)을 코드로 강제하는 부분.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .schema import CAPTION, Episode, Role

# ASS 색상은 &HAABBGGRR (AA=투명도, 00=불투명)
WHITE, BLACK, YELLOW = "&H00FFFFFF", "&H00000000", "&H0000E5FF"
TAG_BOX = {Role.villain: "&H002020D0", Role.hero: "&H00C06020", Role.helper: "&H00606060"}


@dataclass
class Cue:
    start: float
    end: float
    style: str
    text: str


def wrap(text: str, max_chars: int) -> list[str]:
    """띄어쓰기 기준으로 줄당 max_chars 이하가 되게 나눈다. 단어가 너무 길면 강제로 자른다."""
    lines, cur = [], ""
    for word in text.split():
        while len(word) > max_chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{cur} {word}".strip()
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def chunk(text: str, max_chars: int, max_lines: int) -> list[list[str]]:
    """자막 한 장에 max_lines 줄까지. 넘치면 여러 장으로 나눈다."""
    lines = wrap(text, max_chars)
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)] or [[""]]


def _ts(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def build_ass(cfg: Config, ep: Episode, timeline: list[tuple[float, float]], total: float) -> str:
    """timeline[i] = i번째 컷의 (시작, 끝) 초. 마지막 end card는 total까지."""
    w, h = cfg.get_path("video.width"), cfg.get_path("video.height")
    fname = cfg.get_path("subtitle.font_name")
    max_chars = cfg.get_path("subtitle.max_chars_per_line", 11)
    # 한글 한 글자 ≈ 글자 크기만큼 넓다 → 한 줄(max_chars)이 화면 폭 안에 들어오도록 크기 제한
    size = int(min(h * cfg.get_path("subtitle.size_ratio", 0.05), (w - 120) / max_chars))
    max_lines = cfg.get_path("subtitle.max_lines", 2)
    sub_margin = int(h * 0.20)
    tag_size = int(size * 0.62)
    tag_margin = sub_margin + int(size * 1.15) * max_lines + int(h * 0.015)

    def style(name, sz, primary, outline_c, back, border_style, outline, align, margin_v):
        return (f"Style: {name},{fname},{sz},{primary},{primary},{outline_c},{back},"
                f"-1,0,0,0,100,100,0,0,{border_style},{outline},2,{align},60,60,{margin_v},1")

    styles = [
        style("Sub", size, WHITE, BLACK, "&H96000000", 1, max(4, size // 12), 2, sub_margin),
        style("SubEmph", size, YELLOW, BLACK, "&H96000000", 1, max(4, size // 12), 2, sub_margin),
        style("Caption", int(size * 1.05), YELLOW, BLACK, "&H96000000", 1, max(5, size // 10), 5, 0),
        style("Title", int(size * 0.72), WHITE, "&H00000000", "&H00000000", 3, 18, 8, int(h * 0.07)),
        style("End", int(size * 0.8), WHITE, "&H00000000", "&H00000000", 3, 24, 5, 0),
    ]
    for role, box in TAG_BOX.items():
        styles.append(style(f"Tag_{role.value}", tag_size, WHITE, box, box, 3, 14, 2, tag_margin))

    cues: list[Cue] = [Cue(0, total, "Title", _esc(ep.thumbnail_text))]
    for shot, (start, end) in zip(ep.shots, timeline):
        ch = ep.character(shot.speaker)
        if shot.speaker == CAPTION:
            cues.append(Cue(start, end, "Caption", _esc(shot.line)))
            continue
        cues.append(Cue(start, end, f"Tag_{ch.role.value}", _esc(ch.name)))
        cards = chunk(shot.line, max_chars, max_lines)
        weights = [sum(len(l) for l in c) for c in cards]
        t = start
        for card, wgt in zip(cards, weights):
            dur = (end - start) * wgt / max(1, sum(weights))
            cues.append(Cue(t, t + dur, "SubEmph" if shot.emphasis else "Sub",
                            r"\N".join(_esc(l) for l in card)))
            t += dur
    if timeline:
        cues.append(Cue(timeline[-1][1], total, "End", r"\N".join(_esc(l) for l in wrap(ep.end_caption, 13))))

    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = [f"Dialogue: {1 if c.style.startswith('Tag') else 0},{_ts(c.start)},{_ts(c.end)},"
              f"{c.style},,0,0,0,,{c.text}" for c in cues]
    return "\n".join(header + events) + "\n"

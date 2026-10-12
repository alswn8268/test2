from pathlib import Path

from shortdrama.config import load_config
from shortdrama.pipeline import estimate_durations
from shortdrama.schema import Emotion, load_episode
from shortdrama.subtitles import build_ass, chunk, wrap
from shortdrama.validator import check

ROOT = Path(__file__).resolve().parent.parent
cfg = load_config()


def test_wrap_keeps_line_width():
    for line in wrap("우리 가게는 나랑 손자 둘뿐이여. 나는 백발, 얘는 군인!", 11):
        assert len(line) <= 11


def test_chunk_splits_into_cards():
    cards = chunk("가나다라마바사아자차카 " * 5, 11, 2)
    assert all(len(c) <= 2 for c in cards)
    assert len(cards) == 3


def test_sample_episodes_pass_all_rules():
    for path in sorted((ROOT / "episodes").glob("*.yaml")):
        ep = load_episode(path)
        issues = check(cfg, ep, estimate_durations(cfg, ep), history=[])
        assert not issues, f"{path.name}: {[str(i) for i in issues]}"


def test_rules_catch_bad_script():
    ep = load_episode(ROOT / "episodes" / "ep01_gukbap.yaml")
    ep.shots[0].speaker = "caption"
    ep.shots[-1].emotion = Emotion.cider
    rules = {i.rule for i in check(cfg, ep, history=[]) if i.level == "ERROR"}
    assert "원칙1 3초 훅" in rules and "원칙5 감정 설계" in rules


def test_history_warns_on_repeated_twist():
    ep = load_episode(ROOT / "episodes" / "ep01_gukbap.yaml")
    history = [{"id": "old", "twist_type": "증거", "location": "시장"}]
    assert any(i.rule == "원칙7 복제 금지" for i in check(cfg, ep, history=history))


def test_ass_has_name_tags_and_title():
    ep = load_episode(ROOT / "episodes" / "ep02_parking.yaml")
    durs = estimate_durations(cfg, ep)
    timeline, t = [], 0.0
    for d in durs:
        timeline.append((t, t + d))
        t += d
    ass = build_ass(cfg, ep, timeline, t + 2.5)
    assert "Tag_villain" in ass and "강태준" in ass and ep.thumbnail_text in ass

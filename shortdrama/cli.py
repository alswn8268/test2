"""명령어 모음. 사용법: python -m shortdrama <명령> --help"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import Config, load_config
from .pipeline import ValidationFailed, estimate_durations, produce
from .schema import Episode, TwistType, load_episode, save_episode
from .validator import check, load_history

FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Black.otf"


def cmd_setup(cfg: Config, args) -> int:
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        print(f"{'✅' if found else '❌'} {tool}: {found or '없음 - 설치 필요'}")
        ok &= bool(found)
    font = cfg.resolve("subtitle.font_file")
    if font.exists():
        print(f"✅ 자막 글꼴: {font.name}")
    else:
        print("⏬ 자막 글꼴(Noto Sans CJK KR Black, 무료) 내려받는 중...")
        font.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, font)
        print(f"✅ 자막 글꼴: {font}")
    for d in ("episodes", "assets", "output", "inbox"):
        cfg.resolve(f"paths.{d}").mkdir(parents=True, exist_ok=True)
    return 0 if ok else 1


def _print_issues(ep: Episode, issues) -> bool:
    if not issues:
        print("   ✅ 7대 원칙 모두 통과")
    for i in issues:
        print("   " + str(i))
    return not any(i.level == "ERROR" for i in issues)


def cmd_check(cfg: Config, args) -> int:
    ok = True
    for path in args.episodes:
        ep = load_episode(path)
        durs = estimate_durations(cfg, ep)
        print(f"\n▶ {ep.id} - {ep.title} (예상 {sum(durs):.0f}초, {len(ep.shots)}컷)")
        ok &= _print_issues(ep, check(cfg, ep, durs, load_history(cfg)))
    return 0 if ok else 1


def _make(cfg: Config, ep: Episode, force: bool) -> bool:
    print(f"\n▶ {ep.id} - {ep.title}")
    try:
        produce(cfg, ep, force=force)
        return True
    except ValidationFailed as e:
        print("⛔ 원칙 위반으로 중단했습니다. 대본을 고치거나 --force로 강행하세요.")
        return False


def cmd_make(cfg: Config, args) -> int:
    results = [_make(cfg, load_episode(p), args.force) for p in args.episodes]
    print(f"\n완료 {sum(results)}/{len(results)}편 → {cfg.resolve('paths.output')}")
    return 0 if all(results) else 1


def _safe_id(ep_id: str, folder: Path) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", ep_id.lower()).strip("_") or "episode"
    return base if not (folder / f"{base}.yaml").exists() else f"{base}_{datetime.now():%m%d%H%M%S}"


def write_and_save(cfg: Config, topic: str, twist: str | None) -> Path:
    from .writer import write_episode  # anthropic 패키지는 이 명령에서만 필요

    hist = load_history(cfg)[-cfg.get_path("rules.history_window", 3):]
    avoid = [f"{h['location']}/{h['twist_type']}" for h in hist]
    print(f"✍️  대본 작성 중: {topic}")
    ep = write_episode(cfg, topic, twist, avoid)
    folder = cfg.resolve("paths.episodes")
    folder.mkdir(parents=True, exist_ok=True)
    ep.id = _safe_id(ep.id, folder)
    path = folder / f"{ep.id}.yaml"
    save_episode(ep, path)
    print(f"📄 저장: {path}")
    _print_issues(ep, check(cfg, ep, estimate_durations(cfg, ep), load_history(cfg)))
    return path


def cmd_write(cfg: Config, args) -> int:
    path = write_and_save(cfg, args.topic, args.twist)
    if args.make:
        return 0 if _make(cfg, load_episode(path), args.force) else 1
    return 0


def cmd_watch(cfg: Config, args) -> int:
    """inbox 폴더 감시: .yaml(대본) 또는 .txt(주제, 한 줄에 하나)를 넣으면 자동 제작."""
    inbox = cfg.resolve("paths.inbox")
    done, failed = inbox / "done", inbox / "failed"
    for d in (inbox, done, failed):
        d.mkdir(parents=True, exist_ok=True)
    print(f"👀 감시 중: {inbox}  (중지: Ctrl+C)")
    while True:
        for f in sorted(list(inbox.glob("*.yaml")) + list(inbox.glob("*.txt"))):
            print(f"\n📥 {f.name}")
            try:
                if f.suffix == ".yaml":
                    ok = _make(cfg, load_episode(f), args.force)
                else:
                    topics = [t.strip() for t in f.read_text(encoding="utf-8").splitlines() if t.strip()]
                    ok = all([_make(cfg, load_episode(write_and_save(cfg, t, None)), args.force)
                              for t in topics])
            except Exception:
                traceback.print_exc()
                ok = False
            f.rename((done if ok else failed) / f"{datetime.now():%Y%m%d_%H%M%S}_{f.name}")
        if args.once:
            return 0
        time.sleep(args.interval)


def cmd_mpt(cfg: Config, args) -> int:
    from .moneyprinter import narration_script, submit

    if args.episode:
        ep = load_episode(args.episode)
        result = submit(cfg, ep.title, narration_script(ep))
    else:
        result = submit(cfg, args.topic)
    print("완성 영상:", result.get("videos") or result)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="shortdrama", description="시니어 숏드라마 자동 제작 파이프라인")
    p.add_argument("--config", help="설정 파일 경로 (기본: config.yaml)")
    p.add_argument("--tts", help="tts.provider 임시 변경 (edge/espeak/silent)")
    p.add_argument("--images", help="images.provider 임시 변경 (folder/sdwebui/placeholder)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="ffmpeg 확인 + 자막 글꼴 내려받기").set_defaults(fn=cmd_setup)

    s = sub.add_parser("check", help="대본이 7대 원칙을 지키는지 검사")
    s.add_argument("episodes", nargs="+")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("make", help="대본 YAML → 완성 영상 (여러 개 가능)")
    s.add_argument("episodes", nargs="+")
    s.add_argument("--force", action="store_true", help="원칙 위반(ERROR)이 있어도 렌더링")
    s.set_defaults(fn=cmd_make)

    s = sub.add_parser("write", help="주제 한 줄 → Claude가 대본 작성")
    s.add_argument("topic")
    s.add_argument("--twist", choices=[t.value for t in TwistType], help="반전 유형 지정")
    s.add_argument("--make", action="store_true", help="대본 작성 후 바로 영상까지 제작")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_write)

    s = sub.add_parser("watch", help="inbox 폴더에 파일을 넣으면 자동 제작")
    s.add_argument("--interval", type=int, default=10, help="확인 간격(초)")
    s.add_argument("--once", action="store_true", help="한 번만 확인하고 종료")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_watch)

    s = sub.add_parser("mpt", help="MoneyPrinterTurbo로 나레이션형 영상 제작")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic")
    g.add_argument("--episode", help="대본 YAML을 나레이션으로 바꿔서 전달")
    s.set_defaults(fn=cmd_mpt)

    args = p.parse_args(argv)
    cfg = load_config(args.config)
    if args.tts:
        cfg["tts"]["provider"] = args.tts
    if args.images:
        cfg["images"]["provider"] = args.images
    return args.fn(cfg, args)


if __name__ == "__main__":
    sys.exit(main())

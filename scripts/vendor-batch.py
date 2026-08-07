#!/usr/bin/env python3
"""批量 vendor 上游技能:按 batch.json 清单从已 clone 的上游仓库拷贝技能目录,
自动生成 Aolva 规范的 meta.json(从 SKILL.md frontmatter 抽取 name/description 构建 routing 语料)。

用法:
    python3 scripts/vendor-batch.py <batch.json>

batch.json 结构:
{
  "repo": "https://github.com/xxx/yyy",      # 上游仓库(meta.provenance.upstream)
  "commit": "abc123",                        # 锁定的上游 commit
  "license": "MIT",                          # 上游许可证(须在宽松白名单)
  "tier": "extension",                       # own | core | extension
  "base": ".agents/skills",                  # 上游技能目录前缀(相对仓库根)
  "defaults": {                              # 未逐项指定的默认值
    "category": "daily", "invokePolicy": "suggest",
    "sideEffects": ["writes-files"], "enabledByDefault": false,
    "difficulty": "mid", "modelTierHint": "mid", "confidenceThreshold": 0.7
  },
  "skills": [
    {"id": "article-writing", "src": "article-writing", "title": "文章写作"},   # src 相对 base
    {"id": "custom", "src": "path/to/src", "invokePolicy": "auto", ...}         # 可覆盖
  ]
}
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def parse_frontmatter(path):
    """Extract name/description from SKILL.md frontmatter."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if kv:
            fm[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    return fm, text


def extract_keywords(description, title):
    """从 description/title 抽取英文关键词(小写去重,最多 12 个)。"""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", (description or "") + " " + (title or ""))
    stop = {"the", "and", "for", "with", "from", "that", "this", "when",
            "user", "users", "skill", "skills", "agent", "agents", "tool",
            "tools", "file", "files", "use", "using", "used", "via", "you",
            "your", "their", "will", "can", "into", "them", "are", "was",
            "not", "out", "off", "all", "any", "should", "may", "must", "need"}
    out = []
    for w in words:
        wl = w.lower()
        if wl not in stop and wl not in out:
            out.append(wl)
        if len(out) >= 12:
            break
    return out


def gen_meta(cfg, spec):
    fm, _ = parse_frontmatter(ROOT / "skills" / cfg["tier"] / spec["id"] / "SKILL.md")
    d = dict(cfg.get("defaults", {}))
    d.update({k: v for k, v in spec.items() if k not in ("id", "src")})
    desc = fm.get("description") or spec.get("summary", "")
    meta = {
        "id": spec["id"],
        "title": d.get("title") or fm.get("name", spec["id"]),
        "summary": d.get("summary") or (desc[:80] + ("…" if len(desc) > 80 else "")),
        "category": d.get("category", "daily"),
        "version": "1.0.0",
        "license": cfg["license"],
        "tier": cfg["tier"],
        "enabledByDefault": bool(d.get("enabledByDefault", False)),
        "entry": "SKILL.md",
        "routing": {
            "description": desc or f"{spec['id']} 技能(见 SKILL.md)",
            "keywords": d.get("keywords") or extract_keywords(desc, spec["id"]),
            "difficulty": d.get("difficulty", "mid"),
            "modelTierHint": d.get("modelTierHint", "mid"),
            "confidenceThreshold": float(d.get("confidenceThreshold", 0.7)),
        },
        "invokePolicy": d.get("invokePolicy", "suggest"),
        "sideEffects": d.get("sideEffects", ["writes-files"]),
        "requires": {
            "services": d.get("services", []),
            "scopes": d.get("scopes", []),
            "mcp": d.get("mcp", []),
            "tools": d.get("tools", ["shell"]),
        },
        "provenance": {
            "upstream": cfg["repo"],
            "commit": cfg["commit"],
            "upstreamLicense": cfg["license"],
            "adaptations": d.get("adaptations") or [
                "批量 vendor 入库:自动生成 meta.json(frontmatter 抽取 routing 语料)",
                "同步时剔除大媒体与上游 .git",
            ],
        },
    }
    return meta


def main(batch_path):
    cfg = json.loads(pathlib.Path(batch_path).read_text(encoding="utf-8"))
    src_root = pathlib.Path(cfg["source"])
    if not src_root.is_dir():
        sys.exit(f"source 目录不存在: {src_root}")
    base = (cfg.get("base") or "").strip("/")
    dest_root = ROOT / "skills" / cfg["tier"]
    dest_root.mkdir(parents=True, exist_ok=True)
    errors = []
    for spec in cfg["skills"]:
        sid = spec["id"]
        src_root = pathlib.Path(spec.get("source") or cfg["source"])
        if not src_root.is_dir():
            errors.append(f"[skip] {sid}: source 目录不存在 {src_root}")
            continue
        base = (spec.get("base") if spec.get("source") is not None
                else cfg.get("base") or "").strip("/")
        src = src_root / base / spec["src"]
        if not (src / "SKILL.md").exists():
            errors.append(f"[skip] {sid}: 无 SKILL.md @ {src.relative_to(src_root)}")
            continue
        dest = dest_root / sid
        if dest.exists():
            shutil.rmtree(dest)
        # 拷贝内容,排除大媒体与 .git
        def ignore(d, names):
            out = set()
            for n in names:
                p = pathlib.Path(d) / n
                if n == ".git" or p.is_dir() and n == "__pycache__":
                    out.add(n)
                elif p.is_file() and p.suffix.lower() in (
                    ".mp3", ".wav", ".ogg", ".mp4", ".mov", ".mkv", ".zip",
                    ".tar.gz", ".pyc", ".pyo",
                ):
                    out.add(n)
                elif n == ".DS_Store":
                    out.add(n)
            return out

        shutil.copytree(src, dest, ignore=ignore)
        meta = gen_meta(cfg, spec)
        (dest / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[ok]   {cfg['tier']}/{sid}  ({len(list(dest.rglob('*')))} files)")
    if errors:
        for e in errors:
            print(e)
    print(f"done: {len(cfg['skills'])} spec(s), {len(errors)} skipped")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

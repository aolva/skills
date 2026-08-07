#!/usr/bin/env python3
"""从 skills/{own,core,extension}/*/meta.json 生成 catalog.json(App 读取的分发清单)。
每个技能目录计算内容 sha256,App 据此判断更新。"""
import json, hashlib, pathlib, datetime, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
TIERS = ("own", "core", "extension")

def dir_hash(d: pathlib.Path) -> str:
    """Deterministic content hash: same bytes in -> same digest on any OS.

    Skips runtime/py artifacts (bytecode caches, Finder metadata) so the
    digest is stable whether or not the skill was executed locally.
    """
    h = hashlib.sha256()
    for f in sorted(d.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(d).as_posix()
        if "__pycache__" in rel.split("/") or rel.endswith((".pyc", ".pyo")):
            continue
        if rel.endswith(".DS_Store"):
            continue
        h.update(rel.encode())
        h.update(f.read_bytes())
    return h.hexdigest()

skills = []
for tier in TIERS:
    tier_dir = SKILLS / tier
    if not tier_dir.is_dir():
        continue
    for meta_path in sorted(tier_dir.glob("*/meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        skills.append({
            "id": m["id"], "title": m["title"], "summary": m["summary"],
            "category": m["category"], "version": m["version"],
            "tier": tier,
            "enabledByDefault": m["enabledByDefault"], "invokePolicy": m["invokePolicy"],
            "sideEffects": m.get("sideEffects", []),
            "routing": m["routing"], "requires": m["requires"],
            "sha256": dir_hash(meta_path.parent),
            "path": f"skills/{tier}/{m['id']}",
        })

catalog = {
    "catalogVersion": datetime.date.today().isoformat(),
    "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
    "tiers": {
        "own": "自研/深度重写技能(核心,长期维护)",
        "core": "业界事实基建技能(默认内置)",
        "extension": "优质开源技能(按需安装)",
    },
    "skills": skills,
}
(ROOT / "catalog.json").write_text(
    json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"catalog.json: {len(skills)} skill(s) across {', '.join(TIERS)}")

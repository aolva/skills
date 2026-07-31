#!/usr/bin/env python3
"""从 skills/*/meta.json 生成 catalog.json(App 读取的分发清单)。
每个技能目录计算内容 sha256,App 据此判断更新。"""
import json, hashlib, pathlib, datetime, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

def dir_hash(d: pathlib.Path) -> str:
    h = hashlib.sha256()
    for f in sorted(d.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(d).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()

skills = []
for meta_path in sorted(SKILLS.glob("*/meta.json")):
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    skills.append({
        "id": m["id"], "title": m["title"], "summary": m["summary"],
        "category": m["category"], "version": m["version"],
        "enabledByDefault": m["enabledByDefault"], "invokePolicy": m["invokePolicy"],
        "sideEffects": m.get("sideEffects", []),
        "routing": m["routing"], "requires": m["requires"],
        "sha256": dir_hash(meta_path.parent),
        "path": f"skills/{m['id']}",
    })

catalog = {
    "catalogVersion": datetime.date.today().isoformat(),
    "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
    "skills": skills,
}
(ROOT / "catalog.json").write_text(
    json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"catalog.json: {len(skills)} skill(s)")

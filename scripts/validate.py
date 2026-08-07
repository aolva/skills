#!/usr/bin/env python3
"""校验每个 skills/<tier>/<id>/meta.json 符合 schema,且按 tier 准入规则校验。CI 闸门。"""
import json, pathlib, sys
try:
    import jsonschema
except ImportError:
    sys.exit("pip install jsonschema")

ROOT = pathlib.Path(__file__).resolve().parent.parent
schema = json.loads((ROOT / "schema/skill.meta.schema.json").read_text(encoding="utf-8"))
errors = 0

# tier 准入规则:core/extension 必须记录来源与许可;core 必须是默认内置
def tier_admission(m):
    msgs = []
    tier = m.get("tier")
    if tier not in ("own", "core", "extension"):
        msgs.append(f"tier={tier!r} 非法(own/core/extension)")
        return msgs
    if tier in ("core", "extension") and not m.get("provenance", {}).get("upstream"):
        msgs.append(f"{tier} 库技能必须有 provenance.upstream")
    if tier == "core":
        if not m.get("enabledByDefault"):
            msgs.append("core 库技能必须 enabledByDefault=true")
        if not m.get("license"):
            msgs.append("core 库技能必须有明确 license")
    return msgs

for meta_path in sorted((ROOT / "skills").glob("*/**/meta.json")):
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(m, schema)
    except jsonschema.ValidationError as e:
        errors += 1; print(f"[FAIL] {meta_path}: {e.message}"); continue
    for msg in tier_admission(m):
        errors += 1; print(f"[FAIL] {meta_path}: {msg}")
    if not (meta_path.parent / m["entry"]).exists():
        errors += 1; print(f"[FAIL] {meta_path}: entry '{m['entry']}' 不存在")
    # 契约一致性:声明 external-action/spends-money 却设 auto 是危险的
    if m["invokePolicy"] == "auto" and set(m.get("sideEffects", [])) & {
        "writes-files","runs-shell","spends-money","external-action","long-running"}:
        errors += 1; print(f"[FAIL] {m['id']}: auto 策略不得带有副作用,应降级为 suggest/manual")
    else:
        print(f"[ok]   {m['id']} ({m.get('tier', '?')})")
sys.exit(1 if errors else 0)

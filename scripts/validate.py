#!/usr/bin/env python3
"""校验每个 skills/*/meta.json 符合 schema,且 entry 文件存在。CI 闸门。"""
import json, pathlib, sys
try:
    import jsonschema
except ImportError:
    sys.exit("pip install jsonschema")

ROOT = pathlib.Path(__file__).resolve().parent.parent
schema = json.loads((ROOT / "schema/skill.meta.schema.json").read_text(encoding="utf-8"))
errors = 0
for meta_path in sorted((ROOT / "skills").glob("*/meta.json")):
    m = json.loads(meta_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(m, schema)
    except jsonschema.ValidationError as e:
        errors += 1; print(f"[FAIL] {meta_path}: {e.message}"); continue
    if not (meta_path.parent / m["entry"]).exists():
        errors += 1; print(f"[FAIL] {meta_path}: entry '{m['entry']}' 不存在")
    # 契约一致性:声明 external-action/spends-money 却设 auto 是危险的
    if m["invokePolicy"] == "auto" and set(m.get("sideEffects", [])) & {
        "writes-files","runs-shell","spends-money","external-action","long-running"}:
        errors += 1; print(f"[FAIL] {m['id']}: auto 策略不得带有副作用,应降级为 suggest/manual")
    else:
        print(f"[ok]   {m['id']}")
sys.exit(1 if errors else 0)

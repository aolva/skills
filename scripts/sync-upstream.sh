#!/usr/bin/env bash
# 从上游 vendor 一个开源 skill 到本仓库指定库(own/core/extension),并打印锁定的 commit。
# 用法: scripts/sync-upstream.sh <tier>/<id>   例: scripts/sync-upstream.sh core/web-search
#      scripts/sync-upstream.sh <id>           默认落到 extension/(旧调用方式)
set -euo pipefail
arg="${1:?usage: sync-upstream.sh <tier>/<skill-id>}"

if [[ "$arg" == */* ]]; then
  tier="${arg%%/*}"; id="${arg##*/}"
else
  tier="extension"; id="$arg"
fi
case "$tier" in
  own|core|extension) ;;
  *) echo "未知库: $tier (own/core/extension)"; exit 1 ;;
esac

# 技能来源登记表:<id> -> "<repo-url> <上游子路径>"
source_id="${id}"
case "$source_id" in
  autoresearch)
    repo="https://github.com/uditgoenka/autoresearch.git"; sub=".claude/skills/autoresearch" ;;
  *) echo "未知 skill: $id (先在下方登记表补充来源)"; exit 1 ;;
esac

tmp="$(mktemp -d)"; git clone --depth 1 "$repo" "$tmp/src"
commit="$(git -C "$tmp/src" rev-parse HEAD)"
dest="skills/$tier/$id"
mkdir -p "$(dirname "$dest")"
rsync -a --delete --exclude meta.json "$tmp/src/$sub/" "$dest/"
rm -rf "$tmp"
echo "vendored $id -> $tier @ $commit"
echo ">> 回填 $dest/meta.json: tier=$tier, provenance.commit=$commit, 并人工核对内容/许可证"
echo ">> 然后: python3 scripts/validate.py && python3 scripts/build-catalog.py"

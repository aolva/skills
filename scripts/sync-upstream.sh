#!/usr/bin/env bash
# 从上游 vendor 一个开源 skill 到本仓库,并打印锁定的 commit(需人工回填 meta.json)。
# 用法: scripts/sync-upstream.sh autoresearch
set -euo pipefail
id="${1:?usage: sync-upstream.sh <skill-id>}"
case "$id" in
  autoresearch)
    repo="https://github.com/uditgoenka/autoresearch.git"; sub=".claude/skills/autoresearch" ;;
  *) echo "未知 skill: $id"; exit 1 ;;
esac
tmp="$(mktemp -d)"; git clone --depth 1 "$repo" "$tmp/src"
commit="$(git -C "$tmp/src" rev-parse HEAD)"
dest="skills/$id"
rsync -a --delete --exclude meta.json "$tmp/src/$sub/" "$dest/"
rm -rf "$tmp"
echo "vendored $id @ $commit"
echo ">> 回填 $dest/meta.json 的 provenance.commit = $commit,并人工核对内容/许可证"

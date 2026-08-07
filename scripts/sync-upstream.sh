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
  planning-with-files)
    repo="https://github.com/OthmanAdi/planning-with-files.git"; sub=".agents/skills/planning-with-files" ;;
  caveman)
    repo="https://github.com/JuliusBrussee/caveman.git"; sub="skills/caveman" ;;
  huashu-design)
    repo="https://github.com/alchaincyf/huashu-design.git"; sub="" ;;
  marketing-skills)
    repo="https://github.com/coreyhaines31/marketingskills.git"; sub="skills" ;;
  mineru)
    repo="https://github.com/Nebutra/MinerU-Skill.git"; sub="skills/mineru" ;;
  chart-visualization)
    repo="https://github.com/antvis/chart-visualization-skills.git"; sub="skills/chart-visualization" ;;
  *) echo "未知 skill: $id (先在下方登记表补充来源)"; exit 1 ;;
esac

tmp="$(mktemp -d)"; git clone --depth 1 "$repo" "$tmp/src"
commit="$(git -C "$tmp/src" rev-parse HEAD)"
dest="skills/$tier/$id"
mkdir -p "$(dirname "$dest")"
# 通用媒体排除:音频/视频/大型二进制会撑爆技能库仓库与 App 下载
rsync -a --delete \
  --exclude meta.json \
  --exclude '*.mp3' --exclude '*.wav' --exclude '*.ogg' \
  --exclude '*.mp4' --exclude '*.mov' --exclude '*.mkv' \
  --exclude '*.zip' --exclude '*.tar.gz' \
  "$tmp/src/$sub/" "$dest/"
rm -rf "$tmp"
echo "vendored $id -> $tier @ $commit"
echo ">> 回填 $dest/meta.json: tier=$tier, provenance.commit=$commit, 并人工核对内容/许可证"
echo ">> 然后: python3 scripts/validate.py && python3 scripts/build-catalog.py"

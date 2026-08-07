---
name: aolva-skill-authoring
description: Aolva 技能作者技能:按三层技能库规范编写/测试/发布技能(own/core/extension),含 meta.json 契约、准入校验、批量入库流程。适用任何"写一个新技能/把开源技能 vendor 进来/改造技能"类任务。
---

# Aolva Skill Authoring

Aolva 技能生态的标准化生产方式。规则源头:`Products/Aolva/skills` 仓库 + `Platform/Docs`
的《Aolva技能库三大类建设与门卫路由 对齐文档》。

## 技能结构(硬性)

```
skills/<tier>/<id>/
  SKILL.md      # 入口:frontmatter(name/description)+ 正文(定义/工作流/规则)
  meta.json     # 路由/策略/依赖/溯源(见 schema/skill.meta.schema.json)
  reference/    # 可选:参考文档
  scripts/      # 可选:可执行脚本
```

`meta.json` 必填字段:id/title/summary/category(developer|daily|meta)/version/
license/tier(own|core|extension)/enabledByDefault/entry/routing/
invokePolicy/requires/provenance。

## 写 SKILL.md 的规范

1. **frontmatter**:`name` 与目录 id 一致;`description` 第一行是"何时触发",第二行起是能力概述(门卫据此做语义匹配,直接复用为 routing 语料)。
2. **正文结构**:定义 → 适用判定 → 工作流(可执行步骤)→ 规则/边界。避免空泛套话;每条指令可被 agent 直接执行。
3. **副作用透明**:会写文件/跑 shell/联网/花钱的动作在正文显式声明,与 meta.sideEffects 一致。

## 入库流程

1. **自研(own)**:写 SKILL.md + meta.json;`provenance.upstream=null`,license 自持。
2. **vendor(core/extension)**:`scripts/sync-upstream.sh <tier>/<id>`(登记表加来源)→ 回填 commit → 人工核对内容与许可证(四档决策矩阵:宽松许可直接引 / copyleft 不引 / 无许可 clean-room 进 own)。
3. **批量**:`scripts/vendor-batch.py <batch.json>`(清单驱动,自动 meta.json)。
4. **闸门**:`python3 scripts/validate.py`(schema + tier 准入 + 许可白名单)→ `python3 scripts/build-catalog.py` → CI 复验 catalog 一致性。

## 质量自检清单

- [ ] SKILL.md 的 description 可直接作门卫路由语料(适用/不适用清晰)
- [ ] meta.json 通过 validate,sideEffects 与正文一致
- [ ] 引用的文件路径存在;脚本无硬编码绝对路径
- [ ] 无危险指令(外传数据/删除操作/隐藏副作用)
- [ ] vendor 技能记录了 upstream+commit+upstreamLicense

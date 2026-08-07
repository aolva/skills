# Aolva PPT (aolva-ppt)

演示文稿生成技能：PPTD DSL → 可编辑 PPTX。**自研纯 Python 导出引擎**，
不依赖 Node / npm / 浏览器 / Kimi 等任何第三方前端资产——上游 open-kimi-ppt-skill
依赖逆向的 Kimi neo-ppt WASM 前端，随时可能失效，本技能把知识文档 vendor 下来、
把执行引擎全部重写为自研实现，从根上断掉这条失效链路。

## 目录

```
SKILL.md                  # 技能入口(改写:指向自研脚本,声明能力边界)
meta.json                 # Aolva 技能库元数据(路由/策略/溯源)
LICENSE-UPSTREAM          # 上游 MIT 许可(仅知识文档)
UPSTREAM_COMMIT.txt       # 上游 commit: 07eeaad
reference/                # 从上游 vendor 的知识文档(MIT):
  pptd.md                 #   PPTD v2 格式规范(核心)
  shapes.md / fonts.md    #   形状/字体参考
  slides_categories.md + slides_categories/   # 场景设计指南
  design_system/          #   30+ 套预设设计系统
  general-poster.md       #   海报/单页设计指南
  theme.md                #   预设主题列表
scripts/
  pptd_export.py          # CLI: PPTD -> PPTX(自研)
  export_pptx.py          # 兼容包装(同名入口)
  pptd_preview.py         # CLI: PPTD -> HTML 预览(自研)
  aolva_ppt/              # 自研引擎包(stdlib-only)
    yaml_mini.py          # 无依赖 YAML 子集解析器(PyYAML 可用时优先)
    model.py              # PPTD 加载 + 主题引用/样式链解析
    ooxml.py              # OOXML 底层助手(EMU/填充/边框/阴影)
    elements.py           # 富文本/形状/线条/图片/图标/表格渲染
    charts.py             # 原生 OOXML 图表(bar/line/area/pie)
    icons.py              # 自绘 SVG 图标集(~130 个)
    preview.py            # HTML 预览渲染
    pptx_writer.py        # OPC 打包(主题/母版/版式/备注)
```

## 自研边界(与上游的差异)

| 能力 | 上游(会失效) | 本技能 |
|---|---|---|
| PPTD → PPTX | Kimi neo-ppt WASM / 浏览器 | 自研纯 Python OOXML 渲染器 |
| 依赖 | node ≥18 + npx + agent-browser | 仅 python3(无 PyYAML 也能跑) |
| 在线编辑器 / serve | Kimi 前端镜像 | 无(改为 HTML 预览) |
| 图标 | Font Awesome 字体 | 自绘 SVG 嵌入 |
| 图表 | Kimi WASM | 原生 OOXML + 内嵌 Excel |
| PPTX→PPTD 反解 | 编辑器提供 | 暂不支持 |
| 动画 / 视觉质检 | 有 | 暂不支持(诚实声明) |

## 本地验证

```bash
python3 scripts/pptd_export.py <deck.pptd|deck-dir> --output deck.pptx --force
python3 scripts/pptd_preview.py <deck.pptd|deck-dir>
python3 -m zipfile -t deck.pptx
```

## 许可

- `scripts/` 全部为自研代码，MIT。
- `reference/` 与 `LICENSE-UPSTREAM` 来自
  https://github.com/move-brain/open-kimi-ppt-skill (MIT, commit 07eeaad)，
  上游本身 fork 自 https://github.com/Binaryify/open-kimi-ppt-skill。
- PPTD 格式为 Moonshot AI 的公开 DSL 描述，本技能与其服务无任何运行期依赖。

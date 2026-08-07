# Aolva Skills

Aolva 的技能库——门卫 AI 与 Aolva Studio 消费的技能唯一真源,按**三大类技能库**分层治理。

这是三层架构里的**第一层(策展)**:自研与开源技能在此 vendor、改造成 Aolva 规范、
锁版本、留溯源与许可证。第二层是自动生成的分发清单 `catalog.json`,第三层是 App 侧
(默认集内置 + 其余按需安装)。设计全文见 `Platform/Docs/下一步工作规划文档/`
的《Aolva技能库三大类建设与门卫路由 对齐文档》。

## 三大类技能库

```
skills/
  own/         自研技能库 —— Aolva 自研或深度重写去依赖的核心能力,长期维护
  core/        核心基建技能库 —— 业界事实基建(MIT/Apache、>5k★、零重依赖),
               装一个就能干活,默认内置
  extension/   扩展技能库 —— 重要有用但非最核心的开源技能,按需安装
```

| | own/ | core/ | extension/ |
|---|---|---|---|
| 来源 | 自研 / 开源重写 | 业界广泛采用的开源基建 | 优质开源 |
| 准入 | 承诺长期维护 | 明确许可 + 高采用度 + 零重依赖 + 语义稳定 | 明确许可 + 可溯源 |
| enabledByDefault | true(产品能力) | true | false |
| invokePolicy | 按副作用 | auto / suggest | suggest / manual |
| 升级 | 随产品迭代 | 定期锁版本 sync | 用户显式拉取 |

**升级通道**:`extension →(高频使用+稳定) core →(上游将亡/需深度定制) own 重写去依赖`。

## 消费方读什么

App / 门卫 AI 只读 **`catalog.json`**(通过一个可切换的 URL:起步指向本仓库 raw,后续可换成 skills-service)。
它是从各 `skills/<tier>/<id>/meta.json` 自动生成的索引,含内容 `sha256` 与 `tier`,
App 据此判断是否需要更新某个 skill。

## 核心契约:三个正交维度

每个 skill 的 `meta.json` 里,三件事互相独立,别混:

1. **`tier`** — 所属技能库(own/core/extension),决定准入与升级节奏。
2. **`enabledByDefault`** — 是否进 App 的默认内置集(离线可用、开箱即启)。
3. **`invokePolicy`** — 门卫的触及天花板:
   - `auto` — 可静默注入(仅限便宜、无副作用的 skill)。
   - `suggest` — 门卫只能向用户**提议**,由用户确认后再启用(有副作用但可控/可回滚)。
   - `manual` — 门卫**不得**自动触发,只能用户主动选用(昂贵 + 不可逆 / 长时自治)。
4. **`requires`** — 统一能力调用契约:纯 skill 三者皆空;服务型 skill 在此声明依赖哪个 Aolva 后端服务与权限范围。

门卫据 `routing.description` 做语义匹配、据 `routing.difficulty / modelTierHint` 定模型档位、
命中置信度需 ≥ `routing.confidenceThreshold` 才按 `invokePolicy` 处理。

## 加一个 skill

1. `mkdir skills/<tier>/<id>`,写 `meta.json`(见 `schema/skill.meta.schema.json`,`tier` 必填)。
2. 若来自开源,用 `scripts/sync-upstream.sh <tier>/<id>` vendor 进来并回填 `provenance.commit`,
   人工核对内容与许可证。
3. `python scripts/validate.py` 通过(含 tier 准入校验)。
4. `python scripts/build-catalog.py` 重新生成 `catalog.json`。
5. 提交。CI 会重跑校验并确保 `catalog.json` 是最新的。

## 布局

```
skills/own/<id>/          # 自研技能(tier=own)
skills/core/<id>/         # 核心基建技能(tier=core)
skills/extension/<id>/    # 扩展技能(tier=extension)
  meta.json               # 技能元数据(路由/策略/依赖/溯源)
  SKILL.md                # 技能入口(vendored 或原创)
schema/                   # meta 与 catalog 的 JSON Schema
scripts/                  # build-catalog / validate / sync-upstream
catalog.json              # 自动生成的分发清单(App 读这个)
```

许可证:MIT(本仓库封装与脚本)。各 vendored skill 保留其上游许可证,记于 `provenance`。

---
name: aolva-llm-gateway
description: 对接 Aolva Platform ai-gateway(LiteLLM 底座)的统一模型调用技能。按任务难度/成本档位选模型、构造请求、处理限流降级。使用户任何'调用大模型'需求都走统一网关而非散落直连。
---

# Aolva LLM Gateway

Aolva 平台所有 AI 能力的统一出口是 `Platform/Services/ai-gateway`(LiteLLM 实现)。
本技能规范 agent 通过网关调用模型的契约,禁止绕过网关直连供应商 API。

## 契约

- 网关地址与鉴权:见平台环境变量(AGW_BASE_URL / AGW_API_KEY),未配置时先询问用户。
- 请求格式:OpenAI 兼容 `POST /v1/chat/completions`,支持 stream、tools、JSON mode。
- 任务 × 模型档位矩阵(与平台对齐文档一致,选用后写进 prompt 说明):

| 任务类型 | 模型档位 | 典型选择 |
|---|---|---|
| 简单抽取/分类/翻译 | low | deepseek 快档 |
| 常规写作/总结/代码 | mid | deepseek 标准档 |
| 复杂推理/长文/多模态质检 | frontier | 最强可用档(可能昂贵) |

- 降级:frontier 超时或限流时,按 mid → low 降级并告知用户;禁止无限重试(最多 2 次)。

## 工作流

1. **定档**:按上表选档;无法判断时用 mid,并把原因告诉用户。
2. **构造请求**:system 指令 + 上下文 + 明确输出格式(JSON 时给 schema 示例)。
3. **调用**:用 curl 或 python(urllib,不引额外依赖)走网关。
4. **后处理**:校验输出 JSON;失败定位是模型问题还是契约问题;按降级表处理。
5. **记账提示**:网关侧有计量;给用户的成本说明用网关口径。

## 规则

- 除网关外,任何场景都**不**新建其他 LLM 直连凭证。
- 多模态(图片输入/视觉质检)走网关的多模态模型档位,不擅自切换供应商。
- 批量任务必须说明数量与预估成本后执行,单价以网关计量为准。

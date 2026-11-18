# Jira 配置（角色 B）

## 项目与字段
- 项目：`LIVEOPS`，问题类型：Task
- 自定义字段：`Scenario`(下拉 S1/S2/S3)、`Phase`(下拉)、`Market`(下拉 SG/EU)、`Runbook`(文本或下拉 scale/cdn_fix/waf_guard)、`Runbook Params`(多行文本，JSON)、`Agent Investigation URL`(URL)
- 记录 `Runbook`、`Runbook Params` 的 customfield ID，配置到 ops-mcp 环境变量和 GitHub Variables（`JIRA_FIELD_RUNBOOK` / `JIRA_FIELD_PARAMS`）

## 工作流
待诊断 →（Agent）待审批 →（approvers）已批准 →（GitHub）已完成；待诊断 →（Agent）已完成；待审批 → 已驳回
- "待审批 → 已批准"条件：用户属于组 `approvers`

## 账号
| 账号 | 权限 | 用途 |
|---|---|---|
| devops-agent-bot | 浏览、评论、编辑字段、流转到待审批/已完成 | ops-mcp |
| github-runbook-bot | 浏览、评论、流转到已完成 | GitHub Actions |
| 审批人 | approvers 组 | 人工审批 |

## Automation 规则
1. 触发：问题创建（项目 LIVEOPS）→ 发送 Web 请求
   - URL：`<jira-bridge Function URL>/investigate`，Header `x-bridge-token: <token>`
   - Body：`{"key":"{{issue.key}}","summary":"{{issue.summary}}","description":"{{issue.description}}"}`
2. 触发：流转到"已批准" → 发送 Web 请求
   - URL：`https://api.github.com/repos/Denis4563/devops-agent/dispatches`
   - Header：`Authorization: Bearer <GitHub fine-grained token，Contents:read & Actions:write>`、`Accept: application/vnd.github+json`
   - Body：`{"event_type":"liveops-execute","client_payload":{"jira_key":"{{issue.key}}","runbook":"{{issue.Runbook}}","params":{{issue.Runbook Params}}}}`
3. 触发：任意状态变化 → 发送 Web 请求到飞书（可选，与 agent-notify 互补）

## Secrets Manager
| 名称 | 内容 |
|---|---|
| /retail-live/jira | {"base_url","user","token"} |
| /retail-live/agent-webhook | {"url","secret"} |
| /retail-live/bridge | {"token"} |
| /retail-live/feishu | {"webhook","secret"} |
| /retail-live/ops-mcp | {"api_key"} |

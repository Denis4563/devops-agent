# devops-agent：零售直播大促 DevOps Agent 智能运维 Demo

GameDay「Agent to the Rescue」演示项目。AWS DevOps Agent 负责调查和判断，**ops-mcp** 负责把判断写回 Jira 并提交执行请求，Jira 审批后由 GitHub Actions 执行 Runbook，飞书负责通知。

```
告警 → Jira 建单 → DevOps Agent 调查（Skill + ops-mcp）→ ops-mcp 回写结论 / 提交执行请求
     → Jira 审批 → GitHub Actions 执行 Runbook → Jira 回写 + 飞书通知
```

## 三个场景
| 场景 | 关键判断 | Runbook |
|---|---|---|
| S1 分阶段扩缩容 | 结算饱和只扩 checkout；爆款锁争用不扩容 | `scale` |
| S2 SG/EU CloudFront 交付 | EU 变慢是追踪参数拆散缓存，不是容量问题 | `cdn_fix` |
| S3 领券分级防护 | 正常抢券不防护；刷券只限领券接口 | `waf_guard` |

## 目录
| 路径 | 负责人 | 说明 |
|---|---|---|
| `k8s/apps.yaml` | A | catalog / coupon / checkout（nginx）+ HPA |
| `edge/geo-rewrite.js` | A | CloudFront Function：按国家改写 + 剥离追踪参数 |
| `edge/setup_edge.sh` | A | S3 页面、CloudFront Function、WAF 规则 |
| `skills/retail-live-ops/SKILL.md` | A | DevOps Agent Skill |
| `mcp/` | B | ops-mcp（FastMCP，6 个工具）+ 部署脚本 |
| `lambdas/jira_bridge.py` | B | 告警建单 `/alarm`、调用 Agent Webhook `/investigate` |
| `sim/simulate.py` | B | 模拟指标与告警 |
| `config/runbooks.yaml` | C | Runbook 目录（ops-mcp 与 Workflow 共用的白名单） |
| `runbooks/` | C | scale / cdn_fix / waf_guard / reset |
| `lambdas/agent_notify.py` | C | DevOps Agent 事件 → 飞书 |
| `.github/workflows/runbook.yml` | C | Jira 审批后执行 Runbook |
| `docs/` | PM | 方案文档、SOW |

## 快速开始
1. A：`eksctl create cluster -f k8s/cluster.yaml` → `kubectl apply -f k8s/apps.yaml` → `bash edge/setup_edge.sh`
2. B：在 EC2 上 `bash mcp/deploy.sh`；部署 `lambdas/jira_bridge.py`；配置 Jira（见 `docs/jira-setup.md`）
3. C：在仓库 Settings 中配置 Secrets / Variables（见下表），部署 `lambdas/agent_notify.py`
4. 演示：`python sim/simulate.py s1a`，`python sim/simulate.py reset` 复位

## GitHub Secrets / Variables
| 名称 | 类型 | 说明 |
|---|---|---|
| `AWS_ROLE_ARN` | Secret | OIDC 角色 `retail-live-runbook-role` |
| `JIRA_BASE_URL` / `JIRA_USER` / `JIRA_TOKEN` | Secret | `github-runbook-bot` 账号 |
| `FEISHU_WEBHOOK` / `FEISHU_SECRET` | Secret | 飞书群自定义机器人 |
| `EKS_CLUSTER` | Variable | 默认 `retail-live` |
| `CF_FUNCTION_NAME` / `CF_DISTRIBUTION_ID` | Variable | CloudFront |
| `WAF_ACL_NAME` / `WAF_ACL_ID` | Variable | WebACL（us-east-1，CLOUDFRONT 作用域） |

## 安全说明
- 所有密钥放在 Secrets Manager 或 GitHub Secrets，**不要提交到仓库**。
- ops-mcp 只写 Jira，不修改 AWS 资源，也不能审批。
- Workflow 执行前会调用 Jira API 再次校验：状态为"已批准"，且参数与工单一致。

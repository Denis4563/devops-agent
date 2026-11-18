# SOW：GameDay「Agent to the Rescue」Demo 搭建工作说明书

> 依据：《5-最终方案-零售直播智能运维.md》
> 目标：3 人 × 1 天，完成三个业务场景和"告警 → Jira → Agent → ops-mcp → Jira 审批 → GitHub 执行 → 飞书"闭环。

---

## 1. 范围
| 包含 | 不包含 |
|---|---|
| EKS Auto Mode + 3 个 nginx 模拟服务 + HPA | 真实业务代码、数据库、支付 |
| CloudFront（SG/EU）+ CF Function + WAF | 多 Region 部署 |
| DevOps Agent Space + Skill `retail-live-ops` | 细分 Skill、自定义 Agent |
| ops-mcp（6 个工具） | Athena 日志分析 |
| Jira 配置 + jira-bridge + simulate.py | Jira 安装（复用 EC2 已有 Jira） |
| GitHub 仓库 + 3 个 Runbook + Workflow + 飞书通知 | 前端视觉设计 |

---

## 2. 分工总览
| 角色 | 职责 | 产出 |
|---|---|---|
| A | DevOps Agent、Skill、演示资源 | EKS/CloudFront/WAF、Agent Space、SKILL.md、结论截图 |
| B | Jira 对接、ops-mcp、模拟测试 | Jira 配置、jira-bridge、ops-mcp、simulate.py、测试记录 |
| C | GitHub、飞书对接 | 仓库、Runbook、runbook.yml、agent-notify、reset.sh |

---

## 3. 当天时间表

### 角色 A：DevOps Agent + Skill + 演示资源
| 时间 | 任务 | 产出 |
|---|---|---|
| 09:00–09:30 | 开工会，对齐接口（第 4 节） | — |
| 09:30–10:30 | `eksctl` 建 EKS Auto Mode 集群；部署 catalog / coupon / checkout（nginx）+ HPA（NORMAL 初值） | `k8s/apps.yaml` |
| 10:30–11:30 | S3 页面 `/sg/`、`/eu/` + CloudFront（`/live/*` 缓存策略 + CF Function `geo-rewrite`）；WAF WebACL（托管规则 + `coupon-claim-rate-guard` Count）挂到 CloudFront | CloudFront 域名、WebACL |
| 11:30–12:00 | 创建 Agent Space（中文）；关联账号；EKS Access Entry（只读）；集成 GitHub 仓库；生成 Webhook URL + HMAC 密钥 → 交给 B | Agent Space、Webhook |
| 13:00–13:30 | 在 Agent Space 注册 ops-mcp（B 提供地址和 API Key），在聊天中调用 6 个工具验证 | 工具调用截图 |
| 13:30–15:00 | 编写 `skills/retail-live-ops/SKILL.md`（方案附录 A），从 GitHub 导入；手动发起 1 次调查 | Skill 生效 |
| 15:00–17:30 | 与 B、C 联调 5 个用例，检查 Agent 结论、是否调用了 `jira_comment`/`request_runbook`，迭代 Skill 措辞 | 结论截图 |
| 17:30–18:00 | 拓扑截图、调查截图、演示素材整理 | 素材 |

验收：5 个用例的 Agent 结论都符合预期（S1-b 不扩容、S3-a 不防护必须命中）；需要变更的用例中，Agent 通过 ops-mcp 把工单推到"待审批"。

### 角色 B：Jira 对接 + ops-mcp + 模拟测试
| 时间 | 任务 | 产出 |
|---|---|---|
| 09:30–10:15 | Jira：项目 `LIVEOPS`；字段 `Scenario`、`Phase`、`Market`、`Runbook`、`Runbook Params`、`Agent Investigation URL`；工作流（待诊断/待审批/已批准/已完成/已驳回）；"已批准"仅限 `approvers` 组；`devops-agent-bot` 账号和 Token | Jira 配置 |
| 10:15–12:00 | **ops-mcp**：EC2 t3.small，Python FastMCP（`mcp<2`），6 个工具（方案 7.2）；nginx HTTPS + API Key；systemd 常驻 | `mcp/ops_mcp_server.py`、部署脚本 |
| 12:00 | 把 ops-mcp 地址和 API Key 交给 A 注册 | — |
| 13:00–14:00 | jira-bridge Lambda：`/alarm`（SNS 告警 → 建单，description 带阶段/市场/指标快照）、`/investigate`（组装 Agent Schema + HMAC 签名调用 Webhook）；Jira Automation"创建时"调用 `/investigate` | Lambda + Automation |
| 14:00–15:00 | `simulate.py <case>`：向 `RetailLive` 推送指标（附录 B），配置告警 → SNS；S2 同时对 CloudFront 发带随机 `live_trace_id` 的 curl；`simulate.py reset` | 脚本 + 告警 |
| 15:00–17:30 | 联调：5 个用例各跑 1 遍，记录调查时长、结论、ops-mcp 调用情况 | 测试记录 |
| 17:30–18:00 | 演示操作卡（每个场景执行哪条命令、看哪个界面） | 操作卡 |

验收：执行 `simulate.py s1a` 后 3 分钟内 Jira 出单、Agent 开始调查；ops-mcp 的 `request_runbook` 对非白名单参数返回拒绝；bot 账号无法流转"已批准"。

### 角色 C：GitHub + 飞书对接
| 时间 | 任务 | 产出 |
|---|---|---|
| 09:30–10:00 | 建仓库 `retail-live-ops`（第 5 节）、邀请 A/B；OIDC 角色（EKS 更新 HPA、CloudFront 更新 Function 和 invalidation、WAF 更新规则） | 仓库 + IAM 角色 |
| 10:00–10:30 | `config/runbooks.yaml`：Runbook 目录与参数范围（ops-mcp 和 Workflow 共用） | 配置文件 |
| 10:30–12:00 | 3 个 Runbook（bash + aws/kubectl，支持 `DRY_RUN`）：`scale.sh <svc> <min> <max>`、`cdn_fix.sh`、`waf_guard.sh on\|off` | `runbooks/` |
| 13:00–14:00 | `runbook.yml`：`repository_dispatch` → 读取 payload → 调 Jira API 校验状态=已批准、参数与工单一致 → 执行 → 评论回写 Jira → 流转"已完成" | Workflow |
| 14:00–15:00 | 飞书：建群 + 自定义机器人（签名校验）；`agent-notify` Lambda 订阅 EventBridge `aws.aidevops`（Investigation Completed/Failed）→ 飞书卡片；Workflow 结束时发执行结果卡片 | 2 种通知 |
| 15:00–15:30 | 给 B 提供 GitHub Token；B 配 Jira Automation"已批准时 → POST https://api.github.com/repos/&lt;org&gt;/retail-live-ops/dispatches" | Automation 规则 |
| 15:30–17:30 | 联调执行链：审批 → Actions → 资源变更 → Jira/飞书回写 | 运行记录 |
| 17:30–18:00 | `reset.sh`：HPA 回 NORMAL、CF Function 回故障前、WAF 回 Count | 复位脚本 |

验收：未批准或参数不一致时 Actions 拒绝执行；批准后 2 分钟内完成变更，Jira 和飞书都能看到结果。

---

## 4. 开工会对齐的接口（09:00）
| 接口 | 约定 |
|---|---|
| 指标 | 命名空间 `RetailLive`；维度 `Service`、`Market`、`SKU` |
| Runbook 目录 | `config/runbooks.yaml`：`scale`（svc ∈ catalog/coupon/checkout，min 1–10，max 2–30）、`cdn_fix`（无参数）、`waf_guard`（mode ∈ on/off） |
| Jira 字段 | `Runbook` 取值同上；`Runbook Params` 为 JSON，如 `{"svc":"checkout","min":4,"max":20}` |
| dispatch payload | `{"event_type":"liveops-execute","client_payload":{"jira_key":"LIVEOPS-1","runbook":"scale","params":{...}}}` |
| ops-mcp | 地址 `https://<ops-mcp 域名>/sse`；Header `x-api-key`；6 个工具名见方案 7.2 |
| 活动上下文 | SSM `/retail-live/campaign/current`（JSON：phase、t0、hot_skus、coupon_drop_at） |
| 密钥 | Secrets Manager：`/retail-live/jira`、`/retail-live/github`、`/retail-live/feishu`、`/retail-live/agent-webhook`、`/retail-live/ops-mcp` |
| 标签 | 所有资源 `Project=retail-live` |
| Region | 业务 ap-southeast-1；CloudFront/WAF us-east-1 |

---

## 5. 仓库结构
```
retail-live-ops/
├── k8s/apps.yaml                       # A
├── edge/geo-rewrite.js                 # A
├── skills/retail-live-ops/SKILL.md     # A
├── mcp/ops_mcp_server.py               # B
├── mcp/deploy.sh                       # B（EC2 + nginx + systemd）
├── lambdas/jira_bridge.py              # B
├── sim/simulate.py                     # B
├── config/runbooks.yaml                # C
├── runbooks/{scale,cdn_fix,waf_guard,reset}.sh   # C
├── lambdas/agent_notify.py             # C
└── .github/workflows/runbook.yml       # C
```

---

## 6. 演示用例
| 用例 | 模拟（simulate.py） | Agent 预期结论 | ops-mcp 动作 | 执行 |
|---|---|---|---|---|
| S1-a 结算饱和 | PEAK；checkout CPU 85%、InFlight 45/Pod、HPA 在 max；DB CPU 40% | 只扩 checkout | comment + request_runbook `scale checkout 4 20` | 审批后执行 |
| S1-b 爆款锁争用 | checkout 延迟高但 CPU 35%；`SkuLockWaitMs{SKU=HOT-001}` 800ms | **不扩容**，建议排队 | 只写 comment | 不执行 |
| S2 EU 缓存被拆散 | EU CacheHitRate 92%→35%，回源 ×6，SG 正常；curl 带随机 `live_trace_id` | 追踪参数拆散缓存，非容量问题 | comment + request_runbook `cdn_fix` | 审批后执行 |
| S3-a 正常抢券 | 放券窗口内 QPS ×10，成功率 92%，重复提交 1% | **不启用防护** | 只写 comment | 不执行 |
| S3-b 刷券 | 成功率 45%，重复提交 35%，WAF Count 8000/分 | 仅领券接口限速 | comment + request_runbook `waf_guard on` | 审批后执行，回落后 off |

---

## 7. 里程碑（当天）
| 时间 | 检查点 |
|---|---|
| 12:00 | EKS/CloudFront/WAF 就绪；Agent Space 和 Webhook 就绪；ops-mcp 部署完成；Runbook 完成 |
| 13:30 | Agent 能调用 ops-mcp 6 个工具 |
| 15:00 | 单链路打通：告警 → Jira → Agent → ops-mcp → 待审批 |
| 15:30 | 执行链打通：已批准 → GitHub → 回写 → 飞书 |
| 17:30 | 5 个用例全部跑通 1 遍 |
| 18:00 | 操作卡、截图、reset 就绪 |

---

## 8. 风险与预案
| 风险 | 负责人 | 预案 |
|---|---|---|
| ops-mcp 无法注册或连接不稳定 | B / A | 固定 `mcp<2`；SSE + nginx 长超时；12:00 前未通则降级：Agent 输出结论，人工填 Jira 字段，其余链路不变 |
| Agent 不调用 ops-mcp 工具 | A | Skill 中写明必须调用的工具；工具描述写清使用时机；在 Webhook description 中提示"按 retail-live-ops Skill 处理" |
| 拓扑学习 ≥30 分钟 | A | 中午前建好资源 |
| Agent 结论偏离 | A / B | 模拟信号做强；Skill 写明阈值 |
| 并发调查上限 3 | B | 用例间隔 ≥3 分钟触发 |
| CloudFront 部署慢 | A | 上午最先创建；S2 修复只改 CF Function |
| 审批执行链未打通 | C | 降级：审批后由 C 手动 `gh workflow run`，记录仍在 Jira |

---

## 9. 成本
| 项 | 估算 |
|---|---|
| EKS / CloudFront / WAF / ops-mcp EC2 / Lambda | 约 $17 |
| DevOps Agent 调查（约 15 次） | 约 $60，免费额度可覆盖 |
| 结束清理 | `eksctl delete cluster`；删除 CloudFront、WAF、ops-mcp EC2 |

---

## 10. 验收标准
1. 5 个用例可一键模拟、一键复位。
2. 每个用例完整走通：告警 → Jira → Agent 调查 → ops-mcp 回写 → （需要时）审批 → GitHub 执行 → Jira 回写 → 飞书。
3. S1-b"不扩容"、S3-a"不启用防护"必须命中。
4. 治理：bot 无法审批；ops-mcp 拒绝非白名单参数；未审批时执行被拒绝。
5. 交付物：方案文档、SOW、SKILL.md、代码仓库、操作卡、截图/录屏。

---

## 附录 B：模拟指标清单
| 指标 | 维度 | 用于 |
|---|---|---|
| `CheckoutCpu`、`CheckoutInFlight`、`CheckoutP95Ms` | Service | S1 |
| `HpaAtMax` | Service | S1 |
| `DbCpu` | — | S1 |
| `SkuLockWaitMs` | SKU | S1-b |
| `CacheHitRate`、`OriginRequests`、`OriginLatencyMs` | Market | S2 |
| `CouponQps`、`CouponSuccessRate`、`CouponDupRate` | — | S3 |
| `WafCouponCountHits` | — | S3-b |
| `Phase`（0–3） | — | 全部 |

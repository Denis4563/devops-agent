# 可调整项清单

本文件列出演示中可以调整的参数，并标出每一项所在的文件和位置。路径都相对于仓库根目录 `devops-agent/`。

**改动原则**
1. **判定阈值**（Skill）和**模拟注入值**（simulate.py）要一起改：注入值必须明显越过阈值，建议至少高出 20%，否则 Agent 结论会不稳定。
2. **告警阈值**（simulate.py 中的 `ALARMS`）要位于"正常值"和"注入值"之间。
3. 改完 `SKILL.md` 后，要在 Agent Space 的"知识 → 技能"里重新导入，修改才会生效。
4. 改完 `geo-rewrite.js` 后，要重新发布 CloudFront Function（运行 `edge/setup_edge.sh`，或者在控制台发布）。

---

## 1. S1 分阶段扩缩容

### 1.1 HPA 初始值（NORMAL 阶段）
文件：`k8s/apps.yaml`（每个服务的 `HorizontalPodAutoscaler` 段）

| 服务 | 参数 | 当前值 |
|---|---|---|
| catalog | `minReplicas` / `maxReplicas` / `averageUtilization` | 2 / 4 / 65 |
| coupon | 同上 | 1 / 2 / 60 |
| checkout | 同上 | 2 / 4 / 60 |
| 全部 | `behavior.scaleUp.stabilizationWindowSeconds` | 0 |
| 全部 | `behavior.scaleDown.stabilizationWindowSeconds` | 300 |
| 全部 | 容器 `resources.requests` / `limits` | cpu 250m / 500m，memory 256Mi / 512Mi |

### 1.2 各阶段容量（Agent 依据的阶段模型）
文件：`skills/retail-live-ops/SKILL.md` → 第 2 节"阶段模型"表格

| 阶段 | Phase 值 | checkout min/max | 说明 |
|---|---|---|---|
| NORMAL | 0 | 2/4 | 日常 |
| WARMUP | 1 | 2/4（catalog 4/12） | 开播前 30 分钟 |
| PEAK | 2 | 4/20 | 开播后 60 分钟 |
| TAIL | 3 | 2/6 | 下播后 90 分钟 |

### 1.3 判定阈值
文件：`skills/retail-live-ops/SKILL.md` → 第 3 节"S1 扩缩容判定"表格

| 判定 | 当前条件 | Agent 建议的参数 |
|---|---|---|
| 只扩 checkout | `CheckoutCpu>75%` 或 `CheckoutInFlight>40`，且 `HpaAtMax=1`、`DbCpu<50%` | `scale` {"svc":"checkout","min":4,"max":20} |
| 锁争用不扩容 | `CheckoutCpu<50%`，且单个 SKU 的 `SkuLockWaitMs>500` | 不执行 |
| 数据库瓶颈 | `DbCpu>80%` | 不扩应用 |
| 撤容 | `Phase=3` 且积压回落 | `scale` {"svc":"checkout","min":2,"max":4} |

### 1.4 Runbook 参数允许范围（白名单）
文件：`config/runbooks.yaml` → `runbooks.scale.params`

| 参数 | 当前范围 |
|---|---|
| `svc` | catalog / coupon / checkout |
| `min` | 1–10 |
| `max` | 2–30 |

> 如果把 Skill 里建议的 max 调到 30 以上，这里也要同步放宽，否则 ops-mcp 会拒绝这次请求。

---

## 2. S2 CloudFront 地理交付

### 2.1 EU 国家列表与追踪参数
文件：`edge/geo-rewrite.js`

| 变量 | 当前值 |
|---|---|
| `EU`（第 2 行） | DE, FR, NL, BE, IT, ES, IE, AT, PL, SE, DK, FI, PT |
| `TRACKING`（第 3 行） | live_trace_id, share_from, fbclid, ttclid, gclid（另外所有 `utm_*` 参数也会被剥离） |
| `STRIP_EU_TRACKING`（第 5 行） | true（故障注入 F2 会把它改成 false，请勿手动修改） |
| 默认市场 | 不在 EU 列表里的国家一律归到 `sg` |

> EU 国家列表还写在 Skill 里，但只作为说明文字，可选择同步：`skills/retail-live-ops/SKILL.md` 第 4 节。

### 2.2 判定阈值
文件：`skills/retail-live-ops/SKILL.md` → 第 4 节"S2 CloudFront 判定"

| 观察项 | 判定为"缓存被拆散"的条件 |
|---|---|
| `CacheHitRate`（EU） | 从 >90% 降到 <50% |
| `OriginRequests`（EU） | 暴增到基线的数倍 |
| `OriginLatencyMs` | 正常 |
| SG 和 checkout 指标 | 正常 |

---

## 3. S3 领券分级防护

### 3.1 WAF 限速规则
文件：`edge/setup_edge.sh` → `coupon-claim-rate-guard` 规则

| 参数 | 当前值 |
|---|---|
| `Limit` | 100 |
| `EvaluationWindowSec` | 60 |
| `AggregateKeyType` | IP |
| 匹配路径 `SearchString` | /api/coupon/claim（STARTS_WITH） |
| 默认动作 | Count |

> 已经创建好的 WebACL 不会随脚本更新。要么在控制台修改，要么删掉 WebACL 后重新运行脚本。

### 3.2 风险分级阈值
文件：`skills/retail-live-ops/SKILL.md` → 第 5 节"S3 领券防护判定"

| 等级 | 当前条件 |
|---|---|
| L0 正常 | 放券后 15 分钟内，`CouponSuccessRate>85%`，`CouponDupRate<3%` |
| L1 关注 | 成功率 60–85%，或重复提交 >10% |
| L2 异常 | 成功率 <60% 且重复提交 >25%，或 `WafCouponCountHits>5000/分钟` |
| 回落 | `WafCouponCountHits<100/分钟`，持续 10 分钟 |

---

## 4. 模拟数据与告警

文件：`sim/simulate.py`

### 4.1 正常基线 `NORMAL`
| 指标 | 当前值 |
|---|---|
| CheckoutCpu / CheckoutInFlight / CheckoutP95Ms | 35 / 12 / 180 |
| DbCpu | 25 |
| SkuLockWaitMs（HOT-001、HOT-002） | 20 |
| CacheHitRate SG / EU | 93 / 92 |
| OriginRequests SG / EU | 300 / 250 |
| OriginLatencyMs SG / EU | 40 / 210 |
| CouponQps / CouponSuccessRate / CouponDupRate | 50 / 97 / 0.5 |
| WafCouponCountHits | 10 |

### 4.2 用例注入值 `CASES`
| 用例 | 当前注入值 | 要越过的判定阈值 |
|---|---|---|
| `s1a` | CPU 85、InFlight 45、P95 900、HpaAtMax 1、DbCpu 40 | CPU>75、DbCpu<50 |
| `s1b` | CPU 35、InFlight 30、P95 1200、DbCpu 45、HOT-001 锁等待 800 | CPU<50、锁等待>500 |
| `s2` | EU 命中率 35、EU 回源 1500、EU 回源延迟 215 | 命中率<50 |
| `s3a` | QPS 500、成功率 92、重复提交 1、WAF 计数 300 | 成功率>85、重复提交<3 |
| `s3b` | QPS 900、成功率 45、重复提交 35、WAF 计数 8000 | 成功率<60、重复提交>25 |
| `tail` | Phase 3、CPU 20 | Phase=3 |

### 4.3 告警 `ALARMS`
| 告警名 | 指标 | 当前阈值 |
|---|---|---|
| RetailLive-S1-CheckoutSlow | CheckoutP95Ms（checkout） | >600 |
| RetailLive-S2-EUCacheHitLow | CacheHitRate（EU） | <60 |
| RetailLive-S3-CouponSurge | CouponQps | >300 |
| RetailLive-S1-TailRecovered | Phase | >2.5 |
| 公共参数 | `Period` / `EvaluationPeriods` / `DatapointsToAlarm` | 60 秒 / 2 / 2 |

### 4.4 其他
| 参数 | 位置 | 当前值 |
|---|---|---|
| 注入持续时间 | 命令行参数 `--minutes` | 8 分钟 |
| 每次推送的随机波动 | `put()` 中的 `random.uniform` | ±3% |
| S2 的 curl 请求数 | `curl_s2(..., 50)` | 每分钟 50 次 |
| 区域 | `REGION` | ap-southeast-1 |
| SNS 主题 | `SNS_TOPIC` | retail-live-alarms |

---

## 5. 活动上下文

文件：`config/campaign.json`（运行 `python sim/simulate.py setup` 时写入 SSM 参数 `/retail-live/campaign/current`）

| 字段 | 当前值 |
|---|---|
| `campaign_id` | LIVE-2026W47 |
| `t0` | 2026-11-25T20:00:00+08:00 |
| `duration_min` | 120 |
| `hot_skus` | HOT-001, HOT-002 |
| `coupon_drop_at` | 2026-11-25T20:00:00+08:00 |
| `markets` | SG, EU |

> `hot_skus` 如果增加了新的 SKU，还要同步改两处：`mcp/ops_mcp_server.py` 中 `SCENARIO_METRICS["S1"]` 的 `SkuLockWaitMs` 维度，以及 `sim/simulate.py` 的 `NORMAL`。

---

## 6. 环境与集成配置

### 6.1 ops-mcp 环境变量
文件：`mcp/ops_mcp_server.py`（顶部 `os.getenv`）；部署时在 `mcp/deploy.sh` 的 systemd `Environment=` 中设置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AWS_REGION` | ap-southeast-1 | |
| `PORT` | 8000 | 本机监听端口，由 nginx 反代 |
| `MCP_TRANSPORT` | sse | 可选 sse / stdio |
| `CAMPAIGN_PARAM` | /retail-live/campaign/current | |
| `JIRA_SECRET` | /retail-live/jira | |
| `JIRA_FIELD_RUNBOOK` | customfield_10101 | **必须换成你 Jira 实际的字段 ID** |
| `JIRA_FIELD_PARAMS` | customfield_10102 | **必须换成你 Jira 实际的字段 ID** |
| `JIRA_TRANSITION_PENDING` | 待审批 | Jira 工作流中的流转名或状态名 |
| `JIRA_TRANSITION_DONE` | 已完成 | 同上 |

### 6.2 nginx
文件：`mcp/nginx.conf`

| 参数 | 当前值 |
|---|---|
| 监听端口 | 80（TLS 由 ALB 或 certbot 提供） |
| `proxy_read_timeout` / `proxy_send_timeout` | 3600s |
| API Key Header | `x-api-key`（值由 deploy.sh 从 `/retail-live/ops-mcp` 读取后替换进配置） |

### 6.3 GitHub Actions
文件：`.github/workflows/runbook.yml`；具体的值在仓库 Settings → Secrets and variables 中配置

| 名称 | 类型 | 默认值 |
|---|---|---|
| `AWS_ROLE_ARN` | Secret | — |
| `JIRA_BASE_URL` / `JIRA_USER` / `JIRA_TOKEN` | Secret | — |
| `FEISHU_WEBHOOK` / `FEISHU_SECRET` | Secret | — |
| `EKS_CLUSTER` | Variable | retail-live |
| `JIRA_FIELD_RUNBOOK` / `JIRA_FIELD_PARAMS` | Variable | customfield_10101 / 10102 |
| `CF_FUNCTION_NAME` | Variable | geo-rewrite |
| `CF_DISTRIBUTION_ID` | Variable | — |
| `WAF_ACL_NAME` / `WAF_ACL_ID` | Variable | retail-live-acl / — |
| 审批状态名 | 写在 workflow "校验 Jira 审批状态"步骤中 | 已批准 |

### 6.4 Runbook 环境变量
目录：`runbooks/`

| 变量 | 使用它的脚本 | 默认值 |
|---|---|---|
| `DRY_RUN` | 全部 | 0（设为 1 时只预演，不实际变更） |
| `NAMESPACE` | scale.sh | retail |
| `CF_FUNCTION_NAME` / `CF_DISTRIBUTION_ID` | cdn_fix.sh | geo-rewrite / 必填 |
| `WAF_ACL_NAME` / `WAF_ACL_ID` | waf_guard.sh | retail-live-acl / 必填 |
| 复位后的 HPA 值 | reset.sh | catalog 2/4、coupon 1/2、checkout 2/4（要和 `k8s/apps.yaml` 保持一致） |

### 6.5 集群与资源
| 参数 | 文件 | 当前值 |
|---|---|---|
| 集群名 / 区域 / 版本 | `k8s/cluster.yaml` | retail-live / ap-southeast-1 / 1.31 |
| 容器镜像 | `k8s/apps.yaml` | public.ecr.aws/nginx/nginx:1.27 |
| S3 桶名 / Function 名 / WebACL 名 | `edge/setup_edge.sh`（环境变量 `BUCKET` / `CF_FUNCTION_NAME` / `WAF_ACL_NAME`） | retail-live-pages-&lt;账号&gt; / geo-rewrite / retail-live-acl |

### 6.6 Secrets Manager
说明见 `docs/jira-setup.md`

| 名称 | 字段 | 使用方 |
|---|---|---|
| /retail-live/jira | base_url, user, token | ops-mcp、jira-bridge、agent-notify |
| /retail-live/agent-webhook | url, secret | jira-bridge |
| /retail-live/bridge | token | jira-bridge（校验 Jira Automation 请求） |
| /retail-live/feishu | webhook, secret | agent-notify |
| /retail-live/ops-mcp | api_key | nginx |

---

## 7. 修改对照速查

| 想调整 | 需要改的文件 |
|---|---|
| S1 扩容阈值 | `skills/retail-live-ops/SKILL.md` §3 + `sim/simulate.py` CASES s1a/s1b |
| 各阶段容量 | `SKILL.md` §2、§3 + `config/runbooks.yaml`（范围） |
| NORMAL 初始容量 | `k8s/apps.yaml` + `runbooks/reset.sh` |
| EU 国家 | `edge/geo-rewrite.js` `EU`（Skill §4 可选同步） |
| S2 命中率阈值 | `SKILL.md` §4 + `sim/simulate.py` CASES s2 + ALARMS EUCacheHitLow |
| WAF 限速 | `edge/setup_edge.sh`（已创建的 WebACL 要在控制台改） |
| S3 风险分级 | `SKILL.md` §5 + `sim/simulate.py` CASES s3a/s3b + ALARMS CouponSurge |
| 爆款 SKU | `config/campaign.json` + `mcp/ops_mcp_server.py` SCENARIO_METRICS + `sim/simulate.py` NORMAL |
| Jira 字段或状态名 | ops-mcp 环境变量 + GitHub Variables + `runbook.yml` 中的"已批准" |

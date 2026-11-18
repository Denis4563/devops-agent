---
name: retail-live-ops
description: 零售直播大促（SG/EU 双市场）运维判断规则。调查 RetailLive 相关告警或 LIVEOPS 工单时使用，覆盖分阶段扩缩容、CloudFront 地理交付异常、领券接口分级防护，并规定通过 ops-mcp 回写 Jira 和提交执行请求。
metadata:
  author: retail-live-ops
  tags: retail, livestream, eks, cloudfront, waf, jira
---
# 零售直播大促运维 Skill

## 1. 调查开始时必须做
1. 从事件描述中提取 Jira 工单号（格式 `LIVEOPS-数字`）。
2. 调用 ops-mcp `get_campaign_context`：获取阶段、开播时间、爆款 SKU、放券时间。
3. 调用 ops-mcp `get_business_metrics`，scenario 取 S1 / S2 / S3（按告警判断）。
4. S2 额外调用 `get_cdn_market_breakdown`。
5. 需要变更前调用 `get_runbook_catalog`，参数只能取目录内的值。

## 2. 阶段模型
| 阶段 | Phase 值 | 时间 | 主要压力 | checkout HPA |
|---|---|---|---|---|
| NORMAL | 0 | 日常 | — | 2/4 |
| WARMUP | 1 | 开播前 30 分钟 | 浏览 → catalog | 2/4（catalog 4/12） |
| PEAK | 2 | 开播后 60 分钟 | 领券、下单 | 4/20 |
| TAIL | 3 | 下播后 90 分钟 | 支付确认 | 2/6 |
以 `Phase` 指标为准，活动日历只作为先验。

## 3. S1 扩缩容判定
| 条件 | 结论 | 动作 |
|---|---|---|
| CheckoutCpu>75% 或 CheckoutInFlight>40，HpaAtMax=1，DbCpu<50% | 结算服务计算饱和，数据库有余量 | request_runbook `scale` {"svc":"checkout","min":4,"max":20} |
| CheckoutP95Ms 高，但 CheckoutCpu<50%，SkuLockWaitMs 在单一 SKU >500ms | **爆款库存锁争用，扩容无效甚至加剧** | **不扩容**；只写 jira_comment，建议对该 SKU 开启排队 |
| DbCpu>80% 且各服务正常 | 数据库瓶颈 | 不扩应用，jira_comment 建议提高数据库容量 |
| Phase=3 且积压回落 | 活动结束 | request_runbook `scale` {"svc":"checkout","min":2,"max":4} |

## 4. S2 CloudFront 判定
| 观察 | 缓存被拆散 | 容量不足 |
|---|---|---|
| 范围 | 只有 EU 慢，SG 正常 | 两个市场都慢 |
| CacheHitRate | EU 从 >90% 降到 <50% | 基本不变 |
| OriginRequests | 暴增（数倍） | 正常 |
| OriginLatencyMs | 正常 | 升高 |
| checkout 指标 | 正常 | 异常 |
- 符合"缓存被拆散" → 结论：直播链接追踪参数（如 live_trace_id）进入了缓存键；request_runbook `cdn_fix` {}。
- **必须在结论中明确排除**：① 结算服务容量不足；② EU 回源新加坡的跨区延迟（跨区延迟不会导致命中率下降）。

## 5. S3 领券防护判定
| 等级 | 条件 | 动作 |
|---|---|---|
| L0 正常 | 放券窗口内（coupon_drop_at 后 15 分钟），CouponSuccessRate>85%，CouponDupRate<3% | **不启用防护**，只写 jira_comment："涨得快不等于攻击" |
| L1 关注 | 成功率 60–85% 或重复提交率>10% | jira_comment，保持观察 |
| L2 异常 | 成功率<60% 且重复提交率>25%，或 WafCouponCountHits>5000/分钟 | request_runbook `waf_guard` {"mode":"on"} |
| 回落 | WafCouponCountHits<100/分钟持续 10 分钟 | request_runbook `waf_guard` {"mode":"off"} |
- 防护只针对 `/api/coupon/claim`；**下单、支付接口不收紧**；基础托管规则始终开启。

## 6. 收尾（必须执行）
1. 调用 `jira_comment`，内容按下方格式。
2. 需要变更 → 调用 `request_runbook`（工单进入"待审批"）。
3. 结论为"不扩容 / 不启用防护" → 不调用 request_runbook，在评论里写明原因。

评论格式：
```
【结论】一句话
【证据】指标名=数值（对比基线）
【已排除】假设 + 排除依据
【建议】Runbook 与参数 / 或"不执行变更"
【风险】执行或不执行的影响
```

## 7. 禁止
- 不直接修改任何资源（Agent 只读）。
- 不建议 Runbook 目录以外的操作。
- 不对下单、支付接口建议限流。

"""ops-mcp：DevOps Agent 闭环核心 MCP Server
读：活动上下文、业务指标、CDN 分市场数据、Runbook 目录
写：Jira 评论、提交执行请求（只写 Jira，不改 AWS 资源，不能审批）
"""
import json, os, datetime as dt
import boto3, requests, yaml
from mcp.server.fastmcp import FastMCP

REGION = os.getenv("AWS_REGION", "ap-southeast-1")
NS = "RetailLive"
CAMPAIGN_PARAM = os.getenv("CAMPAIGN_PARAM", "/retail-live/campaign/current")
RUNBOOK_FILE = os.getenv("RUNBOOK_FILE", os.path.join(os.path.dirname(__file__), "..", "config", "runbooks.yaml"))
JIRA_SECRET = os.getenv("JIRA_SECRET", "/retail-live/jira")
F_RUNBOOK = os.getenv("JIRA_FIELD_RUNBOOK", "customfield_10101")
F_PARAMS = os.getenv("JIRA_FIELD_PARAMS", "customfield_10102")
T_PENDING = os.getenv("JIRA_TRANSITION_PENDING", "待审批")
T_DONE = os.getenv("JIRA_TRANSITION_DONE", "已完成")

cw = boto3.client("cloudwatch", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
sm = boto3.client("secretsmanager", region_name=REGION)
mcp = FastMCP("ops-mcp", host="127.0.0.1", port=int(os.getenv("PORT", "8000")))

SCENARIO_METRICS = {
    "S1": [("CheckoutCpu", {"Service": "checkout"}), ("CheckoutInFlight", {"Service": "checkout"}),
           ("CheckoutP95Ms", {"Service": "checkout"}), ("HpaAtMax", {"Service": "checkout"}),
           ("DbCpu", {}), ("SkuLockWaitMs", {"SKU": "HOT-001"}), ("SkuLockWaitMs", {"SKU": "HOT-002"}), ("Phase", {})],
    "S2": [("CacheHitRate", {"Market": "SG"}), ("CacheHitRate", {"Market": "EU"}),
           ("OriginRequests", {"Market": "SG"}), ("OriginRequests", {"Market": "EU"}),
           ("OriginLatencyMs", {"Market": "SG"}), ("OriginLatencyMs", {"Market": "EU"}),
           ("CheckoutCpu", {"Service": "checkout"}), ("Phase", {})],
    "S3": [("CouponQps", {}), ("CouponSuccessRate", {}), ("CouponDupRate", {}),
           ("WafCouponCountHits", {}), ("Phase", {})],
}


def _metric(name, dims, minutes):
    end = dt.datetime.utcnow()
    r = cw.get_metric_statistics(Namespace=NS, MetricName=name,
                                 Dimensions=[{"Name": k, "Value": v} for k, v in dims.items()],
                                 StartTime=end - dt.timedelta(minutes=max(minutes, 60)), EndTime=end,
                                 Period=60, Statistics=["Average"])
    pts = sorted(r["Datapoints"], key=lambda p: p["Timestamp"])
    if not pts:
        return {"metric": name, "dims": dims, "latest": None}
    recent = [p["Average"] for p in pts[-minutes:]]
    base = [p["Average"] for p in pts[:-minutes]] or recent
    return {"metric": name, "dims": dims, "latest": round(recent[-1], 2),
            "recent_avg": round(sum(recent) / len(recent), 2),
            "baseline_avg": round(sum(base) / len(base), 2)}


def _jira():
    s = json.loads(sm.get_secret_value(SecretId=JIRA_SECRET)["SecretString"])
    sess = requests.Session()
    sess.auth = (s["user"], s["token"])
    sess.headers.update({"Content-Type": "application/json"})
    return s["base_url"].rstrip("/"), sess


def _transition(base, sess, key, name):
    ts = sess.get(f"{base}/rest/api/2/issue/{key}/transitions", timeout=10).json().get("transitions", [])
    t = next((t for t in ts if t["name"] == name or t["to"]["name"] == name), None)
    if not t:
        return f"未找到流转 {name}，可用：{[x['name'] for x in ts]}"
    sess.post(f"{base}/rest/api/2/issue/{key}/transitions", json={"transition": {"id": t["id"]}}, timeout=10)
    return f"已流转到 {name}"


def _catalog():
    with open(RUNBOOK_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)["runbooks"]


def _validate(runbook, params):
    cat = _catalog()
    if runbook not in cat:
        return f"Runbook {runbook} 不在目录中"
    spec = cat[runbook].get("params") or {}
    extra = set(params) - set(spec)
    if extra:
        return f"不允许的参数：{sorted(extra)}"
    for k, rule in spec.items():
        if k not in params:
            return f"缺少参数：{k}"
        v = params[k]
        if rule["type"] == "enum" and str(v) not in [str(x) for x in rule["values"]]:
            return f"{k}={v} 不在允许值 {rule['values']} 中"
        if rule["type"] == "int":
            if not isinstance(v, int) or not (rule["min"] <= v <= rule["max"]):
                return f"{k}={v} 超出范围 [{rule['min']},{rule['max']}]"
    if runbook == "scale" and params["min"] > params["max"]:
        return "min 不能大于 max"
    return None


@mcp.tool()
def get_campaign_context() -> dict:
    """获取当前直播活动上下文：阶段(phase)、开播时间(t0)、爆款 SKU(hot_skus)、放券时间(coupon_drop_at)。调查 RetailLive 告警时首先调用。"""
    return json.loads(ssm.get_parameter(Name=CAMPAIGN_PARAM)["Parameter"]["Value"])


@mcp.tool()
def get_business_metrics(scenario: str, minutes: int = 5) -> dict:
    """按场景返回 RetailLive 业务指标的最新值、近 N 分钟均值和基线均值。scenario: S1(扩缩容/结算/锁争用) | S2(CDN 分市场) | S3(领券/WAF)。"""
    scenario = scenario.upper()
    if scenario not in SCENARIO_METRICS:
        return {"error": "scenario 只能是 S1/S2/S3"}
    return {"scenario": scenario, "metrics": [_metric(n, d, minutes) for n, d in SCENARIO_METRICS[scenario]]}


@mcp.tool()
def get_cdn_market_breakdown(minutes: int = 5) -> dict:
    """按 SG/EU 市场对比 CloudFront 命中率、回源请求量和回源延迟（近 N 分钟 vs 基线）。用于判断是缓存被拆散还是容量不足。"""
    out = {}
    for m in ("SG", "EU"):
        out[m] = {n: _metric(n, {"Market": m}, minutes) for n in ("CacheHitRate", "OriginRequests", "OriginLatencyMs")}
    return out


@mcp.tool()
def get_runbook_catalog() -> dict:
    """返回可执行的 Runbook 及参数允许范围。调用 request_runbook 前必须先查看。"""
    return _catalog()


@mcp.tool()
def jira_comment(jira_key: str, body: str) -> str:
    """把调查结论写入 Jira 工单评论。body 使用格式：【结论】【证据】【已排除】【建议】【风险】。"""
    base, sess = _jira()
    r = sess.post(f"{base}/rest/api/2/issue/{jira_key}/comment", json={"body": "[DevOps Agent]\n" + body}, timeout=10)
    if r.ok and "不执行变更" in body:
        return "评论已写入；" + _transition(base, sess, jira_key, T_DONE)
    return "评论已写入" if r.ok else f"失败：{r.status_code} {r.text[:200]}"


@mcp.tool()
def request_runbook(jira_key: str, runbook: str, params: dict) -> str:
    """提交执行请求：校验参数白名单后写入 Jira 的 Runbook 和 Runbook Params 字段，并把工单流转到"待审批"。不会执行任何变更，也不能审批。"""
    err = _validate(runbook, params or {})
    if err:
        return f"拒绝：{err}"
    base, sess = _jira()
    r = sess.put(f"{base}/rest/api/2/issue/{jira_key}",
                 json={"fields": {F_RUNBOOK: runbook, F_PARAMS: json.dumps(params, ensure_ascii=False)}}, timeout=10)
    if not r.ok:
        return f"写字段失败：{r.status_code} {r.text[:200]}"
    return f"已提交 {runbook} {params}；" + _transition(base, sess, jira_key, T_PENDING)


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "sse"))

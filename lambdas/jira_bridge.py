"""jira-bridge Lambda（Function URL）
POST /alarm        SNS → CloudWatch 告警 → Jira 建单
POST /investigate  Jira Automation（创建时）→ HMAC 签名调用 DevOps Agent Webhook
"""
import base64, hashlib, hmac, json, os, datetime as dt, urllib.request
import boto3

sm = boto3.client("secretsmanager")
SCENARIO = {"S1": "Scaling", "S2": "CDN", "S3": "WAF"}


def _secret(name):
    return json.loads(sm.get_secret_value(SecretId=name)["SecretString"])


def _http(url, data, headers, auth=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read().decode()


def alarm(event_body):
    msg = json.loads(json.loads(event_body)["Message"]) if "Message" in event_body else json.loads(event_body)
    name = msg.get("AlarmName", "unknown")
    scenario = name.split("-")[1] if name.startswith("RetailLive-") else "S1"
    j = _secret("/retail-live/jira")
    desc = (f"告警：{name}\n状态：{msg.get('NewStateValue')}\n原因：{msg.get('NewStateReason')}\n"
            f"时间：{msg.get('StateChangeTime')}\n区域：ap-southeast-1\n"
            f"请按 retail-live-ops Skill 处理，使用 ops-mcp 获取上下文并回写本工单。")
    body = {"fields": {"project": {"key": "LIVEOPS"}, "issuetype": {"name": "Task"},
                       "summary": f"[{scenario}] {name}", "description": desc,
                       "labels": ["retail-live", scenario]}}
    return _http(f"{j['base_url'].rstrip('/')}/rest/api/2/issue", body,
                 {"Content-Type": "application/json"}, f"{j['user']}:{j['token']}")


def investigate(event_body):
    issue = json.loads(event_body)
    key, summary = issue["key"], issue.get("summary", "")
    desc = issue.get("description", "")
    w = _secret("/retail-live/agent-webhook")
    payload = {
        "eventType": "Incident", "incidentId": key, "action": "created",
        "priority": "HIGH", "title": f"{key} {summary}",
        "description": f"Jira 工单：{key}\n{desc}\n要求：加载 retail-live-ops Skill，调用 ops-mcp 获取活动上下文和业务指标，"
                       f"结论用 jira_comment 写回 {key}，需要变更时用 request_runbook 提交。",
        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "service": "retail-live", "data": issue}
    ts = dt.datetime.utcnow().isoformat() + "Z"
    sig = base64.b64encode(hmac.new(w["secret"].encode(), f"{ts}:{json.dumps(payload)}".encode(), hashlib.sha256).digest()).decode()
    return _http(w["url"], payload, {"Content-Type": "application/json",
                                     "x-amzn-event-timestamp": ts, "x-amzn-event-signature": sig})


def handler(event, context):
    # 共享 Token 校验（Jira Automation 请求头 x-bridge-token）
    if "Records" in event:  # SNS 直接订阅
        return {"results": [alarm(r["Sns"]["Message"]) for r in event["Records"]]}
    token = (event.get("headers") or {}).get("x-bridge-token")
    if token != _secret("/retail-live/bridge")["token"]:
        return {"statusCode": 401, "body": "unauthorized"}
    path = event.get("rawPath", "")
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    status, text = investigate(body) if path.endswith("/investigate") else alarm(body)
    return {"statusCode": status, "body": text}

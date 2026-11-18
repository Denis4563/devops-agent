"""agent-notify Lambda：EventBridge (source=aws.aidevops) → 飞书群自定义机器人卡片"""
import base64, hashlib, hmac, json, time, urllib.request
import boto3

sm = boto3.client("secretsmanager")


def _feishu(title, lines, url=None, color="blue"):
    s = json.loads(sm.get_secret_value(SecretId="/retail-live/feishu")["SecretString"])
    ts = str(int(time.time()))
    sign = base64.b64encode(hmac.new(f"{ts}\n{s['secret']}".encode(), digestmod=hashlib.sha256).digest()).decode()
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}]
    if url:
        elements.append({"tag": "action", "actions": [{"tag": "button", "type": "primary",
                         "text": {"tag": "plain_text", "content": "打开 Jira 工单"}, "url": url}]})
    card = {"timestamp": ts, "sign": sign, "msg_type": "interactive",
            "card": {"header": {"title": {"tag": "plain_text", "content": title}, "template": color},
                     "elements": elements}}
    req = urllib.request.Request(s["webhook"], data=json.dumps(card).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=10).read().decode()


def handler(event, context):
    d = event.get("detail", {})
    dtype = event.get("detail-type", "")
    key = d.get("incidentId") or d.get("title", "").split(" ")[0]
    jira = json.loads(sm.get_secret_value(SecretId="/retail-live/jira")["SecretString"])["base_url"].rstrip("/")
    url = f"{jira}/browse/{key}" if key.startswith("LIVEOPS-") else None
    color = {"Investigation Completed": "green", "Investigation Failed": "red"}.get(dtype, "blue")
    lines = [f"**事件**：{dtype}", f"**工单**：{key}", f"**标题**：{d.get('title', '-')}",
             f"**摘要**：{(d.get('summary') or d.get('rootCause') or '查看 Jira 评论')[:500]}"]
    return _feishu(f"DevOps Agent｜{dtype}", lines, url, color)

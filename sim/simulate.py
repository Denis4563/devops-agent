"""模拟业务指标与告警。用法：python simulate.py setup|s1a|s1b|s2|s3a|s3b|tail|reset [--minutes 8]"""
import argparse, json, random, subprocess, sys, time
import boto3

REGION = "ap-southeast-1"
NS = "RetailLive"
cw = boto3.client("cloudwatch", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
SNS_TOPIC = "arn:aws:sns:ap-southeast-1:{acct}:retail-live-alarms"

NORMAL = {
    ("CheckoutCpu", "Service", "checkout"): 35, ("CheckoutInFlight", "Service", "checkout"): 12,
    ("CheckoutP95Ms", "Service", "checkout"): 180, ("HpaAtMax", "Service", "checkout"): 0,
    ("DbCpu", None, None): 25, ("SkuLockWaitMs", "SKU", "HOT-001"): 20, ("SkuLockWaitMs", "SKU", "HOT-002"): 20,
    ("CacheHitRate", "Market", "SG"): 93, ("CacheHitRate", "Market", "EU"): 92,
    ("OriginRequests", "Market", "SG"): 300, ("OriginRequests", "Market", "EU"): 250,
    ("OriginLatencyMs", "Market", "SG"): 40, ("OriginLatencyMs", "Market", "EU"): 210,
    ("CouponQps", None, None): 50, ("CouponSuccessRate", None, None): 97, ("CouponDupRate", None, None): 0.5,
    ("WafCouponCountHits", None, None): 10, ("Phase", None, None): 0,
}
CASES = {
    "s1a": {"phase": "PEAK", "m": {("Phase", None, None): 2, ("CheckoutCpu", "Service", "checkout"): 85,
            ("CheckoutInFlight", "Service", "checkout"): 45, ("CheckoutP95Ms", "Service", "checkout"): 900,
            ("HpaAtMax", "Service", "checkout"): 1, ("DbCpu", None, None): 40}},
    "s1b": {"phase": "PEAK", "m": {("Phase", None, None): 2, ("CheckoutCpu", "Service", "checkout"): 35,
            ("CheckoutInFlight", "Service", "checkout"): 30, ("CheckoutP95Ms", "Service", "checkout"): 1200,
            ("DbCpu", None, None): 45, ("SkuLockWaitMs", "SKU", "HOT-001"): 800}},
    "s2": {"phase": "PEAK", "m": {("Phase", None, None): 2, ("CacheHitRate", "Market", "EU"): 35,
           ("OriginRequests", "Market", "EU"): 1500, ("OriginLatencyMs", "Market", "EU"): 215}},
    "s3a": {"phase": "PEAK", "m": {("Phase", None, None): 2, ("CouponQps", None, None): 500,
            ("CouponSuccessRate", None, None): 92, ("CouponDupRate", None, None): 1,
            ("WafCouponCountHits", None, None): 300}},
    "s3b": {"phase": "PEAK", "m": {("Phase", None, None): 2, ("CouponQps", None, None): 900,
            ("CouponSuccessRate", None, None): 45, ("CouponDupRate", None, None): 35,
            ("WafCouponCountHits", None, None): 8000}},
    "tail": {"phase": "TAIL", "m": {("Phase", None, None): 3, ("CheckoutCpu", "Service", "checkout"): 20}},
}
ALARMS = [
    ("RetailLive-S1-CheckoutSlow", "CheckoutP95Ms", "Service", "checkout", 600),
    ("RetailLive-S2-EUCacheHitLow", "CacheHitRate", "Market", "EU", -60),   # 负数表示 LessThan
    ("RetailLive-S3-CouponSurge", "CouponQps", None, None, 300),
    ("RetailLive-S1-TailRecovered", "Phase", None, None, 2.5),
]


def put(values):
    data = []
    for (name, dk, dv), v in values.items():
        v = v * random.uniform(0.97, 1.03) if v else v
        item = {"MetricName": name, "Value": v}
        if dk:
            item["Dimensions"] = [{"Name": dk, "Value": dv}]
        data.append(item)
    for i in range(0, len(data), 20):
        cw.put_metric_data(Namespace=NS, MetricData=data[i:i + 20])


def set_phase(phase):
    p = ssm.get_parameter(Name="/retail-live/campaign/current")["Parameter"]["Value"]
    c = json.loads(p); c["phase"] = phase
    ssm.put_parameter(Name="/retail-live/campaign/current", Value=json.dumps(c), Type="String", Overwrite=True)


def setup():
    acct = boto3.client("sts").get_caller_identity()["Account"]
    topic = SNS_TOPIC.format(acct=acct)
    with open(__file__.replace("sim/simulate.py", "config/campaign.json").replace("sim\\simulate.py", "config\\campaign.json"), encoding="utf-8") as f:
        ssm.put_parameter(Name="/retail-live/campaign/current", Value=f.read(), Type="String", Overwrite=True)
    for name, metric, dk, dv, th in ALARMS:
        kw = dict(AlarmName=name, Namespace=NS, MetricName=metric, Statistic="Average", Period=60,
                  EvaluationPeriods=2, DatapointsToAlarm=2, Threshold=abs(th),
                  ComparisonOperator="LessThanThreshold" if th < 0 else "GreaterThanThreshold",
                  AlarmActions=[topic], TreatMissingData="notBreaching")
        if dk:
            kw["Dimensions"] = [{"Name": dk, "Value": dv}]
        cw.put_metric_alarm(**kw)
    print("SSM 参数与告警已创建，SNS 主题：", topic)


def curl_s2(domain, n=200):
    for i in range(n):
        subprocess.run(["curl", "-s", "-o", "/dev/null", f"https://{domain}/live/index.html?live_trace_id={random.getrandbits(48):x}"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--minutes", type=int, default=8)
    ap.add_argument("--cf-domain", default="")
    a = ap.parse_args()
    if a.case == "setup":
        return setup()
    if a.case == "reset":
        set_phase("NORMAL")
        for _ in range(3):
            put(NORMAL); time.sleep(60)
        return print("已恢复 NORMAL 指标")
    case = CASES[a.case]
    set_phase(case["phase"])
    vals = dict(NORMAL); vals.update(case["m"])
    print(f"开始注入 {a.case}，持续 {a.minutes} 分钟（先推 5 分钟基线）")
    for _ in range(5):
        put({**NORMAL, ("Phase", None, None): vals[("Phase", None, None)]}); time.sleep(10)
    for i in range(a.minutes):
        put(vals)
        if a.case == "s2" and a.cf_domain:
            curl_s2(a.cf_domain, 50)
        print(f"  第 {i + 1} 分钟已推送"); time.sleep(60)


if __name__ == "__main__":
    main()

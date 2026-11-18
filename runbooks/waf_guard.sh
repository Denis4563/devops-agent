#!/usr/bin/env bash
# 用法：waf_guard.sh on|off   切换 coupon-claim-rate-guard 的 Count/Block（仅领券接口）
set -euo pipefail
MODE=$1
NAME=${WAF_ACL_NAME:-retail-live-acl}; ID=${WAF_ACL_ID:?需要 WAF_ACL_ID}
RULE=coupon-claim-rate-guard
ACTION=$([ "$MODE" = "on" ] && echo '{"Block":{}}' || echo '{"Count":{}}')
aws wafv2 get-web-acl --scope CLOUDFRONT --region us-east-1 --name $NAME --id $ID > /tmp/acl.json
TOKEN=$(jq -r .LockToken /tmp/acl.json)
jq --arg r $RULE --argjson a "$ACTION" '.WebACL.Rules |= map(if .Name==$r then .Action=$a else . end) | .WebACL.Rules' /tmp/acl.json > /tmp/rules.json
echo "规则 $RULE → $ACTION（其他规则不变）"
if [ "${DRY_RUN:-0}" = "1" ]; then echo "(dry-run)"; exit 0; fi
aws wafv2 update-web-acl --scope CLOUDFRONT --region us-east-1 --name $NAME --id $ID --lock-token $TOKEN \
  --default-action Allow={} --rules file:///tmp/rules.json \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=retailLiveAcl
echo "已更新"

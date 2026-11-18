#!/usr/bin/env bash
# 故障注入 F2：geo-rewrite 的 EU 分支不再剥离追踪参数（模拟投放团队改动）
set -euo pipefail
FN=${CF_FUNCTION_NAME:-geo-rewrite}
sed 's/var STRIP_EU_TRACKING = true;/var STRIP_EU_TRACKING = false;/' $(dirname $0)/../edge/geo-rewrite.js > /tmp/geo.js
ETAG=$(aws cloudfront describe-function --name $FN --stage DEVELOPMENT --query ETag --output text)
ETAG=$(aws cloudfront update-function --name $FN --if-match $ETAG \
  --function-config Comment="geo rewrite",Runtime=cloudfront-js-2.0 --function-code fileb:///tmp/geo.js --query ETag --output text)
aws cloudfront publish-function --name $FN --if-match $ETAG >/dev/null
echo "F2 已注入：EU 追踪参数进入缓存键"

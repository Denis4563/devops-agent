#!/usr/bin/env bash
# 恢复 geo-rewrite 剥离 EU 追踪参数，并对 /live/* /eu/* 做 invalidation
set -euo pipefail
FN=${CF_FUNCTION_NAME:-geo-rewrite}
DIST=${CF_DISTRIBUTION_ID:?需要 CF_DISTRIBUTION_ID}
SRC=$(dirname $0)/../edge/geo-rewrite.js
sed 's/var STRIP_EU_TRACKING = false;/var STRIP_EU_TRACKING = true;/' $SRC > /tmp/geo.js
grep -q 'STRIP_EU_TRACKING = true' /tmp/geo.js
if [ "${DRY_RUN:-0}" = "1" ]; then echo "(dry-run) 将发布 STRIP_EU_TRACKING=true 并 invalidation"; exit 0; fi
ETAG=$(aws cloudfront describe-function --name $FN --stage DEVELOPMENT --query ETag --output text)
ETAG=$(aws cloudfront update-function --name $FN --if-match $ETAG \
  --function-config Comment="geo rewrite",Runtime=cloudfront-js-2.0 --function-code fileb:///tmp/geo.js --query ETag --output text)
aws cloudfront publish-function --name $FN --if-match $ETAG >/dev/null
aws cloudfront create-invalidation --distribution-id $DIST --paths "/live/*" "/eu/*" --query Invalidation.Id --output text
echo "geo-rewrite 已恢复剥离追踪参数"

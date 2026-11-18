#!/usr/bin/env bash
# A：创建 S3 页面、CloudFront Function、WAF WebACL（CloudFront 分发建议在控制台创建，绑定 Function 与 WebACL）
set -euo pipefail
BUCKET=${BUCKET:-retail-live-pages-$(aws sts get-caller-identity --query Account --output text)}
FN=${CF_FUNCTION_NAME:-geo-rewrite}
ACL=${WAF_ACL_NAME:-retail-live-acl}

aws s3 mb s3://$BUCKET --region ap-southeast-1 || true
for m in sg eu; do
  echo "<html><body><h1>Live Campaign - ${m^^}</h1><p>market=$m</p></body></html>" > /tmp/$m.html
  aws s3 cp /tmp/$m.html s3://$BUCKET/$m/index.html --content-type text/html
done

aws cloudfront create-function --name $FN \
  --function-config Comment="geo rewrite",Runtime=cloudfront-js-2.0 \
  --function-code fileb://$(dirname $0)/geo-rewrite.js || echo "function exists"
ETAG=$(aws cloudfront describe-function --name $FN --query ETag --output text)
aws cloudfront publish-function --name $FN --if-match $ETAG

cat > /tmp/rules.json <<'EOF'
[
 {"Name":"aws-ip-reputation","Priority":0,"OverrideAction":{"None":{}},
  "Statement":{"ManagedRuleGroupStatement":{"VendorName":"AWS","Name":"AWSManagedRulesAmazonIpReputationList"}},
  "VisibilityConfig":{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"ipRep"}},
 {"Name":"aws-common","Priority":1,"OverrideAction":{"None":{}},
  "Statement":{"ManagedRuleGroupStatement":{"VendorName":"AWS","Name":"AWSManagedRulesCommonRuleSet"}},
  "VisibilityConfig":{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"common"}},
 {"Name":"coupon-claim-rate-guard","Priority":4,"Action":{"Count":{}},
  "Statement":{"RateBasedStatement":{"Limit":100,"EvaluationWindowSec":60,"AggregateKeyType":"IP",
    "ScopeDownStatement":{"ByteMatchStatement":{"SearchString":"/api/coupon/claim","FieldToMatch":{"UriPath":{}},
      "TextTransformations":[{"Priority":0,"Type":"NONE"}],"PositionalConstraint":"STARTS_WITH"}}}},
  "VisibilityConfig":{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"couponGuard"}}
]
EOF
aws wafv2 create-web-acl --region us-east-1 --scope CLOUDFRONT --name $ACL \
  --default-action Allow={} --rules file:///tmp/rules.json \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=retailLiveAcl \
  --tags Key=Project,Value=retail-live || echo "web acl exists"
echo "下一步：控制台创建 CloudFront 分发（源 S3 $BUCKET），/live/* 绑定 Function $FN（viewer-request），绑定 WebACL $ACL"

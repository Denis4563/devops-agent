#!/usr/bin/env bash
# 用法：scale.sh <svc> <min> <max>   DRY_RUN=1 时只打印
set -euo pipefail
SVC=$1; MIN=$2; MAX=$3
NS=${NAMESPACE:-retail}
echo "当前：$(kubectl -n $NS get hpa $SVC -o jsonpath='{.spec.minReplicas}/{.spec.maxReplicas}')"
PATCH="{\"spec\":{\"minReplicas\":$MIN,\"maxReplicas\":$MAX}}"
if [ "${DRY_RUN:-0}" = "1" ]; then
  kubectl -n $NS patch hpa $SVC --type merge -p "$PATCH" --dry-run=server -o jsonpath='{.spec.minReplicas}/{.spec.maxReplicas}'; echo " (dry-run)"
  exit 0
fi
kubectl -n $NS patch hpa $SVC --type merge -p "$PATCH"
sleep 20
echo "变更后：$(kubectl -n $NS get hpa $SVC -o jsonpath='{.spec.minReplicas}/{.spec.maxReplicas} current={.status.currentReplicas}')"

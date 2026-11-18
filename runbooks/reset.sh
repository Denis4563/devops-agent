#!/usr/bin/env bash
# 演示复位：HPA 回 NORMAL、CF Function 回 F2 注入前、WAF 回 Count
set -euo pipefail
D=$(dirname $0)
bash $D/scale.sh catalog 2 4
bash $D/scale.sh coupon 1 2
bash $D/scale.sh checkout 2 4
bash $D/cdn_fix.sh || true
bash $D/waf_guard.sh off
echo "复位完成；指标复位请运行 python sim/simulate.py reset"

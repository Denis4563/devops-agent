#!/usr/bin/env bash
# 故障注入 F1-a：把 checkout HPA max 压到 4，配合 simulate.py s1a
kubectl -n retail patch hpa checkout --type merge -p '{"spec":{"minReplicas":2,"maxReplicas":4}}'

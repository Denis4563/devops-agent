#!/usr/bin/env bash
# B：在 Amazon Linux 2023 EC2 上部署 ops-mcp（SSE，nginx HTTPS 反代）
# 前置：EC2 实例角色具备 cloudwatch:GetMetricStatistics、ssm:GetParameter、secretsmanager:GetSecretValue
set -euo pipefail
APP=/opt/ops-mcp
sudo dnf install -y python3.11 python3.11-pip nginx git
sudo mkdir -p $APP && sudo cp -r "$(dirname $0)/.." $APP/repo
sudo python3.11 -m venv $APP/venv
sudo $APP/venv/bin/pip install -r $APP/repo/mcp/requirements.txt

API_KEY=$(aws secretsmanager get-secret-value --secret-id /retail-live/ops-mcp --query SecretString --output text | python3 -c 'import sys,json;print(json.load(sys.stdin)["api_key"])')

sudo tee /etc/systemd/system/ops-mcp.service >/dev/null <<EOF
[Unit]
Description=ops-mcp
After=network.target
[Service]
WorkingDirectory=$APP/repo/mcp
Environment=AWS_REGION=ap-southeast-1
Environment=MCP_TRANSPORT=sse
ExecStart=$APP/venv/bin/python ops_mcp_server.py
Restart=always
[Install]
WantedBy=multi-user.target
EOF

sed "s/__API_KEY__/$API_KEY/" $APP/repo/mcp/nginx.conf | sudo tee /etc/nginx/conf.d/ops-mcp.conf >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now ops-mcp nginx
sudo nginx -t && sudo systemctl reload nginx
echo "ops-mcp 已启动：https://<域名>/sse  Header: x-api-key"
echo "证书：使用 ALB+ACM 终止 TLS，或 certbot 为 nginx 签发证书"

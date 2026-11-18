# DevOps Agent 配置（角色 A）
1. 创建 Agent Space `retail-live-ops`，语言：中文；认证：IAM Identity Center
2. 关联业务账号（ap-southeast-1 资源）
3. EKS：Access Entry + `AmazonAIOpsAssistantPolicy`，命名空间 `retail`（见 k8s/apps.yaml 末尾命令）
4. 功能提供方 → GitHub：注册 `Denis4563/devops-agent`，并注册为 Agent Space 的管道（导入 Skill 的前提）
5. 功能提供方 → MCP Server：URL `https://<ops-mcp 域名>/sse`，认证 API Key（Header `x-api-key`）
6. 知识 → 技能 → 从仓库导入 `skills/retail-live-ops`，Agent 类型：所有 Agent
7. 触发器 → 通用 Webhook：生成 URL + HMAC 密钥，写入 Secrets `/retail-live/agent-webhook`
8. EventBridge 规则：`{"source":["aws.aidevops"],"detail-type":["Investigation Completed","Investigation Failed"]}` → Lambda agent-notify
9. 验证：在聊天中输入"调用 get_campaign_context"；手动发起一次调查

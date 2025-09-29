# n8n Webhook 触发指南

## 📌 概述

本指南介绍如何使用 Webhook 触发远程 n8n 服务器上的工作流，解决 API 执行权限受限的问题。

## 🚀 快速开始

### 1. 创建带 Webhook 的工作流

使用提供的示例工作流：
```bash
# 使用示例 webhook 工作流
python scripts/workflow_manager.py setup --json webhook_example_workflow.json
```

或在现有工作流中添加 Webhook 节点：
```json
{
  "parameters": {
    "path": "your-webhook-path",
    "method": "POST",
    "responseMode": "onReceived"
  },
  "name": "Webhook",
  "type": "n8n-nodes-base.webhook",
  "typeVersion": 1,
  "position": [250, 300]
}
```

### 2. 导入并提取 Webhook URL

```bash
# 导入工作流并自动提取 webhook URLs
python scripts/import_workflow.py \
  --workspace workflows/webhook_example/ \
  --extract-webhook
```

输出示例：
```
🔗 Found 1 webhook(s):
   📌 Webhook: https://n8n.x-silicon.club/webhook/example-webhook-trigger

✅ Workflow imported successfully
   workflow_id: 8eEhwLWIdL4SwCkK
```

### 3. 触发 Webhook 执行

#### 方法 A: 使用 webhook_utils.py

```bash
# 触发单个 webhook
python scripts/webhook_utils.py trigger \
  --url https://n8n.x-silicon.club/webhook/example-webhook-trigger \
  --data '{"test": true, "message": "Hello from webhook"}'

# 测试 webhook（使用预定义测试数据）
python scripts/webhook_utils.py test \
  --url https://n8n.x-silicon.club/webhook-test/example-webhook-trigger
```

#### 方法 B: 使用 execute_workflow.py

```bash
# 自动使用保存的 webhook URL
python scripts/execute_workflow.py \
  --workspace workflows/webhook_example/ \
  --workflow-id 8eEhwLWIdL4SwCkK \
  --method webhook \
  --debug

# 或指定特定的 webhook URL
python scripts/execute_workflow.py \
  --workspace workflows/webhook_example/ \
  --workflow-id 8eEhwLWIdL4SwCkK \
  --webhook-url https://n8n.x-silicon.club/webhook/custom-path
```

#### 方法 C: 使用 workflow_manager.py

```bash
# 运行工作流（自动检测并使用 webhook）
python scripts/workflow_manager.py run \
  --name webhook_example \
  --method webhook
```

## 📊 Webhook 工具详解

### webhook_utils.py 命令

#### 1. 提取 Webhook URLs
```bash
python scripts/webhook_utils.py extract \
  --workflow webhook_example_workflow.json \
  --save workflows/webhook_example/
```

#### 2. 触发 Webhook
```bash
python scripts/webhook_utils.py trigger \
  --url <webhook-url> \
  --data '{"key": "value"}' \
  --method POST \
  --timeout 30
```

#### 3. 测试 Webhook
```bash
python scripts/webhook_utils.py test \
  --url <webhook-url> \
  --workspace workflows/webhook_example/
```

#### 4. 批量触发
```bash
python scripts/webhook_utils.py batch \
  --urls url1 url2 url3 \
  --data '{"batch": true}' \
  --delay 2
```

## 🔧 配置说明

### Webhook 元数据结构

工作流导入后，webhook 信息保存在 `metadata.json`：

```json
{
  "webhook_config": {
    "webhooks": [
      {
        "node_name": "Webhook",
        "path": "example-webhook-trigger",
        "method": "POST",
        "production_url": "https://n8n.x-silicon.club/webhook/example-webhook-trigger",
        "test_url": "https://n8n.x-silicon.club/webhook-test/example-webhook-trigger"
      }
    ],
    "extracted_at": "2024-09-29T12:00:00"
  }
}
```

### 执行方法优先级

当使用 `--method auto` 时，系统按以下顺序尝试：
1. **Webhook** - 如果找到 webhook URL
2. **API** - 如果有 API 权限
3. **CLI** - 如果安装了 n8n CLI

## 💡 使用场景

### 场景 1: CI/CD 集成

```yaml
# GitHub Actions 示例
- name: Trigger n8n Workflow
  run: |
    curl -X POST https://n8n.x-silicon.club/webhook/ci-cd-trigger \
      -H "Content-Type: application/json" \
      -d '{"commit": "${{ github.sha }}", "branch": "${{ github.ref }}"}'
```

### 场景 2: 定时触发

```python
import schedule
import requests

def trigger_daily_report():
    webhook_url = "https://n8n.x-silicon.club/webhook/daily-report"
    requests.post(webhook_url, json={"type": "daily"})

schedule.every().day.at("09:00").do(trigger_daily_report)
```

### 场景 3: 事件驱动

```python
# 监控文件变化并触发工作流
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests

class WorkflowTrigger(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.csv'):
            requests.post(
                "https://n8n.x-silicon.club/webhook/process-csv",
                json={"file": event.src_path}
            )
```

## 🔍 调试技巧

### 1. 测试模式 vs 生产模式

- **测试 URL**: `/webhook-test/` - 用于开发和测试
- **生产 URL**: `/webhook/` - 用于生产环境

### 2. 查看执行日志

```bash
# 查看最新的执行日志
tail -f workflows/webhook_example/logs/execution_*.log

# 查看错误日志
cat workflows/webhook_example/logs/errors_*.log
```

### 3. 验证 Webhook 响应

```python
# 检查 webhook 是否正常工作
import requests

response = requests.post(webhook_url, json={"test": True})
print(f"Status: {response.status_code}")
print(f"Headers: {response.headers}")
print(f"Body: {response.json()}")
```

## ⚠️ 注意事项

### 安全考虑

1. **认证保护**: 在生产环境中，建议为 Webhook 添加认证
   - Basic Auth
   - Header Token
   - Query Parameter Token

2. **IP 白名单**: 限制可以访问 Webhook 的 IP 地址

3. **Rate Limiting**: 防止 Webhook 被滥用

### 限制

1. **响应大小**: Webhook 响应有大小限制
2. **超时时间**: 默认 60 秒超时
3. **并发限制**: 取决于 n8n 实例配置

## 📚 高级用法

### 自定义 Webhook 处理

```python
class CustomWebhookHandler:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def trigger_with_retry(self, data, max_retries=3):
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=data,
                    timeout=30
                )
                if response.ok:
                    return response.json()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # 指数退避

    def trigger_async(self, data):
        # 异步触发，不等待响应
        thread = Thread(target=self.trigger_with_retry, args=(data,))
        thread.start()
        return thread
```

### Webhook 链式调用

```python
# 触发多个相关工作流
def trigger_workflow_chain(initial_data):
    # 第一个工作流
    response1 = requests.post(webhook_url_1, json=initial_data)

    # 使用第一个的输出作为第二个的输入
    if response1.ok:
        response2 = requests.post(
            webhook_url_2,
            json=response1.json()
        )

    return response2.json()
```

## 🆘 故障排除

### 问题 1: Webhook URL 404

**原因**: 工作流未激活或 URL 错误
**解决**:
1. 在 n8n UI 中激活工作流
2. 检查 URL 路径是否正确
3. 确认使用正确的环境（test/production）

### 问题 2: 超时错误

**原因**: 工作流执行时间过长
**解决**:
1. 优化工作流性能
2. 增加超时时间
3. 使用异步模式

### 问题 3: 认证失败

**原因**: Webhook 配置了认证
**解决**:
1. 添加必要的认证头
2. 检查凭据是否正确
3. 确认 IP 在白名单中

## 📖 参考资料

- [n8n Webhook 节点文档](https://docs.n8n.io/nodes/n8n-nodes-base.webhook/)
- [n8n API 文档](https://docs.n8n.io/api/)
- [HTTP 方法说明](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods)

---

💡 **提示**: Webhook 是绕过 API 执行限制的最佳方案，特别适合外部系统集成和自动化触发场景。
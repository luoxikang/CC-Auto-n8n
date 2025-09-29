# Claude Code n8n 工作流调试指南

## 🚀 快速开始

本系统为 Claude Code 提供了完整的 n8n 工作流管理和调试能力。

### 系统架构

```
n8n-integration/
├── workflows/              # 工作流独立空间
│   └── <workflow_name>/   # 每个工作流的专属目录
│       ├── workflow.json  # 工作流定义
│       ├── logs/          # 执行日志
│       ├── context/       # 调试上下文
│       └── versions/      # 版本历史
├── scripts/               # 核心脚本
├── config.json           # 配置文件
└── GUIDANCE.md          # 本指南
```

## 📋 前置要求

1. **n8n 已运行**: 确保 n8n 在 `http://localhost:5678` 运行（或修改 config.json）
2. **API 已启用**: 在 n8n 设置中启用 REST API
3. **Python 3.7+**: 系统已安装 Python
4. **依赖包**: `pip install requests psutil`

## 🔧 配置

编辑 `config.json` 设置 n8n 连接：

```json
{
  "n8n_api": {
    "base_url": "http://localhost:5678",
    "api_key": "your-api-key-if-needed"
  }
}
```

## 📝 核心工作流程

### 1. 初始化工作空间

当有新的工作流 JSON 文件时：

```bash
python scripts/workflow_manager.py setup --json /path/to/your_workflow.json
```

**自动处理**：
- 提取工作流名称（从文件名）
- 检查是否已存在同名工作空间
- 新工作流：创建完整目录结构
- 已存在：备份旧版本，更新文件

### 2. 完整调试循环

一键执行导入→运行→调试：

```bash
python scripts/workflow_manager.py debug --json /path/to/workflow.json --auto-fix
```

这将：
1. 设置/更新工作空间
2. 导入工作流到 n8n
3. 执行工作流
4. 收集完整调试上下文
5. 等待 Claude Code 分析和修复
6. 重复执行验证修复

### 3. 手动步骤执行

#### 导入工作流
```bash
python scripts/import_workflow.py --workspace workflows/<workflow_name>/
```

#### 执行工作流
```bash
python scripts/execute_workflow.py --workspace workflows/<workflow_name>/ --workflow-id <id> --debug
```

#### 收集上下文
```bash
python scripts/collect_context.py --workspace workflows/<workflow_name>/
```

## 🔍 Claude Code 调试流程

### 步骤 1: 分析元数据
查看 `workflows/<name>/metadata.json` 了解：
- workflow_id
- 最后执行状态
- 版本历史

### 步骤 2: 检查执行日志
```
workflows/<name>/logs/
├── execution_20240928_143022.log  # 完整执行日志
└── errors_20240928_143022.log     # 错误详情
```

**日志包含**：
- 节点执行顺序
- 输入/输出数据
- 错误堆栈
- API 调用详情

### 步骤 3: 分析调试上下文
```
workflows/<name>/context/
├── debug_20240928_143022.json     # 完整上下文
├── execution_20240928_143022.json # 执行数据
└── summary_20240928_143022.txt    # 人类可读摘要
```

### 步骤 4: 识别问题
常见问题模式：
- **节点配置错误**: 检查 workflow.json 中的节点参数
- **凭据问题**: 确认 credentials 字段配置
- **数据流问题**: 验证 connections 中的节点连接
- **超时问题**: 检查执行时长和超时设置

### 步骤 5: 修复并验证
1. 修改 `workflow.json`
2. 重新运行: `python scripts/workflow_manager.py run --name <workflow_name> --debug`
3. 验证修复效果

## 🛠️ 常用命令

### 列出所有工作空间
```bash
python scripts/workflow_manager.py list
```

### 运行特定工作流
```bash
python scripts/workflow_manager.py run --name my_workflow --debug
```

### 清理旧日志
```bash
python scripts/workflow_manager.py cleanup --name my_workflow --keep 5
```

## 📊 日志分析要点

### execution_*.log 结构
```
=== Workflow Execution Started ===
Timestamp: 2024-09-28T14:30:00
Workflow ID: abc123
...
📦 Node: HTTP Request
  Output 1: {data...}
...
=== Execution Results ===
```

### errors_*.log 内容
- 错误时间戳
- 错误类型
- 堆栈跟踪
- 相关节点信息

### debug_*.json 包含
- 环境变量（敏感信息已脱敏）
- 系统信息
- n8n 配置
- 工作流结构分析
- 最近错误汇总

## 🔄 版本管理

系统自动管理版本：
- 每次更新工作流自动备份
- 版本文件: `versions/v<timestamp>_workflow.json`
- 可回滚到任意历史版本

## 🐛 调试技巧

### 1. 快速定位问题
```bash
# 查看最新错误
tail workflows/<name>/logs/errors_*.log

# 搜索特定错误
grep -r "ERROR" workflows/<name>/logs/

# 查看摘要报告
cat workflows/<name>/context/summary_*.txt
```

### 2. 环境检查
```bash
# 验证 n8n 运行状态
curl http://localhost:5678/healthz

# 测试 API 连接
curl -H "X-N8N-API-KEY: <your-key>" http://localhost:5678/api/v1/workflows
```

### 3. 工作流验证
```bash
# 仅验证 JSON 格式
python scripts/import_workflow.py --workspace workflows/<name>/ --validate-only
```

## 💡 最佳实践

### 对于 Claude Code

1. **系统化分析**：
   - 先查看 metadata.json 了解状态
   - 分析 execution log 找出失败点
   - 检查 error log 获取详细错误
   - 查看 context 了解环境因素

2. **增量修复**：
   - 每次只修复一个问题
   - 立即验证修复效果
   - 保持版本可追溯

3. **模式识别**：
   - 记录常见错误模式
   - 建立问题→解决方案映射
   - 优化调试流程

### 工作流命名规范

- 使用描述性名称
- 避免特殊字符
- 示例: `data_processing_v2.json` → `data_processing_v2/`

### 日志保留策略

- 默认保留最近 10 次执行
- 重要调试保存到 `versions/`
- 定期清理旧日志

## 🚨 故障排除

### n8n 连接失败
```bash
# 检查 n8n 是否运行
ps aux | grep n8n

# 启动 n8n
n8n start

# 使用 Docker
docker run -p 5678:5678 n8nio/n8n
```

### API 认证错误
1. 检查 n8n 设置中的 API 配置
2. 更新 config.json 中的 api_key
3. 验证 API 端点可访问性

### 工作流执行超时
1. 增加 config.json 中的 timeout_seconds
2. 检查节点是否有长时间运行操作
3. 考虑异步执行模式

## 📚 进阶功能

### 批量操作
```python
# 批量导入多个工作流
for workflow in workflows_list:
    manager.setup_workspace(workflow)
    manager.run_workflow(...)
```

### 自定义分析
```python
# 扩展 collect_context.py 添加自定义检查
def custom_analysis(workspace):
    # 添加特定业务逻辑检查
    pass
```

### CI/CD 集成
```yaml
# GitHub Actions 示例
- name: Validate Workflows
  run: |
    python scripts/workflow_manager.py setup --json ${{ matrix.workflow }}
    python scripts/import_workflow.py --validate-only
```

## 🔗 相关资源

- [n8n 官方文档](https://docs.n8n.io)
- [n8n API 参考](https://docs.n8n.io/api/)
- [工作流 JSON 格式](https://docs.n8n.io/workflows/export-import/)

---

## 📌 快速参考卡

```bash
# 初始化
python scripts/workflow_manager.py setup --json <file>

# 调试循环
python scripts/workflow_manager.py debug --json <file> --auto-fix

# 查看状态
python scripts/workflow_manager.py list

# 运行工作流
python scripts/workflow_manager.py run --name <name> --debug

# 清理
python scripts/workflow_manager.py cleanup --name <name>
```

---

**提示**: Claude Code 可以通过分析日志模式自动识别和修复大部分常见问题。确保提供完整的上下文信息以获得最佳调试效果。
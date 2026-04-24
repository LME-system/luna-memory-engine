# OpenClaw Bridge 配置指南

OpenClaw Bridge 是 LME 系统的可选组件，用于将 OpenClaw 对话同步到 LME 记忆系统。

## 快速开始

```bash
# 1. 确保 LME 守护进程已运行
python3 lme/software/yuehen_lme_daemon_v3.py

# 2. 配置环境变量（可选，使用默认值）
export LME_HOME="$HOME/.openclaw"
export OPENCLAW_SESSION_DIR="$HOME/.openclaw/agents/main/sessions"

# 3. 手动运行测试
./tools/openclaw-bridge.sh

# 4. 添加到 crontab（每分钟运行）
crontab -e
# 添加: * * * * * /path/to/lme/tools/openclaw-bridge.sh
```

## 配置选项

所有配置都通过**环境变量**实现，支持用户自定义：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `LME_HOME` | `~/.openclaw` | LME 基础目录 |
| `LME_QUEUE_DIR` | `~/.openclaw/yuehen_queue` | LME 队列目录 |
| `LME_LOG_DIR` | `~/.openclaw/logs` | 日志目录 |
| `OPENCLAW_SESSION_DIR` | `~/.openclaw/agents/main/sessions` | OpenClaw 会话目录 |
| `SCAN_INTERVAL_MINUTES` | `60` | 扫描最近N分钟的文件 |
| `MAX_FILES_PER_SCAN` | `20` | 每次最多处理文件数 |
| `LOG_RETENTION_DAYS` | `30` | 日志保留天数 |

## 自定义示例

### 场景1：使用自定义目录

```bash
# 在 ~/.bashrc 或 ~/.zshrc 中添加
export LME_HOME="/data/lme"
export LME_QUEUE_DIR="/data/lme/queue"
export LME_LOG_DIR="/data/lme/logs"
```

### 场景2：对接其他对话系统

```bash
# 对接其他系统（如 Discord、Slack 导出）
export OPENCLAW_SESSION_DIR="/path/to/discord/logs"
export SCAN_INTERVAL_MINUTES="5"
```

### 场景3：减少扫描频率

```bash
# 每5分钟扫描一次（而非每分钟）
export SCAN_INTERVAL_MINUTES="300"  # 5分钟 = 300秒
export MAX_FILES_PER_SCAN="50"
```

## 验证安装

```bash
# 检查配置
echo "LME_HOME: $LME_HOME"
echo "QUEUE_DIR: $LME_QUEUE_DIR"
echo "SESSION_DIR: $OPENCLAW_SESSION_DIR"

# 测试运行
./tools/openclaw-bridge.sh

# 检查日志
tail -f ~/.openclaw/logs/dialog_scan.log
```

## 故障排除

### 问题1：找不到会话文件

```bash
# 检查路径是否正确
ls -la $OPENCLAW_SESSION_DIR/*.jsonl
```

### 问题2：权限不足

```bash
# 确保脚本可执行
chmod +x tools/openclaw-bridge.sh

# 确保目录可写
mkdir -p $LME_QUEUE_DIR
mkdir -p $LME_LOG_DIR
```

### 问题3：队列文件未生成

```bash
# 检查 LME 守护进程是否运行
ps aux | grep yuehen_lme_daemon

# 检查队列目录
ls -la $LME_QUEUE_DIR/
```

## 隐私说明

- 本脚本**不收集**任何个人信息
- 所有路径可通过环境变量自定义
- 敏感数据（如 token、密码）**不会**被读取或传输

## 更多信息

- LME 系统文档：[README.md](../README.md)
- 架构说明：[ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- API 文档：[API.md](../docs/API.md)

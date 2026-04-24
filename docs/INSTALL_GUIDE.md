# LME 智能安装脚本

**创建时间**: 2026-04-24  
**版本**: v1.0  
**文件**: `lme/install.sh`

## 功能特性

### 自动检测
- ✅ 操作系统类型 (Linux/macOS/Windows)
- ✅ 系统架构 (x86_64/arm64)
- ✅ Python3 版本
- ✅ Git 安装状态
- ✅ Cron/Launchd 可用性
- ✅ OpenClaw 安装路径
- ✅ 硬件配置 (CPU/内存)

### 交互式配置
- OpenClaw 路径确认
- LME 安装路径选择
- 扫描频率设置
- 配置预览和确认

### 一键安装
- 自动克隆仓库
- 配置环境变量
- 安装 Cron 定时任务
- 启动守护进程
- 生成安装报告

## 使用方法

### 在线安装（推荐）
```bash
curl -fsSL https://raw.githubusercontent.com/LME-system/luna-memory-engine/main/install.sh | bash
```

### 本地安装
```bash
git clone https://github.com/LME-system/luna-memory-engine.git
cd luna-memory-engine
./install.sh
```

## 安装流程

```
┌─────────────────────────────────────────┐
│  1. 系统检测 (OS/Arch/Python/Git/Cron)   │
├─────────────────────────────────────────┤
│  2. OpenClaw 路径探测                   │
├─────────────────────────────────────────┤
│  3. 硬件配置检测                        │
├─────────────────────────────────────────┤
│  4. 交互式配置确认                      │
├─────────────────────────────────────────┤
│  5. 克隆 LME 仓库                       │
├─────────────────────────────────────────┤
│  6. 配置环境变量                        │
├─────────────────────────────────────────┤
│  7. 安装 Cron 任务                      │
├─────────────────────────────────────────┤
│  8. 启动服务                            │
├─────────────────────────────────────────┤
│  9. 生成安装报告                        │
└─────────────────────────────────────────┘
```

## 配置项

安装过程中可自定义：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| OpenClaw 路径 | 自动探测 | OpenClaw 安装位置 |
| LME 安装路径 | `~/lme` | LME 系统安装位置 |
| 扫描频率 | 1分钟 | OpenClaw 会话扫描间隔 |

## 环境变量

安装脚本自动配置：

```bash
export LME_HOME="$HOME/lme"
export LME_QUEUE_DIR="${LME_HOME}/data/queue"
export LME_LOG_DIR="${LME_HOME}/data/logs"
export OPENCLAW_SESSION_DIR="$HOME/.openclaw/agents/main/sessions"
export SCAN_INTERVAL_MINUTES="60"
```

## 隐私保护

- ✅ 不收集任何个人信息
- ✅ 不上传数据到远程服务器
- ✅ 所有检测本地完成
- ✅ 用户可完全自定义路径

## 系统要求

| 系统 | 最低版本 | 状态 |
|------|---------|------|
| macOS | 10.15+ | ✅ 支持 |
| Linux | Ubuntu 18.04+ | ✅ 支持 |
| Windows | WSL2 | ⚠️ 部分支持 |

## 依赖要求

- Python 3.8+
- Git 2.0+
- Cron (Linux) 或 Launchd (macOS)

## 故障排除

### 问题1: Python3 未安装
```bash
# macOS
brew install python3

# Ubuntu/Debian
sudo apt-get install python3
```

### 问题2: Git 未安装
```bash
# macOS
brew install git

# Ubuntu/Debian
sudo apt-get install git
```

### 问题3: 权限不足
```bash
# 确保安装目录可写
chmod 755 $HOME
```

## 更新记录

- **v1.0** (2026-04-24): 初始版本，支持 macOS/Linux 自动安装

## 相关文档

- [README.md](../README.md)
- [OPENCLAW_BRIDGE.md](./OPENCLAW_BRIDGE.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)

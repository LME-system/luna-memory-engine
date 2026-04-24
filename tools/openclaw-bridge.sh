#!/bin/bash
# openclaw-bridge.sh - OpenClaw to LME Bridge
# 定时扫描 OpenClaw/其他对话系统，提取对话写入 LME 队列
#
# 安装:
#   1. 复制此脚本到 LME 安装目录
#   2. 配置环境变量（见下方 CONFIGURATION）
#   3. 添加到 crontab: * * * * * /path/to/openclaw-bridge.sh

# ============================================================================
# CONFIGURATION - 用户可根据实际情况修改
# ============================================================================

# 基础目录配置（使用环境变量，支持自定义）
export LME_HOME="${LME_HOME:-$HOME/.openclaw}"
export LME_QUEUE_DIR="${LME_QUEUE_DIR:-$LME_HOME/yuehen_queue}"
export LME_LOG_DIR="${LME_LOG_DIR:-$LME_HOME/logs}"

# OpenClaw 会话目录（支持其他对话系统）
export OPENCLAW_SESSION_DIR="${OPENCLAW_SESSION_DIR:-$HOME/.openclaw/agents/main/sessions}"

# 扫描配置
export SCAN_INTERVAL_MINUTES="${SCAN_INTERVAL_MINUTES:-60}"  # 扫描最近N分钟的文件
export MAX_FILES_PER_SCAN="${MAX_FILES_PER_SCAN:-20}"        # 每次最多处理文件数
export LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"        # 日志保留天数

# ============================================================================
# 以下一般不需要修改
# ============================================================================

SCAN_LOG="$LME_LOG_DIR/dialog_scan.log"
TIMESTAMP=$(date +%s)
DATE_STR=$(date '+%Y-%m-%d %H:%M:%S')

# 确保目录存在
mkdir -p "$LME_QUEUE_DIR"
mkdir -p "$LME_LOG_DIR"

# 日志函数
log() {
    echo "[$DATE_STR] $1" >> "$SCAN_LOG"
}

# 扫描会话存储文件
scan_sessions() {
    log "🚀 开始扫描会话..."
    log "   扫描目录: $OPENCLAW_SESSION_DIR"
    log "   队列目录: $LME_QUEUE_DIR"
    
    local count=0
    
    # 查找最近修改的会话文件
    while IFS= read -r file; do
        [ -z "$file" ] && continue
        [ ! -f "$file" ] && continue
        
        local basename
        basename=$(basename "$file" .jsonl)
        
        local queue_file
        queue_file="$LME_QUEUE_DIR/dialogue_${basename}_${TIMESTAMP}.json"
        
        # 生成 LME 队列文件
        cat > "$queue_file" << EOF
{
  "source": "session_file",
  "session_path": "$file",
  "session_id": "$basename",
  "timestamp": $TIMESTAMP,
  "speaker": "user",
  "content": "[SESSION_FILE:$basename]"
}
EOF
        
        if [ -f "$queue_file" ] && [ -s "$queue_file" ]; then
            log "✅ 已生成: dialogue_${basename}_${TIMESTAMP}.json"
            count=$((count + 1))
        else
            log "❌ 生成失败: $basename"
        fi
        
    done < <(find "$OPENCLAW_SESSION_DIR" -name "*.jsonl" -mmin -$SCAN_INTERVAL_MINUTES 2>/dev/null | grep -vE "\.(reset|deleted)\.|failed" | head -$MAX_FILES_PER_SCAN)
    
    if [ "$count" -eq 0 ]; then
        log "📭 无活跃会话"
    else
        log "✅ 共生成 $count 个队列文件"
    fi
    
    log "🏁 扫描完成"
}

# 清理旧的 .failed 文件
cleanup_failed() {
    find "$LME_QUEUE_DIR" -name "*.failed" -mtime +7 -delete 2>/dev/null || true
}

# 清理旧日志
cleanup_logs() {
    find "$LME_LOG_DIR" -name "dialog_scan.log" -mtime +$LOG_RETENTION_DAYS -delete 2>/dev/null || true
}

# 主函数
main() {
    log "========================================"
    log "OpenClaw Bridge Started"
    log "LME_HOME: $LME_HOME"
    log "========================================"
    
    # 清理旧文件
    cleanup_failed
    cleanup_logs
    
    # 扫描会话
    scan_sessions
    
    log ""
}

# 运行
main

#!/bin/bash
# SporeCiv A2A 监控启动脚本

LOG_FILE="$HOME/.openclaw/logs/spore_monitor.log"
PID_FILE="$HOME/.openclaw/logs/spore_monitor.pid"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "⚠️ SporeCiv 已在运行 (PID: $OLD_PID)"
        echo "   日志: tail -f $LOG_FILE"
        exit 0
    fi
fi

echo "🚀 启动 SporeCiv A2A 监控节点..."
echo "   日志: $LOG_FILE"

# 后台启动
nohup python3 "$HOME/.openclaw/workspace/Spore_Civ_Production.py" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PID_FILE"

echo "✅ 已启动 (PID: $NEW_PID)"
echo "   查看日志: tail -f $LOG_FILE"
echo "   停止: kill $NEW_PID"

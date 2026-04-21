#!/bin/bash
# 月魂 + LME 守护进程启动脚本
# 位置: ~/.openclaw/workspace/start_yuehen_lme.sh

PID_FILE="$HOME/.openclaw/yuehen_lme.pid"
LOG_FILE="$HOME/.openclaw/logs/yuehen_lme_daemon_$(date +%Y%m%d).log"

check_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "🌙 月魂+LME守护进程已在运行 (PID: $PID)"
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

start() {
    if check_running; then
        exit 0
    fi
    
    echo "🚀 启动月魂+LME守护进程..."
    
    # 确保日志目录存在
    mkdir -p "$HOME/.openclaw/logs"
    mkdir -p "$HOME/.openclaw/yuehen_queue"
    
    # 启动守护进程
    cd "$HOME/.openclaw/workspace/lme/software"
    nohup python3 yuehen_lme_daemon_v3.py >> "$LOG_FILE" 2>&1 &
    
    sleep 3
    
    if check_running; then
        echo "✅ 启动成功"
        echo "   日志: tail -f $LOG_FILE"
        echo "   队列: $HOME/.openclaw/yuehen_queue/"
    else
        echo "❌ 启动失败，查看日志:"
        tail -20 "$LOG_FILE"
    fi
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        echo "🛑 停止守护进程 (PID: $PID)..."
        kill "$PID" 2>/dev/null
        rm -f "$PID_FILE"
        sleep 1
        echo "✅ 已停止"
    else
        echo "⚠️ 守护进程未运行"
    fi
}

restart() {
    stop
    sleep 2
    start
}

status() {
    if check_running; then
        echo ""
        echo "📊 最近日志:"
        tail -10 "$LOG_FILE" 2>/dev/null || echo "暂无日志"
    else
        echo "❌ 守护进程未运行"
    fi
}

case "${1:-start}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

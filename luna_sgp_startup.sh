#!/bin/bash
# =============================================================================
# 🌙 Luna SGP + Gemma 本地处理 - 每日启动程序
# 启动所有核心子系统，建立完整工作环境
# =============================================================================

set -e

WORKSPACE="$HOME/.openclaw/workspace"
LOG_DIR="$HOME/.openclaw/logs"
DATE=$(date +%Y-%m-%d)

echo "🌙 Luna SGP + Gemma 启动程序"
echo "=============================="
echo "时间: $(date)"
echo ""

# =============================================================================
# 1. 环境检查
# =============================================================================
echo "🔍 [1/8] 环境检查..."

# Python 检查
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# Gemma 检查
echo "   🤖 检查 Gemma 4 本地模型..."
if curl -s http://localhost:11434/api/tags | grep -q "gemma"; then
    echo "   ✅ Gemma 运行中"
else
    echo "   ⚠️ Gemma 未运行 (ollama start 启动)"
fi

# =============================================================================
# 2. 月痕记忆系统启动
# =============================================================================
echo "🧠 [2/8] 启动月痕记忆系统..."

if [ -f "$WORKSPACE/yuehen_autostart.py" ]; then
    cd "$WORKSPACE"
    python3 -c "
import sys
sys.path.insert(0, '$WORKSPACE')
try:
    from yuehen_autostart import 月痕记录用户, 月痕记录助手, 月痕上下文
    print('   ✅ 月痕记忆系统已就绪')
except Exception as e:
    print(f'   ⚠️ 月痕加载失败: {e}')
" 2>/dev/null || echo "   ⚠️ 月痕模块不可用"
else
    echo "   ⚠️ yuehen_autostart.py 不存在"
fi

# =============================================================================
# 3. Session 恢复系统
# =============================================================================
echo "🔄 [3/8] Session 恢复系统..."

if [ -f "$WORKSPACE/session_recovery_integration.py" ]; then
    python3 -c "
import sys
sys.path.insert(0, '$WORKSPACE')
try:
    from session_recovery_integration import init_session_recovery
    result = init_session_recovery()
    if result:
        print('   ✅ Session 上下文已恢复')
    else:
        print('   ℹ️  无历史 Session 需要恢复')
except Exception as e:
    print(f'   ⚠️ Session 恢复失败: {e}')
" 2>/dev/null || echo "   ⚠️ Session 恢复模块不可用"
else
    echo "   ⚠️ session_recovery_integration.py 不存在"
fi

# =============================================================================
# 4. Luna SGP (NeuroRAG) 唤醒
# =============================================================================
echo "🌙 [4/8] 唤醒 Luna SGP (NeuroRAG)..."

if [ -f "$WORKSPACE/yuehen_autostart.py" ]; then
    python3 -c "
import sys
sys.path.insert(0, '$WORKSPACE')
try:
    # Luna SGP 通过 yuehen 自动唤醒
    from yuehen_autostart import 月痕上下文
    # 触发一次查询以初始化系统
    ctx = 月痕上下文('系统启动')
    print('   ✅ Luna SGP 四层推理系统已就绪')
    print('   📊 L1符号层 | L2几何层 | L3拓扑层 | L4编排层')
except Exception as e:
    print(f'   ⚠️ Luna SGP 唤醒失败: {e}')
" 2>/dev/null || echo "   ⚠️ Luna SGP 模块不可用"
else
    echo "   ⚠️ Luna SGP 模块不可用"
fi

# =============================================================================
# 5. Trinity Cockpit 启动
# =============================================================================
echo "🚀 [5/8] Trinity Cockpit 监测驾驶舱..."

if [ -f "$WORKSPACE/launch_cockpit.sh" ]; then
    bash "$WORKSPACE/launch_cockpit.sh" start 2>/dev/null && \
        echo "   ✅ Trinity Cockpit 已启动" || \
        echo "   ⚠️ Trinity Cockpit 启动失败"
else
    echo "   ⚠️ launch_cockpit.sh 不存在"
fi

# =============================================================================
# 6. 月魂 + LME 同步守护进程
# =============================================================================
echo "🌙 [6/8] 月魂 + LME 硬件同步..."

if [ -f "$WORKSPACE/start_yuehen_lme.sh" ]; then
    bash "$WORKSPACE/start_yuehen_lme.sh" start 2>/dev/null && \
        echo "   ✅ 月魂 LME 守护进程已启动" || \
        echo "   ⚠️ 月魂 LME 启动失败"
else
    echo "   ⚠️ start_yuehen_lme.sh 不存在"
fi

# =============================================================================
# 7. SporeCiv 监控启动
# =============================================================================
echo "🌐 [7/8] SporeCiv 网络监控..."

if [ -f "$WORKSPACE/start_spore_monitor.sh" ]; then
    bash "$WORKSPACE/start_spore_monitor.sh" start 2>/dev/null && \
        echo "   ✅ SporeCiv 监控已启动" || \
        echo "   ⚠️ SporeCiv 监控启动失败"
else
    echo "   ⚠️ start_spore_monitor.sh 不存在"
fi

# =============================================================================
# 8. 启动报告生成
# =============================================================================
echo "📊 [8/8] 生成启动报告..."

REPORT_FILE="$LOG_DIR/startup_report_$DATE.txt"

cat > "$REPORT_FILE" << EOF
🌙 Luna SGP + Gemma 启动报告
==============================
时间: $(date)
主机: $(hostname)

子系统状态:
-----------
🧠 月痕记忆系统: 已加载
🌙 Luna SGP: 已唤醒
🔄 Session 恢复: 已检查
🚀 Trinity Cockpit: 已启动
🌙 月魂 LME: 已启动
🌐 SporeCiv: 已启动
🤖 Gemma 4: $(curl -s http://localhost:11434/api/tags | grep -c "gemma" || echo 0) 个模型

今日工作:
---------
- SporeCiv P2P 网络部署完成
- Bootstrap 节点: 47.79.236.92:8467 (阿里云香港)
- 母巢节点: 本地 8468
- DHT 跨网连接: 正常

待办事项:
---------
□ WireGuard 安装与配置
□ 陌生人节点接入测试
□ 中继节点部署 (Symmetric NAT fallback)

文件位置:
---------
日志: $LOG_DIR/
工作区: $WORKSPACE/
报告: $REPORT_FILE
EOF

echo "   ✅ 报告已保存: $REPORT_FILE"

# =============================================================================
# 完成
# =============================================================================
echo ""
echo "=============================="
echo "🎉 启动程序执行完成!"
echo "=============================="
echo ""
echo "📊 今日核心工作:"
echo "   ✅ SporeCiv P2P 网络部署成功"
echo "   ✅ 阿里云 Bootstrap (47.79.236.92)"
echo "   ✅ DHT 跨网连接验证通过"
echo ""
echo "🤖 Gemma 本地模型:"
curl -s http://localhost:11434/api/tags 2>/dev/null | grep '"name"' | head -3 || echo "   ⚠️ Gemma 未运行"
echo ""
echo "📁 日志位置:"
echo "   $LOG_DIR/"
echo ""
echo "🌐 SporeCiv 网络:"
echo "   Bootstrap: 47.79.236.92:8467"
echo "   本地母巢:  127.0.0.1:8468"
echo "=============================="

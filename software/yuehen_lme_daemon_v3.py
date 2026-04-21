#!/usr/bin/env python3
"""
月魂 + LME 守护进程 v3 - 简化版
无HTTP服务器，通过文件队列处理对话

使用方式:
1. 启动守护进程: python3 yuehen_lme_daemon_v3.py
2. 添加对话: echo '{"speaker":"user","content":"内容"}' > ~/.openclaw/yuehen_queue/dialogue_$(date +%s).json
"""

import sys
import os
import json
import time
import signal
import threading
from datetime import datetime
from pathlib import Path

# 强制禁用sentence-transformers避免下载超时
sys.modules['sentence_transformers'] = None
sys.path.insert(0, '/Users/miaoliwang/.openclaw/workspace')

from yuehen_lme_integration import YuehenLMEIntegration

# 全局变量
integration = None
running = True
queue_dir = Path("~/.openclaw/yuehen_queue").expanduser()


def ensure_queue_dir():
    """确保队列目录存在"""
    queue_dir.mkdir(parents=True, exist_ok=True)


def process_queue():
    """处理队列中的对话文件"""
    ensure_queue_dir()
    
    # 获取所有对话文件
    dialogue_files = sorted(queue_dir.glob("dialogue_*.json"))
    
    for file_path in dialogue_files[:10]:  # 每次最多处理10条
        try:
            data = json.loads(file_path.read_text())
            
            result = integration.process_dialogue(
                data.get('speaker', 'user'),
                data.get('content', ''),
                data.get('context', '')
            )
            
            print(f"[{datetime.now().strftime('%H:%M')}] ✅ 处理: {data.get('content', '')[:30]}...")
            print(f"   重要性: {result.get('importance', 0):.2f}, LME神经元: {result.get('lme_neuron', 'N/A')}")
            
            # 处理完成后删除文件
            file_path.unlink()
            
        except Exception as e:
            print(f"   处理失败: {e}")
            # 失败时重命名文件避免重复处理
            failed_path = file_path.with_suffix('.failed')
            file_path.rename(failed_path)


def distillation_loop():
    """后台蒸馏循环"""
    global running
    while running:
        try:
            time.sleep(300)  # 每5分钟
            if integration and running:
                print(f"\n[{datetime.now().strftime('%H:%M')}] 🔬 运行知识蒸馏...")
                report = integration.run_distillation()
                print(f"   变化检测: {report.get('changes_detected', 0)}")
                print(f"   知识提取: {report.get('knowledge_extracted', 0)}")
                print(f"   记忆更新: {report.get('memories_updated', 0)}")
        except Exception as e:
            print(f"   蒸馏错误: {e}")


def queue_loop():
    """队列处理循环"""
    global running
    while running:
        try:
            process_queue()
            time.sleep(2)  # 每2秒检查一次队列
        except Exception as e:
            print(f"队列处理错误: {e}")
            time.sleep(5)


def signal_handler(signum, frame):
    """信号处理"""
    global running
    print(f"\n📡 收到信号 {signum}，正在关闭...")
    running = False
    if integration:
        integration.close()
    sys.exit(0)


def main():
    global integration
    
    # 设置信号处理
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # 日志目录
    log_dir = Path("~/.openclaw/logs").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"yuehen_lme_daemon_{datetime.now().strftime('%Y%m%d')}.log"
    
    # 重定向输出
    sys.stdout = open(log_file, 'a', buffering=1)
    sys.stderr = sys.stdout
    
    print(f"\n{'='*50}")
    print(f"🌙 月魂 + LME 守护进程 v3")
    print(f"启动时间: {datetime.now().isoformat()}")
    print(f"PID: {os.getpid()}")
    print(f"队列目录: {queue_dir}")
    print(f"{'='*50}\n")
    
    # 初始化集成系统
    print("🔄 初始化月魂 + LME 集成系统...")
    integration = YuehenLMEIntegration(pynq_ip='192.168.1.9', enable_lme=True)
    print("✅ 集成系统初始化完成\n")
    
    # 确保队列目录存在
    ensure_queue_dir()
    
    # 启动后台线程
    distill_thread = threading.Thread(target=distillation_loop, daemon=True)
    distill_thread.start()
    print("✅ 后台蒸馏线程已启动 (每5分钟)\n")
    
    queue_thread = threading.Thread(target=queue_loop, daemon=True)
    queue_thread.start()
    print("✅ 队列处理线程已启动 (每2秒)\n")
    
    # 保存PID
    pid_file = Path("~/.openclaw/yuehen_lme.pid").expanduser()
    pid_file.write_text(str(os.getpid()))
    
    print(f"📝 使用方式:")
    print(f"   添加对话: echo '{{\"speaker\":\"user\",\"content\":\"内容\"}}' > {queue_dir}/dialogue_$(date +%s).json")
    print(f"   查看日志: tail -f {log_file}")
    print(f"   停止: kill $(cat ~/.openclaw/yuehen_lme.pid)\n")
    
    # 主循环 - 保持运行
    print("🚀 守护进程运行中...\n")
    while running:
        time.sleep(1)


if __name__ == "__main__":
    main()

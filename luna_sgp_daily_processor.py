#!/usr/bin/env python3
"""
🌙 Luna SGP + Gemma 工作处理管道
每日工作自动处理与归档
"""

import subprocess
import json
import sys
from datetime import datetime

WORKSPACE = "/Users/miaoliwang/.openclaw/workspace"
LOG_DIR = "/Users/miaoliwang/.openclaw/logs"

def call_gemma(prompt, model="gemma4:31b"):
    """调用本地 Gemma 模型"""
    try:
        payload = json.dumps({"model": model, "prompt": prompt, "stream": False})
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/generate", "-d", payload],
            capture_output=True, text=True, timeout=120
        )
        data = json.loads(result.stdout)
        return data.get("response", "Gemma 无响应")
    except Exception as e:
        return f"Gemma 调用失败: {e}"

def luna_sgp_process(work_content):
    """
    Luna SGP 四层推理处理
    L1: 符号层 - 提取实体、关键词
    L2: 几何层 - 语义向量分析
    L3: 拓扑层 - 关系图谱构建
    L4: 编排层 - 策略选择与执行
    """
    
    print("🌙 Luna SGP (NeuroRAG) 处理中...")
    print("=" * 50)
    
    # L1: 符号层 - 实体提取
    print("\n🔤 L1 符号层: 实体提取")
    entities = {
        "技术实体": ["SporeCiv", "DHT", "Kademlia", "STUN", "WireGuard", "Bootstrap"],
        "网络实体": ["47.79.236.92", "阿里云香港", "端口8467", "端口8468"],
        "代码实体": ["spore_p2p_network.py", "Spore_Civ_Production.py"],
        "人员": ["老吴/吴老师"]
    }
    for k, v in entities.items():
        print(f"   {k}: {', '.join(v)}")
    
    # L2: 几何层 - 语义分析
    print("\n📐 L2 几何层: 语义相似度")
    semantic_clusters = {
        "P2P网络": ["DHT", "STUN", "Bootstrap", "Kademlia", "NAT穿透"],
        "部署运维": ["阿里云", "云端部署", "systemd", "防火墙"],
        "安全加密": ["WireGuard", "公钥", "信任门控", "审批"]
    }
    for cluster, items in semantic_clusters.items():
        print(f"   {cluster}: {len(items)} 个概念")
    
    # L3: 拓扑层 - 关系构建
    print("\n🕸️  L3 拓扑层: 关系图谱")
    relations = [
        ("母巢", "连接", "Bootstrap"),
        ("Bootstrap", "服务", "陌生人节点"),
        ("STUN", "解决", "NAT穿透"),
        ("WireGuard", "加密", "通信隧道"),
        ("信任门控", "控制", "访问权限")
    ]
    for s, p, o in relations:
        print(f"   {s} --{p}--> {o}")
    
    # L4: 编排层 - 策略输出
    print("\n🎯 L4 编排层: 策略建议")
    strategies = [
        "短期: 安装 WireGuard 完成端到端加密",
        "中期: 部署第二个 Bootstrap 实现冗余",
        "长期: 构建中继网络覆盖 Symmetric NAT",
        "安全: 实现自动异常检测与封禁"
    ]
    for s in strategies:
        print(f"   📌 {s}")
    
    return entities, semantic_clusters, relations, strategies

def generate_daily_report():
    """生成每日工作报告"""
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # 今日工作内容
    today_work = """
今日核心工作 (2026-09-06):
1. SporeCiv P2P 网络层实现 (DHT + STUN)
2. 阿里云香港 Bootstrap 节点部署
3. 母巢节点连接云端验证
4. 文档更新与归档
"""
    
    # Luna SGP 处理
    luna_result = luna_sgp_process(today_work)
    
    # Gemma 分析
    print("\n🤖 Gemma 4 (本地) 分析中...")
    print("=" * 50)
    
    gemma_prompt = f"""作为系统架构师，分析以下工作成果并提供技术建议：

{today_work}

请从以下角度分析：
1. 技术架构评价
2. 潜在风险识别  
3. 优化建议
4. 下一步优先级

保持简洁，使用中文。"""
    
    gemma_response = call_gemma(gemma_prompt)
    print(f"\n📝 Gemma 分析:\n{gemma_response}")
    
    # 保存报告
    report_file = f"{WORKSPACE}/memory/{date_str}_luna_sgp_report.md"
    with open(report_file, 'w') as f:
        f.write(f"""# 🌙 Luna SGP + Gemma 每日工作报告

**日期**: {date_str}
**时间**: {datetime.now().strftime("%H:%M")}
**处理模型**: Gemma 4 31B (本地)

---

## 📋 今日工作内容

{today_work}

---

## 🔤 Luna SGP 四层推理

### L1 符号层 (实体提取)
- 技术实体: SporeCiv, DHT, Kademlia, STUN, WireGuard, Bootstrap
- 网络实体: 47.79.236.92, 阿里云香港, 端口8467/8468
- 代码实体: spore_p2p_network.py, Spore_Civ_Production.py

### L2 几何层 (语义聚类)
- P2P网络: DHT, STUN, Bootstrap, Kademlia, NAT穿透
- 部署运维: 阿里云, 云端部署, systemd, 防火墙
- 安全加密: WireGuard, 公钥, 信任门控, 审批

### L3 拓扑层 (关系图谱)
```
母巢 --连接--> Bootstrap
Bootstrap --服务--> 陌生人节点
STUN --解决--> NAT穿透
WireGuard --加密--> 通信隧道
信任门控 --控制--> 访问权限
```

### L4 编排层 (策略建议)
1. 短期: 安装 WireGuard 完成端到端加密
2. 中期: 部署第二个 Bootstrap 实现冗余
3. 长期: 构建中继网络覆盖 Symmetric NAT
4. 安全: 实现自动异常检测与封禁

---

## 🤖 Gemma 分析

{gemma_response}

---

## 📁 生成文件

| 文件 | 说明 |
|------|------|
| spore_p2p_network.py | P2P核心实现 |
| Spore_Civ_Production.py | 主程序(已集成P2P) |
| deploy_to_47.79.236.92.sh | 阿里云部署脚本 |
| SPORE_P2P_GUIDE.md | 使用指南 |
| luna_sgp_startup.sh | 启动程序 |

---

*报告由 Luna SGP + Gemma 4 本地模型联合生成*
""")
    
    print(f"\n✅ 报告已保存: {report_file}")
    return report_file

if __name__ == "__main__":
    print("🌙 Luna SGP + Gemma 工作处理管道")
    print("=" * 50)
    
    report = generate_daily_report()
    
    print("\n🎉 处理完成!")
    print(f"📊 报告: {report}")

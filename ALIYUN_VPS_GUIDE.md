# ☁️ 阿里云轻量应用服务器 - 创建指南

## 推荐产品：轻量应用服务器 (Simple Application Server)

> 适合场景：低负载长期运行服务（如 Bootstrap 节点）
> 优势：配置简单、价格固定、带宽独享

---

## 📋 创建步骤

### 第一步：登录阿里云

1. 访问 [阿里云官网](https://www.aliyun.com)
2. 登录账号（支付宝/淘宝/阿里云账号）
3. 新用户建议先完成实名认证

---

### 第二步：进入轻量应用服务器控制台

1. 顶部导航 → **产品** → **云计算基础** → **轻量应用服务器**
2. 或直接访问：https://swas.console.aliyun.com
3. 点击 **创建实例**

---

### 第三步：配置选择

| 配置项 | 推荐选择 | 说明 |
|--------|----------|------|
| **地域** | 华东1（杭州）或 华东2（上海） | 离你最近，延迟低 |
| **镜像** | **系统镜像** → **Ubuntu 22.04** | 稳定，LTS长期支持 |
| **套餐** | **新用户特惠：2核2G 50GB SSD** | ¥108/年（约$15/年） |
| **数据盘** | 不需要 | 50GB系统盘足够 |
| **购买时长** | 1年 | 新用户首年优惠最大 |

**💰 价格参考（新用户）**：
- 2核2G + 50GB SSD + 3M带宽 = **¥108/年**（约$15/年）
- 2核4G + 60GB SSD + 4M带宽 = **¥198/年**

> ⚠️ 注意：老用户价格会贵一些，约 ¥60-100/月

---

### 第四步：确认订单

1. 勾选服务协议
2. 点击 **立即购买**
3. 选择支付方式（支付宝/网银）
4. 完成支付

---

### 第五步：获取连接信息

创建成功后，在控制台可以看到：

```
🌐 公网 IP：123.45.67.89（示例）
🔑 默认账号：root
🔐 密码：你在创建时设置的（或系统生成的）
🚪 SSH 端口：22
```

**重置密码**（如果忘记）：
1. 控制台 → 选择实例 → **重置密码**
2. 重启实例生效

---

## 🔌 连接服务器

### macOS/Linux

```bash
# 使用终端连接
ssh root@123.45.67.89

# 输入密码（输入时不显示字符）
```

### Windows

推荐使用 **Termius** 或 **PuTTY**：
1. 下载 Termius：[https://termius.com](https://termius.com)
2. 新建连接：Host = 你的IP，Port = 22，Username = root
3. 输入密码连接

---

## 🚀 部署 SporeCiv Bootstrap

连接成功后，一键部署：

```bash
# 1. 更新系统
apt update && apt upgrade -y

# 2. 安装基础依赖
apt install -y python3 python3-pip python3-venv git curl

# 3. 创建工作目录
mkdir -p /opt/sporeciv && cd /opt/sporeciv

# 4. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 5. 安装 Python 库
pip install kademlia zeroconf psutil numpy

# 6. 创建 bootstrap 节点代码
cat > bootstrap.py << 'EOF'
#!/usr/bin/env python3
import asyncio
import logging
import time
from kademlia.network import Server
from kademlia.utils import digest

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger("bootstrap")

class BootstrapNode:
    def __init__(self, port=8467):
        self.server = Server(node_id=digest("spore_bootstrap_ali"))
        self.port = port
        
    async def start(self):
        await self.server.listen(self.port)
        logger.info(f"🌱 Bootstrap node started on port {self.port}")
        logger.info(f"   Kademlia ID: {self.server.node.long_id}")
        while True:
            await asyncio.sleep(60)
            
    async def stop(self):
        self.server.stop()

async def main():
    node = BootstrapNode()
    try:
        await node.start()
    except KeyboardInterrupt:
        await node.stop()

if __name__ == "__main__":
    asyncio.run(main())
EOF

# 7. 创建 systemd 服务
cat > /etc/systemd/system/spore-bootstrap.service << 'EOF'
[Unit]
Description=SporeCiv Bootstrap Node
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/sporeciv
ExecStart=/opt/sporeciv/venv/bin/python /opt/sporeciv/bootstrap.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 8. 启动服务
systemctl daemon-reload
systemctl enable spore-bootstrap
systemctl start spore-bootstrap

# 9. 检查状态
systemctl status spore-bootstrap
```

---

## 🛡️ 防火墙配置

阿里云有**安全组**（虚拟防火墙），需要手动放行端口：

1. 控制台 → 轻量应用服务器 → 选择实例
2. **安全** → **防火墙**
3. 点击 **添加规则**：

| 应用类型 | 协议 | 端口范围 | 备注 |
|----------|------|----------|------|
| 自定义 | TCP | 8467 | SporeCiv DHT |
| 自定义 | UDP | 8467 | SporeCiv DHT |
| SSH | TCP | 22 | 远程连接（默认已有）|

> ⚠️ 不要开放 51820（WireGuard）和 9998（A2A），这是母巢用的

---

## ✅ 验证部署

```bash
# 检查服务状态
systemctl status spore-bootstrap

# 查看日志
journalctl -u spore-bootstrap -f

# 检查端口监听
ss -tlnp | grep 8467
```

**预期输出**：
```
🌱 Bootstrap node started on port 8467
   Kademlia ID: 601145084517987...
```

---

## 🔗 更新母巢配置

部署成功后，在你的 Mac 上更新：

```python
# Spore_Civ_Production.py
CONFIG = {
    # ...
    "P2P_BOOTSTRAP": [
        ("123.45.67.89", 8467),  # ← 你的阿里云公网IP
    ],
}
```

然后重启母巢节点：
```bash
~/.openclaw/workspace/start_spore_monitor.sh restart
```

---

## 📊 后续维护

| 操作 | 命令 |
|------|------|
| 查看日志 | `journalctl -u spore-bootstrap -f` |
| 重启服务 | `systemctl restart spore-bootstrap` |
| 查看资源 | `htop` 或 `df -h` |
| 更新系统 | `apt update && apt upgrade -y` |

---

## 💡 省钱技巧

1. **新用户首年**：¥108/年（2核2G），性价比最高
2. **学生优惠**：通过阿里云学生认证，¥9.5/月
3. **按量付费**：不推荐，关机不计费但 IP 会释放
4. **到期续费**：老用户续费贵，建议到期前快照迁移

---

## 🆘 常见问题

**Q: 连接不上 SSH？**
- 检查安全组是否放行 22 端口
- 检查密码是否正确
- 尝试重置密码后重启

**Q: 服务启动失败？**
- 检查端口是否被占用：`lsof -i :8467`
- 检查日志：`journalctl -u spore-bootstrap -n 50`

**Q: 母巢连不上 bootstrap？**
- 检查阿里云防火墙是否放行 8467
- 检查母巢配置 IP 是否正确
- 测试连通性：`nc -zv 123.45.67.89 8467`

---

*文档版本: 1.0*  
*适用产品: 阿里云轻量应用服务器*

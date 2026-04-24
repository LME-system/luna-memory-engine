#!/bin/bash
# lme-install.sh - LME系统智能安装脚本
# 自动检测环境、交互式配置、一键安装
#
# 使用方法:
#   curl -fsSL https://raw.githubusercontent.com/LME-system/luna-memory-engine/main/install.sh | bash
#   或下载后运行: ./lme-install.sh

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 打印横幅
print_banner() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║           🌙 LME - Luna Memory Engine                      ║"
    echo "║              智能安装程序 v1.0                             ║"
    echo "║                                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
}

# 检测操作系统
detect_os() {
    log_info "检测操作系统..."
    
    OS="$(uname -s)"
    ARCH="$(uname -m)"
    
    case "$OS" in
        Linux*)     PLATFORM="linux" ;;
        Darwin*)    PLATFORM="macos" ;;
        CYGWIN*|MINGW*|MSYS*) PLATFORM="windows" ;;
        *)          PLATFORM="unknown" ;;
    esac
    
    log_success "检测到: $OS $ARCH"
    
    if [ "$PLATFORM" == "unknown" ]; then
        log_error "不支持的操作系统: $OS"
        exit 1
    fi
}

# 检测依赖
detect_dependencies() {
    log_info "检测依赖环境..."
    
    # Python3
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        log_success "Python3: $PYTHON_VERSION"
        HAS_PYTHON=true
    else
        log_warn "Python3 未安装"
        HAS_PYTHON=false
    fi
    
    # Git
    if command -v git &> /dev/null; then
        GIT_VERSION=$(git --version | awk '{print $3}')
        log_success "Git: $GIT_VERSION"
        HAS_GIT=true
    else
        log_warn "Git 未安装"
        HAS_GIT=false
    fi
    
    # Cron
    if command -v crontab &> /dev/null; then
        log_success "Cron: 已安装"
        HAS_CRON=true
    else
        log_warn "Cron 未安装（macOS使用launchd）"
        HAS_CRON=false
    fi
}

# 探测OpenClaw
detect_openclaw() {
    log_info "探测 OpenClaw 安装..."
    
    POSSIBLE_PATHS=(
        "$HOME/.openclaw"
        "$HOME/.config/openclaw"
        "$HOME/Library/Application Support/openclaw"
        "/opt/openclaw"
        "/usr/local/openclaw"
        "/usr/share/openclaw"
    )
    
    FOUND_OPENCLAW=""
    
    for path in "${POSSIBLE_PATHS[@]}"; do
        if [ -d "$path" ]; then
            log_success "发现 OpenClaw: $path"
            FOUND_OPENCLAW="$path"
            break
        fi
    done
    
    if [ -z "$FOUND_OPENCLAW" ]; then
        log_warn "未自动发现 OpenClaw 安装"
    fi
}

# 探测硬件配置
detect_hardware() {
    log_info "检测硬件配置..."
    
    # CPU核心数
    if command -v nproc &> /dev/null; then
        CPU_CORES=$(nproc)
    elif command -v sysctl &> /dev/null; then
        CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo "unknown")
    else
        CPU_CORES="unknown"
    fi
    
    # 内存（如果可用）
    if command -v free &> /dev/null; then
        MEMORY=$(free -h 2>/dev/null | awk '/^Mem:/ {print $2}' || echo "unknown")
    elif command -v sysctl &> /dev/null; then
        MEMORY_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
        MEMORY=$((MEMORY_BYTES / 1024 / 1024 / 1024))GB
    else
        MEMORY="unknown"
    fi
    
    log_success "CPU核心: $CPU_CORES, 内存: $MEMORY"
}

# 交互式配置
interactive_config() {
    log_info "进入交互式配置..."
    echo ""
    
    # OpenClaw路径
    if [ -n "$FOUND_OPENCLAW" ]; then
        read -p "使用检测到的 OpenClaw 路径 [$FOUND_OPENCLAW]? (Y/n): " confirm
        if [[ $confirm =~ ^[Nn]$ ]]; then
            read -p "请输入 OpenClaw 路径: " OPENCLAW_PATH
        else
            OPENCLAW_PATH="$FOUND_OPENCLAW"
        fi
    else
        read -p "请输入 OpenClaw 安装路径 (留空跳过): " OPENCLAW_PATH
    fi
    
    # LME安装路径
    DEFAULT_LME_PATH="$HOME/lme"
    read -p "LME安装路径 [$DEFAULT_LME_PATH]: " LME_PATH
    LME_PATH="${LME_PATH:-$DEFAULT_LME_PATH}"
    
    # 扫描频率
    DEFAULT_SCAN_FREQ="1"
    read -p "OpenClaw扫描频率(分钟) [$DEFAULT_SCAN_FREQ]: " SCAN_FREQ
    SCAN_FREQ="${SCAN_FREQ:-$DEFAULT_SCAN_FREQ}"
    
    # 确认配置
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                     配置确认                               ║"
    echo "╠════════════════════════════════════════════════════════════╣"
    printf "║ %-20s %-35s ║\n" "OpenClaw路径:" "${OPENCLAW_PATH:-未配置}"
    printf "║ %-20s %-35s ║\n" "LME安装路径:" "$LME_PATH"
    printf "║ %-20s %-35s ║\n" "扫描频率:" "每${SCAN_FREQ}分钟"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    
    read -p "确认安装? (Y/n): " confirm_install
    if [[ $confirm_install =~ ^[Nn]$ ]]; then
        log_info "安装已取消"
        exit 0
    fi
}

# 安装LME
install_lme() {
    log_info "开始安装 LME..."
    
    # 检查目录是否存在
    if [ -d "$LME_PATH" ]; then
        log_warn "目录已存在: $LME_PATH"
        read -p "是否覆盖? (y/N): " overwrite
        if [[ $overwrite =~ ^[Yy]$ ]]; then
            rm -rf "$LME_PATH"
        else
            log_error "安装中止"
            exit 1
        fi
    fi
    
    # 克隆仓库
    log_info "克隆 LME 仓库..."
    if [ "$HAS_GIT" = true ]; then
        git clone --depth 1 https://github.com/LME-system/luna-memory-engine.git "$LME_PATH"
    else
        log_error "需要 Git 来克隆仓库"
        exit 1
    fi
    
    log_success "仓库克隆完成"
}

# 配置环境
configure_environment() {
    log_info "配置环境变量..."
    
    SHELL_RC=""
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_RC="$HOME/.bash_profile"
    fi
    
    if [ -n "$SHELL_RC" ]; then
        cat >> "$SHELL_RC" << EOF

# LME 系统配置 (自动添加 by lme-install.sh)
export LME_HOME="$LME_PATH"
export LME_QUEUE_DIR="\${LME_HOME}/data/queue"
export LME_LOG_DIR="\${LME_HOME}/data/logs"
EOF
        
        if [ -n "$OPENCLAW_PATH" ]; then
            cat >> "$SHELL_RC" << EOF
export OPENCLAW_SESSION_DIR="$OPENCLAW_PATH/agents/main/sessions"
export SCAN_INTERVAL_MINUTES="$((SCAN_FREQ * 60))"
EOF
        fi
        
        log_success "环境变量已添加到 $SHELL_RC"
    else
        log_warn "未找到 shell 配置文件，请手动添加环境变量"
    fi
}

# 安装Cron任务
install_cron() {
    if [ "$HAS_CRON" = false ]; then
        log_warn "Cron 不可用，跳过定时任务安装"
        log_info "macOS用户请使用 launchd 或手动运行"
        return
    fi
    
    log_info "安装 Cron 定时任务..."
    
    # 创建临时crontab文件
    TEMP_CRON=$(mktemp)
    crontab -l > "$TEMP_CRON" 2>/dev/null || true
    
    # 添加LME任务
    echo "*/$SCAN_FREQ * * * * $LME_PATH/tools/openclaw-bridge.sh >> $LME_PATH/data/logs/bridge.log 2>&1" >> "$TEMP_CRON"
    
    # 安装新crontab
    crontab "$TEMP_CRON"
    rm "$TEMP_CRON"
    
    log_success "Cron 任务已安装 (每${SCAN_FREQ}分钟)"
}

# 启动服务
start_services() {
    log_info "启动 LME 服务..."
    
    # 创建必要目录
    mkdir -p "$LME_PATH/data/queue"
    mkdir -p "$LME_PATH/data/logs"
    
    # 启动守护进程
    cd "$LME_PATH"
    nohup python3 software/yuehen_lme_daemon_v3.py > /dev/null 2>&1 &
    DAEMON_PID=$!
    
    # 保存PID
    echo "$DAEMON_PID" > "$LME_PATH/data/lme.pid"
    
    log_success "守护进程已启动 (PID: $DAEMON_PID)"
}

# 生成安装报告
generate_report() {
    REPORT_FILE="$LME_PATH/install-report.txt"
    
    cat > "$REPORT_FILE" << EOF
LME 系统安装报告
================
安装时间: $(date)
系统信息: $OS $ARCH
Python: ${PYTHON_VERSION:-未安装}
Git: ${GIT_VERSION:-未安装}

安装路径: $LME_PATH
OpenClaw路径: ${OPENCLAW_PATH:-未配置}
扫描频率: 每${SCAN_FREQ}分钟

服务状态:
  守护进程PID: $DAEMON_PID
  队列目录: $LME_PATH/data/queue
  日志目录: $LME_PATH/data/logs

使用方法:
  查看日志: tail -f $LME_PATH/data/logs/yuehen_lme_daemon_*.log
  停止服务: kill \$(cat $LME_PATH/data/lme.pid)
  重新启动: cd $LME_PATH && python3 software/yuehen_lme_daemon_v3.py

文档:
  README: $LME_PATH/README.md
  配置指南: $LME_PATH/docs/OPENCLAW_BRIDGE.md
EOF
    
    log_success "安装报告已生成: $REPORT_FILE"
}

# 打印完成信息
print_completion() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                   🎉 安装完成!                             ║"
    echo "╠════════════════════════════════════════════════════════════╣"
    printf "║ %-58s ║\n" "安装路径: $LME_PATH"
    printf "║ %-58s ║\n" ""
    printf "║ %-58s ║\n" "常用命令:"
    printf "║ %-58s ║\n" "  查看日志: tail -f $LME_PATH/data/logs/*.log"
    printf "║ %-58s ║\n" "  查看报告: cat $LME_PATH/install-report.txt"
    printf "║ %-58s ║\n" ""
    printf "║ %-58s ║\n" "文档:"
    printf "║ %-58s ║\n" "  $LME_PATH/README.md"
    printf "║ %-58s ║\n" "  $LME_PATH/docs/OPENCLAW_BRIDGE.md"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    log_info "请重新加载 shell 配置或运行: source ~/.bashrc (或 ~/.zshrc)"
}

# 主流程
main() {
    print_banner
    detect_os
    detect_dependencies
    detect_openclaw
    detect_hardware
    interactive_config
    install_lme
    configure_environment
    install_cron
    start_services
    generate_report
    print_completion
}

# 运行
main "$@"

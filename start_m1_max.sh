#!/bin/bash
# ============================================================
# Prism v2 — 机器2 启动脚本
# 设备: M1 Max 32GB | IP: 192.168.0.103
# 推理引擎: llama.cpp (统一)
# 量化: Q8 GGUF
#
# 用法: bash start_m1_max.sh [模型选项]
#
# 模型选项:
#   9b    → Qwen3.5-9B Q8 (中端推理, 端口9200)
#   stop  → 停止所有服务
#
# 注意: M1 Max 32GB 仅支持 9B 模型
# ============================================================

set -e

# ── 路径配置 ──────────────────────────────────────────────────
MLX_ROOT=/Users/alex/Documents/mlx-community
SIM_DIR=$MLX_ROOT/echostream_sim
LOG_DIR=$SIM_DIR/logs
RESULTS_DIR=$SIM_DIR/results
MODEL_PORT=9200
LLAMA_SERVER=$MLX_ROOT/llama.cpp/build/bin/llama-server
THREADS=8

# GGUF 模型路径
GGUF_9B=$MLX_ROOT/Qwen3.5-9B-UD-Q8_K_XL/Qwen3.5-9B-UD-Q8_K_XL.gguf

# Python (数据节点需要)
PYTHON=$MLX_ROOT/3-11-mlx-community-env/bin/python

# ── 颜色输出 ──────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[M1 Max]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

# ── 代理排除 ─────────────────────────────────────────────────
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY 2>/dev/null || true
export no_proxy="localhost,127.0.0.1,192.168.0.0/24"
export NO_PROXY="localhost,127.0.0.1,192.168.0.0/24"

# ── 初始化 ────────────────────────────────────────────────────
log "Prism v2 机器2 (M1 Max 32GB)"
mkdir -p $LOG_DIR $RESULTS_DIR/benchmark $SIM_DIR/data

# 检查 llama-server
if [ ! -f "$LLAMA_SERVER" ]; then
    err "llama-server 不存在: $LLAMA_SERVER"
    exit 1
fi

# 检查依赖
$PYTHON -c "import flask, requests" 2>/dev/null || {
    warn "安装缺失依赖..."
    $PYTHON -m pip install flask requests -q
}

# ── 停止所有模型进程 ──────────────────────────────────────────
stop_all_models() {
    log "停止所有模型服务..."
    pkill -f "llama-server" 2>/dev/null && log "已停止 llama-server 进程" || true
    sleep 2
    if lsof -ti:$MODEL_PORT > /dev/null 2>&1; then
        kill $(lsof -ti:$MODEL_PORT) 2>/dev/null || true
        sleep 2
    fi
    log "所有模型服务已停止"
}

# ── 启动 llama-server ────────────────────────────────────────
start_llama_server() {
    local GGUF_PATH=$1
    local PORT=$2
    local NAME=$3

    if [ ! -f "$GGUF_PATH" ]; then
        err "GGUF 文件不存在: $GGUF_PATH"
        return 1
    fi

    log "启动 llama-server: $NAME (端口 $PORT)..."

    nohup $LLAMA_SERVER \
        -m "$GGUF_PATH" \
        --port $PORT \
        --host 0.0.0.0 \
        -fa on \
        -ngl 999 \
        -t $THREADS \
        -tb $THREADS \
        --mlock \
        -c 32768 \
        -n 8192 \
        --ubatch-size 512 \
        -b 2048 \
        --metrics \
        -to 600 \
        --reasoning-budget 0 \
        > $LOG_DIR/llama_server_${PORT}.log 2>&1 &

    local PID=$!
    echo $PID > $LOG_DIR/llama_server_${PORT}.pid
    log "$NAME PID: $PID"

    local MAX_WAIT=120
    local waited=0
    while [ $waited -lt $MAX_WAIT ]; do
        if curl -s http://localhost:$PORT/v1/models > /dev/null 2>&1; then
            log "✅ $NAME 就绪 (等待 ${waited}s)"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
        echo -n "."
    done
    echo ""
    warn "$NAME 启动较慢，查看: $LOG_DIR/llama_server_${PORT}.log"
}

# ── 启动数据节点 ──────────────────────────────────────────────
start_data_node() {
    if lsof -ti:9211 > /dev/null 2>&1; then
        warn "数据节点(9211)已运行"
        return 0
    fi

    log "启动数据节点: 模拟 iPhone 15 PM (端口 9211)"
    log "  数据来源: Mealens (饮食) + Ururu (情绪)"

    if [ ! -d "$SIM_DIR/data/users/user_01" ]; then
        warn "数据目录未找到，请先从机器1 rsync 同步数据"
        return 1
    fi

    nohup $PYTHON $SIM_DIR/04_lan_protocol.py \
        --role data_node \
        --node_name "M1Max-iPhone-Mealens-Ururu" \
        --apps mealens ururu \
        --port 9211 \
        --data_dir $SIM_DIR/data/users \
        --user_id user_01 \
        > $LOG_DIR/data_node_9211.log 2>&1 &

    local PID=$!
    echo $PID > $LOG_DIR/data_node_9211.pid
    sleep 3

    if curl -s http://localhost:9211/health > /dev/null 2>&1; then
        log "✅ 数据节点就绪 PID: $PID"
    else
        warn "数据节点启动中"
    fi
}

# ── 主逻辑 ───────────────────────────────────────────────────
MODEL_CHOICE="${1:-9b}"

case "$MODEL_CHOICE" in
    9b)
        log "启动 Qwen3.5-9B Q8 (llama.cpp)"
        stop_all_models
        start_llama_server "$GGUF_9B" $MODEL_PORT "Qwen3.5-9B-Q8"
        start_data_node
        ;;
    stop)
        stop_all_models
        if lsof -ti:9211 > /dev/null 2>&1; then
            kill $(lsof -ti:9211) 2>/dev/null || true
            log "已停止数据节点"
        fi
        exit 0
        ;;
    *)
        echo "用法: bash start_m1_max.sh [9b|stop]"
        echo ""
        echo "  9b    → Qwen3.5-9B Q8 (中端推理模型)"
        echo "  stop  → 停止所有服务"
        exit 1
        ;;
esac

# ── 状态汇总 ─────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  机器2 (M1 Max 32G) 服务状态"
echo "============================================================"

check_service() {
    local URL=$1
    local NAME=$2
    if curl -s $URL > /dev/null 2>&1; then
        echo -e "  ${GREEN}✅${NC} $NAME"
    else
        echo -e "  ${RED}❌${NC} $NAME"
    fi
}

check_service "http://localhost:$MODEL_PORT/v1/models" "模型服务 → 端口 $MODEL_PORT ($MODEL_CHOICE)"
check_service "http://localhost:9211/health"            "数据节点(iPhone) → 端口 9211"

echo ""
echo "  引擎: llama.cpp | 量化: Q8 GGUF | 线程: $THREADS"
echo "  当前模型: $MODEL_CHOICE"
echo "  对外提供: Mealens(饮食) + Ururu(情绪) (http://192.168.0.103:9211)"
echo "  日志: $LOG_DIR"
echo "============================================================"

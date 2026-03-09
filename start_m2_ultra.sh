#!/bin/bash
# ============================================================
# Prism v2 — 机器1 启动脚本
# 设备: M2 Ultra 192GB | IP: 192.168.0.113
# 推理引擎: llama.cpp (统一)
# 量化: 全部 Q8 GGUF
#
# 用法: bash start_m2_ultra.sh [模型选项]
#
# 模型选项:
#   35b   → Qwen3.5-35B-A3B (主力全景, 端口9200)
#   9b    → Qwen3.5-9B (中端推理, 端口9200)
#   2b    → Qwen3.5-2B (平板级, 端口9200)
#   0.8b  → Qwen3.5-0.8B (手机级, 端口9200)
#   stop  → 停止所有服务
#
# 注意: 同一时间只运行一个模型，避免OOM
# ============================================================

set -e

# ── 路径配置 ──────────────────────────────────────────────────
MLX_ROOT=/Users/alex/Documents/mlx-community
SIM_DIR=$MLX_ROOT/echostream_sim
LOG_DIR=$SIM_DIR/logs
RESULTS_DIR=$SIM_DIR/results
MODEL_PORT=9200
LLAMA_SERVER=$MLX_ROOT/llama.cpp/build/bin/llama-server
THREADS=16

# GGUF 模型路径
GGUF_35B=$MLX_ROOT/Qwen3.5-35B-A3B-GGUF-UD-Q8_K_XL/Qwen3.5-35B-A3B-UD-Q8_K_XL.gguf
GGUF_9B=$MLX_ROOT/Qwen3.5-9B-UD-Q8_K_XL/Qwen3.5-9B-UD-Q8_K_XL.gguf
GGUF_2B=$MLX_ROOT/Qwen3.5-2B-GGUF-UD-Q8_K_L/Qwen3.5-2B-UD-Q8_K_XL.gguf
GGUF_08B=$MLX_ROOT/Qwen3.5-0.8B-GGUF-UD-Q8_K_XL/Qwen3.5-0.8B-UD-Q8_K_XL.gguf

# Python (仅全景节点需要)
PYTHON=$MLX_ROOT/3-11-mlx-community-env/bin/python

# ── 颜色输出 ──────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[M2 Ultra]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

# ── 代理排除 ─────────────────────────────────────────────────
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY 2>/dev/null || true
export no_proxy="localhost,127.0.0.1,192.168.0.0/24"
export NO_PROXY="localhost,127.0.0.1,192.168.0.0/24"

# ── 初始化 ────────────────────────────────────────────────────
mkdir -p $LOG_DIR $RESULTS_DIR/benchmark $RESULTS_DIR/ablation/raw $RESULTS_DIR/scale/raw

# 检查 llama-server
if [ ! -f "$LLAMA_SERVER" ]; then
    err "llama-server 不存在: $LLAMA_SERVER"
    exit 1
fi

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

    local MAX_WAIT=180
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
    err "$NAME 启动超时，查看: $LOG_DIR/llama_server_${PORT}.log"
    return 1
}

# ── 启动全景节点 ─────────────────────────────────────────────
start_panorama_node() {
    if lsof -ti:9210 > /dev/null 2>&1; then
        warn "全景节点(9210)已运行"
        return 0
    fi

    log "启动全景节点 (端口 9210)..."
    nohup $PYTHON $SIM_DIR/04_lan_protocol.py \
        --role panorama_node \
        --port 9210 \
        --llm_endpoint http://localhost:$MODEL_PORT \
        > $LOG_DIR/panorama_node.log 2>&1 &

    local PID=$!
    echo $PID > $LOG_DIR/panorama_node.pid
    sleep 3

    if curl -s http://localhost:9210/health > /dev/null 2>&1; then
        log "✅ 全景节点就绪 PID: $PID"
    else
        warn "全景节点可能未就绪"
    fi
}

# ── 主逻辑 ───────────────────────────────────────────────────
MODEL_CHOICE="${1:-35b}"

case "$MODEL_CHOICE" in
    35b)
        log "Prism v2 — Qwen3.5-35B-A3B Q8 (llama.cpp)"
        stop_all_models
        start_llama_server "$GGUF_35B" $MODEL_PORT "Qwen3.5-35B-A3B-Q8"
        start_panorama_node
        ;;
    9b)
        log "Prism v2 — Qwen3.5-9B Q8 (llama.cpp)"
        stop_all_models
        start_llama_server "$GGUF_9B" $MODEL_PORT "Qwen3.5-9B-Q8"
        ;;
    2b)
        log "Prism v2 — Qwen3.5-2B Q8 (llama.cpp)"
        stop_all_models
        start_llama_server "$GGUF_2B" $MODEL_PORT "Qwen3.5-2B-Q8"
        ;;
    0.8b)
        log "Prism v2 — Qwen3.5-0.8B Q8 (llama.cpp)"
        stop_all_models
        start_llama_server "$GGUF_08B" $MODEL_PORT "Qwen3.5-0.8B-Q8"
        ;;
    stop)
        stop_all_models
        if lsof -ti:9210 > /dev/null 2>&1; then
            kill $(lsof -ti:9210) 2>/dev/null || true
            log "已停止全景节点"
        fi
        exit 0
        ;;
    *)
        echo "用法: bash start_m2_ultra.sh [35b|9b|2b|0.8b|stop]"
        echo ""
        echo "  35b   → Qwen3.5-35B-A3B Q8 (主力全景模型)"
        echo "  9b    → Qwen3.5-9B Q8 (中端推理)"
        echo "  2b    → Qwen3.5-2B Q8 (平板级)"
        echo "  0.8b  → Qwen3.5-0.8B Q8 (手机级)"
        echo "  stop  → 停止所有服务"
        exit 1
        ;;
esac

# ── 状态汇总 ─────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  机器1 (M2 Ultra 192G) 服务状态"
echo "============================================================"

check_service() {
    local URL=$1
    local NAME=$2
    if curl -s $URL > /dev/null 2>&1; then
        echo -e "  ${GREEN}✅${NC} $NAME"
    else
        echo -e "  ${RED}❌${NC} $NAME (未就绪)"
    fi
}

check_service "http://localhost:$MODEL_PORT/v1/models" "模型服务 → 端口 $MODEL_PORT ($MODEL_CHOICE)"
check_service "http://localhost:9210/health"            "全景节点 → 端口 9210"

echo ""
echo "  引擎: llama.cpp | 量化: Q8 GGUF | 线程: $THREADS"
echo "  当前模型: $MODEL_CHOICE"
echo "  切换模型: bash start_m2_ultra.sh [35b|9b|2b|0.8b]"
echo "  日志: $LOG_DIR"
echo "============================================================"

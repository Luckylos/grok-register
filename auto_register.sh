#!/bin/bash
# Grok 自动注册循环脚本
# 每5分钟执行一次注册，同时监控 grok2api 活跃账户数
# 当活跃账户达到 TARGET_COUNT 时自动停止

set -uo pipefail

GROK_REGISTER_DIR="/opt/grok-register"
VENV_PYTHON="$GROK_REGISTER_DIR/.venv/bin/python"
MAIN_SCRIPT="$GROK_REGISTER_DIR/DrissionPage_example.py"
GROK2API_URL="http://127.0.0.1:8000"
GROK2API_APP_KEY="abfb90fd7109c15ea908e985"
TARGET_COUNT=200
INTERVAL=300  # 5分钟 = 300秒
LOG_FILE="$GROK_REGISTER_DIR/logs/auto_register.log"
PID_FILE="/tmp/grok_auto_register.pid"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

get_active_count() {
    local count
    count=$(curl -s --max-time 15 "$GROK2API_URL/admin/api/tokens" \
        -H "Authorization: Bearer $GROK2API_APP_KEY" 2>/dev/null | \
        python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tokens = data.get('tokens', [])
    active = [t for t in tokens if t.get('status') == 'active']
    print(len(active))
except:
    print(0)
" 2>/dev/null)
    echo "${count:-0}"
}

# 写入 PID 文件
echo $$ > "$PID_FILE"

log "=========================================="
log "Grok 自动注册循环启动 (PID: $$)"
log "目标: $TARGET_COUNT 个活跃账户"
log "间隔: ${INTERVAL}s (5分钟)"
log "=========================================="

while true; do
    # 检查当前活跃账户数
    ACTIVE=$(get_active_count)
    log "当前 grok2api 活跃账户: $ACTIVE / 目标: $TARGET_COUNT"

    if [ "$ACTIVE" -ge "$TARGET_COUNT" ]; then
        log "✅ 已达到目标! 活跃账户 $ACTIVE >= $TARGET_COUNT，停止注册"
        break
    fi

    # 执行一轮注册 (count=1)
    log "开始执行一轮注册..."
    cd "$GROK_REGISTER_DIR"

    RUN_START=$(date +%s)

    if "$VENV_PYTHON" "$MAIN_SCRIPT" --count 1 2>&1 | tee -a "$LOG_FILE"; then
        RUN_END=$(date +%s)
        RUN_DURATION=$((RUN_END - RUN_START))
        log "本轮注册完成 (耗时 ${RUN_DURATION}s)"
    else
        RUN_END=$(date +%s)
        RUN_DURATION=$((RUN_END - RUN_START))
        log "⚠️ 本轮注册出现错误 (耗时 ${RUN_DURATION}s)，继续下一轮"
    fi

    # 再次检查账户数
    NEW_ACTIVE=$(get_active_count)
    DIFF=$((NEW_ACTIVE - ACTIVE))
    if [ "$DIFF" -gt 0 ]; then
        log "✅ 本轮新增 $DIFF 个活跃账户 ($ACTIVE → $NEW_ACTIVE)"
    else
        log "⚠️ 本轮未新增活跃账户 (仍为 $NEW_ACTIVE)"
    fi

    if [ "$NEW_ACTIVE" -ge "$TARGET_COUNT" ]; then
        log "✅ 已达到目标! 活跃账户 $NEW_ACTIVE >= $TARGET_COUNT，停止注册"
        break
    fi

    # 计算还需要注册的数量
    REMAINING=$((TARGET_COUNT - NEW_ACTIVE))
    log "还需约 $REMAINING 个账户，等待 ${INTERVAL}s 后继续..."
    log "------------------------------------------"

    sleep "$INTERVAL"
done

# 清理
rm -f "$PID_FILE"

log "=========================================="
log "自动注册循环结束"
FINAL=$(get_active_count)
log "最终活跃账户数: $FINAL"
log "=========================================="

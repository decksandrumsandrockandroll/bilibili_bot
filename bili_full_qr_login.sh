#!/bin/bash
# B站 Cookie 失效检测与自动续期（调用 update_cookie_qr.py）

set -e

LOG_DIR="/home/zh/bili/logs"
PYTHON_SCRIPT="/home/zh/bili/update_cookie_qr.py"
LOCK_FILE="/tmp/bili_renew.lock"
LOG_FILE="/var/log/bili_qr_login.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

if [ -f "$LOCK_FILE" ]; then
    log "续期流程已在执行，退出。"
    exit 0
fi
trap 'rm -f "$LOCK_FILE"' EXIT
touch "$LOCK_FILE"

TODAY=$(date +%Y%m%d)
DAILY_LOG="$LOG_DIR/daily_${TODAY}.log"

if [ ! -f "$DAILY_LOG" ]; then
    log "今日日志文件不存在，跳过检测。"
    exit 0
fi

if grep -q -E "Cookie失效|登录过期|未登录" "$DAILY_LOG"; then
    log "检测到 Cookie 失效，启动自动续期流程..."
else
    log "Cookie 有效，无需续期。"
    exit 0
fi

if [ ! -f "$PYTHON_SCRIPT" ]; then
    log "❌ 未找到 $PYTHON_SCRIPT"
    exit 1
fi

python3 "$PYTHON_SCRIPT" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
[ $EXIT_CODE -eq 0 ] && log "✅ 续期流程完成" || log "❌ 续期流程失败，退出码 $EXIT_CODE"
exit $EXIT_CODE

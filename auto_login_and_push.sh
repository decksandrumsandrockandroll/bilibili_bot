#!/bin/bash
# 自动执行 Login 并推送二维码链接（带重试）

LOG_FILE="/tmp/login_output_$(date +%s).log"
TIMEOUT_SEC=20
MAX_ATTEMPTS=3

# 等待容器完全启动（最多 10 秒）
for i in {1..5}; do
    if docker exec bili dotnet --version > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

# 执行 Login，超时自动退出
for attempt in $(seq 1 $MAX_ATTEMPTS); do
    timeout $TIMEOUT_SEC docker exec bili dotnet /app/Ray.BiliBiliTool.Console.dll --runTasks=Login > "$LOG_FILE" 2>&1
    QR_URL=$(grep -o 'https://tool.lu/qrcode/basic.html?text=[^"]*' "$LOG_FILE" | head -1)
    if [ -n "$QR_URL" ]; then
        break
    fi
    sleep 3
done

if [ -n "$QR_URL" ]; then
    WEBHOOK_KEY=$(cat /home/zh/bili/.bili_webhook_key)
    curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=$WEBHOOK_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"📱 请点击链接查看二维码并扫码登录：\n\n$QR_URL\"}}"
    echo "✅ 二维码链接已推送到微信"
else
    echo "❌ 未提取到二维码链接（尝试 $MAX_ATTEMPTS 次）"
    # 打印最后一部分日志以便调试
    tail -20 "$LOG_FILE"
fi

# 清理临时文件（可选）
rm -f "$LOG_FILE"

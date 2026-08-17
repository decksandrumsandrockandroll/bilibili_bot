#!/bin/bash
# 从容器日志提取二维码链接并推送到微信

QR_URL=$(docker logs bili 2>/dev/null | grep -o 'https://tool.lu/qrcode/basic.html?text=[^"]*' | head -1)

if [ -z "$QR_URL" ]; then
    echo "日志中暂无二维码，请先执行 Login 任务生成二维码"
    exit 1
fi

WEBHOOK_KEY=$(cat /home/zh/bili/.bili_webhook_key)
curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=$WEBHOOK_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"📱 请点击链接查看二维码并扫码登录：\n\n$QR_URL\"}}"

echo "✅ 二维码链接已推送到微信"

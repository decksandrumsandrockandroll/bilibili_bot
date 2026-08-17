#!/bin/bash
# B站签到 + Cookie 续期包装脚本

cd /home/zh/bili
python3 bili_daily.py >> /home/zh/bili/logs/cron.log 2>&1
/home/zh/bili/bili_full_qr_login.sh >> /home/zh/bili/logs/cron.log 2>&1

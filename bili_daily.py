#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站每日签到脚本（定时任务版）
- 执行 Daily 任务
- 检测失败任务，若无失败则推送简报（注明定时任务）
- 若有失败则调用手动修复脚本，由后者负责重试和推送
"""

import os
import sys
import subprocess
import re
import time
from datetime import datetime

from bili_common import (
    load_webhook_key, log_message, run_daily, parse_detailed,
    send_daily_report, check_container, init_db, rotate_logs,
    save_daily_record, is_today_pushed, mark_push_done,
    send_wechat, CONFIG, LOG_DIR, DAILY_PUSH_DEDUP
)

# 手动脚本路径：与当前脚本同一目录
MANUAL_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bili_daily_manual.py")

def main():
    log_message("开始执行每日签到（定时任务）...")

    init_db()
    rotate_logs()

    if not check_container():
        log_message("容器检查失败，退出。", "ERROR")
        return

    output = run_daily()

    # 保存日志
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = f"{LOG_DIR}/daily_{datetime.now().strftime('%Y%m%d')}.log"
    with open(log_file, 'a') as f:
        f.write(f"\n--- {datetime.now()} ---\n")
        f.write(output)

    webhook_key = load_webhook_key()
    if not webhook_key:
        log_message("未找到机器人 Key，跳过推送。", "WARN")
        return

    # 检测 Cookie 失效
    if re.search(r'【账号个数】\s*0', output):
        alert_msg = CONFIG.get("push_template", {}).get("cookie_invalid", "⚠️ **Cookie 已失效，请重新部署 BiliBiliTool！**\n时间：{time}\n请执行 `./update_cookie.py` 或重新获取 Cookie 并重建容器。")
        alert_msg = alert_msg.format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        send_wechat(webhook_key, alert_msg)
        log_message("Cookie 失效告警已推送。")
        return

    # 解析结果
    result = parse_detailed(output)

    # 保存记录到数据库
    if result["username"] != "未知" and result["coins"] != "未知" and result["exp"] != "未知":
        try:
            coins = int(result["coins"])
            exp = int(result["exp"])
            save_daily_record(
                datetime.now().strftime("%Y-%m-%d"),
                result["username"],
                coins,
                exp,
                result["tasks"],
                output
            )
            log_message("当日数据已保存到数据库。")
        except Exception as e:
            log_message(f"保存数据库失败: {e}", "ERROR")

    # 检测是否有失败任务
    if result["failed_tasks"]:
        log_message(f"检测到 {len(result['failed_tasks'])} 个失败任务，不推送简报，调用手动修复脚本...")
        # 调用手动修复脚本，传递日志文件路径
        try:
            subprocess.run(
                ["python3", MANUAL_SCRIPT, "--log-file", log_file],
                check=True,
                timeout=600  # 10分钟超时
            )
        except subprocess.TimeoutExpired:
            log_message("手动修复脚本执行超时。", "ERROR")
        except subprocess.CalledProcessError as e:
            log_message(f"手动修复脚本执行失败: {e}", "ERROR")
    else:
        log_message("所有任务执行成功，推送简报。")
        today_str = datetime.now().strftime("%Y-%m-%d")
        if DAILY_PUSH_DEDUP and is_today_pushed(today_str, "daily"):
            log_message("今日每日报告已推送过，跳过。")
        else:
            send_daily_report(webhook_key, result, retry_records=[], source="定时任务")
            if DAILY_PUSH_DEDUP:
                mark_push_done(today_str, "daily")

        # 周期报告
        if result["username"] != "未知":
            from bili_common import check_and_send_report
            current_date = datetime.now().date()
            check_and_send_report(webhook_key, current_date, result["username"])

    log_message("定时任务执行完成。")

if __name__ == "__main__":
    main()

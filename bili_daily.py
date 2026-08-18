#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站每日签到脚本（智能重试版）
- 如果当天已执行过完整签到，则只重试失败任务（跳过大会员任务）
- 大会员任务（福利领取、B币券充电等）即使失败也不重试
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
    send_wechat, CONFIG, LOG_DIR, DAILY_PUSH_DEDUP,
    run_single_task
)

MANUAL_SCRIPT = "/root/bili_daily_manual.py"

# 大会员相关任务的关键词（不重试）
VIP_TASKS = ["大会员福利", "B币券充电", "大会员漫画权益"]

def has_daily_run_today():
    """检查当日是否已执行过完整签到"""
    today_str = datetime.now().strftime("%Y%m%d")
    log_file = f"{LOG_DIR}/daily_{today_str}.log"
    if not os.path.exists(log_file):
        return False
    with open(log_file, 'r') as f:
        content = f.read()
    # 判断是否包含签到完成标记
    return "运行结束" in content and "【账号个数】" in content

def get_failed_tasks_from_log():
    """从今日日志中解析失败任务（排除大会员任务）"""
    today_str = datetime.now().strftime("%Y%m%d")
    log_file = f"{LOG_DIR}/daily_{today_str}.log"
    if not os.path.exists(log_file):
        return []
    with open(log_file, 'r') as f:
        content = f.read()
    result = parse_detailed(content)
    # 过滤掉大会员任务
    failed = [t for t in result["failed_tasks"] if t["display"] not in VIP_TASKS]
    return failed

def retry_failed_tasks(failed_tasks):
    """重试失败任务（每个任务最多重试3次）"""
    retry_records = []
    for task in failed_tasks:
        display = task["display"]
        cmd = task["cmd"]
        log_message(f"🔁 重试失败任务: {display}")
        success = False
        attempts = 0
        while attempts < 3:
            attempts += 1
            time.sleep(3)
            output = run_single_task(cmd)
            if "成功" in output and "失败" not in output:
                success = True
                break
            if "已领取过" in output or "已兑换过" in output:
                success = True
                break
        retry_records.append({
            "display": display,
            "attempts": attempts,
            "success": success
        })
        log_message(f"  {'✅' if success else '❌'} {display} 重试 {attempts} 次")
    return retry_records

def main():
    log_message("开始执行每日签到（智能重试）...")

    init_db()
    rotate_logs()

    if not check_container():
        log_message("容器检查失败，退出。", "ERROR")
        return

    # 1. 检查当日是否已执行完整签到
    if has_daily_run_today():
        log_message("今日已执行过完整签到，进入失败任务重试模式...")
        webhook_key = load_webhook_key()
        if not webhook_key:
            log_message("未找到机器人 Key，跳过推送。", "WARN")
            return

        # 获取失败任务（已过滤大会员任务）
        failed_tasks = get_failed_tasks_from_log()
        if not failed_tasks:
            log_message("无失败任务需要重试。")
            # 推送“签到已成功”简报（但防止重复推送）
            today_str = datetime.now().strftime("%Y-%m-%d")
            if DAILY_PUSH_DEDUP and is_today_pushed(today_str, "daily"):
                log_message("今日每日报告已推送过，跳过。")
                return
            # 重新解析一次完整结果用于推送
            with open(f"{LOG_DIR}/daily_{datetime.now().strftime('%Y%m%d')}.log", 'r') as f:
                content = f.read()
            result = parse_detailed(content)
            send_daily_report(webhook_key, result, retry_records=[], source="定时任务")
            if DAILY_PUSH_DEDUP:
                mark_push_done(today_str, "daily")
            return

        # 重试失败任务
        retry_records = retry_failed_tasks(failed_tasks)
        # 推送重试结果简报
        today_str = datetime.now().strftime("%Y-%m-%d")
        if not (DAILY_PUSH_DEDUP and is_today_pushed(today_str, "daily")):
            # 重新解析完整日志用于推送
            with open(f"{LOG_DIR}/daily_{datetime.now().strftime('%Y%m%d')}.log", 'r') as f:
                content = f.read()
            result = parse_detailed(content)
            send_daily_report(webhook_key, result, retry_records, source="手动任务")
            if DAILY_PUSH_DEDUP:
                mark_push_done(today_str, "daily")
        return

    # 2. 否则执行完整签到
    log_message("今日首次执行完整签到...")
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

    # 检测是否有失败任务（忽略大会员任务）
    real_failed = [t for t in result["failed_tasks"] if t["display"] not in VIP_TASKS]
    if real_failed:
        log_message(f"检测到 {len(real_failed)} 个失败任务，调用手动修复脚本...")
        try:
            subprocess.run(
                ["python3", MANUAL_SCRIPT, "--log-file", log_file],
                check=True,
                timeout=600
            )
        except subprocess.TimeoutExpired:
            log_message("手动修复脚本执行超时。", "ERROR")
        except subprocess.CalledProcessError as e:
            log_message(f"手动修复脚本执行失败: {e}", "ERROR")
    else:
        log_message("所有关键任务执行成功，推送简报。")
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

    log_message("签到任务完成。")

if __name__ == "__main__":
    main()

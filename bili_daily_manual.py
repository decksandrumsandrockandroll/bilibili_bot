#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站签到手动修复脚本
- 读取当天的日志文件，解析失败任务
- 循环重试每个失败任务，直至全部成功
- 推送最终简报，注明手动任务执行次数
"""

import os
import sys
import argparse
import time
from datetime import datetime

from bili_common import (
    load_webhook_key, log_message, parse_detailed, send_daily_report,
    retry_single_task, CONFIG, LOG_DIR
)

def main():
    parser = argparse.ArgumentParser(description="B站签到手动修复脚本")
    parser.add_argument("--log-file", required=True, help="当日完整日志文件路径")
    args = parser.parse_args()

    log_file = args.log_file
    if not os.path.exists(log_file):
        log_message(f"日志文件 {log_file} 不存在", "ERROR")
        sys.exit(1)

    log_message(f"开始手动修复，读取日志: {log_file}")

    with open(log_file, 'r') as f:
        content = f.read()

    result = parse_detailed(content)
    if not result["failed_tasks"]:
        log_message("未发现失败任务，无需修复。")
        webhook_key = load_webhook_key()
        if webhook_key:
            send_daily_report(webhook_key, result, retry_records=[], source="手动任务")
        return

    log_message(f"发现 {len(result['failed_tasks'])} 个失败任务，开始逐个重试...")

    retry_records = []
    overall_success = True

    for idx, task in enumerate(result["failed_tasks"], 1):
        display = task["display"]
        cmd = task["cmd"]
        log_message(f"[{idx}/{len(result['failed_tasks'])}] 重试任务: {display} (命令: {cmd})")
        success, attempts, output = retry_single_task(cmd, max_attempts=6)
        retry_records.append({
            "display": display,
            "attempts": attempts,
            "success": success
        })
        if success:
            log_message(f"✅ 任务 {display} 重试成功（尝试 {attempts} 次）")
        else:
            log_message(f"❌ 任务 {display} 重试 {attempts} 次后仍失败", "ERROR")
            overall_success = False

        with open(log_file, 'a') as f:
            f.write(f"\n--- 手动重试 {display} (尝试{attempts}次) ---\n")
            f.write(output)

        time.sleep(2)

    if overall_success:
        log_message("所有失败任务已处理完毕。")
    else:
        log_message("部分任务重试后仍失败，请人工检查。", "WARN")

    webhook_key = load_webhook_key()
    if webhook_key:
        send_daily_report(webhook_key, result, retry_records, source="手动任务")
        log_message("最终简报已推送。")
    else:
        log_message("未找到机器人 Key，无法推送简报。", "WARN")

if __name__ == "__main__":
    main()

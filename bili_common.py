#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BiliBiliTool 公共函数模块（最终稳定版）"""

import os
import json
import subprocess
import re
import requests
import sqlite3
import time
import glob
import fcntl
from datetime import datetime, timedelta, date

# ==================== 加载配置 ====================
CONFIG_PATH = "/home/zh/bili/config.json"
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(f"配置文件 {CONFIG_PATH} 不存在")

with open(CONFIG_PATH, 'r') as f:
    CONFIG = json.load(f)

INSTALL_DIR = os.path.dirname(CONFIG_PATH)

def get_path(key, default_rel=None):
    val = CONFIG.get(key)
    if val and os.path.isabs(val):
        return val
    if val and default_rel is None:
        return os.path.join(INSTALL_DIR, val)
    if default_rel:
        return os.path.join(INSTALL_DIR, default_rel)
    return os.path.join(INSTALL_DIR, "data")

CONTAINER_NAME = CONFIG.get("container_name", "bili")
WEBHOOK_KEY_FILE = get_path("webhook_key_file", ".bili_webhook_key")
DB_PATH = get_path("db_path", "data/bili_stats.db")
LOG_DIR = get_path("log_dir", "logs")
LOG_RETENTION_DAYS = CONFIG.get("log_retention_days", 30)
MAX_RETRIES = CONFIG.get("max_retries", 3)
RETRY_BASE_DELAY = CONFIG.get("retry_base_delay", 5)
USE_EXPONENTIAL = CONFIG.get("use_exponential_backoff", True)
DAILY_PUSH_DEDUP = CONFIG.get("daily_push_dedup", True)
CONTAINER_AUTO_START = CONFIG.get("container_auto_start", True)
TASK_CMD_MAP = CONFIG.get("task_cmd_map", {})
PUSH_TEMPLATE = CONFIG.get("push_template", {})

# ==================== 工具函数 ====================
def load_webhook_key():
    if os.path.exists(WEBHOOK_KEY_FILE):
        with open(WEBHOOK_KEY_FILE, 'r') as f:
            return f.read().strip()
    return None

def log_message(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}")

def run_command(cmd_args, capture=True, check=False):
    full_cmd = ["docker", "exec", CONTAINER_NAME] + cmd_args
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    if result.returncode != 0 and check:
        raise RuntimeError(f"命令执行失败: {result.stderr}")
    # 过滤掉任务状态已经是 success 的失败任务
    
    return result.stdout + result.stderr

def run_daily():
    return run_command(["dotnet", "/app/Ray.BiliBiliTool.Console.dll", "--runTasks=Daily"])

def run_single_task(task_cmd):
    return run_command(["dotnet", "/app/Ray.BiliBiliTool.Console.dll", f"--runTasks={task_cmd}"])

def send_wechat(webhook_key, message):
    if not webhook_key:
        log_message("未配置企业微信机器人，跳过推送。", "WARN")
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    payload = {"msgtype": "text", "text": {"content": message}}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        log_message("推送成功。")
    except Exception as e:
        log_message(f"推送失败: {e}", "ERROR")

# ==================== 容器健康检查 ====================
def check_container():
    result = subprocess.run(["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Status}}"], capture_output=True, text=True)
    status = result.stdout.strip()
    if "Up" in status:
        return True
    elif CONTAINER_AUTO_START:
        log_message(f"容器 {CONTAINER_NAME} 未运行，尝试启动...")
        subprocess.run(["docker", "start", CONTAINER_NAME], check=False)
        time.sleep(3)
        result2 = subprocess.run(["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Status}}"], capture_output=True, text=True)
        if "Up" in result2.stdout:
            log_message("容器启动成功。")
            return True
        else:
            log_message("容器启动失败，请手动检查。", "ERROR")
            return False
    else:
        log_message(f"容器 {CONTAINER_NAME} 未运行，且自动启动未开启。", "ERROR")
        return False

# ==================== 数据库操作 ====================
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            username TEXT,
            coins INTEGER,
            exp INTEGER,
            tasks TEXT,
            full_log TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS push_history (
            date TEXT PRIMARY KEY,
            type TEXT,
            pushed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_daily_record(date_str, username, coins, exp, tasks_status, full_log):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO daily_stats (date, username, coins, exp, tasks, full_log)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (date_str, username, coins, exp, json.dumps(tasks_status), full_log[:2000]))
    conn.commit()
    conn.close()

def is_today_pushed(date_str, push_type="daily"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM push_history WHERE date=? AND type=?", (date_str, push_type))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def mark_push_done(date_str, push_type="daily"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO push_history (date, type) VALUES (?, ?)", (date_str, push_type))
    conn.commit()
    conn.close()

# ==================== 日志轮转 ====================
def rotate_logs():
    if LOG_RETENTION_DAYS <= 0:
        return
    cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    pattern = os.path.join(LOG_DIR, "daily_*.log")
    for fpath in glob.glob(pattern):
        try:
            fname = os.path.basename(fpath)
            date_str = fname.replace("daily_", "").replace(".log", "")
            file_date = datetime.strptime(date_str, "%Y%m%d")
            if file_date < cutoff:
                os.remove(fpath)
                log_message(f"删除旧日志: {fpath}")
        except Exception as e:
            log_message(f"处理日志文件 {fpath} 时出错: {e}", "WARN")

# ==================== 错误上下文提取 ====================
def extract_error_context(output, keyword, lines_before=2, lines_after=2):
    lines = output.split('\n')
    for i, line in enumerate(lines):
        if keyword in line:
            start = max(0, i - lines_before)
            end = min(len(lines), i + lines_after + 1)
            context = '\n'.join(lines[start:end])
            return context.strip()
    return None

# ==================== 增强的任务解析函数 ====================
def parse_detailed(output):
    """
    解析日志，提取任务状态和失败任务（通过上下文推断）
    """
    result = {
        "status": "success",
        "username": "未知",
        "coins": "未知",
        "exp": "未知",
        "tasks": {},
        "errors": [],
        "failed_tasks": []
    }

    # 提取用户信息
    m = re.search(r'【用户名】(.*?)\n', output)
    if m:
        result["username"] = m.group(1).strip()
    m = re.search(r'【硬币余额】(\d+)', output)
    if m:
        result["coins"] = m.group(1)
    m = re.search(r'【当前经验】(\d+)', output)
    if m:
        result["exp"] = m.group(1)

    # 解析各任务状态
    task_status = {}
    if "登录成功" in output:
        task_status["登录"] = "success"
    elif "登录失败" in output:
        task_status["登录"] = "failure"
    else:
        task_status["登录"] = "unknown"

    if "视频分享成功" in output or ("今天已经观看过了" in output and "今天已经分享过了" in output):
        task_status["观看/分享"] = "success"
    elif "视频分享失败" in output or "观看失败" in output:
        task_status["观看/分享"] = "failure"
    else:
        task_status["观看/分享"] = "unknown"

    if "已配置为跳过投币任务" in output:
        task_status["投币"] = "skipped"
    elif "投币成功" in output or "已完成投币任务" in output:
        task_status["投币"] = "success"
    else:
        task_status["投币"] = "unknown"

    if "漫画签到" in output:
        if "签到结果】成功" in output or "签到成功" in output:
            task_status["漫画签到"] = "success"
        else:
            task_status["漫画签到"] = "failure"
    else:
        task_status["漫画签到"] = "unknown"

    if "漫画阅读" in output:
        if "成功" in output:
            task_status["漫画阅读"] = "success"
        else:
            task_status["漫画阅读"] = "failure"
    else:
        task_status["漫画阅读"] = "unknown"

    # 银瓜子兑换：当日已兑换视为成功
    if "银瓜子兑换硬币" in output:
        if "成功兑换" in output or "今日剩余兑换次数】0" in output:
            task_status["银瓜子兑换"] = "success"
        else:
            task_status["银瓜子兑换"] = "failure"
    else:
        task_status["银瓜子兑换"] = "unknown"

    # 大会员福利：已领取视为成功
    if "领取大会员福利" in output:
                if "结果】成功" in output:
            task_status["大会员福利"] = "success"
        else:
            task_status["大会员福利"] = "claimed"
    else:
        task_status["大会员福利"] = "unknown"

    if "B币券充电" in output:
                if "充电结果】成功" in output:
            task_status["B币券充电"] = "success"
        elif "跳过" in output and "目标日期" in output:
            task_status["B币券充电"] = "skipped"
        else:
            task_status["B币券充电"] = "claimed"
    else:
        task_status["B币券充电"] = "unknown"

    result["tasks"] = task_status

    # ========== 增强的失败任务识别（基于上下文） ==========
    lines = output.split('\n')
    task_names = list(TASK_CMD_MAP.keys())

    for i, line in enumerate(lines):
        if ("失败" in line or "[ERR]" in line) and \
           "你已领取过该权益" not in line and \
           "领取太频繁" not in line and \
           "今日剩余兑换次数】0" not in line:
            # 先在本行查找任务名
            task_display = None
            cmd = None
            for task in task_names:
                if task in line:
                    task_display = task
                    cmd = TASK_CMD_MAP.get(task)
                    break
            # 若本行没有，上下各3行查找
            if not task_display:
                for offset in range(-3, 4):
                    if offset == 0:
                        continue
                    idx = i + offset
                    if 0 <= idx < len(lines):
                        for task in task_names:
                            if task in lines[idx]:
                                task_display = task
                                cmd = TASK_CMD_MAP.get(task)
                                break
                    if task_display:
                        break
            # 找到了任务则记录（去重）
            if task_display and cmd:
                existing = next((t for t in result["failed_tasks"] if t["cmd"] == cmd), None)
                if not existing:
                    ctx = extract_error_context(output, task_display, 1, 1)
                    result["failed_tasks"].append({
                        "display": task_display,
                        "cmd": cmd,
                        "error": line.strip(),
                        "context": ctx,
                        "retries": []
                    })
            result["errors"].append(line.strip())

    # 排除漫画签到（容器不支持单独重试）
    result["failed_tasks"] = [t for t in result["failed_tasks"] if t["display"] != "漫画签到"]

    # 过滤掉任务状态已经是 success 的失败任务
    result["failed_tasks"] = [t for t in result["failed_tasks"] if result["tasks"].get(t["display"]) not in ("success", "claimed")]
        # 过滤掉任务状态已经是 success 的失败任务
    result["failed_tasks"] = [t for t in result["failed_tasks"] if result["tasks"].get(t["display"]) not in ("success", "claimed")]
    return result

# ==================== 重试策略 ====================
def retry_single_task(cmd, max_attempts=MAX_RETRIES):
    attempts = 0
    success = False
    output = ""
    while attempts < max_attempts:
        attempts += 1
        delay = RETRY_BASE_DELAY * (2 ** (attempts - 1)) if USE_EXPONENTIAL else RETRY_BASE_DELAY
        time.sleep(delay)
        output = run_single_task(cmd)
        if "成功" in output and "失败" not in output:
            success = True
            break
        if "已领取过" in output or "已兑换过" in output or "今日剩余兑换次数】0" in output:
            success = True
            break
        if "账号异常" in output:
            log_message("检测到账号异常，停止重试。", "WARN")
            break
    return success, attempts, output

# ==================== 周期报告 ====================
def get_stats_for_period(start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT date, coins, exp, tasks FROM daily_stats
        WHERE date >= ? AND date <= ?
        ORDER BY date ASC
    ''', (start_date, end_date))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return None
    first = rows[0]
    last = rows[-1]
    coins_start = first[1]
    coins_end = last[1]
    exp_start = first[2]
    exp_end = last[2]
    days = len(rows)
    task_success = {}
    task_total = {}
    for row in rows:
        tasks = json.loads(row[3])
        for task_name, status in tasks.items():
            task_total[task_name] = task_total.get(task_name, 0) + 1
            if status == "success":
                task_success[task_name] = task_success.get(task_name, 0) + 1
    success_rate = {}
    for task, total in task_total.items():
        success_rate[task] = f"{task_success.get(task, 0)}/{total}"
    return {
        "days": days,
        "coins_start": coins_start,
        "coins_end": coins_end,
        "coins_change": coins_end - coins_start,
        "exp_start": exp_start,
        "exp_end": exp_end,
        "exp_change": exp_end - exp_start,
        "success_rate": success_rate
    }

def get_period_start_end(date_obj, period_type):
    if period_type == "weekly":
        start = date_obj - timedelta(days=date_obj.weekday())
        end = date_obj - timedelta(days=1)
        if start > end:
            start = start - timedelta(days=7)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    elif period_type == "monthly":
        first_day = date_obj.replace(day=1)
        end = date_obj - timedelta(days=1)
        if first_day > end:
            first_day = (date_obj.replace(day=1) - timedelta(days=1)).replace(day=1)
        return first_day.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    elif period_type == "quarterly":
        month = date_obj.month
        quarter_start_month = ((month - 1) // 3) * 3 + 1
        start = date_obj.replace(month=quarter_start_month, day=1)
        end = date_obj - timedelta(days=1)
        if start > end:
            if quarter_start_month == 1:
                start = date_obj.replace(year=date_obj.year-1, month=10, day=1)
            else:
                start = date_obj.replace(month=quarter_start_month-3, day=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    elif period_type == "halfyearly":
        half_start_month = 1 if date_obj.month <= 6 else 7
        start = date_obj.replace(month=half_start_month, day=1)
        end = date_obj - timedelta(days=1)
        if start > end:
            if half_start_month == 1:
                start = date_obj.replace(year=date_obj.year-1, month=7, day=1)
            else:
                start = date_obj.replace(year=date_obj.year, month=1, day=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    elif period_type == "yearly":
        start = date_obj.replace(month=1, day=1)
        end = date_obj - timedelta(days=1)
        if start > end:
            start = date_obj.replace(year=date_obj.year-1, month=1, day=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    return None, None

def check_and_send_report(webhook_key, current_date, username):
    periods = [
        ("weekly", "weekly"),
        ("monthly", "monthly"),
        ("quarterly", "quarterly"),
        ("halfyearly", "halfyearly"),
        ("yearly", "yearly")
    ]
    today = current_date
    for period_type, key in periods:
        start_str, end_str = get_period_start_end(today, period_type)
        if not start_str or not end_str:
            continue
        if start_str != today.strftime("%Y-%m-%d"):
            continue
        if DAILY_PUSH_DEDUP and is_today_pushed(today.strftime("%Y-%m-%d"), f"period_{period_type}"):
            log_message(f"今日 {period_type} 报告已推送过，跳过。")
            continue
        stats = get_stats_for_period(start_str, end_str)
        if not stats:
            continue
        header = PUSH_TEMPLATE.get("period_header", {}).get(period_type, f"{period_type}报告")
        msg_lines = []
        msg_lines.append(f"{header}（{start_str} ~ {end_str}）")
        msg_lines.append(f"👤 用户：{username}")
        msg_lines.append(f"📅 周期天数：{stats['days']}")
        msg_lines.append(f"💰 硬币变化：{stats['coins_start']} → {stats['coins_end']}（{'+' if stats['coins_change']>=0 else ''}{stats['coins_change']}）")
        msg_lines.append(f"📈 经验变化：{stats['exp_start']} → {stats['exp_end']}（{'+' if stats['exp_change']>=0 else ''}{stats['exp_change']}）")
        msg_lines.append("**任务成功率**：")
        for task, rate in stats['success_rate'].items():
            msg_lines.append(f"  - {task}：{rate}")
        send_wechat(webhook_key, "\n".join(msg_lines))
        if DAILY_PUSH_DEDUP:
            mark_push_done(today.strftime("%Y-%m-%d"), f"period_{period_type}")
        time.sleep(1)

# ==================== 每日报告推送 ====================
def send_daily_report(webhook_key, result, retry_records, source="定时任务"):
    emoji_map = {"success": "✅", "failure": "❌", "skipped": "⏭️", "claimed": "⭕️", "unknown": "❓"}
    header = PUSH_TEMPLATE.get("daily_header", "📊 **B站每日任务报告**")
    lines = []
    if source == "定时任务":
        lines.append(f"⏰ {header}（定时任务执行成功）")
    else:
        total_attempts = sum(r.get("attempts", 0) for r in retry_records)
        lines.append(f"🔄 {header}（手动任务执行，总重试次数：{total_attempts}）")

    lines.append(f"👤 用户：{result['username']}")
    lines.append(f"🕒 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"💰 硬币余额：{result['coins']}")
    lines.append(f"📈 当前经验：{result['exp']}")
    lines.append("")
    lines.append("**任务执行状态**：")
    for task_name, status in result["tasks"].items():
        emoji = emoji_map.get(status, "❓")
        lines.append(f"  {emoji} {task_name}")

    if result["errors"]:
        lines.append("")
        lines.append("**首次执行错误详情**：")
        for err in result["errors"]:
            lines.append(f"  - {err}")

    if retry_records:
        lines.append("")
        lines.append("**重试记录**：")
        for rec in retry_records:
            if rec["success"]:
                lines.append(f"  ✅ {rec['display']}：第 {rec['attempts']} 次重试成功")
            else:
                lines.append(f"  ❌ {rec['display']}：重试 {rec['attempts']} 次后仍失败")
    else:
        lines.append("")
        lines.append("**无任务需要重试**")

    send_wechat(webhook_key, "\n".join(lines))

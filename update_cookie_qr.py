#!/usr/bin/env python3
"""
B站 Cookie 自动更新 + BiliBiliTool Pro 二维码登录（完整修复版）
"""

import os
import json
import subprocess
import time
import sys
import tempfile
import requests
from datetime import datetime

# ---------- 配置 ----------
BILI_DIR = "/home/zh/bili"
CONFIG_JSON = os.path.join(BILI_DIR, "config.json")
BILIUP_COOKIE = os.path.expanduser("~/.biliup/cookie.json")
WEBHOOK_KEY_FILE = os.path.join(BILI_DIR, ".bili_webhook_key")
CONTAINER_NAME = "bili"
IMAGE = "zai7lou/bilibili_tool_pro:latest"
LOGS_DIR = "/bili/Logs"
LOG_FILE = "/var/log/update_cookie_qr.log"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}")

def run_cmd(cmd, check=False, capture=True, timeout=None):
    log(f"执行命令: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
        if check and result.returncode != 0:
            log(f"命令执行失败: {result.stderr}")
            raise RuntimeError(result.stderr)
        if capture:
            return result.stdout.strip(), result.stderr.strip()
        else:
            return None, None
    except subprocess.TimeoutExpired:
        log("命令执行超时")
        raise

def read_biliup_cookie():
    if not os.path.exists(BILIUP_COOKIE):
        log(f"❌ biliup cookie 文件不存在: {BILIUP_COOKIE}")
        return None
    try:
        with open(BILIUP_COOKIE, 'r') as f:
            data = json.load(f)
        cookie_info = data.get("cookie_info", {})
        cookies_list = cookie_info.get("cookies", [])
        cookie_dict = {}
        for item in cookies_list:
            cookie_dict[item["name"]] = item["value"]
        sessdata = cookie_dict.get("SESSDATA")
        bili_jct = cookie_dict.get("bili_jct")
        dede_user_id = cookie_dict.get("DedeUserID")
        if not all([sessdata, bili_jct, dede_user_id]):
            log("❌ biliup cookie 缺少必需字段")
            return None
        return f"DedeUserID={dede_user_id}; SESSDATA={sessdata}; bili_jct={bili_jct};"
    except Exception as e:
        log(f"❌ 读取 biliup cookie 失败: {e}")
        return None

def update_config_json(new_cookie):
    if not os.path.exists(CONFIG_JSON):
        log(f"❌ config.json 不存在: {CONFIG_JSON}")
        return False
    try:
        with open(CONFIG_JSON, 'r') as f:
            config = json.load(f)
        config["BiliBiliCookies"] = new_cookie
        with open(CONFIG_JSON, 'w') as f:
            json.dump(config, f, indent=2)
        log("✅ config.json 已更新")
        return True
    except Exception as e:
        log(f"❌ 更新 config.json 失败: {e}")
        return False

def get_webhook_key():
    if os.path.exists(WEBHOOK_KEY_FILE):
        with open(WEBHOOK_KEY_FILE, 'r') as f:
            return f.read().strip()
    return None

def deploy_container_with_push(new_cookie, webhook_key):
    log("🔄 重建容器（含推送配置）...")
    run_cmd(["docker", "rm", "-f", CONTAINER_NAME], check=False)

    env_content = f"""Ray_GlobalConfig__Cookies={new_cookie}
Ray_DailyTaskConfig__IsEnable=true
Ray_DailyTaskConfig__NumberOfCoins=0
Ray_DailyTaskConfig__DayOfExchangeSilver2Coin=-2
Ray_DailyTaskConfig__ReadComic=true
Ray_LiveLotteryTaskConfig__IsEnable=true
Ray_VipBigPointConfig__IsEnable=true
Ray_BiBiCoinTaskConfig__IsEnable=true
"""
    if webhook_key:
        env_content += f"""Ray_PushConfig__WebhookUrl=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}
Ray_PushConfig__PushMessageToken={webhook_key}
Ray_PushConfig__IsEnable=true
Ray_PushConfig__PushStrategy=Webhook
"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(env_content)
        env_file = f.name

    cmd = [
        "docker", "run", "--network=host", "-d", "--name", CONTAINER_NAME,
        "-v", f"{LOGS_DIR}:/app/Logs",
        "--env-file", env_file,
        "--restart", "unless-stopped",
        IMAGE
    ]
    stdout, stderr = run_cmd(cmd)
    os.unlink(env_file)
    if stderr and "Error" in stderr:
        log(f"❌ 容器启动失败: {stderr}")
        return False
    log("✅ 容器已重建（含推送配置）")
    return True

def send_success_push():
    """推送更新成功通知到微信"""
    webhook_key = get_webhook_key()
    if not webhook_key:
        log("未配置 Webhook Key，跳过推送")
        return
    try:
        url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
        msg = "✅ **B站 Cookie 已更新，签到已恢复！**\n"
        msg += f"🕒 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        msg += "请检查签到日志或运行 Daily 任务查看详情。"
        requests.post(url, json={"msgtype": "text", "text": {"content": msg}}, timeout=5)
        log("✅ 成功通知已推送至微信")
    except Exception as e:
        log(f"⚠️ 推送成功通知失败: {e}")

def wait_for_login(max_wait=180):
    """等待用户扫码登录（先等待30秒，然后检测Test任务）"""
    log("📱 二维码已推送，请用 B站 App 扫码登录")
    log("⏳ 等待 30 秒供用户扫码...")
    time.sleep(30)
    log("🔍 开始检测登录状态（最多 {} 秒）...".format(max_wait))
    start_time = time.time()
    while time.time() - start_time < max_wait:
        stdout, stderr = run_cmd(["docker", "exec", CONTAINER_NAME, "dotnet", "/app/Ray.BiliBiliTool.Console.dll", "--runTasks=Test"], check=False)
        if "【账号个数】1个" in stdout:
            log("✅ 检测到登录成功")
            return True
        time.sleep(5)
    log("⏰ 等待扫码超时")
    return False

def run_daily():
    """执行 Daily 任务验证"""
    log("🧪 执行 Daily 任务验证...")
    stdout, stderr = run_cmd(["docker", "exec", CONTAINER_NAME, "dotnet", "/app/Ray.BiliBiliTool.Console.dll", "--runTasks=Daily"])
    log(stdout)
    if "运行结束" in stdout:
        log("✅ Daily 任务执行成功")
        return True
    else:
        log("❌ Daily 任务执行失败")
        return False

def main():
    log("========== 开始更新 Cookie + 二维码登录 ==========")
    new_cookie = read_biliup_cookie()
    if not new_cookie:
        log("❌ 无法从 biliup 获取 Cookie，退出")
        sys.exit(1)

    if not update_config_json(new_cookie):
        log("❌ 更新 config.json 失败，退出")
        sys.exit(1)

    webhook_key = get_webhook_key()
    if not webhook_key:
        log("⚠️ 未找到 Webhook Key，将不启用推送配置")

    if not deploy_container_with_push(new_cookie, webhook_key):
        log("❌ 容器重建失败，退出")
        sys.exit(1)

    # 推送二维码链接（调用外部脚本）
    subprocess.run(["/home/zh/bili/auto_login_and_push.sh"], check=False)

    if not wait_for_login(max_wait=180):
        log("❌ 扫码登录超时，请手动扫码或检查网络")
        sys.exit(1)

    if run_daily():
        log("🎉 Cookie 更新 + 扫码登录完成，签到已恢复")
        send_success_push()
    else:
        log("⚠️ Daily 任务执行失败，请检查容器日志")

if __name__ == "__main__":
    main()

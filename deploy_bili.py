#!/usr/bin/env python3
import subprocess
import os
import json
import tempfile
from datetime import datetime

CONFIG_FILE = os.path.expanduser("~/.bili_config.json")
WEBHOOK_KEY_FILE = os.path.expanduser("~/.bili_webhook_key")
CONTAINER_NAME = "bili"
IMAGE = "zai7lou/bilibili_tool_pro:latest"
LOGS_DIR = "/bili/Logs"

def get_input(prompt, default=None, secret=False):
    import getpass
    if secret:
        return getpass.getpass(prompt)
    else:
        return input(prompt)

def get_yes_no(prompt, default="Y"):
    if default.upper() == "Y":
        prompt += " [Y/n]: "
    else:
        prompt += " [y/N]: "
    while True:
        ans = input(prompt).strip().upper()
        if ans == "":
            return default.upper() == "Y"
        if ans in ("Y", "N"):
            return ans == "Y"
        print("请输入 Y 或 N。")

def get_choice(prompt, options, default=None):
    """获取选项选择，返回选中的值"""
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    if default:
        print(f"默认: {default}")
    while True:
        ans = input("请输入序号: ").strip()
        if ans == "" and default:
            return default
        try:
            idx = int(ans) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except:
            pass
        print(f"请输入 1-{len(options)} 之间的数字。")

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"✅ 配置已保存至 {CONFIG_FILE}")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return None

def save_webhook_key(key):
    with open(WEBHOOK_KEY_FILE, 'w') as f:
        f.write(key.strip())

def load_webhook_key():
    if os.path.exists(WEBHOOK_KEY_FILE):
        with open(WEBHOOK_KEY_FILE, 'r') as f:
            return f.read().strip()
    return None

def run_command(cmd, check=False):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout, result.stderr

def get_auto_config(is_vip, level):
    """根据大会员状态和等级自动生成推荐配置"""
    config = {
        "is_vip": is_vip,
        "level": level,
        "enable_coin": False,      # 默认关闭
        "enable_silver_exchange": True,
        "enable_vip_benefits": is_vip,  # 只有大会员才开启
        "recommendations": []
    }
    
    # 投币建议：Lv6 关闭，Lv1-5 开启（为了升级）
    if level <= 5:
        config["enable_coin"] = True
        config["recommendations"].append("💡 您是 Lv{}，建议开启投币获取经验升级。".format(level))
    else:
        config["recommendations"].append("💡 您是 Lv6，建议关闭投币节约硬币。")
    
    # 银瓜子兑换：始终建议开启
    config["recommendations"].append("💡 建议开启银瓜子兑换，每天白嫖1枚硬币。")
    
    # 大会员权益
    if is_vip:
        config["recommendations"].append("💡 您是大会员，建议开启权益兑换（B币券/大积分）。")
    else:
        config["recommendations"].append("ℹ️ 您不是大会员，大会员权益已自动关闭。")
    
    return config

def show_config_summary(config):
    """显示配置摘要并让用户确认/修改"""
    print("\n" + "="*50)
    print("📋 根据您的账号信息，自动生成以下配置：")
    print(f"  会员状态: {'✅ 大会员' if config['is_vip'] else '❌ 普通会员'}")
    print(f"  会员等级: Lv{config['level']}")
    print(f"  每日投币: {'✅ 开启（5枚/天）' if config['enable_coin'] else '❌ 关闭'}")
    print(f"  银瓜子兑换: {'✅ 开启' if config['enable_silver_exchange'] else '❌ 关闭'}")
    print(f"  大会员权益: {'✅ 开启' if config['enable_vip_benefits'] else '❌ 关闭'}")
    if config.get("recommendations"):
        print("\n📌 推荐说明：")
        for rec in config["recommendations"]:
            print(f"  {rec}")
    print("="*50)
    
    if not get_yes_no("是否使用以上配置？", default="Y"):
        print("\n🔄 手动调整配置：")
        config["enable_coin"] = get_yes_no("是否开启每日投币？", default="Y" if config["enable_coin"] else "N")
        config["enable_silver_exchange"] = get_yes_no("是否开启银瓜子兑换硬币？", default="Y")
        if config["is_vip"]:
            config["enable_vip_benefits"] = get_yes_no("是否开启大会员权益兑换？", default="Y")
        else:
            config["enable_vip_benefits"] = False
            print("ℹ️ 您不是大会员，大会员权益已锁定关闭。")
    return config

def deploy_container(cookie, webhook_key, config):
    env_content = f"""Ray_GlobalConfig__Cookies={cookie}
Ray_DailyTaskConfig__IsEnable=true
Ray_DailyTaskConfig__ReadComic=true
Ray_LiveLotteryTaskConfig__IsEnable=true
Ray_UnfollowBatchedTaskConfig__Cron=0 6 1 * *
Ray_LiveLotteryTaskConfig__Cron=0 22 * * *
Ray_VipBigPointConfig__Cron=7 1 * * *
"""
    # 投币
    if config.get("enable_coin", False):
        env_content += "Ray_DailyTaskConfig__NumberOfCoins=5\n"
        env_content += "Ray_DailyTaskConfig__SelectLike=true\n"
    else:
        env_content += "Ray_DailyTaskConfig__NumberOfCoins=0\n"
    
    # 银瓜子兑换
    if config.get("enable_silver_exchange", True):
        env_content += "Ray_DailyTaskConfig__DayOfExchangeSilver2Coin=-2\n"
    else:
        env_content += "Ray_DailyTaskConfig__DayOfExchangeSilver2Coin=0\n"
    
    # 大会员权益
    if config.get("enable_vip_benefits", False):
        env_content += "Ray_VipBigPointConfig__IsEnable=true\n"
        env_content += "Ray_BiBiCoinTaskConfig__IsEnable=true\n"
    else:
        env_content += "Ray_VipBigPointConfig__IsEnable=false\n"
        env_content += "Ray_BiBiCoinTaskConfig__IsEnable=false\n"
    
    if webhook_key:
        env_content += f"""Ray_PushConfig__WebhookUrl=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}
Ray_PushConfig__PushMessageToken={webhook_key}
Ray_PushConfig__IsEnable=true
Ray_PushConfig__PushStrategy=Webhook
"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(env_content)
        env_file = f.name

    run_command(["docker", "rm", "-f", CONTAINER_NAME], check=False)
    cmd = [
        "docker", "run", "--network=host", "-d", "--name", CONTAINER_NAME,
        "-v", f"{LOGS_DIR}:/app/Logs",
        "--env-file", env_file,
        "--restart", "unless-stopped",
        IMAGE
    ]
    stdout, stderr = run_command(cmd)
    os.unlink(env_file)
    if stderr and "Error" in stderr:
        print(f"❌ 部署失败: {stderr}")
        return False
    print("✅ 容器部署成功。")
    return True

def login():
    print("\n📱 现在执行扫码登录，请准备 B 站 App 扫码。")
    input("按 Enter 键继续...")
    cmd = ["docker", "exec", "-it", CONTAINER_NAME,
           "dotnet", "/app/Ray.BiliBiliTool.Console.dll", "--runTasks=Login"]
    proc = subprocess.Popen(cmd)
    proc.wait()
    print("扫码登录完成。")

def run_daily():
    cmd = ["docker", "exec", CONTAINER_NAME,
           "dotnet", "/app/Ray.BiliBiliTool.Console.dll", "--runTasks=Daily"]
    stdout, stderr = run_command(cmd)
    return stdout + stderr

def main():
    print("=== BiliBiliToolPro 一键部署（智能配置） ===")
    
    # 1. 输入 Cookie
    cookie = get_input("请输入 B 站 Cookie（完整字符串）: ")
    if not cookie:
        print("❌ Cookie 不能为空，退出。")
        return

    # 2. 输入机器人 Key
    webhook_key = get_input("请输入企业微信机器人 Key（留空则禁用推送）: ")
    if webhook_key:
        save_webhook_key(webhook_key)
        print("✅ 机器人 Key 已保存。")
    else:
        saved = load_webhook_key()
        if saved:
            webhook_key = saved
            print(f"自动读取已保存的机器人 Key: {webhook_key}")

    # 3. 智能配置
    print("\n--- 请确认您的账号信息 ---")
    is_vip = get_yes_no("您是否是大会员？", default="Y")
    level = int(get_choice("请选择您的会员等级：", ["Lv1", "Lv2", "Lv3", "Lv4", "Lv5", "Lv6"], default="Lv6").replace("Lv", ""))
    
    # 生成自动配置
    config = get_auto_config(is_vip, level)
    config = show_config_summary(config)
    save_config(config)

    # 4. 部署容器
    if not deploy_container(cookie, webhook_key, config):
        return

    # 5. 扫码登录
    login()

    # 6. 执行每日任务测试
    print("\n🧪 执行 Daily 任务测试...")
    output = run_daily()
    print(output)

    print("\n🎉 部署完成！容器每天 15:00 自动签到。")
    print("查看日志: docker logs bili -f")

if __name__ == "__main__":
    main()

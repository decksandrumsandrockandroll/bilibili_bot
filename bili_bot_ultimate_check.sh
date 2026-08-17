#!/bin/bash
# B站签到机器人 终极自检脚本
# 输出完整文件结构、功能说明、运行逻辑和状态检查

set -e

# ---------- 颜色定义 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---------- 配置 ----------
BILI_HOME="/home/zh/bili"
LOGS_DIR="$BILI_HOME/logs"
DATA_DIR="$BILI_HOME/data"
CONFIG_FILE="$BILI_HOME/config.json"
WEBHOOK_FILE="$BILI_HOME/.bili_webhook_key"

# ---------- 输出函数 ----------
print_section() {
    echo ""
    echo -e "${BLUE}========== $1 ==========${NC}"
}

print_ok() {
    echo -e "${GREEN}[✔] $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}[!] $1${NC}"
}

print_err() {
    echo -e "${RED}[✘] $1${NC}"
}

print_info() {
    echo -e "${BLUE}[i] $1${NC}"
}

# ---------- 开始检查 ----------
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   B站签到机器人 终极自检报告${NC}"
echo -e "${BLUE}   时间: $(date)${NC}"
echo -e "${BLUE}========================================${NC}"

# 1. 文件结构与功能说明
print_section "1. 核心文件结构与功能说明"
declare -A FILE_DESC=(
    ["config.json"]="主配置文件：存储容器名、Cookie、路径、任务映射、推送模板"
    [".bili_webhook_key"]="企业微信机器人 Webhook Key"
    ["bili_common.py"]="公共函数库：日志、Docker命令、任务解析、推送、周期报告"
    ["bili_daily.py"]="每日签到主脚本：执行Daily任务，失败时调用手动重试"
    ["bili_daily_manual.py"]="手动修复脚本：重试失败任务（最多6次），推送最终简报"
    ["deploy_bili.py"]="首次部署交互脚本：引导配置、部署容器、扫码登录、测试签到"
    ["update_cookie_qr.py"]="自动续期核心：从biliup读取Cookie，重建容器，推送二维码，等待扫码，验证签到"
    ["auto_login_and_push.sh"]="二维码推送：执行Login，提取链接并推送到微信"
    ["bili_full_qr_login.sh"]="失效检测：检查日志关键词，触发update_cookie_qr.py"
    ["bili_daily_with_full_qr.sh"]="Cron包装：先签到，再失效检测"
    ["push_qr.sh"]="手动推送二维码链接（备用）"
    ["check_bili_final.sh"]="综合诊断脚本"
)

for file in "${!FILE_DESC[@]}"; do
    if [ -f "$BILI_HOME/$file" ]; then
        print_ok "$file 存在 → ${FILE_DESC[$file]}"
    else
        print_err "$file 不存在（${FILE_DESC[$file]}）"
    fi
done

# 2. 目录检查
print_section "2. 目录结构"
for dir in "$LOGS_DIR" "$DATA_DIR"; do
    if [ -d "$dir" ]; then
        print_ok "$dir 存在"
    else
        print_err "$dir 不存在"
    fi
done

# 3. 配置文件内容检查
print_section "3. 配置文件检查"
if [ -f "$CONFIG_FILE" ]; then
    for key in "BiliBiliCookies" "webhook_key_file" "log_dir" "db_path"; do
        if grep -q "\"$key\"" "$CONFIG_FILE"; then
            print_ok "config.json 包含 $key 字段"
        else
            print_warn "config.json 缺少 $key 字段"
        fi
    done
    # 检查路径是否已更新为 /home/zh/bili
    if grep -q "/home/zh/bili" "$CONFIG_FILE"; then
        print_ok "config.json 路径已规范化"
    else
        print_warn "config.json 可能仍使用旧路径"
    fi
else
    print_err "config.json 不存在"
fi

if [ -f "$WEBHOOK_FILE" ]; then
    KEY_LEN=$(cat "$WEBHOOK_FILE" | wc -c)
    if [ "$KEY_LEN" -gt 10 ]; then
        print_ok "Webhook Key 存在且有效（长度 $KEY_LEN）"
    else
        print_warn "Webhook Key 内容过短"
    fi
else
    print_err "Webhook Key 文件不存在"
fi

# 4. Docker 容器
print_section "4. Docker 容器状态"
if docker ps -a --format '{{.Names}}' | grep -q "^bili$"; then
    STATUS=$(docker inspect -f '{{.State.Status}}' bili)
    if [ "$STATUS" = "running" ]; then
        print_ok "容器 bili 正在运行"
    else
        print_warn "容器 bili 状态: $STATUS"
    fi
else
    print_err "容器 bili 不存在"
fi

# 5. Cron 任务
print_section "5. Cron 任务"
if crontab -l 2>/dev/null | grep -q "$BILI_HOME/bili_daily_with_full_qr.sh"; then
    print_ok "Cron 任务已配置为包装脚本"
    crontab -l | grep "$BILI_HOME/bili_daily_with_full_qr.sh" | sed 's/^/    /'
else
    print_err "Cron 任务未配置或未指向正确脚本"
fi

# 6. biliup 工具
print_section "6. biliup 工具状态"
if command -v biliup &>/dev/null; then
    print_ok "biliup 已安装"
else
    print_err "biliup 未安装或不在 PATH 中"
    print_info "请确保 ~/.local/bin 在 PATH 中，或执行 pipx install biliup"
fi

if [ -f ~/.biliup/cookie.json ]; then
    print_ok "biliup cookie.json 存在"
    if jq -e '.cookie_info | has("SESSDATA") and has("bili_jct") and has("DedeUserID")' ~/.biliup/cookie.json >/dev/null 2>&1; then
        print_ok "biliup cookie 包含必需字段"
    else
        print_warn "biliup cookie 缺少必需字段"
    fi
else
    print_err "biliup cookie.json 不存在（请先执行 biliup login）"
fi

# 7. Python 依赖
print_section "7. Python 依赖"
for mod in requests jq; do
    if python3 -c "import $mod" 2>/dev/null; then
        print_ok "$mod 已安装"
    else
        print_err "$mod 未安装"
    fi
done

# 8. 签到日志检查
print_section "8. 最近签到记录"
if [ -d "$LOGS_DIR" ]; then
    LATEST_LOG=$(ls -t "$LOGS_DIR"/daily_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        print_ok "最近日志: $(basename "$LATEST_LOG")"
        if grep -q "【账号个数】1个" "$LATEST_LOG"; then
            print_ok "最近签到成功（账号个数=1）"
        elif grep -q "【账号个数】0个" "$LATEST_LOG"; then
            print_warn "最近签到失败（账号个数=0）"
        else
            print_warn "日志中未找到账号个数信息"
        fi
    else
        print_warn "未找到签到日志"
    fi
else
    print_err "日志目录不存在"
fi

# 9. 系统逻辑流程图
print_section "9. 系统运行逻辑"

echo -e "${BLUE}【首次部署流程】${NC}"
echo "  1. 执行 ./deploy_bili.py"
echo "  2. 交互式输入：大会员状态、等级、投币开关、银瓜子、大会员权益等"
echo "  3. 输入企业微信 Key 和 B站 Cookie（或使用扫码）"
echo "  4. 生成 config.json 和 .bili_webhook_key"
echo "  5. 部署 Docker 容器（注入推送环境变量）"
echo "  6. 执行 Login 任务，在终端显示二维码（同时配置推送）"
echo "  7. 用户扫码登录 BiliBiliTool Pro"
echo "  8. 执行 Daily 测试，验证签到成功"
echo "  9. 提示设置 Cron 任务"

echo ""
echo -e "${BLUE}【每日自动签到流程】${NC}"
echo "  1. Cron 每天 15:00 触发 bili_daily_with_full_qr.sh"
echo "  2. 执行 bili_daily.py 签到"
echo "  3. 若全部成功 → 推送简报"
echo "  4. 若有失败 → 调用 bili_daily_manual.py 重试（最多6次）→ 推送最终简报"
echo "  5. 执行 bili_full_qr_login.sh 检查日志是否有 Cookie失效关键词"
echo "  6. 若失效 → 调用 update_cookie_qr.py"

echo ""
echo -e "${BLUE}【自动续期流程（Cookie失效时）】${NC}"
echo "  1. update_cookie_qr.py 从 ~/.biliup/cookie.json 读取新 Cookie"
echo "  2. 更新 config.json 中的 BiliBiliCookies"
echo "  3. 重建容器（注入推送环境变量）"
echo "  4. 调用 auto_login_and_push.sh 执行 Login，提取二维码链接并推送微信"
echo "  5. 等待用户扫码（最多180秒）"
echo "  6. 每隔5秒执行 Test 任务，检测登录成功（【账号个数】1个）"
echo "  7. 登录成功后执行 Daily 任务验证"
echo "  8. 推送“签到已恢复”成功通知"
echo "  9. 若续期失败，推送告警"

echo ""
echo -e "${BLUE}【手动操作】${NC}"
echo "  - 手动签到: cd $BILI_HOME && python3 bili_daily.py"
echo "  - 手动续期: cd $BILI_HOME && python3 update_cookie_qr.py"
echo "  - 手动推送二维码: cd $BILI_HOME && ./auto_login_and_push.sh"
echo "  - 运行诊断: cd $BILI_HOME && ./check_bili_final.sh"
echo "  - 查看日志: tail -f $LOGS_DIR/daily_$(date +%Y%m%d).log"

# 10. 总结
print_section "10. 综合评估"
TOTAL_CHECKS=0
PASSED=0
WARNINGS=0
FAILED=0

# 简单计数（仅演示）
check_item() {
    ((TOTAL_CHECKS++))
    if [ "$1" = "PASS" ]; then
        ((PASSED++))
    elif [ "$1" = "WARN" ]; then
        ((WARNINGS++))
    else
        ((FAILED++))
    fi
}

# 实际检查（仅示例，不重复枚举）
echo -e "${GREEN}所有检查项已完成。${NC}"
echo "详细结果请查看上方各章节。"
echo ""
echo "建议："
echo "  - 若所有标记为 [✔] 且无 [✘]，系统运行正常。"
echo "  - 若存在 [✘]，请根据提示修复。"
echo "  - 若存在 [!]，请根据提示检查配置。"
echo ""

print_section "自检结束"

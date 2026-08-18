# B站签到机器人 系统状态报告

> 生成时间: 2026-08-18
> 版本: v1.0.0

---

## ✅ 自检结果

| 模块 | 状态 | 说明 |
|------|------|------|
| 核心文件 | ✅ 通过 | 12/12 文件全部就绪 |
| 目录结构 | ✅ 通过 | logs/ data/ 均存在 |
| 配置文件 | ✅ 通过 | 包含所有必需字段 |
| Webhook Key | ✅ 通过 | 有效（长度 36） |
| Docker 容器 | ✅ 通过 | 运行中 |
| Cron 任务 | ✅ 通过 | 已配置包装脚本 |
| biliup 工具 | ✅ 通过 | 已安装，Cookie 完整 |
| Python 依赖 | ✅ 通过 | requests / jq 已安装 |
| 最近签到 | ✅ 通过 | 账号正常，签到成功 |

---

## 🧩 功能状态

| 功能 | 状态 |
|------|------|
| 首次部署 | ✅ 就绪 |
| 每日签到 | ✅ 就绪 |
| 失败重试 | ✅ 就绪 |
| Cookie 失效检测 | ✅ 就绪 |
| Cookie 自动续期 | ✅ 就绪 |
| 企业微信推送 | ✅ 就绪 |
| 周期报告 | ✅ 就绪 |
| 诊断工具 | ✅ 就绪 |

---

## 📌 系统运行逻辑

### 每日自动签到流程
```
Cron (15:00) → bili_daily_with_full_qr.sh
    → bili_daily.py 签到
        → 全部成功 → 推送简报
        → 有失败 → bili_daily_manual.py 重试 → 推送最终简报
    → bili_full_qr_login.sh 失效检测
        → 检测到 Cookie 失效 → update_cookie_qr.py 自动续期
```

### Cookie 自动续期流程
```
update_cookie_qr.py
    → 读取 ~/.biliup/cookie.json
    → 更新 config.json
    → 重建容器
    → 推送二维码链接到微信
    → 用户扫码
    → 检测登录成功
    → 执行 Daily 验证
    → 推送成功通知
```

---

## 🔒 隐私说明

本报告仅包含系统状态和运行逻辑，**不包含任何个人隐私信息**，包括：
- B站 Cookie / Token（未显示）
- 企业微信 Webhook Key（未显示）
- 个人邮箱或用户名
- 硬币余额 / 账号信息

可放心公开分享。

---

## 📚 相关链接

- [项目仓库](https://github.com/decksandrumsandrockandroll/bilibili_bot)
- [BiliBiliToolPro](https://github.com/RayWangQvQ/BiliBiliToolPro)
- [biliup](https://github.com/biliup/biliup)

---

*本报告由 B站签到机器人 自检脚本自动生成*

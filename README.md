# B站签到机器人

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)

> 基于 Docker 的 B站签到自动化系统，支持每日自动签到、失败重试、Cookie 自动续期、企业微信推送。

---

## 📌 项目简介

本项目整合了 [BiliBiliToolPro](https://github.com/RayWangQvQ/BiliBiliToolPro) 和 [biliup](https://github.com/biliup/biliup)，构建了一套完整的 B站签到自动化解决方案。

**核心交互方式**：

- **首次部署**：终端完成双码登录（BiliBiliToolPro + biliup），一次配置长期有效
- **Cookie 自动续期**：微信推送二维码链接，完全远程扫码，无需登录服务器

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| **每日定时签到** | 每天 15:00 自动执行 B站每日任务（签到、投币、观看分享等） |
| **失败任务重试** | 单个任务失败后自动重试（最多 6 次），并推送最终简报 |
| **Cookie 自动续期** | 通过 biliup 的 refresh_token 机制，在 Cookie 失效时自动完成续期 |
| **双模式二维码登录** | 首次部署在终端扫码，Cookie 续期时微信远程扫码，兼顾安全与便利 |
| **周期统计报告** | 在周、月、季、半年、年的第一天自动推送上一周期的数据统计 |
| **企业微信推送** | 所有通知（签到结果、续期状态、错误告警）均实时推送到企业微信群 |
| **一键部署与诊断** | 提供交互式部署脚本和全面诊断工具，降低使用门槛 |

---

## 🧠 系统架构与运行逻辑

### 整体架构

```mermaid
graph TD
    A[Cron 每天15:00] --> B[bili_daily_with_full_qr.sh]
    B --> C[bili_daily.py 签到]
    C --> D{是否有失败任务?}
    D -->|是| E[bili_daily_manual.py 重试]
    E --> F[推送最终简报]
    D -->|否| G[推送成功简报]
    B --> H[bili_full_qr_login.sh 失效检测]
    H --> I{日志中是否有 Cookie失效?}
    I -->|是| J[update_cookie_qr.py 自动续期]
    I -->|否| K[结束]
    J --> L[从 biliup 读取 Cookie]
    L --> M[更新 config.json]
    M --> N[重建容器]
    N --> O[推送登录二维码链接到微信]
    O --> P[用户在微信点击链接扫码]
    P --> Q[检测登录成功]
    Q --> R[执行 Daily 验证]
    R --> S[推送成功通知]
    H --> K

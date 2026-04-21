# Grok 账号批量注册工具

基于 [DrissionPage](https://github.com/g1879/DrissionPage) 的 Grok (x.ai) 账号自动注册脚本，使用 [CloudMail](https://github.com/dreamhunter2333/cloud_mail) 自建邮箱服务接收验证码，通过 Chrome 扩展修复 CDP `MouseEvent.screenX/screenY` 缺陷绕过 Cloudflare Turnstile。

注册完成后自动推送 SSO token 到 [grok2api](https://github.com/chenyme/grok2api) 号池。

## 特性

- CloudMail 自建邮箱（`curl_cffi` TLS 指纹伪装，支持 Public Token / JWT 双模式轮询）
- Cloudflare Turnstile 自动绕过（Chrome 扩展 patch `MouseEvent.screenX/screenY`）
- 无头服务器支持（Xvfb 虚拟显示器，自动检测 Linux 环境）
- 中英文界面自动适配
- 自动推送 SSO token 到 grok2api（支持 append 合并模式）
- 每轮独立浏览器 Profile，避免 Cookie/Session 复用
- 完善的错误恢复和重试机制

---

## 环境要求

- Python 3.10+（推荐 3.12 / 3.13，3.14+ 可能有 TLS 兼容问题）
- Chromium 或 Chrome 浏览器
- [CloudMail](https://github.com/dreamhunter2333/cloud_mail) 实例（自建邮箱服务）
- 可选：[grok2api](https://github.com/chenyme/grok2api) 实例（用于自动导入 SSO token）

---

## 安装

```bash
# 克隆项目
git clone https://github.com/Luckylos/grok-register.git
cd grok-register

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

无头服务器（Linux）额外安装：

```bash
apt install -y xvfb
pip install PyVirtualDisplay
# 推荐用 playwright 装 chromium（避免 snap 版 AppArmor 限制）
pip install playwright && python -m playwright install chromium && python -m playwright install-deps chromium
```

---

## 配置文件（config.json）

```bash
cp config.example.json config.json
```

编辑 `config.json`：

```json
{
  "run": {
    "count": 10
  },
  "cloudmail_api_base": "https://your-cloudmail-domain.com",
  "cloudmail_public_token": "",
  "cloudmail_email_domain": "your-domain.com",
  "cloudmail_admin_email": "admin@your-domain.com",
  "cloudmail_admin_password": "",
  "proxy": "",
  "browser_proxy": "",
  "api": {
    "endpoint": "",
    "token": "",
    "append": true
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `run.count` | int | 注册轮数，`0` 为无限循环，可通过 `--count` 覆盖 |
| `cloudmail_api_base` | string | CloudMail API 地址，如 `https://mail.example.com` |
| `cloudmail_public_token` | string | CloudMail Public Token（可选，留空则自动通过管理员账号生成） |
| `cloudmail_email_domain` | string | CloudMail 邮箱域名，如 `example.com` |
| `cloudmail_admin_email` | string | CloudMail 管理员邮箱（用于生成 Public Token） |
| `cloudmail_admin_password` | string | CloudMail 管理员密码 |
| `proxy` | string | CloudMail API 请求代理（可选，如 `http://127.0.0.1:7890`） |
| `browser_proxy` | string | 浏览器代理，无头服务器需翻墙时填写（可选） |
| `api.endpoint` | string | grok2api 管理 API 地址，如 `http://127.0.0.1:8000/admin/api/tokens/add`，留空跳过推送 |
| `api.token` | string | grok2api 的 `app_key`（非 `api_key`） |
| `api.append` | bool | `true` 合并线上已有 token，`false` 覆盖 |

---

## CloudMail 部署

本项目使用 [CloudMail](https://github.com/dreamhunter2333/cloud_mail) 作为邮箱服务，需提前部署。

### 快速部署（Docker Compose）

参考 [CloudMail 官方文档](https://github.com/dreamhunter2333/cloud_mail) 部署，大致流程：

1. 准备一个域名并配置 MX 记录指向服务器
2. 使用 Docker Compose 启动 CloudMail
3. 创建管理员账号
4. 生成 Public Token（或在 `config.json` 中填写管理员凭据自动生成）

### 获取 Public Token

如果 `cloudmail_public_token` 留空，脚本会自动用 `cloudmail_admin_email` / `cloudmail_admin_password` 登录并生成。

手动获取方式：

1. 用管理员账号登录 CloudMail
2. 在设置中生成 Public Token
3. 填入 `config.json` 的 `cloudmail_public_token` 字段

---

## grok2api 推送配置

注册完成后，脚本可自动将 SSO token 推送到 grok2api 号池。

### 配置方式

1. `api.endpoint`：填写 grok2api 的管理 API 地址
   - 推荐使用：`http://<grok2api_host>:<port>/admin/api/tokens/add`
2. `api.token`：填写 grok2api 的 `app_key`（在 grok2api 的 `config.toml` 中 `[app]` → `app_key`）
3. `api.append`：
   - `true`（默认）：先查询线上已有 token，合并本次新增后全量推送，保护存量数据
   - `false`：直接用本次 token 列表覆盖，慎用

> ⚠️ 注意：`api.token` 使用的是 grok2api 的 **`app_key`**（管理密钥），不是 `api_key`（客户端调用密钥）。

---

## 启动方式

```bash
# 激活虚拟环境
source .venv/bin/activate

# 按 config.json 中 run.count 执行（默认 10 轮）
python DrissionPage_example.py

# 指定轮数
python DrissionPage_example.py --count 50

# 无限循环
python DrissionPage_example.py --count 0

# 指定 SSO 输出路径
python DrissionPage_example.py --output sso/my_tokens.txt

# 注册完成后额外提取页面数字文本
python DrissionPage_example.py --extract-numbers
```

无头服务器会自动启用 Xvfb，无需额外配置。

---

## 输出文件

```
sso/
  sso_<timestamp>.txt    ← 每行一个 SSO token，持续追加
logs/
  run_<timestamp>.log    ← 每轮注册的邮箱、密码和结果
```

目录在首次运行时自动创建。

---

## 文件结构

```
├── DrissionPage_example.py   # 主脚本（注册流程、浏览器控制、SSO 采集）
├── email_register.py         # CloudMail 临时邮箱封装（创建邮箱、轮询验证码）
├── config.json               # 配置文件（不入库，含敏感信息）
├── config.example.json       # 配置模板
├── requirements.txt          # Python 依赖
├── readme.md                 # 项目文档
├── .gitignore                # Git 忽略规则
├── turnstilePatch/           # Chrome 扩展（Turnstile screenX/screenY patch）
│   ├── manifest.json
│   └── script.js
├── sso/                      # SSO token 输出（自动创建，不入库）
└── logs/                     # 运行日志（自动创建，不入库）
```

---

## 注册流程

```
打开 x.ai 注册页 → 点击"使用邮箱注册"
    → 填写 CloudMail 临时邮箱 → 点击注册
    → 轮询 CloudMail 获取 OTP 验证码 → 填写验证码
    → 绕过 Turnstile → 填写姓名/密码 → 点击完成注册
    → 等待 sso cookie → 写入文件 → 推送到 grok2api
    → 关闭浏览器 → 进入下一轮
```

---

## 无头服务器部署注意

- snap 版 chromium 在 root 下有 AppArmor 限制，推荐用 `playwright install chromium` 安装
- 服务器直连 x.ai 可能被墙，需在 `browser_proxy` 填写代理地址
- 脚本自动检测 Linux 环境并启用 Xvfb + playwright chromium 路径
- 每轮注册使用独立浏览器 Profile，注册完成后自动清理

---

## 常见问题

### Q: 验证码获取超时？
A: 检查 CloudMail 邮件服务是否正常运行，以及 `proxy` 配置是否正确。脚本会自动在 JWT 和 Public Token 两种模式间回退。

### Q: Turnstile 验证失败？
A: 确保 `turnstilePatch/` 扩展被正确加载。4K 屏幕环境下需要使用新版本的 screenX/screenY patch（已内置）。

### Q: 推送 SSO token 到 grok2api 失败？
A: 确认 `api.endpoint` 和 `api.token` 配置正确。`api.token` 应使用 grok2api 的 `app_key`，不是 `api_key`。grok2api 管理端点路径为 `/admin/api/tokens/add`。

### Q: Python 3.14 下出现 TLS 异常？
A: 建议使用 Python 3.12 或 3.13。脚本会自动检测并在 Windows 上尝试切换到更稳定的 Python 版本。

---

## 致谢

- [kevinr229/grok-maintainer](https://github.com/kevinr229/grok-maintainer) — 原始项目
- [grok2api](https://github.com/chenyme/grok2api) — Grok API 代理
- [CloudMail](https://github.com/dreamhunter2333/cloud_mail) — 自建邮箱服务
- [DrissionPage](https://github.com/g1879/DrissionPage) — 浏览器自动化框架

from __future__ import annotations

import json
import logging
import random
import re
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# CloudMail 配置（从 config.json 加载）
# ============================================================

_config_path = Path(__file__).parent / "config.json"
_conf: Dict[str, Any] = {}
if _config_path.exists():
    with _config_path.open("r", encoding="utf-8") as _f:
        _conf = json.load(_f)

CLOUDMAIL_API_BASE = str(_conf.get("cloudmail_api_base", "")).rstrip("/")
CLOUDMAIL_PUBLIC_TOKEN = str(_conf.get("cloudmail_public_token", ""))
CLOUDMAIL_EMAIL_DOMAIN = str(_conf.get("cloudmail_email_domain", ""))
CLOUDMAIL_ADMIN_EMAIL = str(_conf.get("cloudmail_admin_email", ""))
CLOUDMAIL_ADMIN_PASSWORD = str(_conf.get("cloudmail_admin_password", ""))
PROXY = str(_conf.get("proxy", ""))

# ============================================================
# 适配层：为 DrissionPage_example.py 提供简单接口
# ============================================================

# 每个临时邮箱对应的 CloudMail 用户信息缓存
# key: email, value: {"user_id": ..., "account_id": ..., "jwt_token": ...}
_email_user_cache: Dict[str, Dict[str, Any]] = {}

# Public Token 缓存（避免每次都重新生成）
_public_token_cache: Optional[str] = None


def get_email_and_token() -> Tuple[Optional[str], Optional[str]]:
    """
    创建 CloudMail 临时邮箱并返回 (email, jwt_token)。
    供 DrissionPage_example.py 调用。
    jwt_token 用于后续轮询邮件。
    """
    email, user_info = create_temp_email()
    if email and user_info:
        _email_user_cache[email] = user_info
        return email, user_info["jwt_token"]
    return None, None


def get_oai_code(dev_token: str, email: str, timeout: int = 120) -> Optional[str]:
    """
    轮询 CloudMail 获取 OTP 验证码。
    供 DrissionPage_example.py 调用。

    Args:
        dev_token: CloudMail JWT Token
        email: 邮箱地址（用于查找 account_id）
        timeout: 超时秒数

    Returns:
        验证码字符串（去除连字符，如 "MM0SF3"）或 None
    """
    user_info = _email_user_cache.get(email, {})
    account_id = user_info.get("account_id", 0)
    code = wait_for_verification_code(
        jwt_token=dev_token,
        account_id=account_id,
        email=email,
        timeout=timeout,
    )
    if code:
        code = code.replace("-", "")
    return code


# ============================================================
# CloudMail 核心函数
# ============================================================

def _create_session():
    """创建请求会话（优先 curl_cffi 绕 TLS 指纹）"""
    if curl_requests:
        session = curl_requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        if PROXY:
            session.proxies = {"http": PROXY, "https": PROXY}
        return session, True

    # fallback to requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    if PROXY:
        s.proxies = {"http": PROXY, "https": PROXY}
    return s, False


def _do_request(session, use_cffi, method, url, **kwargs):
    """统一请求，curl_cffi 加 impersonate 参数"""
    if use_cffi:
        kwargs.setdefault("impersonate", "chrome131")
    return getattr(session, method)(url, **kwargs)


def _generate_password(length=14):
    """生成符合 CloudMail 要求的密码（6-30位，含大小写+数字+特殊字符）"""
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%"
    pwd = [random.choice(lower), random.choice(upper),
           random.choice(digits), random.choice(special)]
    all_chars = lower + upper + digits + special
    pwd += [random.choice(all_chars) for _ in range(length - 4)]
    random.shuffle(pwd)
    return "".join(pwd)


def _get_public_token() -> str:
    """
    获取 CloudMail Public Token。
    如果已有缓存且未过期则直接返回，否则通过管理员 JWT 重新生成。
    """
    global _public_token_cache

    if _public_token_cache:
        return _public_token_cache

    if not CLOUDMAIL_ADMIN_EMAIL or not CLOUDMAIL_ADMIN_PASSWORD:
        raise Exception("cloudmail_admin_email / cloudmail_admin_password 未设置，无法获取 Public Token")

    session, use_cffi = _create_session()
    api_base = CLOUDMAIL_API_BASE

    # 1. 管理员登录获取 JWT
    login_resp = _do_request(session, use_cffi, "post",
        f"{api_base}/api/login",
        json={"email": CLOUDMAIL_ADMIN_EMAIL, "password": CLOUDMAIL_ADMIN_PASSWORD},
        timeout=15)
    if login_resp.status_code != 200:
        raise Exception(f"CloudMail 管理员登录失败: {login_resp.status_code} - {login_resp.text[:200]}")

    login_data = login_resp.json()
    if login_data.get("code") != 200:
        raise Exception(f"CloudMail 管理员登录失败: {login_data.get('message', '未知错误')}")

    admin_jwt = login_data.get("data", {}).get("token")
    if not admin_jwt:
        raise Exception("CloudMail 管理员登录成功但未获取到 JWT Token")

    # 2. 生成 Public Token
    time.sleep(0.3)
    gen_resp = _do_request(session, use_cffi, "post",
        f"{api_base}/api/public/genToken",
        json={"email": CLOUDMAIL_ADMIN_EMAIL, "password": CLOUDMAIL_ADMIN_PASSWORD},
        headers={"Authorization": admin_jwt},
        timeout=15)
    if gen_resp.status_code != 200:
        raise Exception(f"CloudMail 生成 Public Token 失败: {gen_resp.status_code} - {gen_resp.text[:200]}")

    gen_data = gen_resp.json()
    if gen_data.get("code") != 200:
        raise Exception(f"CloudMail 生成 Public Token 失败: {gen_data.get('message', '未知错误')}")

    public_token = gen_data.get("data", {}).get("token")
    if not public_token:
        raise Exception("CloudMail 生成 Public Token 成功但返回为空")

    _public_token_cache = public_token
    print(f"[*] CloudMail Public Token 获取成功")
    return public_token


def create_temp_email() -> Tuple[str, Dict[str, Any]]:
    """
    创建 CloudMail 临时邮箱，返回 (email, user_info)。
    user_info 包含: {"user_id", "account_id", "jwt_token", "password"}

    流程：
    1. 通过 Public API 批量添加用户（/public/addUser）
    2. 用户登录获取 JWT（/login）
    3. 获取邮箱账号列表找到 account_id（/account/list）
    """
    if not CLOUDMAIL_API_BASE:
        raise Exception("cloudmail_api_base 未设置，无法创建临时邮箱")
    if not CLOUDMAIL_EMAIL_DOMAIN:
        raise Exception("cloudmail_email_domain 未设置，无法创建临时邮箱")

    # 生成随机邮箱
    chars = string.ascii_lowercase + string.digits
    length = random.randint(8, 13)
    email_local = "".join(random.choice(chars) for _ in range(length))
    email = f"{email_local}@{CLOUDMAIL_EMAIL_DOMAIN}"
    password = _generate_password()

    session, use_cffi = _create_session()
    api_base = CLOUDMAIL_API_BASE

    try:
        # 1. 通过 Public API 批量添加用户
        public_token = _get_public_token()
        add_resp = _do_request(session, use_cffi, "post",
            f"{api_base}/api/public/addUser",
            json={"list": [{"email": email, "password": password}]},
            headers={"Authorization": public_token},
            timeout=15)
        if add_resp.status_code != 200:
            raise Exception(f"CloudMail 创建用户失败: {add_resp.status_code} - {add_resp.text[:200]}")

        add_data = add_resp.json()
        if add_data.get("code") != 200:
            raise Exception(f"CloudMail 创建用户失败: {add_data.get('message', '未知错误')}")

        print(f"[*] CloudMail 用户创建成功: {email}")

        # 2. 登录获取 JWT Token
        time.sleep(0.5)
        login_resp = _do_request(session, use_cffi, "post",
            f"{api_base}/api/login",
            json={"email": email, "password": password},
            timeout=15)
        if login_resp.status_code != 200:
            raise Exception(f"CloudMail 用户登录失败: {login_resp.status_code} - {login_resp.text[:200]}")

        login_data = login_resp.json()
        if login_data.get("code") != 200:
            raise Exception(f"CloudMail 用户登录失败: {login_data.get('message', '未知错误')}")

        jwt_token = login_data.get("data", {}).get("token")
        if not jwt_token:
            raise Exception("CloudMail 用户登录成功但未获取到 JWT Token")

        # 3. 获取邮箱账号列表，找到 account_id
        time.sleep(0.3)
        account_resp = _do_request(session, use_cffi, "get",
            f"{api_base}/api/account/list",
            headers={"Authorization": jwt_token},
            timeout=15)
        account_id = 0
        if account_resp.status_code == 200:
            account_data = account_resp.json()
            if account_data.get("code") == 200 and isinstance(account_data.get("data"), list):
                for acc in account_data["data"]:
                    acc_email = acc.get("email", "")
                    if acc_email == email or acc_email.endswith(f"@{CLOUDMAIL_EMAIL_DOMAIN}"):
                        account_id = acc.get("accountId", 0)
                        break

        if not account_id:
            # 如果没找到具体的 account_id，使用 allReceive=1 模式查询所有邮箱
            print(f"[Warn] 未找到 account_id，将使用 allReceive 模式查询邮件")

        user_info = {
            "user_id": 0,
            "account_id": account_id,
            "jwt_token": jwt_token,
            "password": password,
        }

        print(f"[*] CloudMail 临时邮箱就绪: {email} (account_id={account_id})")
        return email, user_info

    except Exception as e:
        raise Exception(f"CloudMail 创建邮箱失败: {e}")


def fetch_emails_via_jwt(jwt_token: str, account_id: int = 0, email_id_cursor: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """
    通过 JWT 认证获取 CloudMail 邮件列表（游标分页）。

    Args:
        jwt_token: 用户 JWT Token
        account_id: 邮箱账号 ID（0 表示查询全部邮箱）
        email_id_cursor: 分页游标，上一页最后一条的 emailId

    Returns:
        (邮件列表, 最新 emailId)
    """
    try:
        session, use_cffi = _create_session()
        api_base = CLOUDMAIL_API_BASE
        headers = {"Authorization": jwt_token}

        params = {
            "type": 0,  # 0=收件
            "size": 50,
            "timeSort": 0,  # 0=降序（最新的在前）
        }
        if account_id:
            params["accountId"] = account_id
        if email_id_cursor:
            params["emailId"] = email_id_cursor
        # 如果没有 account_id，使用 allReceive 查看全部
        if not account_id:
            params["allReceive"] = 1

        res = _do_request(session, use_cffi, "get",
            f"{api_base}/api/email/list",
            headers=headers,
            params=params,
            timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == 200:
                result = data.get("data", {})
                email_list = result.get("list", [])
                latest = result.get("latestEmail", {})
                latest_id = latest.get("emailId", 0) if isinstance(latest, dict) else 0
                return email_list, latest_id
    except Exception as e:
        print(f"[Warn] CloudMail 获取邮件列表异常: {e}")
    return [], 0


def fetch_latest_emails(jwt_token: str, account_id: int = 0, since_email_id: int = 0) -> List[Dict[str, Any]]:
    """
    通过 /email/latest 轮询获取新邮件（emailId > since_email_id 的邮件）。

    Args:
        jwt_token: 用户 JWT Token
        account_id: 邮箱账号 ID
        since_email_id: 当前已知最大 emailId

    Returns:
        新邮件列表（最多 20 条）
    """
    try:
        session, use_cffi = _create_session()
        api_base = CLOUDMAIL_API_BASE
        headers = {"Authorization": jwt_token}

        params = {"emailId": since_email_id}
        if account_id:
            params["accountId"] = account_id
        else:
            params["allReceive"] = 1

        res = _do_request(session, use_cffi, "get",
            f"{api_base}/api/email/latest",
            headers=headers,
            params=params,
            timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == 200:
                return data.get("data", []) or []
    except Exception as e:
        print(f"[Warn] CloudMail 轮询最新邮件异常: {e}")
    return []


def fetch_emails_via_public(to_email: str, public_token: str, page: int = 1, size: int = 20) -> List[Dict[str, Any]]:
    """
    通过 Public API 查询邮件（无需 JWT，用 Public Token）。
    适合不需要用户登录的场景。

    Args:
        to_email: 收件人邮箱（模糊匹配）
        public_token: Public Token
        page: 页码
        size: 每页条数
    """
    try:
        session, use_cffi = _create_session()
        api_base = CLOUDMAIL_API_BASE
        headers = {"Authorization": public_token}

        res = _do_request(session, use_cffi, "post",
            f"{api_base}/api/public/emailList",
            json={
                "toEmail": to_email,
                "type": 0,  # 收件
                "isDel": 0,  # 未删除
                "timeSort": "desc",
                "num": page,
                "size": size,
            },
            headers=headers,
            timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == 200:
                return data.get("data", []) or []
    except Exception as e:
        print(f"[Warn] CloudMail Public API 查询邮件异常: {e}")
    return []


def wait_for_verification_code(jwt_token: str, account_id: int = 0,
                                email: str = "", timeout: int = 120) -> Optional[str]:
    """
    轮询 CloudMail 等待验证码邮件。

    优先使用 /email/latest（JWT 轮询），如果 JWT 方式失败则
    回退到 /public/emailList（Public Token 查询）。

    Args:
        jwt_token: 用户 JWT Token
        account_id: 邮箱账号 ID
        email: 邮箱地址（用于 Public API 回退查询）
        timeout: 超时秒数
    """
    start = time.time()
    seen_ids = set()
    latest_email_id = 0

    # 先获取一次当前最新 emailId，作为基准
    _, latest_email_id = fetch_emails_via_jwt(jwt_token, account_id)

    use_jwt = True  # 优先使用 JWT 方式

    while time.time() - start < timeout:
        messages = []

        if use_jwt:
            messages = fetch_latest_emails(jwt_token, account_id, latest_email_id)
            if not messages and latest_email_id == 0:
                # 如果首次也查不到邮件，可能 account_id 有问题，尝试全量查询
                messages = fetch_latest_emails(jwt_token, 0, latest_email_id)

            if not messages:
                # 尝试回退到 Public API
                if email and CLOUDMAIL_PUBLIC_TOKEN:
                    pub_messages = fetch_emails_via_public(email, CLOUDMAIL_PUBLIC_TOKEN)
                    if pub_messages:
                        messages = pub_messages
                        use_jwt = False  # 切换到 Public API 模式
        else:
            # Public API 模式
            if email and CLOUDMAIL_PUBLIC_TOKEN:
                messages = fetch_emails_via_public(email, CLOUDMAIL_PUBLIC_TOKEN)

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("emailId") or msg.get("id")
            if not msg_id or msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)

            # CloudMail 邮件直接包含 text 和 content 字段
            content = msg.get("text") or msg.get("content") or ""
            code = extract_verification_code(content)
            if code:
                print(f"[*] 从 CloudMail 提取到验证码: {code}")
                # 更新最新 emailId
                if isinstance(msg_id, int) and msg_id > latest_email_id:
                    latest_email_id = msg_id
                return code

        # 更新最新 emailId
        for msg in messages:
            if isinstance(msg, dict):
                mid = msg.get("emailId") or 0
                if isinstance(mid, int) and mid > latest_email_id:
                    latest_email_id = mid

        time.sleep(3)

    return None


def extract_verification_code(content: str) -> Optional[str]:
    """
    从邮件内容提取验证码。
    Grok/x.ai 格式：MM0-SF3（3位-3位字母数字混合）或 6 位纯数字。
    """
    if not content:
        return None

    # 模式 1: Grok 格式 XXX-XXX
    m = re.search(r"(?<![A-Z0-9-])([A-Z0-9]{3}-[A-Z0-9]{3})(?![A-Z0-9-])", content)
    if m:
        return m.group(1)

    # 模式 2: 带标签的验证码
    m = re.search(r"(?:verification code|验证码|your code)[:\s]*[<>\s]*([A-Z0-9]{3}-[A-Z0-9]{3})\b", content, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 3: HTML 样式包裹
    m = re.search(r"background-color:\s*#F3F3F3[^>]*>[\s\S]*?([A-Z0-9]{3}-[A-Z0-9]{3})[\s\S]*?</p>", content)
    if m:
        return m.group(1)

    # 模式 4: Subject 行 6 位数字
    m = re.search(r"Subject:.*?(\d{6})", content)
    if m and m.group(1) != "177010":
        return m.group(1)

    # 模式 5: HTML 标签内 6 位数字
    for code in re.findall(r">\s*(\d{6})\s*<", content):
        if code != "177010":
            return code

    # 模式 6: 独立 6 位数字
    for code in re.findall(r"(?<![&#\d])(\d{6})(?![&#\d])", content):
        if code != "177010":
            return code

    return None

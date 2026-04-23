#!/usr/bin/env python3
"""SSO cookie 获取 + 文件写入 + API 推送 + URL JWT fallback"""

import base64
import datetime
import json
import os
import re
import time
import urllib.parse

from DrissionPage.errors import PageDisconnectedError

import browser
from browser import refresh_active_page
from logger import logger

# SSO 输出目录和默认文件名
SSO_DIR = os.path.join(os.path.dirname(__file__), "sso")
_sso_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
DEFAULT_SSO_FILE = os.path.join(SSO_DIR, f"sso_{_sso_ts}.txt")


def wait_for_sso_cookie(timeout=60):
	"""必须在注册完成后再取 sso，优先抓取精确的 sso cookie。"""
	deadline = time.time() + timeout
	last_seen_names = set()
	poll_count = 0

	logger.info("等待页面跳转完成后再检测 sso cookie...")
	time.sleep(3)

	while time.time() < deadline:
		poll_count += 1
		try:
			refresh_active_page()
			if page is None:
				time.sleep(2)
				continue

			# 每10次轮询打印一次当前URL和cookie数，方便调试
			if poll_count % 10 == 1:
				try:
					current_url = browser.page.url if browser.page else "N/A"
					logger.info(f"sso cookie 轮询 #{poll_count} | URL={current_url} | 已见cookie={sorted(last_seen_names)}")
				except Exception:
					pass

			# URL JWT Fallback：每5次检查一下 URL
			if poll_count % 5 == 0:
				try:
					current_url = browser.page.url
					if 'set-cookie' in current_url and 'q=' in current_url:
						q_match = re.search(r'q=([^&]+)', current_url)
						if q_match:
							q_value = urllib.parse.unquote(q_match.group(1))
							parts = q_value.split('.')
							if len(parts) >= 2:
								payload = parts[1]
								payload += '=' * (4 - len(payload) % 4)
								decoded = base64.b64decode(payload).decode('utf-8')
								jwt_data = json.loads(decoded)
								token = jwt_data.get('config', {}).get('token') or jwt_data.get('token')
								if token:
									logger.info("从 URL JWT 中解析到 sso token")
									return token
				except Exception:
					pass

			cookies = browser.page.cookies(all_domains=True, all_info=True) or []
			for item in cookies:
				if isinstance(item, dict):
					name = str(item.get("name", "")).strip()
					value = str(item.get("value", "")).strip()
				else:
					name = str(getattr(item, "name", "")).strip()
					value = str(getattr(item, "value", "")).strip()

				if name:
					last_seen_names.add(name)

				if name == "sso" and value:
					elapsed = int(time.time() - deadline + timeout)
					logger.info(f"注册完成后已获取到 sso cookie (耗时约{elapsed}s)。")
					return value

		except PageDisconnectedError:
			refresh_active_page()
		except Exception:
			pass

		time.sleep(2)

	raise Exception(f"注册完成后未获取到 sso cookie，当前已见 cookie: {sorted(last_seen_names)}")


def append_sso_to_txt(sso_value, output_path=DEFAULT_SSO_FILE):
	"""按用户要求，一行写一个 sso 值，持续追加。"""
	normalized = str(sso_value or "").strip()
	if not normalized:
		raise Exception("待写入的 sso 为空")

	os.makedirs(os.path.dirname(output_path), exist_ok=True)
	with open(output_path, "a", encoding="utf-8") as file:
		file.write(normalized + "\n")

	logger.info(f"已追加写入 sso 到文件: {output_path}")


def push_sso_to_api(new_tokens: list):
	"""推送 SSO token 到 grok2api 管理接口。"""
	import urllib3
	import requests
	urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

	config_path = os.path.join(os.path.dirname(__file__), "config.json")
	try:
		with open(config_path, "r", encoding="utf-8") as f:
			conf = json.load(f)
	except Exception as e:
		logger.warning(f"读取 config.json 失败，跳过推送: {e}")
		return

	api_conf = conf.get("api", {})
	endpoint = str(api_conf.get("endpoint", "")).strip()
	api_token = str(api_conf.get("token", "")).strip()

	if not endpoint or not api_token:
		return

	headers = {
		"Authorization": f"Bearer {api_token}",
		"Content-Type": "application/json",
	}

	list_endpoint = endpoint.rstrip("/").replace("/add", "")

	tokens_to_push = [t.strip() for t in new_tokens if t and t.strip()]
	if not tokens_to_push:
		logger.info("没有新 token 需要推送")
		return

	existing_tokens = set()
	try:
		get_resp = requests.get(list_endpoint, headers=headers, timeout=15, verify=False)
		if get_resp.status_code == 200:
			data = get_resp.json()
			token_list = data.get("tokens", []) if isinstance(data, dict) else []
			for item in token_list:
				if isinstance(item, dict):
					existing_tokens.add(item.get("token", ""))
				elif isinstance(item, str):
					existing_tokens.add(item)
			logger.info(f"[API] 线上已有 {len(existing_tokens)} 个 token")
		else:
			logger.warning(f"查询线上 token 失败: HTTP {get_resp.status_code}，仍尝试推送新 token")
	except Exception as e:
		logger.warning(f"查询线上 token 异常: {e}，仍尝试推送新 token")

	new_only = [t for t in tokens_to_push if t not in existing_tokens]
	if not new_only:
		logger.info(f"[API] {len(tokens_to_push)} 个 token 已全部存在于线上，无需推送")
		return

	pool_name = api_conf.get("pool", "basic")
	try:
		resp = requests.post(
			endpoint,
			json={"tokens": new_only, "pool": pool_name},
			headers=headers,
			timeout=60,
			verify=False,
		)
		if resp.status_code == 200:
			logger.info(f"[API] 已推送 {len(new_only)} 个新 token 到 grok2api（pool={pool_name}）")
		else:
			logger.warning(f"推送 API 返回异常: HTTP {resp.status_code} {resp.text[:200]}")
	except Exception as e:
		logger.warning(f"推送 API 失败: {e}")

#!/usr/bin/env python3
"""浏览器管理 — 启动/关闭/重启/Xvfb/端口/资源清理"""

import atexit
import glob
import os
import platform
import shutil
import tempfile
import time

from DrissionPage import Chromium, ChromiumOptions

from logger import logger

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_virtual_display = None
_xvfb_pid = None
_chrome_temp_dir: str = ""
_chrome_pid: int = 0
_browser_debug_port: int = 0
browser = None
page = None

# ---------------------------------------------------------------------------
# Xvfb 虚拟显示器
# ---------------------------------------------------------------------------

def _start_virtual_display():
	"""启动 Xvfb 虚拟显示器，记录 PID"""
	global _virtual_display, _xvfb_pid
	if os.environ.get("DISPLAY") and os.environ.get("USE_XVFB") != "1":
		return
	try:
		from pyvirtualdisplay import Display
		_virtual_display = Display(visible=0, size=(1920, 1080))
		_virtual_display.start()
		if hasattr(_virtual_display, "process") and _virtual_display.process:
			_xvfb_pid = _virtual_display.process.pid
		elif hasattr(_virtual_display, "_proc") and _virtual_display._proc:
			_xvfb_pid = _virtual_display._proc.pid
		logger.info(f"Xvfb 虚拟显示器已启动: {os.environ.get('DISPLAY')} (PID={_xvfb_pid})")
	except Exception as e:
		logger.warning(f"Xvfb 启动失败: {e}，将尝试直接运行")


def _stop_virtual_display():
	"""安全关闭 Xvfb 虚拟显示器，确保进程被回收"""
	global _virtual_display, _xvfb_pid
	if _virtual_display is not None:
		try:
			_virtual_display.stop()
		except Exception:
			pass
		_virtual_display = None
	if _xvfb_pid:
		try:
			import subprocess as _sp
			result = _sp.run(["kill", "-0", str(_xvfb_pid)],
							 capture_output=True, timeout=3)
			if result.returncode == 0:
				_sp.run(["kill", "-9", str(_xvfb_pid)],
						capture_output=True, timeout=3)
				logger.info(f"强制终止残留 Xvfb PID={_xvfb_pid}")
		except Exception:
			pass
		_xvfb_pid = None
	_cleanup_orphan_xvfb()


def _cleanup_orphan_xvfb():
	"""清理所有孤立的 Xvfb 进程（父PID=1 被init接管的孤儿）"""
	import subprocess as _sp
	try:
		result = _sp.run(["pgrep", "-f", "Xvfb"],
						 capture_output=True, text=True, timeout=5)
		pids = result.stdout.strip().split('\n') if result.stdout.strip() else []
		if not pids or pids == ['']:
			return
		killed = 0
		for pid_str in pids:
			pid_str = pid_str.strip()
			if not pid_str.isdigit():
				continue
			pid = int(pid_str)
			try:
				ppid_result = _sp.run(["ps", "-o", "ppid=", "-p", str(pid)],
									 capture_output=True, text=True, timeout=3)
				ppid = ppid_result.stdout.strip()
				if ppid == "1" or ppid == "":
					_sp.run(["kill", "-9", str(pid)],
							capture_output=True, timeout=3)
					killed += 1
			except Exception:
				pass
		if killed:
			logger.info(f"清理了 {killed} 个孤立 Xvfb 进程")
	except Exception:
		pass

# ---------------------------------------------------------------------------
# 端口 & 进程管理
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
	"""查找一个空闲的调试端口，避免端口冲突导致启动失败"""
	import socket
	for port in range(9222, 9332):
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
				s.settimeout(1)
				s.connect(("127.0.0.1", port))
		except (ConnectionRefusedError, OSError):
			return port
	return 9222


def _kill_port_owner(port: int):
	"""强制终止占用指定端口的进程"""
	import subprocess as _sp
	try:
		result = _sp.run(["lsof", "-ti", f":{port}"],
						 capture_output=True, text=True, timeout=5)
		pids = result.stdout.strip().split('\n') if result.stdout.strip() else []
		for pid_str in pids:
			pid_str = pid_str.strip()
			if pid_str.isdigit():
				_sp.run(["kill", "-9", str(pid_str)],
						capture_output=True, timeout=3)
				logger.info(f"终止占用端口 {port} 的进程 PID={pid_str}")
	except Exception:
		pass


def _ensure_chrome_dead(pid: int, timeout: int = 5):
	"""确保指定 Chrome 进程及其子进程树已完全退出"""
	import subprocess as _sp
	if not pid:
		return
	try:
		_sp.run(["kill", str(pid)], capture_output=True, timeout=3)
	except Exception:
		pass
	deadline = time.time() + timeout
	while time.time() < deadline:
		try:
			result = _sp.run(["kill", "-0", str(pid)],
							 capture_output=True, timeout=2)
			if result.returncode != 0:
				return
		except Exception:
			return
		time.sleep(0.5)
	try:
		_sp.run(["kill", "-9", str(pid)], capture_output=True, timeout=3)
		logger.info(f"强制终止 Chrome PID={pid}")
	except Exception:
		pass
	try:
		result = _sp.run(["pgrep", "-P", str(pid)],
						 capture_output=True, text=True, timeout=3)
		child_pids = result.stdout.strip().split('\n') if result.stdout.strip() else []
		for cpid_str in child_pids:
			cpid_str = cpid_str.strip()
			if cpid_str.isdigit():
				_sp.run(["kill", "-9", str(cpid_str)],
						capture_output=True, timeout=3)
	except Exception:
		pass

# ---------------------------------------------------------------------------
# ChromiumOptions 初始化
# ---------------------------------------------------------------------------

co = ChromiumOptions()
co.set_local_port(9222)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.set_argument("--disable-software-rasterizer")
# Turnstile 反检测参数
co.set_argument("--disable-blink-features=AutomationControlled")
co.set_argument("--disable-features=AutomationControlled")
co.set_argument("--disable-infobars")
co.set_argument("--window-size=1920,1080")
co.set_argument("--lang=en-US,en;q=0.9")

# 从 config.json 读取代理配置给浏览器
_browser_proxy = ""
try:
	import json as _json_mod
	_cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
	if os.path.isfile(_cfg_path):
		with open(_cfg_path, "r") as _f:
			_cfg = _json_mod.load(_f)
		_browser_proxy = str(_cfg.get("browser_proxy", "") or _cfg.get("proxy", "") or "")
except Exception:
	pass
if _browser_proxy:
	co.set_proxy(_browser_proxy)
	logger.info(f"浏览器代理: {_browser_proxy}")

# Linux 服务器自动检测 chromium 路径
import glob as _glob_mod
if platform.system() == "Linux":
	_pw_chromes = _glob_mod.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"))
	if _pw_chromes:
		co.set_browser_path(_pw_chromes[0])
	else:
		for _candidate in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
			if os.path.isfile(_candidate):
				co.set_browser_path(_candidate)
				break

co.set_timeouts(base=1)

# 加载修复 MouseEvent.screenX / screenY 的扩展
EXTENSION_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "turnstilePatch"))
co.add_extension(EXTENSION_PATH)

# ---------------------------------------------------------------------------
# 浏览器启动 / 关闭 / 重启
# ---------------------------------------------------------------------------

def start_browser():
	global browser, page, _chrome_temp_dir, _chrome_pid, _browser_debug_port

	if _chrome_pid:
		_ensure_chrome_dead(_chrome_pid)
		_chrome_pid = 0

	debug_port = _find_free_port()
	if debug_port != 9222:
		_kill_port_owner(9222)
		time.sleep(1)
		debug_port = 9222

	for _ in range(3):
		import socket as _sock
		try:
			with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
				s.settimeout(1)
				s.connect(("127.0.0.1", 9222))
				_kill_port_owner(9222)
				time.sleep(2)
		except (ConnectionRefusedError, OSError):
			break

	co.set_local_port(debug_port)
	_browser_debug_port = debug_port

	_chrome_temp_dir = tempfile.mkdtemp(prefix="chrome_run_")
	co.set_user_data_path(_chrome_temp_dir)
	try:
		browser = Chromium(co)
		tabs = browser.get_tabs()
		page = tabs[-1] if tabs else browser.new_tab()
		try:
			_chrome_pid = browser.process_id if hasattr(browser, 'process_id') else 0
		except Exception:
			_chrome_pid = 0
		if not _chrome_pid:
			try:
				import subprocess as _sp
				r = _sp.run(["lsof", "-ti", f":{debug_port}"],
							capture_output=True, text=True, timeout=5)
				pids = r.stdout.strip().split('\n')
				if pids and pids[0].strip().isdigit():
					_chrome_pid = int(pids[0].strip())
			except Exception:
				pass
		logger.info(f"[Browser] 启动成功 (port={debug_port}, PID={_chrome_pid}, dir={os.path.basename(_chrome_temp_dir)})")
		# 注入反自动化检测脚本
		try:
			page.run_js("""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
""")
		except Exception:
			pass
	except Exception as e:
		logger.error(f"浏览器启动失败: {e}")
		_chrome_pid = 0
		browser = None
		page = None
		raise
	return browser, page


def stop_browser():
	global browser, page, _chrome_temp_dir, _chrome_pid, _browser_debug_port
	if browser is not None:
		try:
			browser.quit()
		except Exception:
			pass
		browser = None
		page = None

	if _chrome_pid:
		_ensure_chrome_dead(_chrome_pid, timeout=5)
		_chrome_pid = 0

	if _browser_debug_port:
		_kill_port_owner(_browser_debug_port)
		_browser_debug_port = 0

	if _chrome_temp_dir and os.path.isdir(_chrome_temp_dir):
		shutil.rmtree(_chrome_temp_dir, ignore_errors=True)
		_chrome_temp_dir = ""

	try:
		for old_dir in glob.glob("/tmp/chrome_run_*"):
			try:
				dir_mtime = os.path.getmtime(old_dir)
				if time.time() - dir_mtime > 300:
					shutil.rmtree(old_dir, ignore_errors=True)
			except Exception:
				pass
	except Exception:
		pass


def restart_browser():
	global browser, page
	if browser is None:
		start_browser()
		return
	try:
		tabs = browser.get_tabs()
		page = tabs[-1] if tabs else browser.new_tab()
		page.run_js("window.localStorage.clear(); window.sessionStorage.clear();")
		page.clear_cache(session_storage=True, cookies=True)
	except Exception:
		stop_browser()
		start_browser()


def refresh_active_page():
	global browser, page
	if browser is None:
		start_browser()
	try:
		tabs = browser.get_tabs()
		if tabs:
			page = tabs[-1]
		else:
			page = browser.new_tab()
	except Exception:
		restart_browser()
	return page


def close_current_page():
	"""兼容旧调用名，实际行为改为整轮重启浏览器。"""
	restart_browser()


def _full_cleanup():
	"""完整资源清理：浏览器 + Xvfb，供 atexit 和信号处理调用"""
	stop_browser()
	_stop_virtual_display()


# ---------------------------------------------------------------------------
# 启动时初始化 & atexit 注册
# ---------------------------------------------------------------------------
_start_virtual_display()
atexit.register(_full_cleanup)

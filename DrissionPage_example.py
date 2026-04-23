#!/usr/bin/env python3
"""xAI Grok 自动注册脚本 — 入口"""

import argparse
import json
import os
import signal
import sys
import time

from browser import start_browser, stop_browser, _full_cleanup
from signup import run_single_registration
from sso import push_sso_to_api, DEFAULT_SSO_FILE
from logger import setup_run_logger, logger


def load_run_count() -> int:
	"""从 config.json 读取默认执行轮数，配置不存在时返回 10。"""
	config_path = os.path.join(os.path.dirname(__file__), "config.json")
	try:
		with open(config_path, "r", encoding="utf-8") as f:
			conf = json.load(f)
		v = conf.get("run", {}).get("count")
		if isinstance(v, int) and v >= 0:
			return v
	except Exception:
		pass
	return 10


def main():
	run_logger = setup_run_logger()

	# 信号处理：确保被 kill / SSH断连 时也能完整清理所有资源
	def _cleanup_on_signal(signum, frame):
		sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
		logger.info(f"收到信号 {sig_name}({signum})，正在清理所有资源...")
		_full_cleanup()
		sys.exit(1)

	signal.signal(signal.SIGTERM, _cleanup_on_signal)
	signal.signal(signal.SIGINT, _cleanup_on_signal)
	signal.signal(signal.SIGHUP, _cleanup_on_signal)

	# 参数解析
	config_count = load_run_count()
	parser = argparse.ArgumentParser(description="xAI 自动注册并采集 sso")
	parser.add_argument("--count", type=int, default=config_count,
					help=f"执行轮数，0 表示无限循环（默认读取 config.json run.count，当前 {config_count}）")
	parser.add_argument("--output", default=DEFAULT_SSO_FILE, help="sso 输出 txt 路径")
	parser.add_argument("--extract-numbers", action="store_true", help="注册完成后额外提取页面数字文本")
	args = parser.parse_args()

	current_round = 0
	collected_sso: list = []
	consecutive_failures = 0
	MAX_CONSECUTIVE_FAILURES = 5

	try:
		start_browser()
		while True:
			if args.count > 0 and current_round >= args.count:
				break

			current_round += 1
			logger.info(f"\n开始第 {current_round} 轮注册")

			try:
				result = run_single_registration(args.output, extract_numbers=args.extract_numbers)
				collected_sso.append(result["sso"])
				consecutive_failures = 0
				# 每轮注册成功后立即推送到 grok2api
				logger.info(f"\n立即推送第 {current_round} 轮 token 到 API...")
				push_sso_to_api([result["sso"]])
			except KeyboardInterrupt:
				logger.info("\n收到中断信号，停止后续轮次。")
				break
			except Exception as error:
				consecutive_failures += 1
				logger.error(f"第 {current_round} 轮失败: {error}")
				if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
					logger.warning(f"连续 {consecutive_failures} 轮失败，暂停 60 秒后重试...")
					time.sleep(60)
					consecutive_failures = 0
			finally:
				# 每轮彻底关闭浏览器再重启，避免 Chrome 进程残留
				try:
					stop_browser()
				except Exception as e:
					logger.warning(f"stop_browser 异常: {e}")
				try:
					start_browser()
				except Exception as e:
					logger.error(f"start_browser 失败: {e}，等待 10 秒后重试...")
					time.sleep(10)
					try:
						start_browser()
					except Exception:
						logger.error("浏览器无法启动，终止运行")
						break

			if args.count == 0 or current_round < args.count:
				time.sleep(2)

	finally:
		if collected_sso:
			logger.info(f"\n全部完成，共注册 {len(collected_sso)} 个账户（已实时推送）")

		stop_browser()


if __name__ == "__main__":
	main()

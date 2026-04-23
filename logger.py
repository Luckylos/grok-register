#!/usr/bin/env python3
"""日志系统 — setup + 全局 logger + log 快捷函数"""

import datetime
import logging
import os
import sys

# 全局 logger 对象，setup_run_logger() 之前为 NullHandler
logger = logging.getLogger("grok_register")
logger.addHandler(logging.NullHandler())

# 保存 setup 返回的 run_logger 引用
run_logger: logging.Logger = None


def setup_run_logger() -> logging.Logger:
	"""创建本轮运行的日志记录器，同时输出到文件和控制台"""
	global run_logger
	log_dir = os.path.join(os.path.dirname(__file__), "logs")
	os.makedirs(log_dir, exist_ok=True)
	ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
	log_path = os.path.join(log_dir, f"run_{ts}.log")

	logger.setLevel(logging.INFO)
	logger.handlers.clear()

	fmt = logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
	fh = logging.FileHandler(log_path, encoding="utf-8")
	fh.setFormatter(fmt)
	logger.addHandler(fh)
	sh = logging.StreamHandler(sys.stdout)
	sh.setFormatter(fmt)
	logger.addHandler(sh)

	logger.info("日志文件: %s", log_path)
	run_logger = logger
	return logger


def log(msg: str):
	"""快捷日志函数，自动检测 run_logger 是否可用"""
	if run_logger is not None:
		run_logger.info(msg)
	else:
		logger.info(msg)

#!/usr/bin/env python3
"""grok-register 资源泄露实时监控

每30秒采样一次，记录：
- Chrome 进程数（含 crashpad）
- Xvfb 进程数
- chrome_run_ 临时目录数
- 注册成功轮数（从日志文件）
- 9222端口占用

输出到 /opt/grok-register/logs/monitor.log
"""

import subprocess
import time
import os
import glob
from datetime import datetime

MONITOR_LOG = "/opt/grok-register/logs/monitor.log"
SST_DIR = "/opt/grok-register/sso/"
INTERVAL = 30

def count_procs(pattern):
    try:
        r = subprocess.run(["pgrep", "-cf", pattern], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip()) if r.stdout.strip().isdigit() else 0
    except:
        return -1

def count_tmp_dirs():
    return len(glob.glob("/tmp/chrome_run_*"))

def count_port_users(port):
    try:
        r = subprocess.run(["fuser", f"{port}/tcp"], capture_output=True, text=True, timeout=5)
        pids = r.stdout.strip().split()
        return len([p for p in pids if p.isdigit()])
    except:
        return -1

def get_sso_count():
    """统计最新的 sso 文件行数"""
    files = sorted(glob.glob(os.path.join(SST_DIR, "sso_*.txt")))
    if not files:
        return 0
    try:
        with open(files[-1]) as f:
            return len(f.readlines())
    except:
        return -1

def get_latest_log_successes():
    """从最新日志统计注册成功数"""
    log_dir = "/opt/grok-register/logs/"
    files = sorted(glob.glob(os.path.join(log_dir, "run_*.log")))
    if not files:
        return 0
    try:
        with open(files[-1]) as f:
            return sum(1 for line in f if "注册成功" in line)
    except:
        return -1

print(f"[Monitor] 启动，每 {INTERVAL}s 采样一次，日志: {MONITOR_LOG}")

header_written = os.path.exists(MONITOR_LOG)
with open(MONITOR_LOG, "a") as log:
    if not header_written:
        log.write("timestamp | chrome_procs | xvfb_procs | tmp_dirs | port9222 | sso_count | successes | alert\n")
    
    while True:
        ts = datetime.now().strftime("%H:%M:%S")
        chrome = count_procs("chrome")
        xvfb = count_procs("Xvfb")
        tmp = count_tmp_dirs()
        port = count_port_users(9222)
        sso = get_sso_count()
        succ = get_latest_log_successes()
        
        # 泄露检测
        alerts = []
        if tmp > 1:
            alerts.append(f"TMP_DIR_LEAK:{tmp}")
        if chrome > 15:
            alerts.append(f"CHROME_BLOATED:{chrome}")
        if xvfb > 1:
            alerts.append(f"XVFB_LEAK:{xvfb}")
        
        alert_str = ",".join(alerts) if alerts else "OK"
        line = f"{ts} | chrome={chrome} | xvfb={xvfb} | tmpdirs={tmp} | port9222={port} | sso={sso} | success={succ} | {alert_str}"
        
        log.write(line + "\n")
        log.flush()
        
        # 控制台也输出（有告警时高亮）
        if alerts:
            print(f"⚠️  {line}")
        else:
            print(line)
        
        time.sleep(INTERVAL)

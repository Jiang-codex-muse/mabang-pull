#!/bin/sh
# 马帮拉数 v0.2 — 每日运行（Linux / macOS / WSL）
# 一条命令跑完当天所有同步任务，出 output/daily_report_YYYY-MM-DD.md
# 真实模式现在会明确停住（见 mabang_sync.py），先用 --mock 跑通流程。
# 真实拉数时去掉 --mock，程序会按 sync_jobs.json 逐页拉。
# 用法：sh run_daily.sh [--mock]
set -e
cd "$(dirname "$0")"
if [ "$1" = "--mock" ]; then
  python3 mabang_sync.py --mock --date today
else
  python3 mabang_sync.py --date today
fi

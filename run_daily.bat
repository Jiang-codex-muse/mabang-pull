@echo off
REM 马帮拉数 v0.2 — 每日运行（Windows 工作电脑）
REM 一条命令跑完当天所有同步任务，出 output/daily_report_YYYY-MM-DD.md
REM 真实模式现在会明确停住（见 mabang_sync.py），先用 --mock 跑通流程。
REM 真实拉数时去掉 --mock，程序会按 sync_jobs.json 逐页拉。
python mabang_sync.py --mock --date today
pause

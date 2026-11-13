@echo off
REM 马帮拉数 - Windows 一键运行 (在工作电脑上双击或在 CMD 里跑)
REM 先改 config.json 填好 AppKey / AppSecret, 再改下面日期
python mabang_pull.py --start 2026-11-01 --end 2026-11-13
pause

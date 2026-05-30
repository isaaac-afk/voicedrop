@echo off
title VoiceDrop
set KMP_DUPLICATE_LIB_OK=TRUE
cd /d "%~dp0"
python dictate.py
pause

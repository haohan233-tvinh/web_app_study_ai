@echo off
title Network Restriction Audit Tool
color 0B
echo ======================================================================
echo    KHOI DONG KIEM TRA MANG (NETWORK AUDIT DEEP PROBE)
echo ======================================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0network_audit.ps1"
echo.
pause

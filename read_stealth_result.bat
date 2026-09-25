@echo off
title Ket Qua Kiem Tra Mang An Danh (Stealth Audit Result)
color 0A
echo ======================================================================
echo    KET QUA THU THAP THONG TIN MANG (STEALTH MODE)
echo ======================================================================
echo.
if exist "%~dp0.network_cache.txt" (
    type "%~dp0.network_cache.txt"
) else (
    echo [!] Chua co du lieu kiem tra. Hay chay file run_stealth.vbs truoc!
)
echo.
pause

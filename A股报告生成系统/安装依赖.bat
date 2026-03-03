@echo off
chcp 65001 > nul

echo ========================================
echo   安装依赖包
echo ========================================
echo.

echo 在当前虚拟环境中安装...
pip install -r requirements.txt

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 现在可以运行: python batch_generate.py
echo.
pause

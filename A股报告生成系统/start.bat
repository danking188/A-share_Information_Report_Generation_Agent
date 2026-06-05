@echo off
chcp 65001 > nul
title A股研究报告批量生成系统

echo.
echo ========================================
echo   A股研究报告批量生成系统
echo ========================================
echo.

REM 检查Python是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 检查依赖是否已安装
if not exist "venv\" (
    echo 首次运行，正在安装依赖...
    echo.
    pip install -r requirements.txt
    echo.
    echo 依赖安装完成！
    echo.
)

REM 显示配置信息
echo 配置信息：
echo   输出目录: output\
echo   配置文件: config\.env
echo   数据文件: data\stocks_code.txt
echo.

REM 询问是否继续
echo 准备开始批量生成，实际耗时取决于股票数量和API响应速度。
set /p confirm="确认开始？(Y/N): "

if /i not "%confirm%"=="Y" (
    echo 已取消
    pause
    exit /b 0
)

echo.
echo ========================================
echo   开始批量生成...
echo ========================================
echo.

REM 运行批量生成脚本
python batch_generate.py

echo.
echo ========================================
echo   程序已结束
echo ========================================
pause

"""
内存监控工具
实时显示程序内存使用情况
"""

import psutil
import time
from datetime import datetime


def get_process_memory():
    """获取当前Python进程的内存使用"""
    process = psutil.Process()
    mem_info = process.memory_info()

    return {
        'rss': mem_info.rss / 1024 / 1024,  # 物理内存 MB
        'vms': mem_info.vms / 1024 / 1024,  # 虚拟内存 MB
        'percent': process.memory_percent(),  # 内存占用百分比
    }


def get_system_memory():
    """获取系统内存使用情况"""
    mem = psutil.virtual_memory()

    return {
        'total': mem.total / 1024 / 1024 / 1024,  # GB
        'available': mem.available / 1024 / 1024 / 1024,  # GB
        'used': mem.used / 1024 / 1024 / 1024,  # GB
        'percent': mem.percent,  # 使用百分比
    }


def format_bar(percent, width=30):
    """生成进度条"""
    filled = int(width * percent / 100)
    bar = '█' * filled + '░' * (width - filled)
    return bar


def main():
    """主函数"""
    print("""
╔════════════════════════════════════════════════════════════╗
║                  内存监控工具                                ║
║              按 Ctrl+C 退出                                  ║
╚════════════════════════════════════════════════════════════╝
    """)

    try:
        while True:
            # 清屏（Windows）
            os = 'windows'
            print('\033c', end='')

            print(f"{'='*60}")
            print(f"内存监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            print()

            # 系统内存
            sys_mem = get_system_memory()
            print(f"【系统内存】")
            print(f"  总计:     {sys_mem['total']:.2f} GB")
            print(f"  已用:     {sys_mem['used']:.2f} GB")
            print(f"  可用:     {sys_mem['available']:.2f} GB")
            print(f"  使用率:   {sys_mem['percent']:.1f}%")
            print(f"  {format_bar(sys_mem['percent'])}")
            print()

            # 进程内存
            proc_mem = get_process_memory()
            print(f"【Python进程】")
            print(f"  物理内存: {proc_mem['rss']:.2f} MB")
            print(f"  虚拟内存: {proc_mem['vms']:.2f} MB")
            print(f"  占用率:   {proc_mem['percent']:.2f}%")
            print()

            # 状态提示
            rss_mb = proc_mem['rss']
            if rss_mb < 500:
                status = "✓ 正常"
                color = "绿色"
            elif rss_mb < 1000:
                status = "⚠ 轻微压力"
                color = "黄色"
            elif rss_mb < 2000:
                status = "⚠⚠ 内存压力较大"
                color = "橙色"
            else:
                status = "✗✗ 内存压力过大！建议重启程序"
                color = "红色"

            print(f"【状态】{status}")
            print()

            # 建议
            if rss_mb > 1500:
                print("【建议】")
                print("  1. 使用改进版 batch_generate_improved.py")
                print("  2. 考虑重启程序")
                print("  3. 分批处理股票（每次500-1000只）")
                print()

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n退出监控")


if __name__ == "__main__":
    main()

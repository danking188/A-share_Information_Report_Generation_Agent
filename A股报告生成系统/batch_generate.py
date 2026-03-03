import sys
import os
import re
import time
import json
import signal
from datetime import datetime, timedelta
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.main import ResearchReportGenerator
from src.data_fetcher import StockDataFetcher
from dotenv import load_dotenv

# 全局变量用于退出
should_exit = False


def signal_handler(signum, frame):
    """处理中断信号"""
    global should_exit
    print("\n\n收到中断信号，正在安全退出...")
    should_exit = True


def load_failed_stocks(data_dir):
    """加载失败股票列表"""
    failed_file = os.path.join(data_dir, 'failed_stocks.json')
    if os.path.exists(failed_file):
        try:
            with open(failed_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_failed_stocks(data_dir, failed_stocks):
    """保存失败股票列表"""
    failed_file = os.path.join(data_dir, 'failed_stocks.json')
    try:
        with open(failed_file, 'w', encoding='utf-8') as f:
            json.dump(failed_stocks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"警告：保存失败股票列表时出错: {e}")


def load_progress(data_dir):
    """加载进度"""
    progress_file = os.path.join(data_dir, 'progress.json')
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'current_index': 0}


def save_progress(data_dir, current_index):
    """保存进度"""
    progress_file = os.path.join(data_dir, 'progress.json')
    try:
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump({'current_index': current_index}, f, ensure_ascii=False)
    except Exception as e:
        print(f"警告：保存进度时出错: {e}")


def get_generated_files(output_dir):
    """获取已生成的文件列表"""
    try:
        if os.path.exists(output_dir):
            return set([f.replace('.docx', '') for f in os.listdir(output_dir) if f.endswith('.docx')])
    except:
        pass
    return set()


def get_stock_name_improved(fetcher, stock_code, max_retries=3):
    """
    改进的股票名称获取方法
    使用多种方式尝试获取公司名称
    """
    for attempt in range(max_retries):
        try:
            # 方法1：从get_stock_list获取
            stock_list = fetcher.get_stock_list()
            if stock_list is not None and not stock_list.empty:
                match = stock_list[stock_list['code'] == stock_code]
                if not match.empty:
                    name = match.iloc[0]['name']
                    if name and name != stock_code:
                        return str(name)

            # 方法2：从get_stock_basic_info获取
            stock_info = fetcher.get_stock_basic_info(stock_code)
            if stock_info and 'individual_info' in stock_info:
                items = stock_info['individual_info'].get('item', [])
                values = stock_info['individual_info'].get('value', [])
                # 查找'股票简称'对应的值
                for i, item in enumerate(items):
                    if '股票简称' in str(item) or '名称' in str(item):
                        if i < len(values) and values[i]:
                            return str(values[i])
                # 备用：取第三个值
                if len(values) > 2:
                    return str(values[2])

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            else:
                print(f"  获取股票名称失败: {e}")

    # 如果所有方法都失败，返回股票代码
    return stock_code


def main():
    global should_exit

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 加载环境变量
    config_dir = os.path.join(os.path.dirname(__file__), 'config')
    env_file = os.path.join(config_dir, '.env')
    load_dotenv(env_file)

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误：未找到DASHSCOPE_API_KEY，请检查config/.env文件")
        return

    # 初始化生成器
    print("=" * 60)
    print("A股研究报告批量生成系统 - 增强版")
    print("=" * 60)
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n正在初始化...")
    generator = ResearchReportGenerator(api_key=api_key)
    fetcher = StockDataFetcher()

    # 读取股票列表
    print("\n正在读取股票列表...")
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    stock_file = os.path.join(data_dir, 'stocks_code.txt')

    if not os.path.exists(stock_file):
        print(f"错误：找不到股票列表文件 {stock_file}")
        return

    with open(stock_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 过滤出股票代码（跳过注释行）
    stock_list = [line.strip() for line in lines if line.strip() and not line.startswith('#')]

    # 加载失败股票记录
    failed_stocks = load_failed_stocks(data_dir)
    if failed_stocks:
        print(f"\n已加载 {len(failed_stocks)} 条失败记录")

    # 加载进度
    progress = load_progress(data_dir)
    start_index = progress.get('current_index', 0)

    if start_index > 0:
        print(f"从第 {start_index + 1} 个股票继续...")

    # 获取已生成的文件
    output_dir = os.path.join(os.path.dirname(__file__), 'output')
    os.makedirs(output_dir, exist_ok=True)
    generated_files = get_generated_files(output_dir)
    print(f"已发现 {len(generated_files)} 个已生成文件，将自动跳过")

    # 设置输出目录
    print(f"\n待生成股票数: {len(stock_list)}")
    print(f"从: {stock_list[0] if stock_list else 'N/A'}")
    print(f"到: {stock_list[-1] if stock_list else 'N/A'}")
    print(f"输出目录: {output_dir}")

    # 开始批量生成
    print("\n开始批量生成报告...")
    print("=" * 60)

    success_count = 0
    fail_count = 0
    skip_count = 0
    start_time = time.time()

    # 跳过连续失败的阈值
    MAX_CONTINUOUS_FAILURES = 5
    continuous_failures = 0

    for i in range(start_index, len(stock_list)):
        if should_exit:
            print("\n收到退出信号，保存进度后退出...")
            save_progress(data_dir, i)
            save_failed_stocks(data_dir, failed_stocks)
            break

        stock_code = stock_list[i]
        stock_start_time = time.time()

        # 检查是否已失败太多次
        if stock_code in failed_stocks:
            fail_count = failed_stocks[stock_code].get('count', 1)
            if fail_count >= 3:
                print(f"\n[{i+1}/{len(stock_list)}] 跳过 {stock_code}（已失败{fail_count}次）")
                skip_count += 1
                continue

        try:
            print(f"\n[{i+1}/{len(stock_list)}] 正在生成 {stock_code} 的报告...")

            # 获取股票名称
            stock_name = get_stock_name_improved(fetcher, stock_code)
            print(f"  公司名称: {stock_name}")

            # 检查文件是否已存在
            clean_name = re.sub(r'[\\/*?:"<>|]', '', stock_name).strip()
            output_filename = f"{clean_name}.docx"
            output_path = os.path.join(output_dir, output_filename)

            # 如果文件已存在，跳过
            if clean_name in generated_files and os.path.exists(output_path):
                file_mtime = os.path.getmtime(output_path)
                file_age = time.time() - file_mtime
                if file_age < 3600:  # 文件生成于1小时内
                    print(f"  [OK] 文件已存在，跳过: {output_filename}")
                    skip_count += 1
                    continue

            # 生成报告
            result_path = generator.generate_report(stock_code, output_path)

            # 成功：从失败记录中移除
            if stock_code in failed_stocks:
                del failed_stocks[stock_code]

            success_count += 1
            continuous_failures = 0
            stock_elapsed = time.time() - stock_start_time
            print(f"  [OK] 成功: {output_filename} (耗时: {stock_elapsed:.1f}秒)")

            # 保存进度
            if i % 5 == 0:
                save_progress(data_dir, i + 1)

            # 每10个显示详细进度
            if (i + 1) % 10 == 0:
                elapsed_total = time.time() - start_time
                avg_time = elapsed_total / (i + 1 - start_index)
                remaining = (len(stock_list) - i - 1) * avg_time
                eta = datetime.now() + timedelta(seconds=remaining)

                print(f"\n--- 进度: {i+1-start_index}/{len(stock_list)-start_index} ({(i+1-start_index)/(len(stock_list)-start_index)*100:.1f}%) ---")
                print(f"成功: {success_count}, 失败: {fail_count}, 跳过: {skip_count}")
                print(f"平均耗时: {avg_time:.1f}秒/只")
                print(f"预计剩余: {remaining/3600:.1f}小时")
                print(f"预计完成: {eta.strftime('%Y-%m-%d %H:%M')}")
                print(f"速度: {3600/avg_time:.1f}只/小时")

            # 动态延迟
            if i < len(stock_list) - 1:
                time.sleep(2)

        except Exception as e:
            fail_count += 1
            continuous_failures += 1
            error_msg = str(e)

            # 记录失败
            if stock_code not in failed_stocks:
                failed_stocks[stock_code] = {'count': 0, 'errors': []}
            failed_stocks[stock_code]['count'] += 1
            failed_stocks[stock_code]['errors'].append({
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'error': error_msg
            })

            print(f"  [FAIL] 失败: {error_msg}")

            # 如果连续失败太多，可能是网络问题
            if continuous_failures >= MAX_CONTINUOUS_FAILURES:
                print(f"\n警告：连续失败 {continuous_failures} 次，可能是网络问题")
                print("等待30秒后继续...")
                time.sleep(30)
                continuous_failures = 0
            else:
                time.sleep(5)

            # 保存失败记录
            save_failed_stocks(data_dir, failed_stocks)

    # 清除进度文件（任务完成）
    progress_file = os.path.join(data_dir, 'progress.json')
    if os.path.exists(progress_file):
        try:
            os.remove(progress_file)
        except:
            pass

    # 最终统计
    total_time = time.time() - start_time
    processed = success_count + fail_count
    print("\n" + "=" * 60)
    print("批量生成完成！")
    print("=" * 60)
    print(f"总数: {len(stock_list)}")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"跳过: {skip_count}")
    if processed > 0:
        print(f"成功率: {success_count/processed*100:.2f}%")
    print(f"总耗时: {total_time/3600:.2f}小时")
    if processed > 0:
        print(f"平均速度: {processed/(total_time/3600):.1f}只/小时")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"报告保存位置: {output_dir}")

    # 显示失败股票统计
    if failed_stocks:
        print(f"\n失败股票统计（共{len(failed_stocks)}只）：")
        for code, info in sorted(failed_stocks.items(), key=lambda x: x[1]['count'], reverse=True)[:10]:
            print(f"  {code}: 失败{info['count']}次")

    print("\n提示：可重新运行程序继续生成失败的股票")


if __name__ == "__main__":
    main()

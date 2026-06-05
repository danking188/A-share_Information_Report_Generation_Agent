# 快速使用指南

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置 API Key

复制示例配置：

```bash
cp config/.env.example config/.env
```

编辑 `config/.env`，填入 DashScope API Key：

```text
DASHSCOPE_API_KEY=你的DashScope API Key
```

## 3. 准备股票列表

编辑 `data/stocks_code.txt`，每行一个 6 位股票代码：

```text
000001
600519
```

如果文件里没有有效代码，程序会直接退出并提示补充股票列表。

## 4. 运行

批量生成：

```bash
python batch_generate.py
```

先验证流程：

```bash
python batch_generate.py --dry-run --limit 1
```

生成单只股票：

```bash
python src/main.py 000001
```

单只股票 dry-run：

```bash
python src/main.py 000001 --dry-run
```

## 输出位置

批量生成的报告保存在：

```text
output/
```

文件名使用公司简称，例如：

```text
平安银行.docx
贵州茅台.docx
```

## 断点续跑

程序运行时会自动写入：

- `data/progress.json`
- `data/failed_stocks.json`

中断后重新运行，会继续处理后续股票。已生成的同名报告会自动跳过。

## 本地知识库

将 `.md` 或 `.txt` 资料放入：

```text
knowledge_base/raw/
```

系统会在生成报告时检索相关资料，并把资料片段注入报告生成提示词。

常用参数：

```bash
python batch_generate.py --rag-top-k 6
python batch_generate.py --no-rag
```

## 常用批处理参数

```bash
python batch_generate.py --limit 10
python batch_generate.py --start-from 600519
python batch_generate.py --retry-failed
python batch_generate.py --output-dir output/test
```

## 日志

日志保存在：

```text
logs/
```

查看最新日志：

```bash
tail -f logs/*.log
```

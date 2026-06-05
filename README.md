# A-share Information Report Generation Agent

这是一个用于批量生成 A 股上市公司研究报告的 Python 项目。项目主体位于 `A股报告生成系统/`。

## 快速开始

```bash
cd A股报告生成系统
pip install -r requirements.txt
cp config/.env.example config/.env
python batch_generate.py
```

运行前需要在 `config/.env` 中填写 DashScope API Key，并在 `data/stocks_code.txt` 中添加待生成报告的股票代码。

可以先用 dry-run 验证流程：

```bash
python batch_generate.py --dry-run --limit 1
```

## 本地知识库

项目支持轻量 RAG。将 `.md` 或 `.txt` 资料放入：

```text
A股报告生成系统/knowledge_base/raw/
```

运行生成时，系统会检索与股票名称、行业和主营业务相关的资料片段，并注入到报告生成提示词中。

## 文档

- `A股报告生成系统/PROJECT_INFO.md`：项目说明
- `A股报告生成系统/QUICKSTART.md`：快速使用指南

## 注意

`config/.env`、`output/`、`logs/`、`knowledge_base/index/` 和本地 IDE 配置不会提交到仓库。API Key 只应保存在本地环境中。

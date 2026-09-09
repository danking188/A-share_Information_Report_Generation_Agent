# A-share Information Report Generation Workflow

面向 A 股初步调研的信息汇总与研报生成工作流。系统串联数据采集、财务口径清洗、数据质量检查、本地知识检索、LLM 章节生成和 Word 导出，并支持失败记录与阶段恢复。

> 项目用于信息整理与工程实践，不构成投资建议。

## 工作流

```text
股票代码 → 数据 Provider → 字段清洗/同报告期同比 → 质量门禁
        → RAG 检索与证据编号 → LLM Provider → Word 报告
        → 阶段状态、缓存、日志与失败记录
```

核心实现位于 `A股报告生成系统/`：

- `src/api_providers.py`：AkShare、标准 HTTP 数据接口、DashScope 与 OpenAI-compatible 模型接口
- `src/main.py`：单股研报工作流与阶段恢复
- `batch_generate.py`：批量调度、断点续跑和失败管理
- `src/data_quality.py`：关键数据门禁与降级状态
- `src/rag/`：带证据编号的轻量 TF-IDF 检索
- `src/report_generator.py`：跨平台字体配置和 Word 导出

## 快速开始

```bash
cd A股报告生成系统
pip install -r requirements.txt
cp config/.env.example config/.env
python batch_generate.py
```

运行前需要在 `config/.env` 中配置模型服务，并在 `data/stocks_code.txt` 中添加待生成报告的股票代码。

可以先用 dry-run 验证流程：

```bash
python batch_generate.py --dry-run --limit 1
```

完全离线、不访问行情或模型 API 的回归验证：

```bash
python batch_generate.py --dry-run --no-rag --limit 1 \
  --stock-file tests/fixtures/stocks.txt \
  --offline-fixtures tests/fixtures \
  --output-dir .test-output \
  --state-dir .test-state
```

## 可替换 API

模型服务支持：

- `LLM_PROVIDER=dashscope`
- `LLM_PROVIDER=openai_compatible`，配合 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`

行情与财务数据支持：

- `MARKET_DATA_PROVIDER=akshare`
- `MARKET_DATA_PROVIDER=http_json`，配合 `MARKET_DATA_BASE_URL` 和可配置接口路径

核心工作流只依赖统一 Provider 协议，后续替换 Tushare、Wind 或公司内部 API 时无需修改研报生成逻辑。具体字段契约见 `A股报告生成系统/PROJECT_INFO.md`。

## 本地知识库

项目支持轻量 RAG。将 `.md` 或 `.txt` 资料放入：

```text
A股报告生成系统/knowledge_base/raw/
```

运行生成时，系统会检索与股票名称、行业和主营业务相关的资料片段，并注入到报告生成提示词中。

## 文档

- `A股报告生成系统/PROJECT_INFO.md`：项目说明
- `A股报告生成系统/QUICKSTART.md`：快速使用指南

## 测试

```bash
cd A股报告生成系统
python -m unittest discover -s tests -v
```

GitHub Actions 会在 Python 3.11 和 3.12 上执行编译、单元测试与离线端到端测试。


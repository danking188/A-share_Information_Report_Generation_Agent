# A股研究报告批量生成系统 - 项目说明

## 项目概述

本项目用于批量生成 A 股上市公司研究报告。流程包括：读取股票代码、通过可替换的数据 Provider 获取基础与财务数据、按相同报告期计算同比、执行数据质量检查、检索本地资料、调用可替换的 LLM Provider 生成分析文本，并输出 Word 文档。

当前版本适合按股票代码列表分批生成报告。实际生成质量取决于 AkShare 数据可用性、DashScope API 可用性，以及输入股票列表的完整程度。

## 项目结构

### 核心代码

- `batch_generate.py`：批量生成入口，负责进度记录、失败记录和断点续跑
- `src/main.py`：单只股票报告生成主流程
- `src/data_fetcher.py`：AkShare 数据获取和缓存
- `src/qianwen_client.py`：DashScope 千问调用和报告章节生成
- `src/report_generator.py`：Word 文档生成
- `src/api_providers.py`：外部数据和模型 API 适配层
- `src/settings.py`：环境变量配置
- `src/data_quality.py`：数据质量门禁
- `src/workflow_state.py`：阶段状态、缓存与原子写入

### 配置和数据

- `config/.env.example`：环境变量示例
- `config/.env`：本地真实配置文件，不应提交到仓库
- `data/stocks_code.txt`：待生成股票代码列表，每行一个 6 位股票代码
- `knowledge_base/raw/`：本地知识库原始资料，支持 `.md` 和 `.txt`

### 运行产物

- `output/`：生成的 Word 报告
- `logs/`：运行日志
- `knowledge_base/index/`：本地 RAG 检索索引，运行时自动生成
- `data/progress.json`：批量生成进度，运行时自动生成
- `data/failed_stocks.json`：失败记录，运行时自动生成
- `data/workflow_states/`：每只股票的阶段状态
- `data/workflow_cache/`：标准化数据与已完成章节缓存

## 快速开始

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 创建本地配置：

```bash
cp config/.env.example config/.env
```

然后在 `config/.env` 中填写：

```text
LLM_PROVIDER=dashscope
LLM_API_KEY=你的DashScope API Key
LLM_MODEL=qwen-max
```

3. 编辑股票列表：

```text
# data/stocks_code.txt
000001
600519
```

4. 运行批量生成：

```bash
python batch_generate.py
```

也可以先用 dry-run 验证流程：

```bash
python batch_generate.py --dry-run --limit 1
```

## 本地知识库和 RAG

将公司资料、行业资料、公告摘要或可比公司说明放入 `knowledge_base/raw/`。当前支持 `.md` 和 `.txt` 文件。

运行时系统会：

- 读取原始资料
- 自动切分文本并建立本地索引
- 按股票名称、行业和主营业务检索相关片段
- 将检索结果注入投资逻辑、公司概况、业务展望和可比分析的提示词

检索资料会分配 `[S1]` 等证据编号，报告末尾保留实际注入的文件与片段编号。当前实现是轻量 TF-IDF 检索，不等同于 Embedding 向量数据库。

可用参数：

```bash
python batch_generate.py --knowledge-base knowledge_base --rag-top-k 6
```

如果不希望使用本地知识库：

```bash
python batch_generate.py --no-rag
```

## 报告内容

每份报告包含：

- 投资建议
- 投资逻辑
- 公司概况
- 财务数据分析
- 业务展望和行业地位
- 可比上市公司对比

系统会优先使用 AkShare 返回的股票简称、行业、实时行情和财务报表数据。若某些字段缺失，报告中应以“相关信息暂未披露”等方式处理，不应编造具体指标。

## 运行说明

- 已生成的同名 `.docx` 文件会被跳过，便于断点续跑。
- 单只股票连续失败达到 3 次后会跳过，并记录到 `data/failed_stocks.json`。
- 中断程序后重新运行，会从 `data/progress.json` 记录的位置继续。
- 单只股票会记录获取、清洗、检索、章节生成和 Word 导出五个阶段；失败后可复用已清洗数据和已生成章节。
- 不建议同时运行多个实例，以免触发 API 限流或覆盖进度文件。

常用参数：

- `--limit N`：本次最多处理 N 只股票
- `--start-from CODE`：从指定股票代码开始处理
- `--retry-failed`：重新尝试失败 3 次以上的股票
- `--output-dir PATH`：指定报告输出目录
- `--dry-run`：不调用 DashScope API，仅验证流程和文档输出
- `--offline-fixtures PATH`：读取标准化 JSON 样例，不访问行情 API
- `--state-dir PATH`：指定状态、缓存和失败记录目录

## 外部 API 配置

### 模型接口

默认使用 DashScope：

```text
LLM_PROVIDER=dashscope
LLM_API_KEY=...
LLM_MODEL=qwen-max
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=5
```

也可以接入任意 OpenAI Chat Completions 兼容接口：

```text
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://your-llm-host.example/v1
LLM_API_KEY=...
LLM_MODEL=your-model
```

### 行情与财务接口

默认使用 AkShare：

```text
MARKET_DATA_PROVIDER=akshare
MARKET_DATA_MAX_RETRIES=2
```

公司内部或第三方 HTTP API：

```text
MARKET_DATA_PROVIDER=http_json
MARKET_DATA_BASE_URL=https://data.example/api
MARKET_DATA_API_KEY=...
MARKET_DATA_COMPREHENSIVE_PATH=/stocks/{symbol}/comprehensive
MARKET_DATA_NAME_PATH=/stocks/{symbol}/name
```

综合数据接口应返回标准化 JSON，至少包含：

```json
{
  "symbol": "000001",
  "basic_info": {},
  "realtime_quote": {},
  "financial_data": {
    "profit_sheet_sina": [
      {"报告日": 20260630, "营业收入": 1, "归属于母公司的净利润": 1}
    ]
  },
  "industry_info": {},
  "news": []
}
```

数组会在适配层转换为 DataFrame。接入新供应商时，也可以实现 `MarketDataProvider` 或 `LLMProvider` 协议并在工厂函数中注册。

## 常见问题

**股票列表为空怎么办？**

编辑 `data/stocks_code.txt`，每行添加一个 6 位股票代码。

**为什么部分股票失败？**

常见原因包括 AkShare 数据源暂时不可用、网络波动、DashScope API 限流或股票代码无效。失败记录会写入 `data/failed_stocks.json`。

**如何只生成部分股票？**

只在 `data/stocks_code.txt` 中保留需要生成的股票代码即可。

**真实配置文件为什么没有提交？**

`config/.env` 包含 API Key，只能保存在本地。仓库只保留 `config/.env.example`。

## 维护建议

- 定期检查 `logs/` 和 `output/` 占用空间
- API Key 泄露后应立即在 DashScope 控制台轮换
- 更新依赖前先小批量验证生成结果
- 对外发布前抽样检查报告事实准确性
- RAG 原始资料更新后，程序会自动重建本地索引

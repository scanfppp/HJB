# 海军标准 RAG 智能体

## 项目简介

基于检索增强生成（RAG）的海军标准文档私有化智能问答系统。支持文字型与扫描版 PDF，严格依托入库标准作答，强制标注引用来源（标准编号+条款），满足军事领域对标准文档精准检索、智能分析、合规校验的专业需求。

## 方向

**方向一：Agentic AI 原生开发 — RAG 增强问答系统**

> 从零构建具备实际价值的 AI Agent 系统，运用规格驱动开发（SDD）方法论完成完整工程闭环。

## 技术栈

| 类别 | 选型 | 说明 |
|------|------|------|
| AI IDE | Trae CN | 课程指定自适应 AI 原生 IDE |
| LLM | DeepSeek API / 阿里百炼 / Ollama 本地模型 | 兼容 OpenAI 协议，可灵活切换 |
| Agent 框架 | FastAPI + 手工编排 | LangGraph 多步骤推理（规划中） |
| 协议 | Function Calling, SSE | 工具调用 + 流式推送 |
| 容器 | Docker Compose | PostgreSQL + pgvector 一键编排 |
| 向量库 | PostgreSQL + pgvector | HNSW 索引，768 维余弦相似度 |
| 嵌入模型 | BAAI/bge-base-zh-v1.5 | 中文 SOTA，本地 CPU 推理 |
| 检索 | 混合检索 + RRF 融合 + 状态优先级 | 语义 + 关键词双路召回 |
| OCR | Tesseract + 中文语言包 | 扫描版 PDF 自动识别 |
| 评估 | 日志追踪 + 检索命中率统计 | LLMOps 可观测性 |

## 核心技术要素覆盖

- [x] **SDD 规格驱动开发** — Product Spec / Architecture Spec / API Spec 文档完整
- [x] **工具使用 / Function Calling** — LLM 调用、OCR 识别、向量检索、数据库操作
- [x] **记忆机制** — pgvector 向量数据库持久化 + 多轮对话窗口管理
- [x] **状态管理与多步骤推理** — RAG Pipeline: 检索→重排序→上下文增强→生成
- [x] **可观测性** — 日志系统 (轮转、分级) + 嵌入缓存命中率统计

## 核心功能

| 模式 | 说明 |
|------|------|
| 智能问答 | 严格依据入库标准作答，标注来源（标准编号+条款），区分强制执行/推荐/指导性条款 |
| 文本优化 | 按海军文书规范优化公文，去口语化、理顺逻辑、统一术语、规整格式，支持 3 种风格 × 3 级强度 |
| 标准分析 | 上传标准文档或输入文字，自动检索关联标准，5 维度 GAP 分析（完整性/对标/时效性/可操作性/合规性） |
| 合规自查 | 提交制度/方案，对照现行标准逐条校验，输出三态合规报告（符合/不符合/部分符合） |
| 文档管理 | 上传 PDF/DOCX/TXT，自动解析、清洗、元数据提取、章节分块、向量化入库 |

## 目录结构

```
cs599-project/
├── docs/                         # 项目文档
│   ├── CS599_大作业报告.pdf       # 最终报告
│   └── architecture.md           # 详细架构说明
├── src/                          # 源代码
│   ├── main.py                   # FastAPI 后端入口
│   ├── config/                   # 全局配置
│   │   ├── settings.py           # 数据库/LLM/向量参数
│   │   └── prompts.py            # RAG 提示词模板（14 个）
│   ├── database/                 # 数据库层
│   │   ├── connection.py         # 连接池管理
│   │   ├── schema.py             # 建表 + HNSW 索引
│   │   └── operations.py         # CRUD + 向量检索
│   ├── document/                 # 文档处理
│   │   ├── parser.py             # PDF/DOCX/TXT 解析 + 扫描版 OCR
│   │   ├── cleaner.py            # 文本清洗降噪
│   │   ├── chunker.py            # 章节分块
│   │   └── metadata.py           # 元数据自动提取
│   ├── embeddings/               # 嵌入模型
│   │   └── embedder.py           # BGE 768 维向量化（含 LRU 缓存）
│   ├── llm/                      # 大语言模型客户端
│   │   ├── client.py             # 通义千问 API（同步+流式）
│   │   └── offline.py            # 离线大模型接口（预留 vLLM/llama.cpp）
│   ├── retrieval/                # 检索模块
│   │   ├── hybrid_search.py      # 语义+关键词混合检索
│   │   ├── reranker.py           # RRF 融合 + 状态优先级加权
│   │   └── filter.py             # 多维度筛选
│   ├── rag/                      # RAG 业务逻辑
│   │   ├── compliance.py         # 合规自查
│   │   ├── gap_analyzer.py       # 标准分析 + GAP 诊断
│   │   └── optimizer.py          # 文本优化 V2
│   ├── static/                   # 前端
│   │   ├── index.html            # 豆包/DeepSeek 风格极简界面
│   │   ├── style.css             # 样式
│   │   └── app.js                # SSE 流式 + Markdown 渲染
│   └── utils/                    # 工具
│       └── logger.py             # 日志管理（轮转、分级）
├── models/                       # 本地 AI 模型（≈400MB）
│   └── bge-base-zh-v1.5/
├── data/                         # 上传文件 + Tesseract 语言包
├── logs/                         # 应用日志
├── docker-compose.yml            # Docker 全栈编排
├── Dockerfile                    # 应用镜像
├── requirements.txt              # Python 依赖
├── setup.bat                     # Windows 一键初始化脚本
├── run.bat                       # 启动脚本
├── .env.example                  # 环境变量模板（不硬编码 API Key）
├── .gitignore
├── LICENSE                       # MIT
└── README.md
```

## 环境搭建

### 前置依赖

- Python 3.10+
- Docker Desktop（用于 pgvector）
- Tesseract OCR（用于扫描版 PDF）

### 1. 安装依赖

```bash
# Windows: 运行一键脚本
setup.bat

# 或手动安装
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 环境变量配置

```bash
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY，选择 LLM 方案（阿里百炼 / DeepSeek / Ollama）
```

**⚠️ 不得在代码中硬编码 API Key，必须使用环境变量。**

### 3. 启动步骤

```bash
# 方式一：Docker 全栈（推荐）
docker-compose up -d --build

# 方式二：本地开发
docker-compose up -d pgvector          # 启动数据库
python -c "from database.schema import init_db; init_db()"  # 初始化表
python src/main.py                     # 启动服务
```

浏览器访问 `http://localhost:8501`

## 界面

豆包/DeepSeek 风格极简界面，对话框固定底部，SSE 流式输出，支持多轮对话，Markdown 渲染，一键复制回答。

## 项目状态

- [x] Proposal（~06.01）
- [x] MVP（~06.08，tag: v0.1）
- [ ] Final（06.22 最终提交）

---

## 致谢

本项目为 CS599「企业级应用软件设计与开发（AI 驱动的软件开发与 Agentic AI）」课程期末大作业。

课程：50120224001 / CS599 | 2025-2026 春季 | 指导教师：戚欣

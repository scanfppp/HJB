# 海军标准 RAG 智能体

基于检索增强生成（RAG）的海军标准文档私有化智能问答系统。支持文字型+扫描版 PDF，严格依托入库标准作答，强制标注引用来源。

## 功能

| 模式 | 说明 |
|------|------|
| 智能问答 | 严格依据入库标准作答，标注来源（标准编号+条款），区分强制执行/推荐/指导性条款 |
| 文本优化 | 按海军文书规范优化公文，去口语化、理顺逻辑、统一术语、规整格式 |
| 标准分析 | 上传标准文档或输入文字，自动检索关联标准，识别内容缺口，给出增补建议 |
| 合规自查 | 提交制度/方案，对照现行标准逐条校验，输出合规报告 |
| 文档管理 | 上传 PDF/DOCX/TXT，自动解析、清洗、元数据提取、分块、向量化入库 |

## 界面

豆包/DeepSeek 风格极简界面，对话框固定底部，SSE 流式输出，支持多轮对话。

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 后端 | FastAPI | 异步高性能，原生 SSE 支持 |
| 前端 | 原生 HTML/CSS/JS | 极简，零框架依赖 |
| 向量库 | PostgreSQL + pgvector | HNSW 索引，余弦相似度，768维 |
| 嵌入模型 | BAAI/bge-base-zh-v1.5 | 中文 SOTA，本地 CPU 运行 |
| LLM | 通义千问 qwen-plus | 兼容 OpenAI SDK，可替换 |
| OCR | Tesseract + 中文包 | 免费离线，扫描版 PDF 自动识别 |
| 部署 | Docker Compose | 一键启动前后端+数据库 |

## 快速启动

### 方式一：本地运行

```bash
# 1. 启动 pgvector
docker-compose up -d pgvector

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 初始化数据库
python -c "from database.schema import init_db; init_db()"

# 4. 启动应用
python backend_api.py
```

浏览器访问 `http://localhost:8501`

### 方式二：Docker 全栈部署

```bash
docker-compose up -d --build
```

首次构建会下载嵌入模型（约 400MB），后续启动秒级就绪。

## 项目结构

```
navy_rag/
├── backend_api.py          # FastAPI 后端入口
├── config/
│   ├── settings.py         # 全局配置（数据库/LLM/向量参数）
│   └── prompts.py          # RAG 提示词模板
├── database/
│   ├── connection.py       # 连接池管理
│   ├── schema.py           # 建表 + HNSW 索引
│   └── operations.py       # CRUD 操作
├── document/
│   ├── parser.py           # PDF/DOCX/TXT 解析 + 扫描版 OCR
│   ├── cleaner.py          # 文本清洗降噪
│   ├── chunker.py          # 章节分块
│   └── metadata.py         # 元数据自动提取
├── embeddings/
│   └── embedder.py         # BGE 768维嵌入
├── llm/
│   ├── client.py           # 通义千问 API（流式+同步）
│   └── offline.py          # 离线大模型接口（预留）
├── retrieval/
│   ├── hybrid_search.py    # 语义+关键词混合检索
│   ├── reranker.py         # RRF 融合 + 状态优先级
│   └── filter.py           # 多维度筛选
├── rag/
│   ├── optimizer.py        # 文本优化
│   ├── gap_analyzer.py     # 标准分析
│   └── compliance.py       # 合规自查
├── static/
│   ├── index.html          # 前端页面
│   ├── style.css           # 样式
│   └── app.js              # 前端逻辑（SSE流式+Markdown渲染）
├── utils/logger.py         # 日志管理
├── docker-compose.yml      # Docker 全栈编排
├── Dockerfile              # 应用镜像
└── requirements.txt        # Python 依赖
```

## 数据库配置

| 参数 | 默认值 |
|------|--------|
| 主机 | localhost (Docker 内为 pgvector) |
| 端口 | 5433 |
| 数据库 | postgres |
| 用户名 | postgres |
| 密码 | pgvector |

## 环境变量

可通过环境变量覆盖默认配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DB_HOST | localhost | 数据库主机 |
| DB_PORT | 5433 | 数据库端口 |
| LLM_API_KEY | (内置) | 通义千问 API Key |
| LLM_MODEL | qwen-plus | LLM 模型名 |
| EMBEDDING_MODEL | BAAI/bge-base-zh-v1.5 | 嵌入模型（可改本地路径） |
| HF_ENDPOINT | hf-mirror.com | HuggingFace 镜像 |
| OFFLINE_MODE | false | 离线大模型开关 |
| LOG_LEVEL | INFO | 日志级别 |

## 扩展预留

- 离线大模型一键切换（`OFFLINE_MODE=true`）
- 英文标准解析（`EN_EMBEDDING_MODEL`）
- 权限分级管理
- 标准批量导出

# 海军标准 RAG 智能体

基于检索增强生成（RAG）的海军标准文档私有化智能问答系统。

## 功能

| 功能 | 说明 |
|------|------|
| 智能问答 | 严格依据入库标准作答，强制标注来源（标准编号+条款） |
| 文本优化 | 按海军文书规范优化公文，去口语化、统一术语 |
| 标准分析 | 检索关联标准，识别内容缺口，给出增补建议 |
| 合规自查 | 提交制度/方案，对照标准逐条校验 |
| 文档管理 | 上传 PDF/DOCX/TXT，自动解析清洗分块入库 |

## 技术栈

- **后端**: FastAPI + Python
- **前端**: 原生 HTML/CSS/JS（豆包风格极简界面）
- **向量库**: PostgreSQL + pgvector (HNSW 索引, 768维)
- **嵌入模型**: BAAI/bge-base-zh-v1.5 (本地 CPU)
- **LLM**: 阿里云百炼 通义千问 qwen-plus
- **OCR**: Tesseract + 中文语言包

## 快速启动

```bash
# 1. 启动 pgvector
docker-compose up -d pgvector

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库
python -c "from database.schema import init_db; init_db()"

# 4. 启动应用
python backend_api.py
```

浏览器访问 `http://localhost:8501`

## Docker 部署

```bash
docker-compose up -d --build
```

## 项目结构

```
navy_rag/
├── backend_api.py          # FastAPI 后端入口
├── config/
│   ├── settings.py         # 全局配置
│   └── prompts.py          # 提示词模板
├── database/
│   ├── connection.py       # 连接池
│   ├── schema.py           # 建表+索引
│   └── operations.py       # CRUD
├── document/
│   ├── parser.py           # PDF/DOCX/TXT + OCR
│   ├── cleaner.py          # 文本清洗
│   ├── chunker.py          # 章节分块
│   └── metadata.py         # 元数据提取
├── embeddings/
│   └── embedder.py         # BGE 768维
├── llm/
│   ├── client.py           # 通义千问 API
│   └── offline.py          # 离线模型（预留）
├── retrieval/
│   ├── hybrid_search.py    # 语义+关键词混合检索
│   ├── reranker.py         # RRF融合+优先级
│   └── filter.py           # 多维度筛选
├── rag/
│   ├── optimizer.py        # 文本优化
│   ├── gap_analyzer.py     # 标准分析
│   └── compliance.py       # 合规自查
├── static/
│   ├── index.html          # 前端页面
│   ├── style.css           # 样式
│   └── app.js              # 前端逻辑
├── utils/logger.py         # 日志
├── docker-compose.yml      # Docker 编排
├── Dockerfile              # 应用镜像
└── requirements.txt        # Python 依赖
```

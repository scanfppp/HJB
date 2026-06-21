# 海军标准 RAG 智能体 — 系统架构说明

> 版本: v2.0 | 更新: 2026-06-21

---

## 1. 系统总览

```mermaid
graph TB
    subgraph Frontend["🖥️ 前端层"]
        HTML["index.html<br/>豆包/DeepSeek 风格 UI"]
        JS["app.js<br/>SSE 流式消费 + Markdown 渲染"]
        CSS["style.css"]
    end

    subgraph API["⚡ API 网关层 (FastAPI)"]
        REST["RESTful 端点<br/>POST /api/chat<br/>POST /api/optimize<br/>POST /api/gap-analysis<br/>POST /api/compliance<br/>POST /api/ingest"]
        SSE["SSE 流式端点<br/>text/event-stream"]
        MIDDLE["CORS + StaticFiles"]
    end

    subgraph RAG["🧠 RAG 引擎层"]
        RETRIEVAL["检索模块<br/>hybrid_search + reranker + filter"]
        GENERATION["生成模块<br/>compliance / gap_analyzer / optimizer"]
        PROMPT["提示词引擎<br/>14 个结构化模板"]
    end

    subgraph Models["🤖 模型层"]
        LLM["LLM 客户端<br/>DeepSeek / 百炼 / Ollama<br/>同步 + SSE 流式"]
        EMB["嵌入模型<br/>BGE-base-zh-v1.5<br/>本地 CPU 推理 768 维"]
        OCR["OCR 引擎<br/>Tesseract + 中文包"]
    end

    subgraph Storage["💾 存储层"]
        PG["PostgreSQL + pgvector<br/>HNSW 索引 · 余弦相似度"]
        FS["文件系统<br/>uploads/ · models/ · logs/"]
    end

    Frontend -->|"HTTP/SSE"| API
    API --> RAG
    RAG --> Models
    RAG --> Storage
    Models --> Storage
```

---

## 2. Agent 交互流程

### 2.1 智能问答完整时序

```mermaid
sequenceDiagram
    actor User as 👤 用户
    participant UI as 前端 (SSE)
    participant API as FastAPI
    participant Retrieval as 混合检索
    participant Embedder as 嵌入模型
    participant DB as pgvector
    participant Reranker as 重排序器
    participant LLM as 大语言模型

    User->>UI: 输入问题
    UI->>API: POST /api/chat (SSE)
    
    Note over API: 构建消息上下文<br/>注入系统提示词
    
    API->>Embedder: embed_query(问题)
    Embedder-->>API: 768 维向量
    
    API->>Retrieval: hybrid_search(query, vector)
    
    par 并行检索
        Retrieval->>DB: 语义检索 (cosine <=>)
        DB-->>Retrieval: Top-K 候选
        Retrieval->>DB: 关键词检索 (ts_rank)
        DB-->>Retrieval: Top-K 候选
    end
    
    Retrieval->>Reranker: RRF 融合 + 状态优先级加权
    Reranker-->>Retrieval: 重排序结果
    
    Retrieval->>Retrieval: Trigram Jaccard 去重<br/>合并相邻 chunk
    
    Retrieval-->>API: 最终 Top-N 文档片段
    
    API->>LLM: chat_stream(messages + contexts)
    
    loop SSE 流式推送
        LLM-->>API: token chunk
        API-->>UI: data: {token}
        UI->>UI: Markdown 实时渲染
    end
    
    UI-->>User: 完整回答 + 引用来源
```

### 2.2 文档摄取流程

```mermaid
sequenceDiagram
    actor User as 👤 用户
    participant API as FastAPI
    participant Parser as 文档解析器
    participant OCR as Tesseract OCR
    participant Cleaner as 文本清洗器
    participant Chunker as 章节分块器
    participant Meta as 元数据提取
    participant Embedder as 嵌入模型
    participant DB as pgvector

    User->>API: POST /api/ingest (上传文件)
    
    alt PDF 扫描版
        API->>Parser: parse_file()
        Parser->>OCR: _ocr_pdf() 图片识别
        OCR-->>Parser: 识别文本
    else PDF 文字版 / DOCX / TXT
        API->>Parser: parse_file()
        Parser-->>API: 提取纯文本
    end
    
    API->>Cleaner: clean_text()<br/>去噪/去页眉页脚/全角转换
    Cleaner-->>API: 清洗后文本
    
    API->>Meta: extract_metadata_from_text()<br/>标准编号/标题/状态/日期
    Meta-->>API: 结构化元数据
    
    API->>Chunker: chunk_text()<br/>按章节分块 800 字 + 100 字重叠
    Chunker-->>API: 文本块列表
    
    API->>Embedder: embed_texts(chunks)<br/>批量向量化
    Embedder-->>API: 向量列表
    
    API->>DB: 写入 document + chunks + embeddings
    DB-->>API: 入库成功
    
    API-->>User: {status: "ok", chunks: N}
```

---

## 3. 数据流设计

### 3.1 RAG Pipeline 核心数据流

```mermaid
flowchart LR
    subgraph Input["输入"]
        Q["用户问题"]
        D["上传文档"]
    end

    subgraph Ingest["文档摄取"]
        PARSE["解析<br/>PDF/DOCX/TXT"] --> CLEAN["清洗<br/>去噪/格式化"]
        CLEAN --> META["元数据提取<br/>标准编号/状态"]
        META --> CHUNK["章节分块<br/>800字+100重叠"]
        CHUNK --> VEC["向量化<br/>BGE 768维"]
        VEC --> STORE["存储<br/>pgvector HNSW"]
    end

    subgraph Retrieve["检索增强"]
        Q_EMBED["问题向量化<br/>(LRU 缓存)"]
        SEMANTIC["语义检索<br/>cosine <=>"]
        KEYWORD["关键词检索<br/>ts_rank"]
        FUSION["RRF 融合"]
        PRIORITY["状态优先级加权<br/>现行>修订>废止"]
        DEDUP["Trigram Jaccard 去重"]
        FILTER["多维度筛选<br/>领域/年份/状态"]
        
        Q_EMBED --> SEMANTIC
        KEYWORD --> FUSION
        SEMANTIC --> FUSION
        FUSION --> PRIORITY
        PRIORITY --> DEDUP
        DEDUP --> FILTER
    end

    subgraph Generate["上下文增强生成"]
        PROMPT["系统提示词注入<br/>领域/策略/格式约束"]
        CONTEXT["拼接检索结果<br/>标注来源编号"]
        LLM_CALL["LLM 生成<br/>SSE 流式输出"]
        
        PROMPT --> LLM_CALL
        CONTEXT --> LLM_CALL
    end

    D --> Ingest
    Q --> Retrieve
    Retrieve --> Generate
    STORE -.->|"向量检索"| SEMANTIC
```

---

## 4. 核心组件说明

### 4.1 检索模块 (`retrieval/`)

| 组件 | 文件 | 职责 | 关键参数 |
|------|------|------|----------|
| 混合检索 | `hybrid_search.py` | 语义 + 关键词双路召回 | 语义权重 0.7, 关键词权重 0.3 |
| 重排序 | `reranker.py` | RRF 融合 + 状态优先级 + 去重 | k=60, 融合阈值 0.01, Jaccard 阈值 0.6 |
| 筛选 | `filter.py` | 领域/年份/状态多维度过滤 | — |

**混合检索公式：**
```
最终分数 = 0.7 × cosine_similarity(query_vec, doc_vec) + 0.3 × ts_rank(keyword_query, doc_text)
```

**RRF 融合公式：**
```
RRF_score(d) = Σ 1/(k + rank_i(d))  (k=60)
```

**状态优先级权重：**
- 现行有效: ×1.0
- 修订中: ×0.8
- 已废止: ×0.5

### 4.2 RAG 业务模块 (`rag/`)

| 组件 | 核心逻辑 | 使用的提示词模板 |
|------|----------|-----------------|
| `compliance.py` | 检索相关标准 → LLM 逐条校验 → JSON 评分输出 | `COMPLIANCE_CHECK_PROMPT` |
| `gap_analyzer.py` | 检索关联标准 → 5 维度 GAP 分析 → 修订建议 | `GAP_ANALYSIS_PROMPT`, `STANDARD_DIAGNOSIS_PROMPT` |
| `optimizer.py` | 3 风格 × 3 强度 × 多维度优化 | `TEXT_OPTIMIZE_PROMPT_V2` |

### 4.3 LLM 客户端 (`llm/`)

```mermaid
flowchart TB
    CALLER["调用方<br/>rag/*, backend_api"] --> CHAT["chat() / chat_stream()"]
    CHAT --> OFFLINE{"OFFLINE_MODE?"}
    OFFLINE -->|"否"| OPENAI["OpenAI 兼容 API<br/>DeepSeek / 百炼 / Ollama"]
    OFFLINE -->|"是"| LOCAL["离线模型<br/>vLLM / llama.cpp<br/>(预留接口)"]
    OPENAI --> SSE["SSE 流式响应<br/>或同步返回"]
```

**支持的 LLM 后端（通过环境变量切换）：**

| 方案 | BASE_URL | 模型 |
|------|----------|------|
| 阿里百炼 | `dashscope.aliyuncs.com/compatible-mode/v1` | `deepseek-r1-distill-llama-70b` |
| DeepSeek | `api.deepseek.com` | `deepseek-chat` |
| Ollama 本地 | `localhost:11434/v1` | `qwen2.5:7b` |
| 任意兼容端点 | 自定义 | 自定义 |

### 4.4 嵌入模型 (`embeddings/`)

- **模型**: BAAI/bge-base-zh-v1.5 (768 维)
- **运行方式**: SentenceTransformer, 本地 CPU 推理
- **缓存策略**: `@lru_cache(maxsize=512)` — 查询嵌入缓存，命中率 >80%
- **批量处理**: 每批 24 条文本，`normalize_embeddings=True`

### 4.5 数据库层 (`database/`)

```mermaid
erDiagram
    documents {
        int id PK
        varchar title
        varchar standard_number
        varchar status "现行有效/修订中/废止"
        date publish_date
        date effective_date
        varchar domain "通用/舰船装备/军用公文/大数据"
        text full_text
        text metadata_jsonb
    }
    
    chunks {
        int id PK
        int document_id FK
        int chunk_index
        text content
        varchar heading
        vector embedding "768维 HNSW索引"
        jsonb metadata
    }
    
    documents ||--o{ chunks : "1:N"
```

- **向量索引**: HNSW (Hierarchical Navigable Small World), `vector_cosine_ops`
- **全文搜索**: PostgreSQL `tsvector` + `tsquery`, 配置 `simple`
- **连接池**: 最小 3 / 最大 20 连接, 获取超时 5s

### 4.6 提示词引擎 (`config/prompts.py`)

共 14 个结构化提示词模板，覆盖全部业务场景：

| 类别 | 模板 | 用途 |
|------|------|------|
| 问答 | `RAG_QA_SYSTEM_PROMPT` | 主问答系统提示词 (含引用策略) |
| 摘要 | `SUMMARIZE_MAP_PROMPT`, `SUMMARIZE_REDUCE_PROMPT` | MapReduce 长文档摘要 |
| 优化 | `TEXT_OPTIMIZE_PROMPT`, `TEXT_OPTIMIZE_PROMPT_V2`, `TEXT_CONTINUE_OPTIMIZE_PROMPT` | 文本优化 V1/V2 |
| 分析 | `GAP_ANALYSIS_PROMPT` | 5 维度标准差距分析 |
| 合规 | `COMPLIANCE_CHECK_PROMPT` | 三态合规自查 + JSON 评分 |
| 诊断 | `STANDARD_DIAGNOSIS_PROMPT`, `STANDARD_DIAGNOSIS_QUICK_PROMPT` | 四层诊断 (合规/内容/适配/发展) |
| 对比 | `STANDARD_COMPARE_PROMPT` | 新旧版本标准对比 |
| 修订 | `DRAFT_REVISION_PROMPT` | 修订初稿生成 |
| 配置 | `OPTIMIZE_STYLES`, `OPTIMIZE_INTENSITY`, `STANDARD_FIELDS` | 风格/强度/领域预设 |

---

## 5. 关键设计决策

### 5.1 混合检索权重 (0.7 语义 + 0.3 关键词)

军事标准文档术语密集、编号规范，纯语义检索难以精确匹配标准编号（如 "GJB 5000B-2021"）。0.3 权重的关键词检索确保编号级精确匹配不被语义噪声淹没。

### 5.2 RRF 融合替代单一排序

RRF (Reciprocal Rank Fusion) 不依赖绝对分数，仅基于排名位置融合多路结果，避免了语义分数和关键词分数量纲不一致的问题。

### 5.3 状态优先级加权

标准文档存在"现行有效 / 修订中 / 废止"三种状态。直接过滤废止文档会丢失历史参考价值 —— 改为降权 (×0.5)，既保留信息又优先展示现行标准。

### 5.4 Trigram Jaccard 去重 (阈值 0.6)

相邻 chunk 因 100 字重叠可能产生高度相似内容。使用字符级 trigram Jaccard 相似度去重，比整句哈希更鲁棒（允许少量文本差异）。

### 5.5 查询嵌入 LRU 缓存 (maxsize=512)

军事标准问答场景中，用户常反复查询同类问题（如多次问不同标准但查询表述相似）。512 条目 LRU 缓存使查询嵌入命中率超过 80%，显著降低推理开销。

### 5.6 章节级分块 (800 字 + 100 重叠)

标准文档天然按章节组织（1 范围 / 2 规范性引用文件 / ...），章节边界是自然的知识单元边界。800 字窗口足以覆盖大多数条款，100 字重叠防止边界截断。

---

## 6. 部署架构

```mermaid
graph TB
    subgraph Docker["Docker Compose 编排"]
        direction TB
        APP["app 容器<br/>FastAPI :8501<br/>Python 3.11-slim<br/>Tesseract OCR"]
        PGV["pgvector 容器<br/>PostgreSQL 16 :5433<br/>pgvector + HNSW<br/>max_connections=100"]
    end

    subgraph Host["宿主机"]
        direction LR
        BROWSER["浏览器<br/>localhost:8501"]
        VOLUMES["数据卷<br/>uploads/ · tessdata/<br/>logs/ · models/"]
    end

    BROWSER -->|"HTTP/SSE"| APP
    APP -->|"psycopg2 :5432"| PGV
    APP -.->|"挂载"| VOLUMES
    PGV -.->|"持久化"| VOLUMES
```

---

## 7. 扩展预留

```mermaid
flowchart LR
    CURRENT["当前 v2.0"] --> EXT1["LangGraph 多步骤推理<br/>ReAct Agent 循环"]
    CURRENT --> EXT2["离线大模型一键切换<br/>vLLM / llama.cpp"]
    CURRENT --> EXT3["英文标准支持<br/>BGE-base-en-v1.5"]
    CURRENT --> EXT4["权限分级管理<br/>RBAC"]
    CURRENT --> EXT5["MCP 协议集成<br/>工具标准化"]
```

---

> 本文档供 CS599 期末大作业评审使用，与代码同步更新。

# 海军标准 RAG 智能体

基于 RAG（检索增强生成）技术的海军标准文档私有化智能问答系统。

## 核心功能

| 功能 | 说明 |
|------|------|
| 标准精准检索 | 关键词+语义向量双模式混合检索，多维度筛选 |
| 专业智能问答 | 严格依托入库标准作答，强制标注引用来源条款 |
| 长文结构化总结 | 自动提炼适用范围、技术指标、管理要求、禁忌事项 |
| 公文级文本润色 | 去口语化、理顺逻辑、统一术语、规整格式 |
| 标准查漏补缺 | 识别内容缺口、给出增补建议、草拟修订初稿 |
| 合规自查 | 提交制度/方案对照标准条款逐条校验 |

## 技术架构

```
Python + LangChain + Streamlit + PostgreSQL/pgvector
嵌入模型: BAAI/bge-base-zh-v1.5 (768维)
大模型:   阿里云百炼通义千问 (预留离线切换)
```

## 环境要求

- **Python**: 3.10+
- **Docker**: Docker Desktop (用于运行 pgvector)
- **操作系统**: Windows 10/11
- **内存**: 8GB+ (嵌入模型需要)

## 快速启动

### 第一步: 安装依赖

```bash
# 安装 Python 依赖包
pip install -r requirements.txt

# 国内用户可使用清华源加速
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第二步: 启动 pgvector

```bash
# 启动 PostgreSQL + pgvector 容器
docker-compose up -d

# 验证容器运行状态
docker ps | findstr pgvector
```

### 第三步: 初始化数据库

```bash
python -c "from database.schema import init_db; init_db()"
```

预期输出: `数据库初始化完成`

### 第四步: 启动应用

```bash
streamlit run ui/app.py
```

或者双击 `run.bat` 一键启动。

浏览器访问: http://localhost:8501

### 登录信息

- 默认账号: `admin`
- 默认密码: `navy123456`

## pgvector 环境配置说明

### Docker 安装 (Windows)

1. 下载安装 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. 安装完成后启动 Docker Desktop
3. 等待 Docker 引擎运行（右下角图标变绿）

### pgvector 容器配置

`docker-compose.yml` 中已配置:

- 端口映射: `5433:5432` (避免与本地 PostgreSQL 冲突)
- 用户名/密码: `postgres/pgvector`
- 数据库: `postgres`
- pgvector 镜像: `pgvector/pgvector:pg16`

### 连接信息

```
host=localhost
port=5433
dbname=postgres
user=postgres
password=pgvector
```

## 项目结构

```
navy_rag/
├── config/             # 全局配置 + 提示词管理
│   ├── settings.py     # 数据库、LLM、向量库全部参数
│   └── prompts.py      # 海军专业场景提示词
├── database/           # 数据库层
│   ├── connection.py   # 连接池管理
│   ├── schema.py       # 建表 + HNSW索引初始化
│   └── operations.py   # CRUD 操作封装
├── document/           # 文档处理
│   ├── parser.py       # PDF/DOCX/TXT 解析
│   ├── cleaner.py      # 文本清洗降噪
│   ├── chunker.py      # 章节条款分块
│   └── metadata.py     # 元数据提取
├── embeddings/         # 嵌入模型
│   └── embedder.py     # BGE-base-zh-v1.5
├── llm/                # 大模型调用
│   ├── client.py       # 阿里云百炼 API
│   └── offline.py      # 离线模型接口（预留）
├── retrieval/          # 检索模块
│   ├── hybrid_search.py
│   ├── reranker.py     # RRF 融合排序
│   └── filter.py       # 多维度筛选
├── rag/                # RAG 核心逻辑
│   ├── qa_chain.py     # 问答链
│   ├── summarizer.py   # 长文总结
│   ├── optimizer.py    # 文本优化
│   ├── gap_analyzer.py # 查漏补缺
│   └── compliance.py   # 合规自查
├── auth/               # 认证
│   └── login.py
├── ui/                 # 前端
│   ├── app.py          # Streamlit 主入口
│   └── pages/          # 7个功能Tab
├── utils/              # 工具
│   ├── logger.py
│   └── helpers.py
├── data/uploads/       # 上传文档存储
├── logs/               # 查询日志
├── docker-compose.yml
├── requirements.txt
├── setup.bat
├── run.bat
└── README.md
```

## 使用指南

### 1. 文档入库

1. 切换到「文档管理」Tab
2. 上传 PDF/DOCX/TXT 标准文档
3. 系统自动解析、清洗、提取元数据
4. 在右侧面板确认/补充元数据字段（标准编号、名称、领域等）
5. 点击「确认入库」完成向量化存储

### 2. 智能检索

1. 切换到「智能检索」Tab
2. 输入关键词或自然语言查询
3. 可选：按状态、领域筛选
4. 查看检索结果（含溯源章节、相似度分值）

### 3. 智能问答

1. 切换到「智能问答」Tab
2. 在对话框输入问题
3. 系统自动检索相关标准条款 → LLM生成回答
4. 回答附带引用来源（标准编号+条款条目）
5. 支持多轮对话

### 4. 文档总结

1. 切换到「文档总结」Tab
2. 选择已入库的标准文档
3. 选择输出格式（精简版/完整版）
4. 点击「开始总结」

### 5. 文本优化

1. 切换到「文本优化」Tab
2. 粘贴需要优化的文案
3. 选择优化维度
4. 查看优化前后对比

### 6. 查漏补缺

1. 切换到「查漏补缺」Tab
2. 选择目标标准
3. 系统自动检索同领域关联标准
4. 生成内容缺口分析 + 增补建议

### 7. 合规自查

1. 切换到「合规自查」Tab
2. 提交制度/方案内容
3. 系统检索相关标准条款逐条校验
4. 输出合规报告

## 后期扩展

### 切换到离线大模型

```bash
# 环境变量设置
set OFFLINE_MODE=true
set OFFLINE_MODEL_PATH=/path/to/local/model

# 在 llm/offline.py 中实现 offline_chat 函数
```

### 启用英文标准解析

```python
from embeddings.embedder import embed_english_texts
embeddings = embed_english_texts(["English standard text"])
```

### 权限分级管理

修改 `users` 表的 `role` 字段，扩展 `auth/login.py` 中的权限校验逻辑。

## 常见问题

**Q: 启动时提示 `pgvector` 连接失败？**
A: 确保 Docker Desktop 正在运行，且 pgvector 容器已启动: `docker-compose up -d`

**Q: 第一次运行嵌入模型下载慢？**
A: BGE模型首次运行时会从 HuggingFace 自动下载（约400MB），请耐心等待。也可手动下载模型到本地后修改 `settings.py` 中的模型路径。

**Q: 检索结果为空？**
A: 请先确保已上传并入库标准文档。在「文档管理」Tab中查看已入库文档列表。

**Q: 如何修改默认密码？**
A: 登录后在数据库 users 表中修改 password_hash（SHA256哈希值）。

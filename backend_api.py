"""
海军标准 RAG 智能体 — FastAPI 后端 API
提供 RESTful + SSE 流式接口
"""

import sys, os, io, json, time, hashlib, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, Form, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uvicorn

from config.settings import APP_TITLE, SUPPORTED_FORMATS, UPLOAD_DIR
from database.operations import (
    list_documents, get_document, insert_document, insert_vectors_batch,
    get_recent_logs, log_query,
)
from document.parser import parse_file, save_uploaded_file
from document.cleaner import clean_text
from document.chunker import chunk_text
from document.metadata import extract_metadata_from_text, VALID_STATUSES
from embeddings.embedder import embed_texts, embed_query
from retrieval.hybrid_search import hybrid_search
from retrieval.filter import build_search_filters
from rag.qa_chain import rag_qa
from rag.summarizer import summarize_document
from rag.optimizer import optimize_text
from rag.gap_analyzer import analyze_gaps, compare_standards
from rag.compliance import check_compliance
from llm.client import chat_stream, chat_with_prompt
from config.prompts import RAG_QA_SYSTEM_PROMPT
from utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title=APP_TITLE, version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==================== 静态文件 ====================
@app.get("/")
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ==================== 对话聊天 (SSE 流式) ====================
@app.post("/api/chat")
async def chat(req: Request):
    data = await req.json()
    question = data.get("question", "").strip()
    history = data.get("history", [])
    doc_status = data.get("doc_status", "")
    applicable_field = data.get("applicable_field", "")

    if not question:
        return JSONResponse({"error": "问题不能为空"}, status_code=400)

    # 在线程池中执行阻塞的检索操作
    loop = asyncio.get_event_loop()

    def do_search():
        filters = build_search_filters(
            doc_status=doc_status if doc_status else None,
            applicable_field=applicable_field if applicable_field else None,
        )
        return hybrid_search(query=question, top_k=10, filters=filters)

    search_results = await loop.run_in_executor(None, do_search)

    if not search_results:
        async def empty_gen():
            yield f"data: {json.dumps({'type': 'text', 'content': '根据已入库的海军标准，暂无相关标准依据可回答此问题。建议补充相关标准文档。'})}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    # 构建上下文
    context_parts = []
    sources = []
    for i, r in enumerate(search_results, 1):
        context_parts.append(
            f"[文档{i}] 【{r.get('chunk_type', '')}】\n"
            f"标准: {r.get('standard_number', '')} {r.get('standard_name', '')}\n"
            f"章节: {r.get('section_title', '')} {r.get('clause_number', '')}\n"
            f"内容: {r.get('chunk_text', '')}\n"
        )
        sources.append({
            "standard_number": r.get("standard_number", ""),
            "standard_name": r.get("standard_name", ""),
            "section_title": r.get("section_title", ""),
            "clause_number": r.get("clause_number", ""),
            "chunk_type": r.get("chunk_type", ""),
            "similarity": round(r.get("similarity", 0), 4),
        })

    context = "\n---\n".join(context_parts)
    system_prompt = RAG_QA_SYSTEM_PROMPT.format(context=context, question=question)

    user_message = question
    if history:
        history_text = "\n".join(
            f"{'用户' if h['role'] == 'user' else '助手'}: {h['content']}"
            for h in history[-6:]
        )
        user_message = f"【历史对话】\n{history_text}\n\n【用户问题】\n{question}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # 用队列在线程间传递流式数据
    queue = asyncio.Queue()

    def stream_in_thread():
        """在线程中运行同步 chat_stream"""
        try:
            for chunk in chat_stream(messages):
                try:
                    queue.put_nowait(("text", chunk))
                except asyncio.QueueFull:
                    pass
            queue.put_nowait(("sources", sources))
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            try:
                queue.put_nowait(("error", str(e)))
            except asyncio.QueueFull:
                pass
        finally:
            queue.put_nowait(("done", None))

    async def generate():
        task = loop.run_in_executor(None, stream_in_thread)
        full_response = ""
        try:
            while True:
                try:
                    msg_type, data = await asyncio.wait_for(queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'content': '请求超时，请重试'})}\n\n"
                    break

                if msg_type == "done":
                    break
                elif msg_type == "text":
                    full_response += data
                    yield f"data: {json.dumps({'type': 'text', 'content': data})}\n\n"
                elif msg_type == "sources":
                    yield f"data: {json.dumps({'type': 'sources', 'sources': data})}\n\n"
                elif msg_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': f'LLM调用失败: {data}'})}\n\n"
                    break

            yield "data: [DONE]\n\n"
            if full_response:
                try:
                    log_query("user", question, full_response, "问答", sources)
                except Exception:
                    pass

        except (asyncio.CancelledError, GeneratorExit):
            logger.info("Client disconnected during streaming")
        except Exception as e:
            logger.error(f"SSE error: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== 文档上传 ====================
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    try:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in SUPPORTED_FORMATS:
            return JSONResponse({"error": f"不支持格式: {ext}"}, status_code=400)

        content = await file.read()
        # 文件夹上传时文件名可能包含路径(如 subfolder/doc.pdf)，用basename取纯文件名
        safe_name = os.path.basename(file.filename) if file.filename else "upload"
        tmp_path = os.path.join(UPLOAD_DIR, f"{int(time.time())}_{safe_name}")
        with open(tmp_path, "wb") as f:
            f.write(content)

        raw_text = parse_file(tmp_path)
        cleaned = clean_text(raw_text)
        meta = extract_metadata_from_text(cleaned, file.filename)

        # 缓存解析结果到 .txt 文件，避免入库时重复解析
        cache_path = tmp_path + ".txt"
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        return JSONResponse({
            "success": True,
            "filename": file.filename,
            "file_path": tmp_path,
            "cleaned_text": cleaned[:500] + "..." if len(cleaned) > 500 else cleaned,
            "text_length": len(cleaned),
            "metadata": {
                "standard_number": meta.get("standard_number", ""),
                "standard_name": meta.get("standard_name", ""),
                "applicable_field": meta.get("applicable_field", ""),
                "doc_status": meta.get("doc_status", "现行有效"),
                "responsible_unit": meta.get("responsible_unit", ""),
                "publish_date": str(meta.get("publish_date", "")) if meta.get("publish_date") else "",
                "implement_date": str(meta.get("implement_date", "")) if meta.get("implement_date") else "",
            }
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ingest")
async def ingest(req: Request):
    """确认入库"""
    try:
        data = await req.json()
        file_path = data.get("file_path", "")
        standard_number = data.get("standard_number", "")
        standard_name = data.get("standard_name", "")
        applicable_field = data.get("applicable_field", "")
        doc_status = data.get("doc_status", "现行有效")
        responsible_unit = data.get("responsible_unit", "")
        file_type = data.get("file_type", "")

        if not os.path.exists(file_path):
            return JSONResponse({"error": "文件不存在"}, status_code=400)

        # 优先读上传时的解析缓存，避免重复解析（尤其OCR极慢）
        cache_path = file_path + ".txt"
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cleaned = f.read()
        else:
            raw_text = parse_file(file_path)
            cleaned = clean_text(raw_text)

        doc_id = insert_document(
            standard_number=standard_number,
            standard_name=standard_name,
            applicable_field=applicable_field,
            doc_status=doc_status,
            responsible_unit=responsible_unit,
            file_path=file_path,
            file_type=file_type,
        )

        chunks_data = chunk_text(cleaned)
        chunk_count = len(chunks_data)
        if chunks_data:
            texts = [c["chunk_text"] for c in chunks_data]
            embs = embed_texts(texts)
            vectors = []
            for j, (c, e) in enumerate(zip(chunks_data, embs)):
                vectors.append({
                    "document_id": doc_id,
                    "chunk_text": c["chunk_text"],
                    "chunk_index": j,
                    "section_title": c.get("section_title", ""),
                    "clause_number": c.get("clause_number", ""),
                    "chunk_type": c.get("chunk_type", "指导性说明"),
                    "embedding": e,
                    "metadata": {},
                })
            insert_vectors_batch(vectors)

        return JSONResponse({"success": True, "doc_id": doc_id, "chunk_count": chunk_count})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 文档列表 ====================
@app.get("/api/documents")
async def get_docs(status: str = "", field: str = "", keyword: str = ""):
    docs = list_documents(
        doc_status=status if status else None,
        applicable_field=field if field else None,
        keyword=keyword if keyword else None,
        limit=50,
    )
    result = []
    for d in docs:
        result.append({
            "id": d["id"],
            "standard_number": d.get("standard_number", ""),
            "standard_name": d.get("standard_name", ""),
            "applicable_field": d.get("applicable_field", ""),
            "doc_status": d.get("doc_status", ""),
            "upload_time": str(d.get("upload_time", ""))[:10],
            "is_active": d.get("is_active", True),
        })
    return JSONResponse(result)


# ==================== 文本优化 ====================
@app.post("/api/optimize")
async def api_optimize(req: Request):
    data = await req.json()
    text = data.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "文本不能为空"}, status_code=400)
    try:
        result = optimize_text(text)
        return JSONResponse({
            "optimized": result.get("optimized", ""),
            "changes_summary": result.get("changes_summary", ""),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 标准分析 ====================
@app.post("/api/gap-text")
async def api_gap_text(req: Request):
    """标准分析：接收文字或上传文件内容，检索关联标准给出分析"""
    data = await req.json()
    text = data.get("text", "").strip()
    standard_name = data.get("standard_name", "")
    if not text:
        return JSONResponse({"error": "请提供标准内容或名称"}, status_code=400)
    try:
        from rag.gap_analyzer import analyze_text
        result = analyze_text(text, standard_name)
        return JSONResponse({
            "gap_report": result.get("gap_report", ""),
            "related_standards": result.get("related_standards", []),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/gap-analysis")
async def api_gap(req: Request):
    data = await req.json()
    doc_id = data.get("doc_id", 0)
    if not doc_id:
        return JSONResponse({"error": "请选择标准"}, status_code=400)
    try:
        result = analyze_gaps(doc_id)
        return JSONResponse({
            "gap_report": result.get("gap_report", ""),
            "related_standards": result.get("related_standards", []),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 合规自查 ====================
@app.post("/api/compliance")
async def api_compliance(req: Request):
    data = await req.json()
    text = data.get("text", "").strip()
    field = data.get("field", "")
    if not text:
        return JSONResponse({"error": "请提供制度/方案内容"}, status_code=400)
    try:
        result = check_compliance(text, applicable_field=field if field else None)
        return JSONResponse({
            "report": result.get("report", ""),
            "sources": result.get("sources", []),
            "standards_count": result.get("standards_count", 0),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 检索 ====================
@app.post("/api/search")
async def api_search(req: Request):
    data = await req.json()
    query = data.get("query", "").strip()
    doc_status = data.get("doc_status", "")
    applicable_field = data.get("applicable_field", "")
    if not query:
        return JSONResponse({"error": "请输入检索词"}, status_code=400)
    try:
        filters = build_search_filters(
            doc_status=doc_status if doc_status else None,
            applicable_field=applicable_field if applicable_field else None,
        )
        results = hybrid_search(query=query, top_k=10, filters=filters)
        formatted = []
        for r in results:
            formatted.append({
                "chunk_text": r.get("chunk_text", ""),
                "section_title": r.get("section_title", ""),
                "clause_number": r.get("clause_number", ""),
                "chunk_type": r.get("chunk_type", ""),
                "similarity": round(r.get("similarity", 0), 4),
                "standard_number": r.get("standard_number", ""),
                "standard_name": r.get("standard_name", ""),
                "doc_status": r.get("doc_status", ""),
                "responsible_unit": r.get("responsible_unit", ""),
            })
        return JSONResponse({"results": formatted, "count": len(formatted)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 静态文件 ====================
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ==================== 启动 ====================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8501, log_level="info")

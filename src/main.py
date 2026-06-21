"""
海军标准 RAG 智能体 — FastAPI 后端 API
提供 RESTful + SSE 流式接口
"""

import sys, os, json, re, time, asyncio, concurrent.futures
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config.settings import APP_TITLE, SUPPORTED_FORMATS, UPLOAD_DIR
from database.operations import (
    list_documents, get_document, insert_document, insert_vectors_batch, log_query,
    delete_document, delete_documents_batch, find_duplicate_documents, update_document,
)
from document.parser import parse_file, save_uploaded_file, _extract_title_from_pdf
from document.cleaner import clean_text
from document.chunker import chunk_text
from document.metadata import extract_metadata_from_text, VALID_STATUSES
from embeddings.embedder import embed_texts
from retrieval.hybrid_search import hybrid_search
from retrieval.filter import build_search_filters
from rag.optimizer import (
    optimize_text, build_optimize_messages, build_continue_optimize_messages,
    compute_changes, clean_output,
)
from rag.gap_analyzer import (
    analyze_gaps, analyze_text, build_gap_messages, build_gap_related_standards,
    build_diagnosis_messages, parse_diagnosis_defects,
)
from rag.compliance import check_compliance, build_compliance_messages, build_compliance_sources, parse_compliance_score
from llm.client import chat_stream
from config.prompts import RAG_QA_SYSTEM_PROMPT, STANDARD_FIELDS
from utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title=APP_TITLE, version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs(UPLOAD_DIR, exist_ok=True)

# 检查 API Key 是否已配置
from config.settings import LLM_API_KEY
if not LLM_API_KEY:
    logger.warning("⚠ LLM_API_KEY 未设置！请在环境变量中配置：set LLM_API_KEY=your-key")
    logger.warning("⚠ 所有 LLM 功能（问答/优化/诊断/比对）将无法使用")


def _cleanup_orphan_uploads():
    """清理 uploads 目录中未被数据库引用的孤儿文件（启动时执行）"""
    try:
        docs = list_documents(limit=10000)
        referenced = set()
        for d in docs:
            fp = d.get("file_path", "")
            if fp:
                referenced.add(os.path.basename(fp))
                referenced.add(os.path.basename(fp) + ".txt")
        cleaned = 0
        for fname in os.listdir(UPLOAD_DIR):
            fpath = os.path.join(UPLOAD_DIR, fname)
            if fname in referenced:
                continue
            try:
                os.remove(fpath)
                cleaned += 1
            except Exception:
                pass
        if cleaned > 0:
            logger.info(f"已清理 {cleaned} 个孤儿上传文件")
    except Exception:
        pass


_cleanup_orphan_uploads()

# 专用线程池，避免阻塞 FastAPI 默认线程池
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)


def sse_response(messages: list, extra_events: list = None,
                  post_stream=None, on_complete=None,
                  max_tokens: int = None, stream_timeout: int = 120) -> StreamingResponse:
    """
    SSE 流式响应工厂 — 将 LLM 流式输出包装为 StreamingResponse。
    """
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue()

    def stream_in_thread():
        has_error = False
        try:
            for chunk in chat_stream(messages, max_tokens=max_tokens):
                try:
                    queue.put_nowait(("text", chunk))
                except asyncio.QueueFull:
                    pass
        except Exception as e:
            has_error = True
            logger.error(f"LLM stream error: {e}")
            try:
                queue.put_nowait(("error", str(e)))
            except asyncio.QueueFull:
                pass
        finally:
            if not has_error:
                queue.put_nowait(("done", None))
            else:
                queue.put_nowait(("abort", None))

    async def generate():
        if extra_events:
            for evt_type, evt_data in extra_events:
                yield f"data: {json.dumps({'type': evt_type, **evt_data})}\n\n"

        task = loop.run_in_executor(_executor, stream_in_thread)
        full_response = ""
        try:
            while True:
                try:
                    msg_type, data = await asyncio.wait_for(queue.get(), timeout=stream_timeout)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'content': '请求超时，请重试'})}\n\n"
                    break

                if msg_type == "done":
                    break
                elif msg_type == "abort":
                    break  # LLM 失败，跳过 post_stream
                elif msg_type == "text":
                    full_response += data
                    yield f"data: {json.dumps({'type': 'text', 'content': data})}\n\n"
                elif msg_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': f'LLM调用失败: {data}'})}\n\n"
                    break

            # 文本流结束后，发送后处理事件（如变更摘要、评分等）
            if post_stream and full_response:
                try:
                    for evt_type, evt_data in post_stream(full_response):
                        yield f"data: {json.dumps({'type': evt_type, **evt_data})}\n\n"
                except Exception as e:
                    logger.error(f"post_stream error: {e}")

            yield "data: [DONE]\n\n"
            if on_complete and full_response:
                try:
                    on_complete(full_response)
                except Exception as e:
                    logger.error(f"on_complete error: {e}")

        except (asyncio.CancelledError, GeneratorExit):
            logger.info("Client disconnected during streaming")
        except Exception as e:
            logger.error(f"SSE error: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ==================== 静态文件 ====================
@app.get("/")
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/health")
async def health():
    """心跳检测端点 — 前端通过此接口判断后端是否在线"""
    return JSONResponse({"status": "ok", "timestamp": time.time()})


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
        return hybrid_search(query=question, top_k=5, filters=filters)

    search_results = await loop.run_in_executor(None, do_search)

    if not search_results:
        async def empty_gen():
            yield f"data: {json.dumps({'type': 'text', 'content': '根据已入库的海军标准，暂无相关标准依据可回答此问题。建议补充相关标准文档。'})}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    # 构建上下文（过滤低相关度结果）
    MIN_SIM = 0.01
    context_parts = []
    sources = []
    for i, r in enumerate(search_results, 1):
        sim = r.get("similarity", 0)
        if sim < MIN_SIM:
            continue
        context_parts.append(
            f"[来源{i}] {r.get('standard_name', '')} ({r.get('standard_number', '')})\n"
            f"{r.get('section_title', '')} {r.get('clause_number', '')}\n"
            f"{r.get('chunk_text', '')}\n"
        )
        sources.append({
            "standard_number": r.get("standard_number", ""),
            "standard_name": r.get("standard_name", ""),
            "section_title": r.get("section_title", ""),
            "clause_number": r.get("clause_number", ""),
            "chunk_type": r.get("chunk_type", ""),
            "similarity": round(sim, 4),
            "source_display": r.get("source_display", ""),
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
        has_error = False
        try:
            for chunk in chat_stream(messages):
                try:
                    queue.put_nowait(("text", chunk))
                except asyncio.QueueFull:
                    pass
            queue.put_nowait(("sources", sources))
        except Exception as e:
            has_error = True
            logger.error(f"LLM stream error: {e}")
            try:
                queue.put_nowait(("error", str(e)))
            except asyncio.QueueFull:
                pass
        finally:
            if not has_error:
                queue.put_nowait(("done", None))
            else:
                queue.put_nowait(("abort", None))

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
                elif msg_type == "abort":
                    break
                elif msg_type == "text":
                    full_response += data
                    yield f"data: {json.dumps({'type': 'text', 'content': data})}\n\n"
                elif msg_type == "sources":
                    if "暂无相关标准依据" in full_response:
                        yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
                    else:
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


# ==================== 文档查看 ====================
@app.get("/api/documents/{doc_id}/file")
async def view_document_file(doc_id: int):
    """查看已入库文档的原始文件（HTML 内嵌预览）"""
    doc = get_document(doc_id)
    if not doc or not doc.get("file_path"):
        return JSONResponse({"error": "文档不存在"}, status_code=404)

    file_path = doc["file_path"]
    if not os.path.exists(file_path):
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>文件已丢失</title>
<style>*{{margin:0;padding:0}}body{{background:#1a1d23;color:#999;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:15px;flex-direction:column;gap:8px}}</style></head>
<body><div>文件已丢失</div><div style="font-size:13px">请重新上传该文档入库</div></body></html>""", status_code=404)

    std_num = doc.get("standard_number", "")
    std_name = doc.get("standard_name", "")
    title = f"{std_num} {std_name}".strip() or os.path.basename(file_path)
    file_url = f"/api/documents/{doc_id}/raw"

    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{title}</title>
<style>*{{margin:0;padding:0}}html,body{{overflow:hidden;height:100%}}iframe{{border:none;width:100%;height:100%;display:block}}</style></head>
<body><iframe src="{file_url}"></iframe></body></html>""")


@app.get("/api/documents/{doc_id}/raw")
async def view_document_raw(doc_id: int):
    """返回文档原始文件"""
    doc = get_document(doc_id)
    if not doc or not doc.get("file_path"):
        return JSONResponse({"error": "文档不存在"}, status_code=404)

    from fastapi.responses import FileResponse
    file_path = doc["file_path"]
    if not os.path.exists(file_path):
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>文件已丢失</title>
<style>*{{margin:0;padding:0}}body{{background:#1a1d23;color:#999;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:15px;flex-direction:column;gap:8px}}</style></head>
<body><div>文件已丢失</div><div style="font-size:13px">请重新上传该文档入库</div></body></html>""", status_code=404)
    return FileResponse(file_path, media_type="application/pdf")


@app.put("/api/documents/{doc_id}")
async def update_doc(doc_id: int, req: Request):
    """更新文档元数据（名称、编号等）"""
    try:
        data = await req.json()
        doc = get_document(doc_id)
        if not doc:
            return JSONResponse({"error": "文档不存在"}, status_code=404)
        update_document(doc_id, **{k: v for k, v in data.items() if v})
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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

        extracted_title = ""
        if ext == "pdf":
            try:
                extracted_title = _extract_title_from_pdf(tmp_path)
                logger.info(f"标题提取: {extracted_title}")
            except Exception as e:
                logger.warning(f"标题提取失败: {e}")

        meta = extract_metadata_from_text(cleaned, safe_name, extracted_title=extracted_title)

        # 上传时查重：标准号+标准名匹配，仅标准号兜底
        std_num = meta.get("standard_number", "")
        std_name = meta.get("standard_name", "")
        duplicate = None
        if std_num:
            dups = find_duplicate_documents(std_num, std_name) if std_name else []
            if not dups:
                # 名称可能略有偏差，仅按标准号再查一次
                from database.operations import find_documents_by_standard_number
                dups = find_documents_by_standard_number(std_num)
            if dups:
                duplicate = [{
                    "id": d["id"],
                    "standard_name": d.get("standard_name", ""),
                    "doc_status": d.get("doc_status", ""),
                    "upload_time": str(d.get("upload_time", ""))[:10],
                } for d in dups]

        # 缓存解析结果到 .txt 文件，避免入库时重复解析
        cache_path = tmp_path + ".txt"
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        return JSONResponse({
            "success": True,
            "filename": safe_name,
            "file_path": tmp_path,
            "cleaned_text": cleaned[:500] + "..." if len(cleaned) > 500 else cleaned,
            "text_length": len(cleaned),
            "duplicate": duplicate,
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


@app.delete("/api/upload")
async def delete_upload(req: Request):
    """删除上传的临时文件及其解析缓存"""
    try:
        data = await req.json()
        file_path = data.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            return JSONResponse({"error": "文件不存在"}, status_code=404)
        # 删除源文件和缓存
        for p in [file_path, file_path + ".txt"]:
            if os.path.exists(p):
                os.remove(p)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ingest")
async def ingest(req: Request):
    """确认入库，支持查重与覆盖"""
    try:
        data = await req.json()
        file_path = data.get("file_path", "")
        standard_number = data.get("standard_number", "").strip()
        standard_name = data.get("standard_name", "")
        applicable_field = data.get("applicable_field", "")
        doc_status = data.get("doc_status", "现行有效")
        responsible_unit = data.get("responsible_unit", "")
        file_type = data.get("file_type", "")
        overwrite = data.get("overwrite", False)

        if not os.path.exists(file_path):
            return JSONResponse({"error": "文件不存在"}, status_code=400)

        # 查重：标准号+标准名都非空时双重匹配
        if standard_number and standard_name:
            existing = find_duplicate_documents(standard_number, standard_name)
            if existing:
                if not overwrite:
                    # 返回冲突信息，让前端确认
                    return JSONResponse({
                        "conflict": True,
                        "standard_number": standard_number,
                        "standard_name": standard_name,
                        "existing": [{
                            "id": d["id"],
                            "standard_name": d.get("standard_name", ""),
                            "doc_status": d.get("doc_status", ""),
                            "upload_time": str(d.get("upload_time", ""))[:10],
                        } for d in existing],
                        "message": f"「{standard_number} {standard_name}」已存在 {len(existing)} 条记录",
                    })
                # 覆盖：先删旧记录
                for old in existing:
                    try:
                        delete_document(old["id"])
                        logger.info(f"覆盖删除旧文档: ID={old['id']} ({old.get('standard_name','')})")
                    except Exception as del_err:
                        logger.error(f"删除旧文档失败: {del_err}")

        # 优先读上传时的解析缓存，避免重复解析
        cache_path = file_path + ".txt"
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cleaned = f.read()
        else:
            raw_text = parse_file(file_path)
            cleaned = clean_text(raw_text)

        # CID 字体乱码 → 入库时全页 OCR
        if "【CID_GARBLED】" in cleaned:
            logger.info(f"CID乱码文档，启动全页OCR: {os.path.basename(file_path)}")
            from document.parser import _ocr_pdf
            ocred = _ocr_pdf(file_path)
            if ocred and not ocred.startswith("此PDF为扫描版"):
                cleaned = clean_text(ocred)
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(cleaned)
            else:
                cleaned = cleaned.replace("【CID_GARBLED】\n", "")

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

        was_overwritten = overwrite and standard_number and standard_name
        return JSONResponse({
            "success": True,
            "doc_id": doc_id,
            "chunk_count": chunk_count,
            "overwritten": was_overwritten,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 文档列表 ====================
@app.get("/api/documents")
async def get_docs(status: str = "", field: str = "", keyword: str = "", limit: int = 10, offset: int = 0):
    from database.operations import count_documents
    docs = list_documents(
        doc_status=status if status else None,
        applicable_field=field if field else None,
        keyword=keyword if keyword else None,
        limit=limit,
        offset=offset,
    )
    total = count_documents(
        doc_status=status if status else None,
        applicable_field=field if field else None,
        keyword=keyword if keyword else None,
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
    return JSONResponse({"docs": result, "total": total})


@app.delete("/api/documents/{doc_id}")
async def delete_doc(doc_id: int):
    """删除文档及其所有向量块（同时清理磁盘文件）"""
    try:
        # 先检查文档是否存在
        doc = get_document(doc_id)
        if not doc:
            return JSONResponse({"error": f"文档 {doc_id} 不存在"}, status_code=404)
        delete_document(doc_id)
        logger.info(f"文档 {doc_id} 删除成功: {doc.get('standard_number','')} {doc.get('standard_name','')}")
        return JSONResponse({"success": True, "message": f"文档 {doc_id} 已删除"})
    except Exception as e:
        logger.error(f"删除文档 {doc_id} 失败: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/documents/batch-delete")
async def batch_delete_docs(req: Request):
    """批量删除文档及其所有向量块（同时清理磁盘文件）"""
    try:
        data = await req.json()
        doc_ids = data.get("ids", [])
        if not doc_ids or not isinstance(doc_ids, list):
            return JSONResponse({"error": "请提供要删除的文档ID列表"}, status_code=400)
        result = delete_documents_batch(doc_ids)
        logger.info(f"批量删除完成: {result}")
        return JSONResponse({"success": True, **result})
    except Exception as e:
        logger.error(f"批量删除失败: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 文本优化 ====================
@app.post("/api/optimize")
async def api_optimize(req: Request):
    """
    文本智能优化（V2 SSR流式）— 支持文风/力度/继续调整（力度自动控制篇幅）
    参数: {text, file_path, style, intensity, previous_result, adjustment}
    """
    data = await req.json()
    text = data.get("text", "").strip()
    file_path = data.get("file_path", "")
    style = data.get("style", "standard")
    intensity = data.get("intensity", "medium")
    previous_result = data.get("previous_result", "").strip()
    adjustment = data.get("adjustment", "").strip()

    # 如果传了文件路径，从缓存读完整文本
    if file_path:
        cache_path = file_path + ".txt"
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif os.path.exists(file_path):
            raw = parse_file(file_path)
            text = clean_text(raw)
        if not text:
            return JSONResponse({"error": "文件内容为空"}, status_code=400)

    # 二次调整模式
    if previous_result and adjustment:
        messages = build_continue_optimize_messages(previous_result, adjustment)
        phase_message = f"正在按「{adjustment[:50]}」继续调整..."
        log_prefix = f"[继续调整] {adjustment[:200]}"
    elif text:
        messages = build_optimize_messages(text, style=style, intensity=intensity)
        phase_message = "正在按海军文书规范优化中..."
        log_prefix = f"[文本优化] {text[:200]}"
    else:
        return JSONResponse({"error": "文本不能为空"}, status_code=400)

    def post_stream(full_response):
        cleaned = clean_output(full_response)
        base = previous_result if previous_result else text
        changes = compute_changes(base, cleaned, intensity=intensity)
        events = [("changes", changes)]
        # 如果清洗后与原输出不同，发送清洗版让前端更新气泡
        if cleaned != full_response:
            events.append(("cleaned_text", {"content": cleaned}))
        return events

    def on_complete(full_response):
        try:
            log_query("user", log_prefix, full_response[:500], "优化", None)
        except Exception:
            pass

    return sse_response(
        messages=messages,
        extra_events=[("phase", {"phase": "optimizing", "message": phase_message})],
        post_stream=post_stream,
        on_complete=on_complete,
        max_tokens=16384,
    )


# ==================== 标准诊断分析（V4 四层引擎） ====================
@app.post("/api/gap-text")
async def api_gap_text(req: Request):
    """标准诊断：四层分析引擎（SSE流式）— 参数 {text, file_path, standard_name, depth, field, continue_content}"""
    data = await req.json()
    text = data.get("text", "").strip()
    file_path = data.get("file_path", "")
    standard_name = data.get("standard_name", "")
    depth = data.get("depth", "full")
    field = data.get("field", "general")
    continue_content = data.get("continue_content", "").strip()

    # 如果传了文件路径，从缓存读完整文本
    if file_path and not text:
        cache_path = file_path + ".txt"
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif os.path.exists(file_path):
            raw = parse_file(file_path)
            text = clean_text(raw)

    if not text:
        return JSONResponse({"error": "请提供标准内容或名称"}, status_code=400)

    loop = asyncio.get_event_loop()

    def do_search():
        filters = None
        if field and field != "general":
            field_info = STANDARD_FIELDS.get(field, {})
            field_label = field_info.get("label", "")
            if field_label:
                filters = {"applicable_field": field_label}
        return hybrid_search(
            query=text if not standard_name else standard_name,
            top_k=10,
            filters=filters,
        )

    search_results = await loop.run_in_executor(_executor, do_search)
    related_standards = build_gap_related_standards(search_results)
    messages = build_diagnosis_messages(text, standard_name, search_results, depth=depth, field=field)
    if continue_content:
        messages.append({"role": "user", "content": f"【请从以下断点处直接续写，不要重复已有内容】\n{continue_content[-2000:]}"})

    depth_label = "快速合规" if depth == "quick" else "全链路诊断"
    extra_events = [
        ("phase", {"phase": "analyzing", "message": f"检索到 {len(search_results)} 条关联标准，启动{depth_label}..."}),
        ("related_standards", {"standards": related_standards}),
    ]

    def post_stream(full_response):
        defects = parse_diagnosis_defects(full_response)
        return [("defects", {"defects": defects})]

    def on_complete(full_response):
        try:
            log_query("user", f"[标准诊断] {text[:200]}", full_response[:500], "诊断", related_standards)
        except Exception:
            pass

    return sse_response(
        messages=messages,
        extra_events=extra_events,
        post_stream=post_stream,
        on_complete=on_complete,
        max_tokens=16384,
        stream_timeout=300,
    )


@app.post("/api/gap-analysis")
async def api_gap(req: Request):
    """标准分析（按库中文档ID），同步返回（保持向后兼容）"""
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


# ==================== 合规自查（向后兼容，路由到快速诊断模式） ====================
@app.post("/api/compliance")
async def api_compliance(req: Request):
    """合规自查 — 内部路由到标准诊断 quick 模式（向后兼容）"""
    data = await req.json()
    text = data.get("text", "").strip()
    app_field = data.get("field", "")
    if not text:
        return JSONResponse({"error": "请提供制度/方案内容"}, status_code=400)

    loop = asyncio.get_event_loop()

    def do_search():
        filters = None
        if app_field and app_field.strip():
            filters = {"applicable_field": app_field.strip()}
        return hybrid_search(query=text[:500], top_k=10, filters=filters)

    search_results = await loop.run_in_executor(_executor, do_search)

    if not search_results:
        async def empty_gen():
            yield f"data: {json.dumps({'type': 'error', 'content': '未能检索到相关的海军标准条款，无法进行合规校验。'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    field_key = app_field if app_field in ("ship", "document", "bigdata", "safety") else "general"
    messages = build_diagnosis_messages(text, "", search_results, depth="quick", field=field_key)
    sources = build_compliance_sources(search_results)

    def post_stream(full_response):
        defects = parse_diagnosis_defects(full_response)
        return [("sources", {"sources": sources}), ("defects", {"defects": defects})]

    def on_complete(full_response):
        try:
            log_query("user", f"[合规自查] {text[:200]}", full_response[:500], "合规", sources)
        except Exception:
            pass

    return sse_response(
        messages=messages,
        extra_events=[("standards_count", {"count": len(search_results),
                                           "message": f"正在对照 {len(search_results)} 条标准条款逐条校验..."})],
        post_stream=post_stream,
        on_complete=on_complete,
        max_tokens=16384,
    )


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
        # 解析用户指定的返回条数：匹配 "5条"、"前10条"、"返回20条" 等
        import re
        top_k = 10
        match = re.search(r'(?:返回|前|取)?\s*(\d+)\s*(?:条|个|项)', query)
        if match:
            top_k = int(match.group(1))
            top_k = max(1, min(top_k, 50))  # 限制 1-50 条
            query = re.sub(r'(?:返回|前|取)?\s*\d+\s*(?:条|个|项)\s*', '', query).strip()
        if not query:
            return JSONResponse({"error": "请输入检索词"}, status_code=400)
        results = hybrid_search(query=query, top_k=top_k, filters=filters)
        MIN_SIM = 0.005  # 最低相关度阈值，仅过滤明显无关的结果
        formatted = []
        for r in results:
            if r.get("similarity", 0) < MIN_SIM:
                continue
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


# ==================== 标准比对 ====================
@app.post("/api/compare")
async def api_compare(req: Request):
    """标准比对：两份标准文本或文件，SSE 流式输出差异分析"""
    data = await req.json()
    instruction = data.get("instruction", "").strip()
    file_a = data.get("file_a", "")
    file_b = data.get("file_b", "")
    text_a = data.get("text_a", "").strip()
    text_b = data.get("text_b", "").strip()
    continue_content = data.get("continue_content", "").strip()

    # 读取标准内容：文件优先，文本兜底
    def read_file(fp):
        if not fp: return ""
        cache = fp + ".txt"
        if os.path.exists(cache):
            with open(cache, "r", encoding="utf-8") as f:
                return f.read()
        if os.path.exists(fp):
            return clean_text(parse_file(fp))
        return ""

    content_a = read_file(file_a) or text_a
    content_b = read_file(file_b) or text_b

    if not content_a or not content_b:
        if not continue_content:
            return JSONResponse({"error": "请提供两份标准内容（上传文件或直接输入文本）"}, status_code=400)
        # 续写模式：不需要重新提供文件，用占位内容跳过校验
        content_a = content_a or "(从已上传文件读取)"
        content_b = content_b or "(从已上传文件读取)"

    instruction_text = f"\n\n【用户额外要求】\n{instruction}" if instruction else ""
    messages = [
        {"role": "system", "content": "你是一名标准化专家，请对两份标准文本进行逐条比对分析，用结构化格式输出差异。"},
        {"role": "user", "content": f"【标准A】\n{content_a[:8000]}\n\n【标准B】\n{content_b[:8000]}{instruction_text}\n\n请逐条比对：1.技术指标差异 2.范围差异 3.术语定义差异 4.引用标准差异 5.互补关系"}
    ]
    if continue_content:
        messages.append({"role": "user", "content": f"【请从以下断点处直接续写，不要重复已有内容】\n{continue_content[-2000:]}"})

    def on_complete(full_response):
        try: log_query("user", "[标准比对]", full_response[:500], "比对", None)
        except: pass

    return sse_response(
        messages=messages,
        extra_events=[("phase", {"phase": "comparing", "message": "正在逐条比对两份标准..."})],
        on_complete=on_complete,
        max_tokens=16384,
    )


# ==================== 静态文件 ====================
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ==================== 启动事件 ====================
@app.on_event("startup")
async def startup():
    """应用启动时自动初始化数据库"""
    from database.schema import init_db
    max_retries = 10
    for i in range(max_retries):
        try:
            init_db()
            logger.info("数据库初始化完成")
            return
        except Exception as e:
            logger.warning(f"数据库初始化等待 {i+1}/{max_retries}: {e}")
    logger.error("数据库初始化失败，请检查连接")

# ==================== 启动 ====================
if __name__ == "__main__":
    import webbrowser, threading
    def _open_browser():
        webbrowser.open("http://localhost:8501")
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8501, log_level="info")

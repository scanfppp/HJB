/* ====== state ====== */
const S = {
    convs: JSON.parse(localStorage.getItem('navy_v2') || '{}'),
    cid: null,
    msgs: [],
    streaming: false,
    pending: [],
    chatMode: 'chat',  // chat | optimize | gap | compliance
    gapFile: null,      // 标准分析模式上传的文件
};

/* ====== init ====== */
document.addEventListener('DOMContentLoaded', () => {
    renderHistory();
    switchPanel('chat');
    loadDocs();
});

/* ====== panel ====== */
function switchPanel(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('show'));
    document.querySelectorAll('.tool-item').forEach(b => b.classList.remove('active'));

    const page = document.getElementById('page-' + name);
    if (page) page.classList.add('show');

    const tool = document.querySelector(`[data-panel="${name}"]`);
    if (tool) tool.classList.add('active');

    if (name === 'gap') loadDocs();
    if (name === 'upload') loadUploadedDocs();
}

/* ====== chat ====== */
function newChat() {
    if (S.msgs.length) saveConv();
    S.cid = null;
    S.msgs = [];
    renderMsgs();
    switchPanel('chat');
}

function saveConv() {
    if (!S.msgs.length) return;
    const id = S.cid || 'c' + Date.now();
    const title = (S.msgs.find(m => m.role === 'user') || {}).content || '对话';
    const old = S.convs[id] || {};
    S.convs[id] = { title: old.title || title.slice(0, 40), msgs: S.msgs.slice(), time: Date.now(), pinned: old.pinned || false };
    S.cid = id;
    localStorage.setItem('navy_v2', JSON.stringify(S.convs));
    renderHistory();
}

function renderHistory() {
    const list = document.getElementById('historyList');
    const convs = Object.entries(S.convs).sort((a, b) => {
        if (a[1].pinned && !b[1].pinned) return -1;
        if (!a[1].pinned && b[1].pinned) return 1;
        return b[1].time - a[1].time;
    });

    if (!convs.length) {
        list.innerHTML = '<div class="history-empty">暂无历史对话</div>';
        return;
    }

    list.innerHTML = convs.map(([id, c]) => `
        <div class="history-item${id === S.cid ? ' active' : ''}${c.pinned ? ' pinned' : ''}">
            <span class="history-title" onclick="loadConv('${id}')">${c.pinned ? '📌 ' : ''}${c.title}</span>
            <button class="history-menu-btn" onclick="event.stopPropagation();toggleHistoryMenu(event, '${id}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>
            </button>
        </div>`
    ).join('');
}

function toggleHistoryMenu(e, id) {
    // 关闭已打开的菜单
    document.querySelectorAll('.history-dropdown').forEach(d => d.remove());
    const btn = e.currentTarget;
    const rect = btn.getBoundingClientRect();
    const menu = document.createElement('div');
    menu.className = 'history-dropdown';
    menu.style.position = 'fixed';
    menu.style.top = rect.bottom + 4 + 'px';
    menu.style.left = Math.min(rect.left, window.innerWidth - 140) + 'px';
    const c = S.convs[id];
    menu.innerHTML = `
        <div class="history-dropdown-item" onclick="pinConv('${id}')">📌 ${c && c.pinned ? '取消置顶' : '置顶'}</div>
        <div class="history-dropdown-item" onclick="renameConv('${id}')">✏️ 重命名</div>
        <div class="history-dropdown-item danger" onclick="deleteConv('${id}')">🗑️ 删除</div>
    `;
    document.body.appendChild(menu);
    // 点击其他地方关闭
    setTimeout(() => document.addEventListener('click', function close() {
        menu.remove();
        document.removeEventListener('click', close);
    }), 0);
}

function pinConv(id) {
    const c = S.convs[id];
    if (c) { c.pinned = !c.pinned; localStorage.setItem('navy_v2', JSON.stringify(S.convs)); renderHistory(); }
}
function renameConv(id) {
    const c = S.convs[id];
    if (!c) return;
    const name = prompt('重命名对话:', c.title);
    if (name && name.trim()) { c.title = name.trim().slice(0, 40); localStorage.setItem('navy_v2', JSON.stringify(S.convs)); renderHistory(); }
}
function deleteConv(id) {
    if (!confirm('确定删除这个对话？')) return;
    delete S.convs[id];
    if (S.cid === id) { S.cid = null; S.msgs = []; renderMsgs(); }
    localStorage.setItem('navy_v2', JSON.stringify(S.convs));
    renderHistory();
}

function loadConv(id) {
    saveConv();
    const c = S.convs[id];
    if (c) { S.cid = id; S.msgs = c.msgs.slice(); renderMsgs(); switchPanel('chat'); renderHistory(); }
}

function clearHistory() {
    if (!confirm('清空所有历史对话？')) return;
    S.convs = {}; S.cid = null; S.msgs = [];
    localStorage.removeItem('navy_v2');
    renderMsgs(); renderHistory();
}

/* ====== render messages ====== */
function renderMsgs() {
    const body = document.getElementById('chatBody');
    const welcome = document.getElementById('welcomeBlock');
    const list = document.getElementById('msgList');

    if (!S.msgs.length) {
        welcome.style.display = '';
        list.innerHTML = '';
        body.scrollTop = 0;
        return;
    }

    welcome.style.display = 'none';
    list.innerHTML = S.msgs.map(m => {
        const isUser = m.role === 'user';
        let html = `<div class="msg ${m.role}"><div class="msg-bubble">`;
        html += isUser ? escHtml(m.content) : mdRender(m.content);
        if (m.sources && m.sources.length) {
            html += `<div class="msg-sources"><span class="src-icon"></span> ${m.sources.map(s =>
                `[${s.standard_number}] ${s.section_title} ${s.clause_number}`
            ).join('；')}</div>`;
        }
        html += '</div></div>';
        return html;
    }).join('');

    scrollDown();
}

function scrollDown() {
    const body = document.getElementById('chatBody');
    body.scrollTop = body.scrollHeight;
}

function addMsg(role, content, sources) {
    S.msgs.push({ role, content, sources });
    renderMsgs();
}

let _renderPending = false;
let _pendingContent = '';

function updateLastBubble(content) {
    // 流式更新：requestAnimationFrame 节流，每帧最多渲染一次markdown
    if (!S.msgs.length) return;
    S.msgs[S.msgs.length - 1].content = content;
    _pendingContent = content;

    if (!_renderPending) {
        _renderPending = true;
        requestAnimationFrame(() => {
            _renderPending = false;
            const bubbles = document.querySelectorAll('#msgList .msg.assistant .msg-bubble');
            const last = bubbles[bubbles.length - 1];
            if (last) {
                last.innerHTML = mdRender(_pendingContent);
                scrollDown();
            }
        });
    }
}

function finalizeLastBubble(content, sources) {
    // 流结束后确保最终渲染 + 来源
    if (!S.msgs.length) return;
    S.msgs[S.msgs.length - 1].content = content;
    S.msgs[S.msgs.length - 1].sources = sources;
    const bubbles = document.querySelectorAll('#msgList .msg.assistant .msg-bubble');
    const last = bubbles[bubbles.length - 1];
    if (last) {
        last.innerHTML = mdRender(content);
        if (sources && sources.length) {
            const srcDiv = document.createElement('div');
            srcDiv.className = 'msg-sources';
            srcDiv.textContent = sources.map(s =>
                `[${s.standard_number}] ${s.section_title} ${s.clause_number}`
            ).join('；');
            last.appendChild(srcDiv);
        }
        scrollDown();
    }
    _renderPending = false;
}

function escHtml(t) {
    const d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML;
}

// 轻量内置markdown解析器，不依赖外部CDN，流式输出时即时生效
function parseMD(text) {
    if (!text) return '';
    // 先转义HTML
    let html = escHtml(text);
    // 代码块 ```...```
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // 行内代码 `...`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // 粗体 **...**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // 斜体 *...*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // 标题 ### ...
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    // 无序列表 - ... 或 * ...
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    // 引用 > ...
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    // 双换行 → 段落分隔
    html = html.replace(/\n\n/g, '</p><p>');
    // 单换行 → <br>
    html = html.replace(/\n/g, '<br>');
    // 包装段落
    if (!html.startsWith('<')) html = '<p>' + html;
    if (!html.endsWith('>')) html = html + '</p>';
    return html;
}

function mdRender(t) {
    // 优先使用marked（更完整的表格/嵌套支持），降级用内置parseMD
    if (typeof marked !== 'undefined' && marked.parse) {
        try { marked.setOptions({ breaks: true, gfm: true }); return marked.parse(t); } catch (e) {}
    }
    return parseMD(t);
}

/* ====== send ====== */
async function send() {
    const input = document.getElementById('chatInput');
    const q = input.value.trim();
    if (!q || S.streaming) return;
    const mode = S.chatMode;

    input.value = ''; input.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;
    S.streaming = true;

    addMsg('user', q);
    S.msgs.push({ role: 'assistant', content: '', sources: [] });
    renderMsgs();
    document.getElementById('welcomeBlock').style.display = 'none';

    try {
        if (mode === 'chat') {
            await sendChat(q);
        } else if (mode === 'optimize') {
            await sendOptimize(q);
        } else if (mode === 'gap') {
            await sendGap(q);
        } else if (mode === 'compliance') {
            await sendCompliance(q);
        }
    } catch (e) {
        finalizeLastBubble('请求失败: ' + e.message, []);
    } finally {
        S.streaming = false;
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('chatBody').scrollTop = document.getElementById('chatBody').scrollHeight;
        saveConv();
    }
}

async function sendChat(q) {
    const hist = S.msgs.filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(0, -1).map(m => ({ role: m.role, content: m.content }));
    const res = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history: hist }),
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let full = '', sources = [];
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of dec.decode(value).split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const d = line.slice(6);
            if (d === '[DONE]') continue;
            try {
                const p = JSON.parse(d);
                if (p.type === 'text') { full += p.content; updateLastBubble(full); }
                else if (p.type === 'sources') { sources = p.sources; }
                else if (p.type === 'error') { full += '\n\n' + p.content; updateLastBubble(full); }
            } catch (e) {}
        }
    }
    if (full) { finalizeLastBubble(full, sources); }
    else { finalizeLastBubble('抱歉，未能获取到回复，请重试。', []); }
}

async function sendOptimize(text) {
    updateLastBubble('正在按海军文书规范优化中...');
    const res = await fetch('/api/optimize', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
    });
    const d = await res.json();
    if (d.error) { finalizeLastBubble(d.error, []); return; }
    const result = `### 优化结果\n\n${d.optimized || ''}`;
    finalizeLastBubble(result, []);
}

async function sendGap(q) {
    updateLastBubble('正在检索相关标准文献，比对分析中...');
    let url, body;
    if (S.gapFile) {
        // 先上传文件
        const fd = new FormData(); fd.append('file', S.gapFile);
        const upRes = await fetch('/api/upload', { method: 'POST', body: fd });
        const upData = await upRes.json();
        if (upData.error) { finalizeLastBubble('文件上传失败: ' + upData.error, []); S.gapFile = null; return; }
        // 用上传文件的文本内容做分析
        url = '/api/gap-text';
        body = JSON.stringify({ text: upData.cleaned_text, standard_name: upData.metadata?.standard_name || S.gapFile.name });
        S.gapFile = null;
    } else {
        url = '/api/gap-text';
        body = JSON.stringify({ text: q, standard_name: q });
    }
    const res = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body,
    });
    const d = await res.json();
    if (d.error) { finalizeLastBubble(d.error, []); return; }
    let result = '';
    if (d.related_standards && d.related_standards.length) {
        result += '### 关联标准\n' + d.related_standards.map(s => `- [${s.standard_number}] ${s.standard_name}`).join('\n') + '\n\n';
    }
    result += '### 分析报告\n' + (d.gap_report || d.report || '分析完成');
    finalizeLastBubble(result, []);
}

async function sendCompliance(text) {
    updateLastBubble('正在对照标准条款逐条校验中...');
    const res = await fetch('/api/compliance', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
    });
    const d = await res.json();
    if (d.error) { finalizeLastBubble(d.error, []); return; }
    const result = `### 合规校验报告\n\n对照片 ${d.standards_count || 0} 条标准条款\n\n${d.report || ''}`;
    finalizeLastBubble(result, []);
}

function setMode(mode) {
    S.chatMode = mode;
    S.gapFile = null;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.mode-btn[data-mode="${mode}"]`).classList.add('active');
    // 标准分析模式显示附件按钮
    const attachBtn = document.getElementById('attachBtn');
    attachBtn.classList.toggle('show', mode === 'gap');
    // 更新placeholder
    const input = document.getElementById('chatInput');
    const placeholders = {chat:'输入你的问题...', optimize:'粘贴需要优化的公文文本...', gap:'输入标准名称或问题，或上传文档...', compliance:'粘贴需要校验的制度/方案内容...'};
    input.placeholder = placeholders[mode] || '输入...';
    document.getElementById('footHint').textContent = mode === 'gap' ? '可上传文档或直接输入问题' : mode === 'optimize' ? '粘贴文本后发送即可优化' : mode === 'compliance' ? '粘贴制度内容后发送即可校验' : 'Enter 发送，Shift+Enter 换行';
    input.focus();
}

function onGapFile(files) {
    if (!files.length) return;
    const f = files[0];
    S.gapFile = f;
    // 在输入框里显示文件名
    document.getElementById('chatInput').value = `[已选择文件: ${f.name}] 请描述分析要求`;
    document.getElementById('gapFileInput').value = '';
}

function sendHint(t) {
    document.getElementById('chatInput').value = t;
    // 根据提示内容自动切换模式
    if (t.includes('优化')) setMode('optimize');
    else if (t.includes('内容缺口') || t.includes('分析')) setMode('gap');
    else setMode('chat');
    send();
}

function onInputKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
}

function autoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

/* ====== upload ====== */
async function onFiles(files) {
    const exts = ['pdf', 'docx', 'txt'];
    const all = Array.from(files);
    const valid = all.filter(f => exts.includes(f.name.split('.').pop().toLowerCase()));
    const skipped = all.length - valid.length;
    if (skipped > 0) toast(`已跳过 ${skipped} 个不支持的文件`, 'info');
    if (!valid.length) { toast('未找到 PDF/DOCX/TXT 文件', 'error'); return; }
    S._uploading = true; renderPending();
    let done = 0, fail = 0;
    for (const f of valid) {
        const tmpId = Date.now().toString(36) + Math.random().toString(36).slice(2,6);
        S.pending.push({ _id: tmpId, filename: f.name, text_length: 0, metadata: {}, _status: 'parsing' });
        S._uploadProgress = `正在上传 ${done+1}/${valid.length}`; renderPending();
        const fd = new FormData(); fd.append('file', f);
        try {
            const r = await fetch('/api/upload', { method: 'POST', body: fd });
            const d = await r.json();
            if (d.error) { toast(f.name + ': ' + d.error, 'error'); S.pending = S.pending.filter(p => p._id !== tmpId); renderPending(); fail++; continue; }
            d._id = tmpId; d._status = 'parsed';
            const idx = findPendingIdx(tmpId);
            if (idx >= 0) S.pending[idx] = d;
            done++; renderPending();
        } catch (e) { toast(f.name + ' 上传失败', 'error'); S.pending = S.pending.filter(p => p._id !== tmpId); fail++; renderPending(); }
    }
    S._uploading = false; S._uploadProgress = '';
    if (fail > 0) toast(`上传完成: ${done}成功 ${fail}失败`, fail > 0 ? 'error' : 'success');
    else toast(`${done} 个文件上传完成`, 'success');
    renderPending();
    document.getElementById('fileInput').value = '';
    const folderInp = document.getElementById('folderInput');
    if (folderInp) folderInp.value = '';
}

function findPendingIdx(id) { return S.pending.findIndex(p => p._id === id); }
function toast(msg, type) {
    const t = document.createElement('div'); t.className = 'toast';
    t.innerHTML = `<div class="toast-msg ${type}">${msg}</div>`;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, 2500);
}

function renderPending() {
    const area = document.getElementById('pendingArea');
    if (!S.pending.length) { area.innerHTML = ''; return; }
    const ingesting = S._ingesting || false;
    const uploading = S._uploading || false;
    const hasParsing = S.pending.some(p => p._status === 'parsing');
    // 有文件还在上传中时禁用全部入库
    const disableIngest = ingesting || hasParsing;
    const statusLabel = s => ({parsing:'解析中...', parsed:'已上传', ingesting:'入库中...'}[s] || '');
    area.innerHTML =
        `<div class="btn-row">
            <button class="btn-ingest-all" onclick="doIngestAll()" ${disableIngest ? 'disabled' : ''}>
                ${ingesting ? '<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> 正在入库...' :
                  uploading ? '<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> 文件上传中...' :
                  '📦 全部入库'}
                <span class="count">${S.pending.length}</span>
            </button>
            <button class="btn-remove-all" onclick="clearAllPending()">
                🗑️ 全部移除
            </button>
        </div>` +
        (S._uploadProgress ? `<div class="ingest-progress"><span class="spinner"></span> ${S._uploadProgress}</div>` : '') +
        (S._ingestProgress ? `<div class="ingest-progress"><span class="spinner"></span> ${S._ingestProgress}</div>` : '') +
        S.pending.map(f => {
        const id = f._id;
        const status = f._status || '';
        return `
        <div class="pending-row">
            <div class="info">
                <div class="name">${f.filename} ${status ? `<span class="file-status ${status}">${statusLabel(status)}</span>` : ''}</div>
                <div class="meta">${f.text_length} 字 | 编号: ${f.metadata.standard_number || '未识别'} | 名称: ${f.metadata.standard_name || '未识别'}</div>
                <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
                    <input value="${f.metadata.standard_number||''}" placeholder="标准编号" onchange="S.pending[findPendingIdx('${id}')].metadata.standard_number=this.value">
                    <input value="${f.metadata.standard_name||''}" placeholder="标准名称" onchange="S.pending[findPendingIdx('${id}')].metadata.standard_name=this.value" style="width:180px">
                    <select onchange="S.pending[findPendingIdx('${id}')].metadata.doc_status=this.value">
                        <option ${f.metadata.doc_status==='现行有效'?'selected':''}>现行有效</option>
                        <option ${f.metadata.doc_status==='修订中'?'selected':''}>修订中</option>
                        <option ${f.metadata.doc_status==='废止'?'selected':''}>废止</option>
                    </select>
                </div>
            </div>
            <div style="display:flex;gap:8px">
                <button class="btn-sm-primary" onclick="doIngest('${id}')" ${ingesting ? 'disabled' : ''}>入库</button>
                <button class="btn-sm-ghost" onclick="removePending('${id}')" ${ingesting ? 'disabled' : ''}>移除</button>
            </div>
        </div>`;
    }).join('');
}

async function doIngest(id, showToast = true) {
    const i = findPendingIdx(id);
    if (i < 0) return false;
    const f = S.pending[i];
    f._status = 'ingesting'; renderPending();
    try {
        const r = await fetch('/api/ingest', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: f.file_path,
                standard_number: f.metadata.standard_number,
                standard_name: f.metadata.standard_name || f.filename,
                applicable_field: f.metadata.applicable_field || '',
                doc_status: f.metadata.doc_status || '现行有效',
                responsible_unit: f.metadata.responsible_unit || '',
                file_type: f.filename.split('.').pop(),
            }),
        });
        const d = await r.json();
        if (d.error) { toast('入库失败: ' + d.error, 'error'); f._status = ''; renderPending(); return false; }
        if (showToast) toast(`✅ ${f.filename} 入库成功 (ID:${d.doc_id}, ${d.chunk_count}块)`, 'success');
        S.pending.splice(i, 1); renderPending(); loadUploadedDocs();
        return true;
    } catch (e) {
        toast('入库失败: ' + e.message, 'error');
        f._status = ''; renderPending(); return false;
    }
}

async function doIngestAll() {
    if (!S.pending.length) return;
    S._ingesting = true; renderPending();
    const total = S.pending.length;
    let fail = 0;
    // 顺序执行避免竞态，每次从当前数组取第一个待入库文件
    for (let i = 0; i < total; i++) {
        if (!S.pending.length) break;
        const id = S.pending[0]._id;
        S._ingestProgress = `正在入库 ${i+1}/${total}`; renderPending();
        const ok = await doIngest(id, false);
        if (!ok) fail++;
    }
    S._ingesting = false; S._ingestProgress = '';
    if (fail > 0) toast(`入库完成: ${total-fail}成功, ${fail}失败`, 'error');
    else if (total-fail > 0) toast(`${total-fail} 个文件入库完成`, 'success');
    renderPending(); loadUploadedDocs();
}

function removePending(id) {
    const i = findPendingIdx(id);
    if (i >= 0) { S.pending.splice(i, 1); renderPending(); }
}
function clearAllPending() {
    if (!S.pending.length) return;
    S.pending = []; renderPending();
    toast('已清空待入库列表', 'info');
}

async function loadUploadedDocs() {
    try {
        const r = await fetch('/api/documents'); const docs = await r.json();
        const area = document.getElementById('docsArea');
        if (!docs.length) { area.innerHTML = '<p style="color:var(--text3);font-size:13px">暂无已入库文档</p>'; return; }
        area.innerHTML = '<h4 style="margin-bottom:8px">已入库文档</h4>' + docs.map(d => {
            const cls = d.doc_status === '现行有效' ? 'green' : d.doc_status === '修订中' ? 'yellow' : 'red';
            return `<div class="doc-item"><span class="dot ${cls}"></span>[${d.standard_number}] ${d.standard_name} (${d.doc_status})</div>`;
        }).join('');
    } catch (e) {}
}

/* ====== optimize ====== */
async function doOptimize() {
    const text = document.getElementById('optInput').value.trim();
    if (!text) return alert('请输入需要优化的文本');
    const box = document.getElementById('optResult');
    box.innerHTML = '<p style="color:var(--text3)">优化中...</p>';
    try {
        const r = await fetch('/api/optimize', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        const d = await r.json();
        if (d.error) { box.innerHTML = `<p style="color:red">${d.error}</p>`; return; }
        box.innerHTML = `<p style="color:#52c41a;margin-bottom:12px">${d.changes_summary}</p>${mdRender(d.optimized)}`;
    } catch (e) { box.innerHTML = `<p style="color:red">请求失败</p>`; }
}

/* ====== gap ====== */
async function loadDocs() {
    try {
        const r = await fetch('/api/documents'); const docs = await r.json();
        document.getElementById('gapSelect').innerHTML =
            '<option value="">选择目标标准...</option>' +
            docs.map(d => `<option value="${d.id}">[${d.standard_number}] ${d.standard_name} (${d.doc_status})</option>`).join('');
    } catch (e) {}
}

async function doGap() {
    const id = document.getElementById('gapSelect').value;
    if (!id) return alert('请选择目标标准');
    const box = document.getElementById('gapResult');
    box.innerHTML = '<p style="color:var(--text3)">分析中，请稍候...</p>';
    try {
        const r = await fetch('/api/gap-analysis', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ doc_id: parseInt(id) }),
        });
        const d = await r.json();
        if (d.error) { box.innerHTML = `<p style="color:red">${d.error}</p>`; return; }
        let h = '';
        if (d.related_standards && d.related_standards.length) {
            h += '<h4>📎 关联标准</h4>' + d.related_standards.map(s =>
                `<p style="font-size:13px;color:var(--text2)">[${s.standard_number}] ${s.standard_name}</p>`
            ).join('');
        }
        h += '<h4 style="margin-top:14px">📊 分析报告</h4>' + mdRender(d.gap_report);
        box.innerHTML = h;
    } catch (e) { box.innerHTML = '<p style="color:red">请求失败</p>'; }
}

/* ====== compliance ====== */
async function doCompliance() {
    const text = document.getElementById('complyInput').value.trim();
    if (!text) return alert('请输入校验内容');
    const box = document.getElementById('complyResult');
    box.innerHTML = '<p style="color:var(--text3)">校验中...</p>';
    try {
        const r = await fetch('/api/compliance', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        const d = await r.json();
        if (d.error) { box.innerHTML = `<p style="color:red">${d.error}</p>`; return; }
        box.innerHTML = `<p style="color:#52c41a;margin-bottom:12px">对照片 ${d.standards_count} 条标准条款</p>` + mdRender(d.report);
    } catch (e) { box.innerHTML = '<p style="color:red">请求失败</p>'; }
}

/* ====== drag & drop ====== */
const drop = document.getElementById('dropZone');
if (drop) {
    drop.addEventListener('dragover', e => { e.preventDefault(); drop.style.borderColor = 'var(--brand)'; });
    drop.addEventListener('dragleave', () => { drop.style.borderColor = '#d0d4e0'; });
    drop.addEventListener('drop', e => { e.preventDefault(); drop.style.borderColor = '#d0d4e0'; onFiles(e.dataTransfer.files); });
}

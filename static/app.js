/* ====== state ====== */
const S = {
    convs: JSON.parse(localStorage.getItem('navy_v2') || '{}'),
    cid: null,
    msgs: [],
    streaming: false,
    pending: [],
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
    S.convs[id] = { title: title.slice(0, 40), msgs: S.msgs.slice(), time: Date.now() };
    S.cid = id;
    localStorage.setItem('navy_v2', JSON.stringify(S.convs));
    renderHistory();
}

function renderHistory() {
    const list = document.getElementById('historyList');
    const convs = Object.entries(S.convs).sort((a, b) => b[1].time - a[1].time);

    if (!convs.length) {
        list.innerHTML = '<div class="history-empty">暂无历史对话</div>';
        return;
    }

    list.innerHTML = convs.map(([id, c]) =>
        `<div class="history-item${id === S.cid ? ' active' : ''}" onclick="loadConv('${id}')" title="${c.title}">${c.title}</div>`
    ).join('');
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

function updateLastBubble(content) {
    // 流式更新：直接设textContent，不调用marked避免闪烁
    if (!S.msgs.length) return;
    S.msgs[S.msgs.length - 1].content = content;
    const bubbles = document.querySelectorAll('#msgList .msg.assistant .msg-bubble');
    const last = bubbles[bubbles.length - 1];
    if (last) {
        last.textContent = content;
        scrollDown();
    }
}

function finalizeLastBubble(content, sources) {
    // 流结束后一次性渲染markdown + 来源
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
}

function escHtml(t) {
    const d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML.replace(/\n/g, '<br>');
}

function mdRender(t) {
    if (typeof marked !== 'undefined' && marked.parse) {
        try { marked.setOptions({ breaks: true, gfm: true }); return marked.parse(t); } catch (e) {}
    }
    return '<p>' + escHtml(t).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>') + '</p>';
}

/* ====== send ====== */
async function send() {
    const input = document.getElementById('chatInput');
    const q = input.value.trim();
    if (!q || S.streaming) return;

    input.value = ''; input.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;
    S.streaming = true;

    addMsg('user', q);
    // placeholder for assistant
    S.msgs.push({ role: 'assistant', content: '', sources: [] });
    renderMsgs();
    document.getElementById('welcomeBlock').style.display = 'none';

    try {
        const hist = S.msgs.filter(m => m.role === 'user' || m.role === 'assistant')
            .slice(0, -1).map(m => ({ role: m.role, content: m.content }));

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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

        // 流结束，一次性渲染markdown
        if (full) {
            finalizeLastBubble(full, sources);
        } else {
            finalizeLastBubble('抱歉，未能获取到回复，请重试。', []);
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

function sendHint(t) {
    document.getElementById('chatInput').value = t;
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
    for (const f of files) {
        const fd = new FormData(); fd.append('file', f);
        try {
            const r = await fetch('/api/upload', { method: 'POST', body: fd });
            const d = await r.json();
            if (d.error) { alert(d.error); continue; }
            S.pending.push(d);
            renderPending();
        } catch (e) { alert('上传失败: ' + e.message); }
    }
    // 重置file input，确保能再次选择同一文件
    const inp = document.getElementById('fileInput');
    if (inp) inp.value = '';
}

function renderPending() {
    const area = document.getElementById('pendingArea');
    area.innerHTML = S.pending.map((f, i) => `
        <div class="pending-row">
            <div class="info">
                <div class="name">${f.filename}</div>
                <div class="meta">${f.text_length} 字 | 编号: ${f.metadata.standard_number || '未识别'} | 名称: ${f.metadata.standard_name || '未识别'}</div>
                <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
                    <input value="${f.metadata.standard_number||''}" placeholder="标准编号" onchange="S.pending[${i}].metadata.standard_number=this.value">
                    <input value="${f.metadata.standard_name||''}" placeholder="标准名称" onchange="S.pending[${i}].metadata.standard_name=this.value" style="width:180px">
                    <select onchange="S.pending[${i}].metadata.doc_status=this.value">
                        <option ${f.metadata.doc_status==='现行有效'?'selected':''}>现行有效</option>
                        <option ${f.metadata.doc_status==='修订中'?'selected':''}>修订中</option>
                        <option ${f.metadata.doc_status==='废止'?'selected':''}>废止</option>
                    </select>
                </div>
            </div>
            <div style="display:flex;gap:8px">
                <button class="btn-sm-primary" onclick="doIngest(${i})">入库</button>
                <button class="btn-sm-ghost" onclick="S.pending.splice(${i},1);renderPending()">移除</button>
            </div>
        </div>
    `).join('');
}

async function doIngest(i) {
    const f = S.pending[i];
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
    if (d.error) { alert('入库失败: ' + d.error); return; }
    alert(`入库成功！ID:${d.doc_id}, 分块:${d.chunk_count}`);
    S.pending.splice(i, 1); renderPending(); loadUploadedDocs();
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

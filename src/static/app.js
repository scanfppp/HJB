/* ====== state ====== */
const S = {
    convs: JSON.parse(localStorage.getItem('navy_v2') || '{}'),
    cid: null,           // 当前显示的对话 ID
    pending: [],
    batchMode: false,
    // 以下为瞬态 UI 状态（非对话级）
    gapFile: null,
    optimizeFile: null,
    compareFileA: null,
    compareFileB: null,
    compareTextA: '',
    compareTextB: '',
    docSearch: '',
    docStatusFilter: '',
    docPage: 1,
    docPerPage: 10,
    docTotalPages: 0,
    docHasMore: false,
};

/* ====== helpers ====== */
function newConvState() {
    return {
        title: '',
        msgs: [],
        streaming: false,
        abortController: null,
        chatMode: 'chat',
        createdAt: Date.now(),
        pinned: false,
        optStyle: 'standard',
        optIntensity: 'medium',
        lastOptimized: null,
        optimizingComplete: false,
        diagnosisDepth: 'full',
        diagnosisField: 'general',
    };
}

function active() {
    if (!S.cid) { S.cid = 'c' + Date.now(); S.convs[S.cid] = newConvState(); }
    if (!S.convs[S.cid]) S.convs[S.cid] = newConvState();
    return S.convs[S.cid];
}

/* ====== init ====== */
document.addEventListener('DOMContentLoaded', () => {
    Object.keys(S.convs).forEach(id => {
        const c = S.convs[id];
        if (!c.createdAt) c.createdAt = c.time || Date.now();
        // 补齐旧对话缺失的字段
        if (!c.msgs) c.msgs = [];
        if (c.streaming === undefined) c.streaming = false;
        if (!c.chatMode) c.chatMode = 'chat';
        if (c.abortController === undefined) c.abortController = null;
    });

    const hasHistory = Object.keys(S.convs).length > 0;

    if (hasHistory) {
        // 有历史对话：不自动创建新对话，仅渲染历史和欢迎页
        renderHistory();
        switchPanel('chat');
        initChatUI();
    } else {
        // 无历史对话：自动创建新对话并渲染
        active();
        renderHistory();
        switchPanel('chat');
        setMode('chat');
    }

    loadDocs();
    initOptimizePills();
});

/** 跨标签页同步：其他标签页修改了 localStorage 时自动刷新历史 */
window.addEventListener('storage', (e) => {
    if (e.key !== 'navy_v2') return;
    try {
        const data = JSON.parse(e.newValue || '{}');
        // 合并远程数据（保留当前正在流式生成的对话）
        Object.entries(S.convs).forEach(([id, c]) => {
            if (c.streaming && !data[id]) {
                data[id] = { title: c.title, msgs: c.msgs, createdAt: c.createdAt, pinned: c.pinned, chatMode: c.chatMode };
            }
        });
        S.convs = data;
        S.cid = null;
        renderHistory();
        initChatUI();
    } catch (_) {}
});

/** 初始化聊天 UI（不创建对话，仅设置界面元素） */
function initChatUI() {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    const modeBtn = document.querySelector('.mode-btn[data-mode="chat"]');
    if (modeBtn) modeBtn.classList.add('active');
    document.getElementById('optimizePanel').style.display = 'none';
    document.getElementById('diagnosisPanel').style.display = 'none';
    document.getElementById('comparePanel').style.display = 'none';
    document.getElementById('chatInput').placeholder = '请输入您的问题...';
    document.getElementById('footHint').textContent = '💬 Enter 发送，Shift+Enter 换行';
    document.getElementById('welcomeBlock').style.display = '';
    document.getElementById('msgList').innerHTML = '';
}

function initOptimizePills() {
    ['stylePills', 'intensityPills'].forEach(id => {
        const container = document.getElementById(id);
        if (!container) return;
        container.addEventListener('click', e => {
            const pill = e.target.closest('.opt-pill');
            if (!pill) return;
            container.querySelectorAll('.opt-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            const val = pill.dataset.val;
            if (id === 'stylePills') active().optStyle = val;
            else if (id === 'intensityPills') active().optIntensity = val;
        });
    });
    // 诊断面板 pills
    ['depthPills', 'fieldPills'].forEach(id => {
        const container = document.getElementById(id);
        if (!container) return;
        container.addEventListener('click', e => {
            const pill = e.target.closest('.opt-pill');
            if (!pill) return;
            container.querySelectorAll('.opt-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            const val = pill.dataset.val;
            if (id === 'depthPills') active().diagnosisDepth = val;
            else if (id === 'fieldPills') active().diagnosisField = val;
        });
    });
}

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
    // 不中断后台流 — 仅保存当前对话并创建新的
    if (S.cid && S.convs[S.cid] && S.convs[S.cid].msgs.length) {
        saveConv();
    }
    S.cid = null;
    renderMsgs();  // active() 在这里创建新对话，只创建一次
    renderHistory();
    switchPanel('chat');
    setMode('chat');  // 重置欢迎内容、输入提示等 UI 状态
}

function saveConv() {
    const conv = active();
    if (!conv.msgs.length) return;
    const title = (conv.msgs.find(m => m.role === 'user') || {}).content || '对话';
    conv.title = conv.title || title.slice(0, 40);
    conv.createdAt = conv.createdAt || Date.now();
    // 只在对话不处于流式生成时持久化（避免频繁写入）
    if (!conv.streaming) {
        persistConvs();
    }
    renderHistory();
}

function renderHistory() {
    const list = document.getElementById('historyList');
    const convs = Object.entries(S.convs).sort((a, b) => {
        if (a[1].pinned && !b[1].pinned) return -1;
        if (!a[1].pinned && b[1].pinned) return 1;
        return b[1].createdAt - a[1].createdAt;
    });

    if (!convs.length) {
        list.innerHTML = '<div class="history-empty">暂无历史对话</div>';
        return;
    }

    list.innerHTML = convs.map(([id, c]) => {
        const isStreaming = c.streaming === true;
        const isActive = id === S.cid;
        const justDone = c._justFinished === true;
        return `
        <div class="history-item${isActive ? ' active' : ''}${c.pinned ? ' pinned' : ''}${isStreaming ? ' streaming' : ''}${justDone ? ' just-finished' : ''}">
            ${isStreaming ? '<span class="stream-spinner"></span>' : ''}
            <span class="history-title" onclick="loadConv('${id}')">${c.pinned ? '📌 ' : ''}${c.title || '新对话'}</span>
            <button class="history-menu-btn" onclick="event.stopPropagation();toggleHistoryMenu(event, '${id}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>
            </button>
        </div>`;
    }).join('');
}

function toggleHistoryMenu(e, id) {
    document.querySelectorAll('.history-dropdown').forEach(d => d.remove());
    const btn = e.currentTarget;
    const rect = btn.getBoundingClientRect();
    const menu = document.createElement('div');
    menu.className = 'history-dropdown';
    menu.style.position = 'fixed';
    menu.style.top = rect.bottom + 4 + 'px';
    menu.style.left = (rect.right - 130) + 'px';
    const c = S.convs[id];
    const isStreaming = c && c.streaming === true;
    menu.innerHTML = `
        <div class="history-dropdown-item" onclick="pinConv('${id}')">📌 ${c && c.pinned ? '取消置顶' : '置顶'}</div>
        <div class="history-dropdown-item" onclick="renameConv('${id}')">✏️ 重命名</div>
        ${isStreaming ? `<div class="history-dropdown-item" onclick="abortConv('${id}')">⏹ 停止生成</div>` : ''}
        <div class="history-dropdown-item danger" onclick="deleteConv('${id}')">🗑️ 删除</div>
    `;
    document.body.appendChild(menu);
    setTimeout(() => document.addEventListener('click', function close() {
        menu.remove();
        document.removeEventListener('click', close);
    }), 0);
}

function abortConv(id) {
    const c = S.convs[id];
    if (c && c.abortController) {
        c.abortController.abort();
        c.abortController = null;
        c.streaming = false;
        const last = c.msgs.length ? c.msgs[c.msgs.length - 1] : null;
        if (last && last.role === 'assistant') {
            last._continue = true;
            if (!last.content) {
                last.content = '⚓ 已停止生成，暂无回复。';
            }
        }
        renderHistory();
        if (S.cid === id) {
            renderMsgs();
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
        }
        persistConvs();
    }
}

function persistConvs() {
    const toSave = {};
    Object.entries(S.convs).forEach(([k, v]) => {
        toSave[k] = { title: v.title, msgs: v.msgs, createdAt: v.createdAt, pinned: v.pinned, chatMode: v.chatMode };
    });
    localStorage.setItem('navy_v2', JSON.stringify(toSave));
}

function pinConv(id) {
    const c = S.convs[id];
    if (c) { c.pinned = !c.pinned; persistConvs(); renderHistory(); }
}
async function renameConv(id) {
    const c = S.convs[id];
    if (!c) return;
    const name = await showModal('重命名', '请输入新的对话名称', c.title);
    if (name && name.trim()) { c.title = name.trim().slice(0, 40); persistConvs(); renderHistory(); }
}
async function deleteConv(id) {
    const ok = await showModal('删除对话', '确定删除这个对话？此操作不可撤销。');
    if (!ok) return;
    const c = S.convs[id];
    // 如果正在流式生成，先中断
    if (c && c.abortController) {
        c.abortController.abort();
        c.abortController = null;
    }
    delete S.convs[id];
    if (S.cid === id) {
        S.cid = null;
        const remaining = Object.keys(S.convs).sort((a, b) =>
            (S.convs[b].createdAt || 0) - (S.convs[a].createdAt || 0)
        );
        if (remaining.length > 0) {
            // 直接加载最新对话，不走 loadConv（loadConv 里的 saveConv 会触发 active() 创建新对话）
            S.cid = remaining[0];
            renderMsgs();
            switchPanel('chat');
            setMode(S.convs[S.cid].chatMode || 'chat');
        } else {
            initChatUI();
        }
    }
    persistConvs();
    renderHistory();
}

function loadConv(id) {
    saveConv();
    const c = S.convs[id];
    if (c) {
        S.cid = id;
        renderMsgs();
        switchPanel('chat');
        renderHistory();
        // 如果该对话正在流式生成，恢复 UI 状态
        if (c.streaming) {
            document.getElementById('sendBtn').disabled = true;
            document.getElementById('stopBtn').style.display = 'flex';
        } else {
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
        }
        // 恢复模式按钮
        setMode(c.chatMode || 'chat');
    }
}

async function clearHistory() {
    const ok = await showModal('清空历史', '确定清空所有历史对话？此操作不可撤销。');
    if (!ok) return;
    // 中断所有正在生成的对话
    Object.values(S.convs).forEach(c => {
        if (c.abortController) { c.abortController.abort(); c.abortController = null; }
    });
    S.convs = {};
    S.cid = null;
    localStorage.removeItem('navy_v2');
    initChatUI();
    renderHistory();
}

function showModal(title, message, inputValue, confirmLabel) {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        const hasInput = inputValue !== undefined;
        const btnLabel = confirmLabel || (hasInput ? '确定' : '删除');
        overlay.innerHTML = `
            <div class="modal-box">
                <div class="modal-title">${title}</div>
                <div class="modal-msg">${message}</div>
                ${hasInput ? `<input class="modal-input" id="modalInput" value="${inputValue||''}" maxlength="40">` : ''}
                <div class="modal-btns">
                    <button class="modal-btn cancel">取消</button>
                    <button class="modal-btn confirm">${btnLabel}</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        const close = (val) => { overlay.remove(); resolve(val); };
        overlay.querySelector('.cancel').onclick = () => close(null);
        overlay.querySelector('.confirm').onclick = () => {
            const val = hasInput ? document.getElementById('modalInput').value : true;
            close(val);
        };
        overlay.addEventListener('click', e => { if (e.target === overlay) close(null); });
        document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { close(null); document.removeEventListener('keydown', esc); } });
        setTimeout(() => { const inp = document.getElementById('modalInput'); if (inp) { inp.focus(); inp.select(); } }, 100);
    });
}

function renderMsgs() {
    const body = document.getElementById('chatBody');
    const welcome = document.getElementById('welcomeBlock');
    const list = document.getElementById('msgList');
    const msgs = active().msgs;

    if (!msgs.length) {
        welcome.style.display = '';
        list.innerHTML = '';
        body.scrollTop = 0;
        return;
    }

    welcome.style.display = 'none';
    list.innerHTML = msgs.map((m, idx) => {
        const isUser = m.role === 'user';
        const isLastAssistantStreaming = !isUser && !m.content && idx === msgs.length - 1;
        let html = `<div class="msg ${m.role}"><div class="msg-bubble">`;
        if (isLastAssistantStreaming) {
            html += '<div class="typing"><span></span><span></span><span></span></div>';
        } else {
            html += isUser ? escHtml(m.content) : mdRender(m.content);
        }
        if (!isUser && m.content) {
            html += `<button class="btn-copy-msg" onclick="copyMsg(this)" title="复制"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>`;
        }
        if (m._continue) {
            const isRegen = m.content === '⚓ 已停止生成，暂无回复。';
            const label = isRegen ? '重新生成' : '继续生成';
            html += `<div class="continue-row"><button class="btn-continue" onclick="continueChat()"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> ${label}</button></div>`;
        }
        if (m.sources && m.sources.length) {
            const uniqueSrc = uniqueSources(m.sources);
            html += renderSourcesBlock(uniqueSrc);
        }
        html += '</div></div>';
        return html;
    }).join('');

    scrollDown();
}

function renderSourcesBlock(sources) {
    const maxShow = 3;
    let html = `<div class="msg-sources">`;
    html += `<button class="src-toggle" onclick="toggleSources(this)">📎 ${sources.length} 个来源 ▾</button>`;
    html += `<div class="src-list">`;
    html += sources.map(s =>
        `<span class="src-item">${s.source_display || `[${s.standard_number}] ${s.section_title} ${s.clause_number}`}</span>`
    ).join('');
    html += `</div></div>`;
    return html;
}

function scrollDown(force = false) {
    const body = document.getElementById('chatBody');
    const threshold = 80;
    const isNearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < threshold;
    if (force || isNearBottom) {
        body.scrollTo({ top: body.scrollHeight, behavior: 'smooth' });
    }
}

function addMsg(role, content, sources) {
    active().msgs.push({ role, content, sources });
    renderMsgs();
    scrollDown();
}

let _renderPending = false;
let _renderRafId = null;
let _pendingContent = '';

function updateLastBubble(content) {
    const msgs = active().msgs;
    if (!msgs.length) return;
    msgs[msgs.length - 1].content = content;
    _pendingContent = content;

    if (!_renderPending) {
        _renderPending = true;
        _renderRafId = requestAnimationFrame(() => {
            _renderPending = false;
            _renderRafId = null;
            const bubbles = document.querySelectorAll('#msgList .msg.assistant .msg-bubble');
            const last = bubbles[bubbles.length - 1];
            if (last) {
                if (_pendingContent) {
                    last.innerHTML = mdRender(_pendingContent);
                    // 添加复制按钮
                    const btn = document.createElement('button');
                    btn.className = 'btn-copy-msg';
                    btn.title = '复制';
                    btn.onclick = function() { copyMsg(this); };
                    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
                    last.appendChild(btn);
                } else {
                    last.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
                }
                scrollDown();
            }
        });
    }
}

function finalizeLastBubble(content, sources) {
    // 取消未执行的 rAF，防止覆盖来源 DOM
    if (_renderRafId) { cancelAnimationFrame(_renderRafId); _renderRafId = null; }
    _renderPending = false;

    const msgs = active().msgs;
    if (!msgs.length) return;
    msgs[msgs.length - 1].content = content;
    msgs[msgs.length - 1].sources = sources;
    const bubbles = document.querySelectorAll('#msgList .msg.assistant .msg-bubble');
    const last = bubbles[bubbles.length - 1];
    if (last) {
        last.innerHTML = mdRender(content);
        // 复制按钮
        const btn = document.createElement('button');
        btn.className = 'btn-copy-msg';
        btn.title = '复制';
        btn.onclick = function() { copyMsg(this); };
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        last.appendChild(btn);
        // 来源
        if (sources && sources.length) {
            const uniqueSrc = uniqueSources(sources);
            const srcBlock = document.createElement('div');
            srcBlock.innerHTML = renderSourcesBlock(uniqueSrc);
            last.appendChild(srcBlock.firstElementChild);
        }
        scrollDown();
    }
}

function uniqueSources(sources) {
    const seen = new Set();
    return sources.filter(s => {
        const key = s.standard_number || s.source_display || '';
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

function escHtml(t) {
    const d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML;
}

function toggleSources(btn) {
    const block = btn.closest('.msg-sources');
    block.classList.toggle('expanded');
    btn.textContent = block.classList.contains('expanded')
        ? btn.textContent.replace('▾', '▴')
        : btn.textContent.replace('▴', '▾');
}

async function copyMsg(btn) {
    const bubble = btn.closest('.msg-bubble');
    const srcBlock = bubble.querySelector('.msg-sources');
    // 临时移除来源块再复制，避免复制到来源标记
    if (srcBlock) srcBlock.style.display = 'none';
    const text = bubble.innerText.trim();
    if (srcBlock) srcBlock.style.display = '';
    try {
        await navigator.clipboard.writeText(text);
        btn.classList.add('copied');
        setTimeout(() => btn.classList.remove('copied'), 1500);
    } catch (e) {
        // fallback
        const ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
        document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
    }
}

function friendlyError(msg) {
    msg = String(msg);
    if (msg.includes('403') || msg.includes('FreeTierOnly') || msg.includes('exhausted'))
        return '⚓ 模型额度已用完，请更换 API Key 或切换模型。';
    if (msg.includes('404') || msg.includes('model_not_found'))
        return '⚓ 模型不存在或无访问权限，请检查模型名称配置。';
    if (msg.includes('401') || msg.includes('invalid_api_key') || msg.includes('authentication'))
        return '⚓ API Key 无效，请检查密钥配置。';
    if (msg.includes('timeout') || msg.includes('timed out'))
        return '⚓ 模型响应超时，请稍后重试。';
    if (msg.includes('connection') || msg.includes('NetworkError'))
        return '⚓ 网络连接失败，请检查网络后重试。';
    return '⚓ 服务暂时不可用，请稍后重试。';
}

function parseMD(text) {
    if (!text) return '';
    let html = escHtml(text);
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    if (!html.startsWith('<')) html = '<p>' + html;
    if (!html.endsWith('>')) html = html + '</p>';
    return html;
}

function mdRender(t) {
    if (typeof marked !== 'undefined' && marked.parse) {
        try { marked.setOptions({ breaks: true, gfm: true }); return marked.parse(t); } catch (e) {}
    }
    return parseMD(t);
}

async function send() {
    const input = document.getElementById('chatInput');
    const q = input.value.trim();
    const hasFile = S.gapFile || S.optimizeFile || S.compareFileA || S.compareFileB;
    const conv = active();
    const mode = conv.chatMode;
    // 比对模式：检查两边是否都就绪
    if (mode === 'compare') {
        const aOk = S.compareFileA || S.compareTextA;
        const bOk = S.compareFileB || S.compareTextB;
        if (!aOk || !bOk) return;
    }
    if ((!q && !hasFile) || conv.streaming) return;
    const convId = S.cid;  // 捕获当前对话 ID，用于后台流检测

    input.value = ''; input.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;
    conv.streaming = true;
    renderHistory();  // 侧边栏显示 spinner
    document.getElementById('stopBtn').style.display = 'flex';

    let displayMsg = q;
    if (hasFile) {
        if (mode === 'compare') {
            const na = S.compareFileA?.name || (S.compareTextA ? '✏️ 文本A' : '未选择');
            const nb = S.compareFileB?.name || (S.compareTextB ? '✏️ 文本B' : '未选择');
            displayMsg = (q ? `⚖️ A:${na} vs B:${nb}\n${q}` : `⚖️ A:${na} vs B:${nb}`);
        } else {
            const fname = (S.gapFile || S.optimizeFile).name;
            let opts = '';
            if (mode === 'optimize') {
                const labels = {standard:'标准制式',concise:'简洁干练',authoritative:'权威专业'};
                const intLabels = {light:'轻度润色',medium:'中度优化',deep:'深度重构'};
                opts = ` | ${labels[conv.optStyle]||conv.optStyle} · ${intLabels[conv.optIntensity]||conv.optIntensity}`;
            } else if (mode === 'gap') {
                opts = ` | ${conv.diagnosisDepth==='quick'?'快速合规':'全链路诊断'} · ${conv.diagnosisField||'通用'}`;
            }
            displayMsg = (q ? `📄 ${fname}${opts}\n${q}` : `📄 ${fname}${opts}`);
        }
    }
    addMsg('user', displayMsg);
    saveConv(); // 立即更新历史列表，不等回复完成
    conv.msgs.push({ role: 'assistant', content: '', sources: [] });
    renderMsgs();
    document.getElementById('welcomeBlock').style.display = 'none';

    try {
        if (mode === 'chat') {
            await sendChat(q, conv, convId);
        } else if (mode === 'optimize') {
            const file = S.optimizeFile;
            S.optimizeFile = null;
            clearAttachedFile();
            const isContinue = conv.optimizingComplete && !!conv.lastOptimized && !file;
            await sendOptimize(q, isContinue, file, conv, convId);
        } else if (mode === 'gap') {
            await sendDiagnosis(q, conv, convId);
        } else if (mode === 'search') {
            await sendSearch(q, conv, convId);
        } else if (mode === 'compare') {
            await sendCompare(q, conv, convId);
            S.compareFileA = null; S.compareFileB = null;
            updateCompareUI();
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            // stopGeneration() 已处理 UI（设置 _continue 标志），此处不再重复覆盖
        } else {
            if (S.cid === convId) finalizeLastBubble(friendlyError(e.message), []);
        }
    } finally {
        conv.streaming = false;
        conv.abortController = null;
        // 闪烁提示（后台完成）
        if (S.cid !== convId) {
            conv._justFinished = true;
            renderHistory();
            setTimeout(() => { conv._justFinished = false; renderHistory(); }, 2000);
        } else {
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
        }
        renderHistory();
        saveConv();
    }
}

async function sendChat(q, conv, convId) {
    conv.abortController = new AbortController();
    const hist = conv.msgs.filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(0, -1).map(m => ({ role: m.role, content: m.content }));
    const res = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history: hist }),
        signal: conv.abortController.signal,
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
                if (p.type === 'text') {
                    full += p.content;
                    // 始终更新对话数据
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    // 仅在当前显示该对话时更新 DOM
                    if (S.cid === convId) updateLastBubble(full);
                } else if (p.type === 'sources') {
                    sources = p.sources;
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].sources = sources;
                } else if (p.type === 'error') {
                    full += '\n\n' + p.content;
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    if (S.cid === convId) updateLastBubble(full);
                }
            } catch (e) {}
        }
    }
    if (full) {
        if (S.cid === convId) { finalizeLastBubble(full, sources); }
        else {
            if (conv.msgs.length) {
                conv.msgs[conv.msgs.length - 1].content = full;
                conv.msgs[conv.msgs.length - 1].sources = sources;
            }
        }
    } else {
        if (S.cid === convId) { finalizeLastBubble('抱歉，未能获取到回复，请重试。', []); }
        else {
            if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = '抱歉，未能获取到回复，请重试。';
        }
    }
}

async function sendOptimize(text, isContinue, file, conv, convId) {
    conv.abortController = new AbortController();
    if (S.cid === convId) updateLastBubble(isContinue ? '正在继续调整...' : '正在按海军文书规范优化中...');

    let bodyObj = { style: conv.optStyle, intensity: conv.optIntensity };

    if (file) {
        const fd = new FormData(); fd.append('file', file);
        const upRes = await fetch('/api/upload', { method: 'POST', body: fd, signal: conv.abortController.signal });
        const upData = await upRes.json();
        if (upData.error) {
            if (S.cid === convId) finalizeLastBubble('文件上传失败: ' + upData.error, []);
            return;
        }
        bodyObj.file_path = upData.file_path;
        bodyObj.text = text || '';
    } else {
        bodyObj.text = text;
    }

    const body = isContinue ? {
        previous_result: conv.lastOptimized,
        adjustment: text,
    } : bodyObj;

    const res = await fetch('/api/optimize', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: conv.abortController.signal,
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let full = '', changes = null;
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of dec.decode(value).split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const d = line.slice(6);
            if (d === '[DONE]') continue;
            try {
                const p = JSON.parse(d);
                if (p.type === 'text') {
                    full += p.content;
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    if (S.cid === convId) updateLastBubble(full);
                } else if (p.type === 'cleaned_text') {
                    full = p.content;  // cleaned_text 是完整文本，直接替换
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    if (S.cid === convId) updateLastBubble(full);
                } else if (p.type === 'phase') {
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = p.message || full;
                    if (S.cid === convId) updateLastBubble(p.message || full);
                } else if (p.type === 'changes') {
                    changes = p;
                } else if (p.type === 'error') {
                    full += '\n\n' + p.content;
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    if (S.cid === convId) updateLastBubble(full);
                }
            } catch (e) {}
        }
    }
    if (full) {
        let result = isContinue ? `### 调整结果\n\n${full}` : `### 优化结果\n\n${full}`;
        if (changes && (changes.terminology_changes || changes.structural_changes || changes.format_changes || changes.correction_count)) {
            result += '\n\n---\n### 变更摘要\n';
            if (changes.correction_count) result += `- 基础纠错: ${changes.correction_count}处\n`;
            if (changes.terminology_changes) result += `- 术语统一: ${changes.terminology_changes}处\n`;
            if (changes.structural_changes) result += `- 结构调整: ${changes.structural_changes}处\n`;
            if (changes.format_changes) result += `- 格式规整: ${changes.format_changes}处\n`;
            result += `\n${changes.summary || ''}`;
        }
        if (S.cid === convId) {
            finalizeLastBubble(result, []);
        } else {
            if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = result;
        }
        conv.lastOptimized = full;
        conv.optimizingComplete = true;
    } else {
        if (S.cid === convId) finalizeLastBubble('优化失败，请重试。', []);
        else { if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = '优化失败，请重试。'; }
    }
}


async function sendDiagnosis(q, conv, convId) {
    conv.abortController = new AbortController();
    const depthLabel = conv.diagnosisDepth === 'quick' ? '快速合规' : '全链路诊断';
    if (S.cid === convId) updateLastBubble(`正在启动${depthLabel}，检索关联标准...`);
    let url, body;
    if (S.gapFile) {
        const fd = new FormData(); fd.append('file', S.gapFile);
        const upRes = await fetch('/api/upload', { method: 'POST', body: fd, signal: conv.abortController.signal });
        const upData = await upRes.json();
        if (upData.error) {
            if (S.cid === convId) finalizeLastBubble('文件上传失败: ' + upData.error, []);
            clearAttachedFile();
            return;
        }
        url = '/api/gap-text';
        conv._gapFilePath = upData.file_path;
        body = JSON.stringify({ file_path: upData.file_path, text: q || '', standard_name: upData.metadata?.standard_name || S.gapFile.name, depth: conv.diagnosisDepth, field: conv.diagnosisField });
        clearAttachedFile();
    } else {
        url = '/api/gap-text';
        body = JSON.stringify({ text: q, standard_name: q, depth: conv.diagnosisDepth, field: conv.diagnosisField });
    }
    const res = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body,
        signal: conv.abortController.signal,
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let full = '', relatedStandards = [], defects = null;
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of dec.decode(value).split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const d = line.slice(6);
            if (d === '[DONE]') continue;
            try {
                const p = JSON.parse(d);
                if (p.type === 'text') {
                    let content = p.content;
                    if (content.includes('📎') || content.includes('undefined undefined')) {
                        content = content.split('\n').filter(line =>
                            !line.includes('📎') && !line.includes('undefined undefined')
                        ).join('\n');
                        if (!content.trim()) continue;
                    }
                    full += content;
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    if (S.cid === convId) updateLastBubble(full);
                }
                else if (p.type === 'phase') {
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = p.message || full;
                    if (S.cid === convId) updateLastBubble(p.message || full);
                }
                else if (p.type === 'related_standards') {
                    relatedStandards = p.standards || [];
                }
                else if (p.type === 'defects') { defects = p.defects; }
                else if (p.type === 'cleaned_text') {
                    full = p.content;
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    if (S.cid === convId) updateLastBubble(full);
                }
                else if (p.type === 'error') {
                    full += '\n\n' + p.content;
                    if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                    if (S.cid === convId) updateLastBubble(full);
                }
            } catch (e) {}
        }
    }
    if (full) {
        let result = '';
        if (defects && defects.total > 0) {
            result += renderDefectsCard(defects);
        }
        if (relatedStandards.length) {
            result += '### 关联标准\n' + relatedStandards.map(s => `- [${s.standard_number}] ${s.standard_name}`).join('\n') + '\n\n';
        }
        result += full;
        if (S.cid === convId) {
            finalizeLastBubble(result, relatedStandards);
        } else {
            if (conv.msgs.length) { conv.msgs[conv.msgs.length - 1].content = result; conv.msgs[conv.msgs.length - 1].sources = relatedStandards; }
        }
    } else {
        if (S.cid === convId) finalizeLastBubble('诊断分析失败，请重试。', []);
        else { if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = '诊断分析失败，请重试。'; }
    }
}

function renderDefectsCard(d) {
    return '### 缺陷统计\n'
        + '| P0致命 | P1重要 | P2一般 | P3建议 | 合计 |\n'
        + '|:---:|:---:|:---:|:---:|:---:|\n'
        + `| ${d.p0 || 0} | ${d.p1 || 0} | ${d.p2 || 0} | ${d.p3 || 0} | ${d.total || 0} |\n\n`;
}

function stopGeneration() {
    const conv = active();
    if (conv.abortController) {
        conv.abortController.abort();
        conv.abortController = null;
        conv.streaming = false;
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('stopBtn').style.display = 'none';

        const last = conv.msgs.length ? conv.msgs[conv.msgs.length - 1] : null;
        if (last && last.role === 'assistant') {
            last._continue = true;  // 始终保留气泡，允许重新/继续生成
            if (!last.content) {
                last.content = '⚓ 已停止生成，暂无回复。';  // 占位提示
            }
            renderMsgs();
        }

        renderHistory();
        saveConv();
    }
}

async function continueChat() {
    const conv = active();
    if (conv.streaming) return;

    const last = conv.msgs.length ? conv.msgs[conv.msgs.length - 1] : null;
    if (!last || last.role !== 'assistant' || !last._continue) return;

    // 文本优化：后端已支持续写（previous_result + adjustment）
    if (conv.chatMode === 'optimize') {
        last._continue = false;
        conv.optimizingComplete = true;
        conv.lastOptimized = last.content || '';
        renderMsgs();
        document.getElementById('welcomeBlock').style.display = 'none';
        // 调用 sendOptimize 的续写模式
        const convId = S.cid;
        conv.streaming = true;
        conv.abortController = new AbortController();
        document.getElementById('sendBtn').disabled = true;
        document.getElementById('stopBtn').style.display = 'flex';
        renderHistory();
        try {
            await sendOptimize('请继续完成未完成的优化', true, null, conv, convId);
        } catch (e) {
            if (e.name !== 'AbortError' && S.cid === convId) finalizeLastBubble(friendlyError(e.message), []);
        } finally {
            conv.streaming = false;
            conv.abortController = null;
            renderHistory();
            if (S.cid === convId) {
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('stopBtn').style.display = 'none';
            }
            saveConv();
        }
        return;
    }

    // 检索：非流式，重新生成
    if (conv.chatMode === 'search') {
        last._continue = false;
        const userMsg = conv.msgs.slice(0, -1).reverse().find(m => m.role === 'user');
        conv.msgs.pop();
        conv.msgs.push({ role: 'assistant', content: '', sources: [] });
        renderMsgs();
        document.getElementById('chatInput').value = userMsg?.content || '';
        setTimeout(() => send(), 50);
        return;
    }

    // 诊断、比对：LLM 流式，断点续写
    if (conv.chatMode === 'gap' || conv.chatMode === 'compare') {
        last._continue = false;
        const partial = last.content || '';
        renderMsgs();
        const convId = S.cid;
        conv.streaming = true;
        conv.abortController = new AbortController();
        document.getElementById('sendBtn').disabled = true;
        document.getElementById('stopBtn').style.display = 'flex';
        renderHistory();
        try {
            const userMsg = conv.msgs.slice(0, -1).reverse().find(m => m.role === 'user');
            const endpoint = conv.chatMode === 'gap' ? '/api/gap-text' : '/api/compare';
            const body = conv.chatMode === 'gap'
                ? { text: userMsg?.content || '', file_path: conv._gapFilePath || '', standard_name: userMsg?.content || '', depth: conv.diagnosisDepth, field: conv.diagnosisField, continue_content: partial }
                : { instruction: userMsg?.content || '', file_a: conv._comparePathA || '', file_b: conv._comparePathB || '', text_a: conv._compareTextA || '', text_b: conv._compareTextB || '', continue_content: partial };
            const res = await fetch(endpoint, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: conv.abortController.signal,
            });
            const reader = res.body.getReader(); const dec = new TextDecoder();
            let full = partial;
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                for (const line of dec.decode(value).split('\n')) {
                    if (!line.startsWith('data: ')) continue;
                    const d = line.slice(6);
                    if (d === '[DONE]') continue;
                    try {
                        const p = JSON.parse(d);
                        if (p.type === 'text') {
                            full += p.content;
                            conv.msgs[conv.msgs.length - 1].content = full;
                            if (S.cid === convId) updateLastBubble(full);
                        }
                    } catch (_) {}
                }
            }
            if (S.cid === convId) finalizeLastBubble(full, []);
        } catch (e) {
            if (e.name !== 'AbortError' && S.cid === convId) finalizeLastBubble(friendlyError(e.message), []);
        } finally {
            conv.streaming = false;
            conv.abortController = null;
            renderHistory();
            if (S.cid === convId) { document.getElementById('sendBtn').disabled = false; document.getElementById('stopBtn').style.display = 'none'; }
            saveConv();
        }
        return;
    }

    // 智能问答：支持断点续写
    const isRegen = last.content === '⚓ 已停止生成，暂无回复。';
    const partialContent = isRegen ? '' : last.content;

    last._continue = false;
    renderMsgs();

    if (isRegen) {
        conv.msgs.pop();
        conv.msgs.push({ role: 'assistant', content: '', sources: [] });
        renderMsgs();
    }

    document.getElementById('welcomeBlock').style.display = 'none';
    conv.streaming = true;
    conv.abortController = new AbortController();
    const convId = S.cid;
    document.getElementById('sendBtn').disabled = true;
    document.getElementById('stopBtn').style.display = 'flex';
    renderHistory();

    try {
        const allMsgs = conv.msgs.filter(m => m.role === 'user' || m.role === 'assistant');
        const hist = allMsgs.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

        let question, history;
        if (isRegen) {
            history = hist.slice(0, -1);
            question = hist.length ? hist[hist.length - 1].content : '';
        } else {
            history = hist.slice(0, -1);
            const userQ = hist.length ? hist[hist.length - 1].content : '';
            question = `【以下是你未完成的回答前半部分，请从断点处直接续写，不要重复已有内容】\n原始问题：${userQ}\n\n已有内容：\n${partialContent.slice(-300)}`;
        }

        const res = await fetch('/api/chat', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question, history: history }),
            signal: conv.abortController.signal,
        });
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let full = partialContent, sources = [];
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            for (const line of dec.decode(value).split('\n')) {
                if (!line.startsWith('data: ')) continue;
                const d = line.slice(6);
                if (d === '[DONE]') continue;
                try {
                    const p = JSON.parse(d);
                    if (p.type === 'text') {
                        full += p.content;
                        if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                        if (S.cid === convId) updateLastBubble(full);
                    } else if (p.type === 'sources') {
                        sources = p.sources;
                        if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].sources = sources;
                    } else if (p.type === 'error') {
                        full += '\n\n' + p.content;
                        if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                        if (S.cid === convId) updateLastBubble(full);
                    }
                } catch (e) {}
            }
        }
        if (full && full !== partialContent) {
            if (S.cid === convId) { finalizeLastBubble(full, sources); }
            else {
                if (conv.msgs.length) {
                    conv.msgs[conv.msgs.length - 1].content = full;
                    conv.msgs[conv.msgs.length - 1].sources = sources;
                }
            }
        } else if (full === partialContent) {
            if (S.cid === convId) { finalizeLastBubble('抱歉，无法继续生成，请重试。', []); }
            else { if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = '抱歉，无法继续生成，请重试。'; }
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            conv.abortController = null;
            conv.streaming = false;
            const lastMsg = conv.msgs.length ? conv.msgs[conv.msgs.length - 1] : null;
            if (lastMsg && lastMsg.role === 'assistant') {
                lastMsg._continue = true;
                if (!lastMsg.content) {
                    lastMsg.content = '⚓ 已停止生成，暂无回复。';
                }
            }
            if (S.cid === convId) {
                renderMsgs();
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('stopBtn').style.display = 'none';
            }
        } else {
            if (S.cid === convId) finalizeLastBubble(friendlyError(e.message), []);
        }
    } finally {
        conv.streaming = false;
        conv.abortController = null;
        renderHistory();
        if (S.cid === convId) {
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
        }
        saveConv();
    }
}

function setMode(mode) {
    const conv = active();
    const modeChanged = conv.chatMode !== mode;
    conv.chatMode = mode;
    S.gapFile = null;
    S.optimizeFile = null;
    S.compareFileA = null;
    S.compareFileB = null;
    S.compareTextA = '';
    S.compareTextB = '';
    clearAttachedFile();
    updateCompareUI();
    if (modeChanged) {
        conv.lastOptimized = null;
        conv.optimizingComplete = false;
    }
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    const modeBtn = document.querySelector(`.mode-btn[data-mode="${mode}"]`);
    if (modeBtn) modeBtn.classList.add('active');
    const attachBtn = document.getElementById('attachBtn');
    attachBtn.classList.toggle('show', mode === 'gap' || mode === 'optimize');
    document.getElementById('optimizePanel').style.display = mode === 'optimize' ? 'block' : 'none';
    document.getElementById('diagnosisPanel').style.display = mode === 'gap' ? 'block' : 'none';
    document.getElementById('comparePanel').style.display = mode === 'compare' ? 'flex' : 'none';
    const input = document.getElementById('chatInput');
    const placeholders = {chat:'请输入您的问题...', optimize:'输入文本或上传文件...', gap:'输入文本或上传文件...', search:'输入关键词检索标准...', compare:'输入对比要求，或上传两份标准文件...'};
    input.placeholder = placeholders[mode] || placeholders['chat'];
    const hints = {gap:'🔬 输入文本或上传标准文件，发送诊断', optimize:'✏️ 输入文本或上传文件，发送优化', compare:'⚖️ 上传两份标准文件进行比对', search:'🔎 输入关键词，在已入库标准中检索相关条款', chat:'💬 Enter 发送，Shift+Enter 换行'};
    document.getElementById('footHint').textContent = hints[mode] || hints['chat'];

    // 切换欢迎区内容
    const welcome = document.getElementById('welcomeBlock');
    if (welcome) {
        const welcomes = {
            chat: `<h1>⚓ 您好，我是海军标准智能助手</h1>
                <p class="welcome-desc">严格依托入库标准作答，杜绝编造，<strong style="color: #f5c542;">强制溯源</strong></p>
                <div class="hint-grid">
                    <button class="hint-card" onclick="sendHint('信息技术与大数据服务的安全能力应符合哪些标准要求？')"><span class="hint-icon">🔐</span><span>信息技术与大数据服务的安全能力应符合哪些标准要求？</span></button>
                    <button class="hint-card" onclick="sendHint('机械电气设备的电磁兼容抗扰度要求有哪些？')"><span class="hint-icon">⚡</span><span>机械电气设备的电磁兼容抗扰度要求有哪些？</span></button>
                    <button class="hint-card" onclick="sendHint('个体防护装备的术语定义与规范依据是什么？')"><span class="hint-icon">🛡️</span><span>个体防护装备的术语定义与规范依据是什么？</span></button>
                    <button class="hint-card" onclick="sendHint('船舶自动识别系统的技术要求应符合哪些标准？')"><span class="hint-icon">🧭</span><span>船舶自动识别系统的技术要求应符合哪些标准？</span></button>
                </div>`,
            optimize: `<h1>✏️ 文本优化</h1>
                <p class="welcome-desc">粘贴文本或上传文件，选择文风和优化力度后发送，AI 将按海军文书规范优化</p>
                <div class="info-cards">
                    <div class="info-card"><span class="info-icon">🎨</span><div class="info-body"><strong>文风</strong><div class="info-opt"><em>标准制式</em> 严格按军用标准规范行文，用词正式严谨</div><div class="info-opt"><em>简洁干练</em> 精简冗余修饰，突出重点信息</div><div class="info-opt"><em>权威专业</em> 突出技术深度，引用标准依据</div></div></div>
                    <div class="info-card"><span class="info-icon">⚡</span><div class="info-body"><strong>力度</strong><div class="info-opt"><em>轻度润色</em> 仅修正错别字、语法和标点错误</div><div class="info-opt"><em>中度优化</em> 优化句式结构+统一专业术语+精简冗余</div><div class="info-opt"><em>深度重构</em> 全维度重构+逻辑重组+格式规整</div></div></div>
                    <div class="info-card info-card-full"><span class="info-icon">💡</span><div class="info-body"><strong>提示</strong>优化时可在输入框提出调整要求，例如"精简到500字"、"补充技术细节"或"调整为更正式的语气"</div></div>
                </div>`,
            gap: `<h1>🔬 标准诊断</h1>
                <p class="welcome-desc">上传标准文件或输入文本，选择分析深度和适用领域后发送，AI 将自动检索关联标准并逐条诊断</p>
                <div class="info-cards">
                    <div class="info-card"><span class="info-icon">🔍</span><div class="info-body"><strong>分析深度</strong><div class="info-opt"><em>快速合规</em> 快速扫描主要条款，输出合规结论</div><div class="info-opt"><em>全链路诊断</em> 逐条对标+缺口识别+交叉重复检测+增补建议</div></div></div>
                    <div class="info-card"><span class="info-icon">🎯</span><div class="info-body"><strong>适用领域</strong><div class="info-opt"><em>通用</em> 全库检索，不限定领域</div><div class="info-opt"><em>舰船装备</em> 优先检索舰船装备类标准</div><div class="info-opt"><em>军用公文</em> 优先检索军用公文类标准</div><div class="info-opt"><em>大数据</em> 优先检索大数据类标准</div></div></div>
                    <div class="info-card info-card-full"><span class="info-icon">💡</span><div class="info-body"><strong>提示</strong>诊断时可在输入框提出要求，例如"给出致命缺陷的整改方案"、"补充舰船装备相关的标准要求"或"帮我总结主要风险点"</div></div>
                </div>`,
            search: `<h1>🔎 全文检索</h1>
                <p class="welcome-desc">在已入库标准中按关键词搜索，返回相关条款原文及出处</p>
                <div class="info-cards">
                    <div class="info-card info-card-full"><span class="info-icon">💡</span><div class="info-body"><strong>提示</strong>输入关键词即可在已入库标准中检索，例如"电磁兼容"、"焊缝检测"或"防护等级要求"。默认返回10条，可指定数量如"电磁兼容 5条"或"前3条 焊缝检测"</div></div>
                </div>`,
            compare: `<h1>⚖️ 标准比对</h1>
                <p class="welcome-desc">上传两份标准文件或直接输入文本，逐条比对差异并识别冲突项和互补内容</p>
                <div class="info-cards">
                    <div class="info-card info-card-full"><span class="info-icon">💡</span><div class="info-body"><strong>提示</strong>用下方按钮上传标准A和标准B的文件，每个标准可选择上传文件或点击✏️直接输入文本内容。两份内容都准备好后，可在输入框填写比对要求（如"只对比技术指标"）并发送</div></div>
                </div>`,
        };
        welcome.innerHTML = welcomes[mode] || welcomes['chat'];
    }

    input.focus();
}

async function sendSearch(q, conv, convId) {
    if (!q) return;
    conv.abortController = new AbortController();
    if (S.cid === convId) updateLastBubble('...');
    try {
        const res = await fetch('/api/search', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q }),
            signal: conv.abortController.signal,
        });
        const data = await res.json();
        if (data.error) {
            if (S.cid === convId) finalizeLastBubble(data.error, []);
            else { if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = data.error; }
            return;
        }
        if (!data.results.length) {
            const hint = '未找到匹配的标准条款。请输入与标准相关的关键词检索，例如"电磁兼容"、"焊缝检测"或"防护等级"';
            if (S.cid === convId) finalizeLastBubble(hint, []);
            else { if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = hint; }
            return;
        }

        let html = `<div class="search-summary">找到 <strong>${data.count}</strong> 条结果</div><div class="search-results">`;
        const seen = new Set();
        data.results.forEach(r => {
            const key = r.standard_number + r.chunk_text.slice(0, 50);
            if (seen.has(key)) return; seen.add(key);
            const cls = r.doc_status === '现行有效' ? 'green' : r.doc_status === '修订中' ? 'yellow' : 'red';
            let txt = r.chunk_text.replace(/\s{2,}/g, ' ').trim();
            html += `<div class="search-card">
                <div class="search-card-head"><span class="dot ${cls}"></span><strong>${r.standard_number}</strong> ${r.standard_name}</div>
                <div class="search-card-section">${r.section_title || '正文'} ${r.clause_number||''}</div>
                <div class="search-card-text">${txt.slice(0, 500)}${txt.length>500?'...':''}</div>
            </div>`;
        });
        html += '</div>';

        if (conv.msgs.length) {
            conv.msgs[conv.msgs.length - 1].content = html;
            conv.msgs[conv.msgs.length - 1].sources = data.results;
        }
        if (S.cid === convId) {
            renderMsgs();
            const bubbles = document.querySelectorAll('#msgList .msg.assistant .msg-bubble');
            const last = bubbles[bubbles.length - 1];
            if (last) last.innerHTML = html;
        }
    } catch (e) {
        if (e.name === 'AbortError') return;  // stopGeneration() 已处理 UI
        if (S.cid === convId) finalizeLastBubble(friendlyError(e.message), []);
        else { if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = friendlyError(e.message); }
    }
}

async function sendCompare(q, conv, convId) {
    conv.abortController = new AbortController();
    const fdA = S.compareFileA, fdB = S.compareFileB;
    const signal = conv.abortController.signal;
    const uploadFile = async (file) => {
        if (!file) return '';
        const fd = new FormData(); fd.append('file', file);
        const r = await fetch('/api/upload', { method: 'POST', body: fd, signal });
        const d = await r.json();
        return d.file_path || '';
    };
    const contentA = S.compareTextA, contentB = S.compareTextB;
    if (S.cid === convId && (fdA || fdB)) updateLastBubble('正在上传文件...');
    const pathA = fdA ? await uploadFile(fdA) : '';
    const pathB = fdB ? await uploadFile(fdB) : '';

    if (S.cid === convId) updateLastBubble('正在逐条比对两份标准...');
    // 保存路径用于续写
    conv._comparePathA = pathA; conv._comparePathB = pathB;
    conv._compareTextA = contentA; conv._compareTextB = contentB;
    S.compareFileA = null; S.compareFileB = null;
    S.compareTextA = ''; S.compareTextB = '';
    clearAttachedFile();
    updateCompareUI();

    const res = await fetch('/api/compare', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            instruction: q || '',
            file_a: pathA, file_b: pathB,
            text_a: contentA, text_b: contentB,
        }),
        signal,
    });
    const reader = res.body.getReader(); const dec = new TextDecoder(); let full = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of dec.decode(value).split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const d = JSON.parse(line.slice(6));
            if (d.type === 'text') {
                full += d.content;
                if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
                if (S.cid === convId) updateLastBubble(full);
            } else if (d.type === 'phase') {
                if (S.cid === convId) updateLastBubble(d.message);
            } else if (d.type === 'error') {
                if (S.cid === convId) finalizeLastBubble(d.content, []);
                else { if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = d.content; }
                return;
            } else if (d.type === 'done') break;
        }
    }
    if (S.cid === convId) {
        finalizeLastBubble(full, []);
    } else {
        if (conv.msgs.length) conv.msgs[conv.msgs.length - 1].content = full;
    }
}

function onCompareFileA(files) {
    if (files.length) { S.compareFileA = files[0]; updateCompareUI(); }
    document.getElementById('compareFileA').value = '';
}
function onCompareFileB(files) {
    if (files.length) { S.compareFileB = files[0]; updateCompareUI(); }
    document.getElementById('compareFileB').value = '';
}
async function openCompareText(slot) {
    const label = slot === 'A' ? '标准A' : '标准B';
    const current = slot === 'A' ? S.compareTextA : S.compareTextB;
    const text = await new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal-box" style="max-width:560px;">
                <div class="modal-title">输入${label}内容</div>
                <textarea class="modal-textarea" id="modalTextarea" rows="10" placeholder="直接粘贴或输入标准文本内容…">${current || ''}</textarea>
                <div class="modal-btns">
                    <button class="modal-btn cancel">取消</button>
                    <button class="modal-btn confirm">确定</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        const textarea = document.getElementById('modalTextarea');
        const close = (val) => { overlay.remove(); resolve(val); };
        overlay.querySelector('.cancel').onclick = () => close(null);
        overlay.querySelector('.confirm').onclick = () => close(textarea.value);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(null); });
        document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { close(null); document.removeEventListener('keydown', esc); } });
        setTimeout(() => textarea.focus(), 100);
    });
    if (text !== null) {
        if (slot === 'A') S.compareTextA = text;
        else S.compareTextB = text;
        updateCompareUI();
    }
}
function updateCompareUI() {
    const a = S.compareFileA, b = S.compareFileB;
    const ta = S.compareTextA, tb = S.compareTextB;
    const btnA = document.getElementById('btnCompareA');
    const btnB = document.getElementById('btnCompareB');
    if (btnA) {
        btnA.textContent = a ? '📄 ' + a.name : ta ? '✏️ 文本A' : '📄 选择标准A';
        btnA.classList.toggle('has-file', !!(a || ta));
    }
    if (btnB) {
        btnB.textContent = b ? '📄 ' + b.name : tb ? '✏️ 文本B' : '📄 选择标准B';
        btnB.classList.toggle('has-file', !!(b || tb));
    }
}

function onGapFile(files) {
    if (!files.length) return;
    const f = files[0];
    if (active().chatMode === 'optimize') {
        S.optimizeFile = f;
    } else {
        S.gapFile = f;
    }
    showFileChip(f.name);
    document.getElementById('gapFileInput').value = '';
}

function showFileChip(name) {
    document.getElementById('fileChipName').textContent = name;
    document.getElementById('fileChip').style.display = 'flex';
}

function clearAttachedFile() {
    S.gapFile = null;
    S.optimizeFile = null;
    document.getElementById('fileChip').style.display = 'none';
    document.getElementById('gapFileInput').value = '';
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

async function onFiles(files) {
    // 防止重复触发
    if (S._uploading) { toast('正在上传中，请稍候...', 'info'); return; }

    const exts = ['pdf', 'docx', 'txt'];
    const all = Array.from(files);
    const valid = all.filter(f => exts.includes(f.name.split('.').pop().toLowerCase()));
    const skipped = all.length - valid.length;
    if (skipped > 0) toast(`已跳过 ${skipped} 个不支持的文件`, 'info');
    if (!valid.length) { toast('未找到 PDF/DOCX/TXT 文件', 'error'); return; }

    S._uploading = true;
    let done = 0, fail = 0;
    const total = valid.length;

    // 先把所有文件加入 pending（状态 parsing）
    valid.forEach(f => {
        const tmpId = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
        f._tmpId = tmpId;
        S.pending.push({ _id: tmpId, filename: f.name, text_length: 0, metadata: {}, _status: 'parsing' });
    });
    renderPending();

    try {
        // 并发控制：最多 3 个同时上传
        const CONCURRENCY = 3;
        const uploadOne = async (f) => {
            const fd = new FormData(); fd.append('file', f);
            try {
                const r = await fetch('/api/upload', { method: 'POST', body: fd });
                const d = await r.json();
                if (d.error) {
                    toast(f.name + ': ' + d.error, 'error');
                    S.pending = S.pending.filter(p => p._id !== f._tmpId);
                    fail++;
                } else {
                    d._id = f._tmpId; d._status = 'parsed'; d.duplicate = d.duplicate || null;
                    const idx = findPendingIdx(f._tmpId);
                    if (idx >= 0) S.pending[idx] = d;
                    done++;
                }
            } catch (e) {
                toast(f.name + ' 上传失败', 'error');
                S.pending = S.pending.filter(p => p._id !== f._tmpId);
                fail++;
            }
            S._uploadProgress = `正在上传 ${done + fail}/${total}`;
            renderPending();
        };

        // 分批并行
        for (let i = 0; i < valid.length; i += CONCURRENCY) {
            const batch = valid.slice(i, i + CONCURRENCY);
            await Promise.all(batch.map(uploadOne));
        }

        if (fail > 0) toast(`上传完成: ${done}成功 ${fail}失败`, fail > 0 ? 'error' : 'success');
        else toast(`${done} 个文件上传完成`, 'success');
        renderPending();
    } catch (e) {
        toast('上传过程出错: ' + (e.message || '未知错误'), 'error');
    } finally {
        S._uploading = false;
        S._uploadProgress = '';
        renderPending();
        document.getElementById('fileInput').value = '';
        const folderInp = document.getElementById('folderInput');
        if (folderInp) folderInp.value = '';
    }
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
    // 保存当前焦点，DOM 重建后恢复
    const focusedId = document.activeElement?.closest('.pending-row')?.querySelector('input')?.dataset?.pid || null;
    const ingesting = S._ingesting || false;
    const uploading = S._uploading || false;
    const hasParsing = S.pending.some(p => p._status === 'parsing');
    const disableIngest = ingesting || hasParsing;
    const statusLabel = s => ({parsing:'解析中...', parsed:'已上传', ingesting:'入库中...'}[s] || '');
    const dupCount = S.pending.filter(p => p.duplicate).length;
    const idleLabel = dupCount > 0
        ? (dupCount === S.pending.length ? `📦 全部覆盖(${S.pending.length})` : `📦 入库+覆盖 ${S.pending.length - dupCount}新/${dupCount}覆盖`)
        : `📦 全部入库 <span class="count">${S.pending.length}</span>`;
    area.innerHTML =
        `<div class="btn-row">
            <button class="${dupCount > 0 ? 'btn-ingest-all has-overwrite' : 'btn-ingest-all'}" onclick="doIngestAll()" ${disableIngest ? 'disabled' : ''}>
                ${ingesting ? '<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> 正在入库...' :
                  uploading ? '<span class="spinner" style="width:18px;height:18px;border-width:2px"></span> 文件上传中...' :
                  idleLabel}
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
                <div class="meta">
                    ${f.text_length} 字 | 编号: ${f.metadata.standard_number || '未识别'} | 名称: ${f.metadata.standard_name || '未识别'}
                    ${f.duplicate ? `<span style="background:rgba(220,20,60,0.15);color:#f87171;font-size:11px;padding:2px 6px;border-radius:4px;margin-left:6px">⚠ 已存在(${f.duplicate.length}条)</span>` : ''}
                </div>
                <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
                    <input value="${f.metadata.standard_number||''}" placeholder="标准编号" data-pid="${id}" oninput="S.pending[findPendingIdx('${id}')].metadata.standard_number=this.value">
                    <input value="${f.metadata.standard_name||''}" placeholder="标准名称" data-pid="${id}" oninput="S.pending[findPendingIdx('${id}')].metadata.standard_name=this.value" style="width:180px">
                    <select onchange="S.pending[findPendingIdx('${id}')].metadata.doc_status=this.value">
                        <option ${f.metadata.doc_status==='现行有效'?'selected':''}>现行有效</option>
                        <option ${f.metadata.doc_status==='修订中'?'selected':''}>修订中</option>
                        <option ${f.metadata.doc_status==='废止'?'selected':''}>废止</option>
                    </select>
                </div>
            </div>
            <div style="display:flex;gap:8px">
                <button class="${f.duplicate ? 'btn-sm-warning' : 'btn-sm-primary'}" onclick="doIngest('${id}')" ${(ingesting || status === 'parsing') ? 'disabled' : ''}>${f.duplicate ? '🔄 覆盖旧文档' : '入库'}</button>
                <button class="btn-sm-ghost" onclick="removePending('${id}')" ${ingesting ? 'disabled' : ''}>移除</button>
            </div>
        </div>`;
    }).join('');

    // 恢复焦点到之前正在编辑的输入框
    if (focusedId) {
        const el = document.querySelector(`input[data-pid="${focusedId}"]`);
        if (el) { const len = el.value.length; el.focus(); el.setSelectionRange(len, len); }
    }
}

async function doIngest(id, showToast = true) {
    const i = findPendingIdx(id);
    if (i < 0) return false;
    const f = S.pending[i];
    f._status = 'ingesting'; renderPending();
    try {
        const body = {
            file_path: f.file_path,
            standard_number: f.metadata.standard_number,
            standard_name: f.metadata.standard_name || f.filename,
            applicable_field: f.metadata.applicable_field || '',
            doc_status: f.metadata.doc_status || '现行有效',
            responsible_unit: f.metadata.responsible_unit || '',
            file_type: f.filename.split('.').pop(),
        };

        // 上传时已检测到重复，直接覆盖，跳过二次弹窗
        if (f.duplicate) {
            body.overwrite = true;
        }

        let r = await fetch('/api/ingest', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        let d = await r.json();

        // 处理重复冲突（上传时未检出，入库时才发现的兜底）
        if (d.conflict && !f.duplicate) {
            f._status = ''; renderPending();
            const existingInfo = d.existing && d.existing.length > 0
                ? d.existing.map(e => `[${e.standard_name}] (${e.upload_time})`).join('<br>')
                : '';
            const ok = await showModal(
                '文档重复',
                `该文档已存在：<br><br>标准号：${d.standard_number}<br>标准名：${d.standard_name}<br><br>已入库记录：<br>${existingInfo}<br><br>是否覆盖旧记录？覆盖将删除旧文档及其向量块，重新入库。`,
                undefined,
                '覆盖'
            );
            if (!ok) { return false; }

            body.overwrite = true;
            f._status = 'ingesting'; renderPending();
            r = await fetch('/api/ingest', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            d = await r.json();
            if (d.error) { toast('覆盖入库失败: ' + d.error, 'error'); f._status = ''; renderPending(); return false; }
            if (showToast) toast(`🔄 ${f.filename} 覆盖成功 (ID:${d.doc_id}, ${d.chunk_count}块)`, 'success');
            S.pending.splice(i, 1); renderPending(); loadUploadedDocs();
            return true;
        }

        if (d.error) { toast('入库失败: ' + d.error, 'error'); f._status = ''; renderPending(); return false; }
        if (showToast) {
            const label = f.duplicate ? '覆盖成功' : '入库成功';
            const emoji = f.duplicate ? '🔄' : '✅';
            toast(`${emoji} ${f.filename} ${label} (ID:${d.doc_id}, ${d.chunk_count}块)`, 'success');
        }
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
    let fail = 0, overwrite = 0, newDoc = 0;
    for (let i = 0; i < total; i++) {
        if (!S.pending.length) break;
        const id = S.pending[0]._id;
        const isDup = !!S.pending[0].duplicate;
        S._ingestProgress = `正在${isDup ? '覆盖' : '入库'} ${i+1}/${total}`; renderPending();
        const ok = await doIngest(id, false);
        if (!ok) fail++;
        else if (isDup) overwrite++;
        else newDoc++;
    }
    S._ingesting = false; S._ingestProgress = '';
    const success = total - fail;
    const parts = [];
    if (newDoc > 0) parts.push(`${newDoc}个入库`);
    if (overwrite > 0) parts.push(`${overwrite}个覆盖`);
    const detail = parts.join('，');
    if (fail > 0) toast(`${detail}，${fail}个失败`, 'error');
    else if (success > 0) toast(`${detail} 完成`, 'success');
    renderPending(); loadUploadedDocs();
}

async function removePending(id) {
    const i = findPendingIdx(id);
    if (i < 0) return;
    const f = S.pending[i];
    S.pending.splice(i, 1); renderPending();
    // 异步删除磁盘临时文件（不影响 UI）
    if (f.file_path) {
        fetch('/api/upload', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: f.file_path }),
        }).catch(() => {});
    }
}
async function clearAllPending() {
    if (!S.pending.length) return;
    const items = [...S.pending];
    S.pending = []; renderPending();
    toast('已清空待入库列表', 'info');

    // 分批删除磁盘临时文件，避免同时发出大量请求堵死连接池
    const BATCH = 3;
    for (let i = 0; i < items.length; i += BATCH) {
        const batch = items.slice(i, i + BATCH);
        await Promise.all(batch.map(f =>
            f.file_path ? fetch('/api/upload', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: f.file_path }),
            }).catch(() => {}) : Promise.resolve()
        ));
    }
}

function getCheckedDocIds() {
    const boxes = document.querySelectorAll('.doc-checkbox:checked');
    return Array.from(boxes).map(b => parseInt(b.dataset.id));
}

function resetBatchState() {
    S._selectAll = false;
    S._checkedIds = new Set();
    S._excludedIds = new Set();
}

function enterBatchMode() {
    S.batchMode = true;
    resetBatchState();
    renderDocsArea();
}

function exitBatchMode() {
    S.batchMode = false;
    resetBatchState();
    renderDocsArea();
}

function toggleSelectAllDocs() {
    if (S._selectAll && S._excludedIds && S._excludedIds.size > 0) {
        // 有排除项时：清空排除，重新全选
        S._excludedIds = new Set();
    } else if (S._selectAll) {
        // 完全全选时：取消全选
        S._selectAll = false;
        S._excludedIds = new Set();
        S._checkedIds = new Set();
    } else {
        // 非全选时：全选
        S._selectAll = true;
        S._excludedIds = new Set();
        S._checkedIds = new Set();
    }
    document.querySelectorAll('.doc-checkbox').forEach(b => { b.checked = S._selectAll; });
    updateSelectAllBtn();
    updateBatchCount();
}

function updateSelectAllBtn() {
    const btn = document.getElementById('selectAllBtn');
    if (!btn) return;
    const isAll = S._selectAll && (!S._excludedIds || S._excludedIds.size === 0);
    btn.textContent = isAll ? '☑️ 取消全选' : '☐ 全选';
    btn.className = isAll ? 'btn-batch-bar active' : 'btn-batch-bar';
}

function onCheckToggle(id) {
    if (!S._excludedIds) S._excludedIds = new Set();
    if (S._selectAll) {
        // 全选模式下：记录被排除的 ID
        const box = document.querySelector(`.doc-checkbox[data-id="${id}"]`);
        if (box && box.checked) {
            S._excludedIds.delete(id);
        } else {
            S._excludedIds.add(id);
        }
    } else {
        // 手动模式：记录选中的 ID
        if (!S._checkedIds) S._checkedIds = new Set();
        const box = document.querySelector(`.doc-checkbox[data-id="${id}"]`);
        if (box && box.checked) {
            S._checkedIds.add(id);
        } else {
            S._checkedIds.delete(id);
            if (S._checkedIds.size === 0) S._checkedIds = new Set();
        }
    }
    updateBatchCount();
}

function updateBatchCount() {
    const btn = document.getElementById('batchConfirmBtn');
    if (!btn) return;
    updateSelectAllBtn();

    let n;
    if (S._selectAll) {
        const total = S.docTotal || (S.docTotalPages * S.docPerPage) || 0;
        n = total - (S._excludedIds ? S._excludedIds.size : 0);
    } else if (S._checkedIds && S._checkedIds.size > 0) {
        n = S._checkedIds.size;
    } else {
        n = document.querySelectorAll('.doc-checkbox:checked').length;
    }
    btn.textContent = n > 0 ? `确认删除(${n})` : '确认删除';
    btn.disabled = (n === 0 || n === '0' || !n);
}

async function batchDeleteDocs() {
    let ids;
    if (S._selectAll) {
        const r = await fetch('/api/documents?limit=10000');
        const allDocs = await r.json();
        ids = (allDocs.docs || allDocs).map(d => d.id);
        // 排除被取消勾选的
        if (S._excludedIds && S._excludedIds.size > 0) {
            ids = ids.filter(id => !S._excludedIds.has(id));
        }
    } else if (S._checkedIds && S._checkedIds.size > 0) {
        ids = Array.from(S._checkedIds);
    } else {
        ids = getCheckedDocIds();
    }
    if (!ids || !ids.length) return;
    const ok = await showModal('批量删除', `确定删除全部 ${ids.length} 个文档及其所有向量块？此操作不可撤销。`);
    if (!ok) return;
    try {
        const r = await fetch('/api/documents/batch-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
        const data = await r.json();
        if (data.success) {
            toast(`已删除 ${data.deleted} 个文档` + (data.failed ? `，${data.failed} 个失败` : ''), data.failed ? 'error' : 'info');
            exitBatchMode();
            loadUploadedDocs(S.docPage);
            loadDocs();
        } else {
            toast(`删除失败: ${data.error}`, 'error');
        }
    } catch (e) {
        toast(`删除失败: ${e.message}`, 'error');
    }
}

async function editDoc(id) {
    const doc = _docsCache.find(d => d.id === id);
    if (!doc) return;
    const result = await showEditModal(doc.standard_number || '', doc.standard_name || '');
    if (!result) return;
    try {
        const r = await fetch(`/api/documents/${id}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(result),
        });
        const d = await r.json();
        if (d.success) { toast('已更新', 'info'); loadUploadedDocs(S.docPage); }
        else toast(d.error, 'error');
    } catch (e) { toast('更新失败', 'error'); }
}

function showEditModal(num, name) {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal-box" style="width:420px">
                <div class="modal-title">编辑文档</div>
                <div style="margin-bottom:10px"><label style="font-size:12px;color:var(--text3)">标准编号</label>
                <input class="modal-input" id="editNum" value="${num||''}" style="margin-bottom:10px"></div>
                <div style="margin-bottom:12px"><label style="font-size:12px;color:var(--text3)">标准名称</label>
                <input class="modal-input" id="editName" value="${name||''}"></div>
                <div class="modal-btns">
                    <button class="modal-btn cancel">取消</button>
                    <button class="modal-btn confirm">保存</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        overlay.querySelector('.cancel').onclick = () => { overlay.remove(); resolve(null); };
        overlay.querySelector('.confirm').onclick = () => {
            const n = document.getElementById('editNum').value.trim();
            const m = document.getElementById('editName').value.trim();
            overlay.remove();
            resolve({ standard_number: n || undefined, standard_name: m || undefined });
        };
        overlay.addEventListener('click', e => { if (e.target === overlay) { overlay.remove(); resolve(null); } });
    });
}

async function deleteDoc(id) {
    const ok = await showModal('删除文档', '确定删除该文档及其所有向量块？此操作不可撤销。');
    if (!ok) return;
    try {
        const r = await fetch(`/api/documents/${id}`, { method: 'DELETE' });
        const data = await r.json();
        if (data.success) {
            toast('文档已删除', 'info');
            loadUploadedDocs(S.docPage);
            loadDocs();
        } else {
            toast(`删除失败: ${data.error}`, 'error');
        }
    } catch (e) {
        toast(`删除失败: ${e.message}`, 'error');
    }
}

let _docsCache = [];

function renderDocsArea() {
    const area = document.getElementById('docsArea');
    const docs = _docsCache;
    const inBatch = S.batchMode;
    const hasAnyFilter = S.docSearch || S.docStatusFilter;

    // 空状态：没有任何文档
    if (!docs.length && !hasAnyFilter && S.docPage === 1) {
        area.innerHTML = '<p style="color:var(--text3);font-size:13px">暂无已入库文档</p>';
        return;
    }

    const STATUSES = ['', '现行有效', '修订中', '废止'];
    const STATUS_LABELS = { '': '全部', '现行有效': '现行有效', '修订中': '修订中', '废止': '废止' };

    let html = '';

    // ===== 搜索栏 =====
    html += `<div class="docs-toolbar">
        <div class="docs-search-wrap">
            <button class="docs-search-icon-btn" onclick="searchDocs()" title="搜索">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            </button>
            <input class="docs-search" id="docsSearchInput" autocomplete="off" placeholder="搜索标准编号或名称..." value="${escHtml(S.docSearch)}"
                onkeydown="if(event.key==='Enter')searchDocs()">
            ${S.docSearch ? `<button class="docs-search-clear" onclick="clearDocSearch()" title="清除">✕</button>` : ''}
        </div>
    </div>`;

    // ===== 状态筛选 tabs =====
    html += `<div class="docs-status-tabs">`;
    STATUSES.forEach(s => {
        const active = S.docStatusFilter === s ? ' active' : '';
        html += `<button class="docs-status-tab${active}" onclick="filterByStatus('${s}')">${STATUS_LABELS[s]}</button>`;
    });
    html += `</div>`;

    // ===== 头部：标题 + 操作按钮 =====
    html += `<div class="docs-header">
        <div class="docs-header-left">
            <h4>📚 已入库文档</h4>
            <span class="badge-count">第${S.docPage}页</span>
        </div>
        <div class="docs-header-right">`;

    if (inBatch) {
        html += `<button class="btn-batch-bar" onclick="toggleSelectAllDocs()" id="selectAllBtn">☐ 全选</button>
            <button class="btn-batch-cancel" onclick="exitBatchMode()">取消</button>`;
    } else {
        html += `<button class="btn-batch-entry" onclick="enterBatchMode()">📋 批量删除</button>`;
    }

    html += `</div></div>`;

    // ===== 批量删除栏 =====
    if (inBatch) {
        html += `<div class="batch-bar"><span>勾选要删除的文档</span><button id="batchConfirmBtn" class="btn-batch-del" onclick="batchDeleteDocs()" disabled>确认删除</button></div>`;
    }

    // ===== 文档列表 =====
    if (!docs.length) {
        html += `<div class="docs-empty-msg">🔍 没有匹配的文档，尝试调整筛选条件</div>`;
    } else {
        html += `<div class="docs-list">`;
        html += docs.map(d => {
            const cls = d.doc_status === '现行有效' ? 'green' : d.doc_status === '修订中' ? 'yellow' : 'red';
            const sn = d.standard_number || '未编号';
            const sname = d.standard_name || '未知标准';
            let row = '<div class="doc-row">';
            if (inBatch) {
                let checked;
                if (S._selectAll) {
                    checked = !(S._excludedIds && S._excludedIds.has(d.id));
                } else {
                    checked = S._checkedIds && S._checkedIds.has(d.id);
                }
                row += `<input type="checkbox" class="doc-checkbox" data-id="${d.id}" onchange="onCheckToggle(${d.id})" ${checked ? 'checked' : ''}>`;
            }
            row += `<span class="dot ${cls}"></span>`;
            row += `<span class="doc-info" title="[${sn}] ${sname}">`;
            row += `<span class="doc-sn">[${sn}]</span>`;
            row += `<span class="doc-name">${sname}</span>`;
            row += `<span class="doc-status-tag ${cls}">${d.doc_status || ''}</span>`;
            row += `</span>`;
            if (!inBatch) {
                row += `<button class="btn-edit-doc" onclick="event.stopPropagation();editDoc(${d.id})" title="编辑"><svg width="12" height="12" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z\"/></svg></button>`;
                row += `<button class="btn-view-doc" onclick="event.stopPropagation();window.open('/api/documents/${d.id}/file')" title="查看原文"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button>`;
                row += `<button class="btn-del-doc" onclick="event.stopPropagation();deleteDoc(${d.id})" title="删除文档"><svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M3 3L10 10M10 3L3 10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>`;
            }
            row += '</div>';
            return row;
        }).join('');
        html += `</div>`;
    }

    // ===== 分页栏 =====
    html += `<div class="docs-pagination">
        <button class="docs-page-btn" onclick="goPage(${S.docPage - 1})" ${S.docPage <= 1 ? 'disabled' : ''}>← 上一页</button>
        <span class="docs-page-info">第 ${S.docPage} / ${S.docTotalPages || 1} 页</span>
        <button class="docs-page-btn" onclick="goPage(${S.docPage + 1})" ${!S.docHasMore ? 'disabled' : ''}>下一页 →</button>
    </div>`;

    area.innerHTML = html;
}

function searchDocs() {
    const input = document.getElementById('docsSearchInput');
    S.docSearch = input ? input.value.trim() : '';
    loadUploadedDocs(1);
}

function clearDocSearch() {
    S.docSearch = '';
    const input = document.getElementById('docsSearchInput');
    if (input) input.value = '';
    S.docStatusFilter = '';
    loadUploadedDocs(1);
}

function filterByStatus(status) {
    S.docStatusFilter = status;
    loadUploadedDocs(1);
}

function goPage(n) {
    if (n < 1 || n > S.docTotalPages) return;
    loadUploadedDocs(n);
    // 滚动到列表顶部
    const area = document.getElementById('docsArea');
    if (area) area.scrollIntoView({ behavior: 'smooth' });
}

async function loadUploadedDocs(page) {
    page = page || S.docPage || 1;
    S.docPage = page;
    const params = new URLSearchParams();
    if (S.docSearch) params.set('keyword', S.docSearch);
    if (S.docStatusFilter) params.set('status', S.docStatusFilter);
    params.set('limit', S.docPerPage);
    params.set('offset', (page - 1) * S.docPerPage);

    try {
        const r = await fetch('/api/documents?' + params.toString());
        const data = await r.json();
        const docs = data.docs || data;
        const total = data.total || 0;
        S.docTotal = total;
        S.docTotalPages = Math.ceil(total / S.docPerPage);
        S.docHasMore = page < S.docTotalPages;
        _docsCache = docs;
        if (!S.batchMode) {
            resetBatchState();
        }
        renderDocsArea();
        if (S.batchMode) updateBatchCount();
    } catch (e) {}
}

async function loadDocs() {
    try {
        const r = await fetch('/api/documents?limit=200');
        const data = await r.json();
        const docs = Array.isArray(data) ? data : (data.docs || []);
        const sel = document.getElementById('gapSelect');
        if (sel) {
            sel.innerHTML = '<option value="">选择目标标准...</option>' +
                (docs.length ? docs.map(d => `<option value="${d.id}">[${d.standard_number}] ${d.standard_name} (${d.doc_status})</option>`).join('') : '');
        }
    } catch (e) {
        console.warn('loadDocs error:', e);
    }
}

const drop = document.getElementById('dropZone');
if (drop) {
    drop.addEventListener('dragover', e => { e.preventDefault(); drop.style.borderColor = 'var(--brand-gold)'; });
    drop.addEventListener('dragleave', () => { drop.style.borderColor = 'var(--border)'; });
    drop.addEventListener('drop', e => { e.preventDefault(); drop.style.borderColor = 'var(--border)'; onFiles(e.dataTransfer.files); });
}


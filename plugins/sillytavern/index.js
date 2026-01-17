/**
 * Recall Memory Plugin for SillyTavern
 * 
 * 为 SillyTavern 提供智能记忆管理功能。
 */

// 插件配置
const defaultSettings = {
    enabled: true,
    apiUrl: 'http://127.0.0.1:18888',
    autoInject: true,
    maxMemories: 10,
    injectPosition: 'before_system',  // before_system, after_system, before_chat
    showPanel: true,
    language: 'zh-CN'
};

// 插件状态
let pluginSettings = { ...defaultSettings };
let isConnected = false;
let currentCharacterId = null;

/**
 * 初始化插件
 */
jQuery(async () => {
    console.log('[Recall] 插件初始化...');
    
    // 等待 SillyTavern 完全加载
    const context = SillyTavern.getContext();
    
    // 加载设置
    loadSettings();
    
    // 创建UI
    createUI();
    
    // 注册事件监听
    registerEventHandlers(context);
    
    // 检查连接
    await checkConnection();
    
    console.log('[Recall] 插件初始化完成');
});

/**
 * 加载设置
 */
function loadSettings() {
    const saved = localStorage.getItem('recall_settings');
    if (saved) {
        try {
            pluginSettings = { ...defaultSettings, ...JSON.parse(saved) };
        } catch (e) {
            console.error('[Recall] 加载设置失败:', e);
        }
    }
}

/**
 * 保存设置
 */
function saveSettings() {
    localStorage.setItem('recall_settings', JSON.stringify(pluginSettings));
}

/**
 * 创建UI
 */
function createUI() {
    // 添加设置面板
    const settingsHtml = `
        <div id="recall-settings" class="recall-panel">
            <h4>🧠 Recall 记忆设置</h4>
            <div class="recall-setting-item">
                <label>
                    <input type="checkbox" id="recall-enabled" ${pluginSettings.enabled ? 'checked' : ''}>
                    启用记忆功能
                </label>
            </div>
            <div class="recall-setting-item">
                <label>API 地址:</label>
                <input type="text" id="recall-api-url" value="${pluginSettings.apiUrl}" placeholder="http://127.0.0.1:8000">
            </div>
            <div class="recall-setting-item">
                <label>
                    <input type="checkbox" id="recall-auto-inject" ${pluginSettings.autoInject ? 'checked' : ''}>
                    自动注入记忆到上下文
                </label>
            </div>
            <div class="recall-setting-item">
                <label>最大记忆数:</label>
                <input type="number" id="recall-max-memories" value="${pluginSettings.maxMemories}" min="1" max="50">
            </div>
            <div class="recall-setting-item">
                <button id="recall-test-connection" class="recall-btn">测试连接</button>
                <span id="recall-connection-status" class="recall-status"></span>
            </div>
            <div class="recall-setting-item">
                <button id="recall-save-settings" class="recall-btn recall-btn-primary">保存设置</button>
            </div>
        </div>
    `;
    
    // 添加记忆面板
    const memoryPanelHtml = `
        <div id="recall-memory-panel" class="recall-panel" style="display: ${pluginSettings.showPanel ? 'block' : 'none'}">
            <h4>📚 记忆</h4>
            <div id="recall-memory-list" class="recall-memory-list">
                <p class="recall-empty">暂无记忆</p>
            </div>
            <div class="recall-actions">
                <input type="text" id="recall-search-input" placeholder="搜索记忆...">
                <button id="recall-search-btn" class="recall-btn">搜索</button>
            </div>
            <div class="recall-actions">
                <input type="text" id="recall-add-input" placeholder="添加新记忆...">
                <button id="recall-add-btn" class="recall-btn recall-btn-primary">添加</button>
            </div>
        </div>
    `;
    
    // 添加伏笔面板
    const foreshadowingPanelHtml = `
        <div id="recall-foreshadowing-panel" class="recall-panel">
            <h4>🎭 伏笔</h4>
            <div id="recall-foreshadowing-list" class="recall-foreshadowing-list">
                <p class="recall-empty">暂无伏笔</p>
            </div>
            <div class="recall-actions">
                <input type="text" id="recall-foreshadowing-input" placeholder="埋下新伏笔...">
                <button id="recall-foreshadowing-btn" class="recall-btn">埋下</button>
            </div>
        </div>
    `;
    
    // 插入到页面
    const extensionContainer = document.getElementById('extensions_settings');
    if (extensionContainer) {
        extensionContainer.insertAdjacentHTML('beforeend', settingsHtml);
    }
    
    // 插入侧边栏面板
    const sidebar = document.getElementById('right-nav-panel');
    if (sidebar) {
        sidebar.insertAdjacentHTML('beforeend', memoryPanelHtml + foreshadowingPanelHtml);
    }
    
    // 绑定事件
    document.getElementById('recall-save-settings')?.addEventListener('click', onSaveSettings);
    document.getElementById('recall-test-connection')?.addEventListener('click', onTestConnection);
    document.getElementById('recall-search-btn')?.addEventListener('click', onSearch);
    document.getElementById('recall-add-btn')?.addEventListener('click', onAddMemory);
    document.getElementById('recall-foreshadowing-btn')?.addEventListener('click', onPlantForeshadowing);
}

/**
 * 注册事件处理器
 */
function registerEventHandlers(context) {
    const { eventSource, event_types } = context;
    
    if (eventSource && event_types) {
        // 监听用户消息发送
        eventSource.on(event_types.MESSAGE_SENT, onMessageSent);
        
        // 监听AI响应
        eventSource.on(event_types.MESSAGE_RECEIVED, onMessageReceived);
        
        // 监听聊天切换（角色/群组切换时触发）
        eventSource.on(event_types.CHAT_CHANGED, onChatChanged);
        
        // 监听生成前 - 用于注入记忆上下文
        eventSource.on(event_types.GENERATION_AFTER_COMMANDS, onBeforeGeneration);
        
        console.log('[Recall] 事件监听器已注册');
    } else {
        console.warn('[Recall] SillyTavern 事件系统不可用');
    }
}

/**
 * 检查API连接
 */
async function checkConnection() {
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/health`);
        if (response.ok) {
            isConnected = true;
            updateConnectionStatus(true);
            console.log('[Recall] API 连接成功');
        } else {
            throw new Error('API 响应异常');
        }
    } catch (e) {
        isConnected = false;
        updateConnectionStatus(false);
        console.warn('[Recall] API 连接失败:', e.message);
    }
}

/**
 * 更新连接状态显示
 */
function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('recall-connection-status');
    if (statusEl) {
        statusEl.textContent = connected ? '✓ 已连接' : '✗ 未连接';
        statusEl.className = `recall-status ${connected ? 'recall-status-ok' : 'recall-status-error'}`;
    }
}

/**
 * 保存设置
 */
function onSaveSettings() {
    pluginSettings.enabled = document.getElementById('recall-enabled')?.checked ?? true;
    pluginSettings.apiUrl = document.getElementById('recall-api-url')?.value ?? defaultSettings.apiUrl;
    pluginSettings.autoInject = document.getElementById('recall-auto-inject')?.checked ?? true;
    pluginSettings.maxMemories = parseInt(document.getElementById('recall-max-memories')?.value) || 10;
    
    saveSettings();
    checkConnection();
    
    alert('设置已保存');
}

/**
 * 测试连接
 */
async function onTestConnection() {
    await checkConnection();
    alert(isConnected ? '连接成功！' : '连接失败，请检查 API 地址');
}

/**
 * 搜索记忆
 */
async function onSearch() {
    const query = document.getElementById('recall-search-input')?.value;
    if (!query || !isConnected) return;
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/memories/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                user_id: currentCharacterId || 'default',
                top_k: pluginSettings.maxMemories
            })
        });
        
        const results = await response.json();
        displayMemories(results);
    } catch (e) {
        console.error('[Recall] 搜索失败:', e);
    }
}

/**
 * 添加记忆
 */
async function onAddMemory() {
    const content = document.getElementById('recall-add-input')?.value;
    if (!content || !isConnected) return;
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/memories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content,
                user_id: currentCharacterId || 'default'
            })
        });
        
        const result = await response.json();
        if (result.success) {
            document.getElementById('recall-add-input').value = '';
            loadMemories();
        }
    } catch (e) {
        console.error('[Recall] 添加记忆失败:', e);
    }
}

/**
 * 埋下伏笔
 */
async function onPlantForeshadowing() {
    const content = document.getElementById('recall-foreshadowing-input')?.value;
    if (!content || !isConnected) return;
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content,
                importance: 0.5
            })
        });
        
        const result = await response.json();
        if (result.id) {
            document.getElementById('recall-foreshadowing-input').value = '';
            loadForeshadowings();
        }
    } catch (e) {
        console.error('[Recall] 埋下伏笔失败:', e);
    }
}

/**
 * 消息发送时
 */
async function onMessageSent(messageIndex) {
    if (!pluginSettings.enabled || !isConnected) return;
    
    try {
        const context = SillyTavern.getContext();
        const chat = context.chat;
        const message = chat[messageIndex];
        
        if (!message || !message.mes) return;
        
        // 保存用户消息作为记忆
        await fetch(`${pluginSettings.apiUrl}/v1/memories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: message.mes,
                user_id: currentCharacterId || 'default',
                metadata: { 
                    role: 'user', 
                    source: 'sillytavern',
                    timestamp: Date.now()
                }
            })
        });
        console.log('[Recall] 已保存用户消息');
    } catch (e) {
        console.warn('[Recall] 保存用户消息失败:', e);
    }
}

/**
 * 消息接收时
 */
async function onMessageReceived(messageIndex) {
    if (!pluginSettings.enabled || !isConnected) return;
    
    try {
        const context = SillyTavern.getContext();
        const chat = context.chat;
        const message = chat[messageIndex];
        
        if (!message || !message.mes) return;
        
        // 保存AI响应作为记忆
        await fetch(`${pluginSettings.apiUrl}/v1/memories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: message.mes,
                user_id: currentCharacterId || 'default',
                metadata: { 
                    role: 'assistant', 
                    source: 'sillytavern',
                    character: message.name || 'AI',
                    timestamp: Date.now()
                }
            })
        });
        console.log('[Recall] 已保存AI响应');
    } catch (e) {
        console.warn('[Recall] 保存AI响应失败:', e);
    }
}

/**
 * 聊天切换时（角色/群组切换）
 */
function onChatChanged() {
    // 获取当前角色信息
    const context = SillyTavern.getContext();
    const characterId = context.characterId;
    const character = characterId !== undefined ? context.characters[characterId] : null;
    
    if (character) {
        currentCharacterId = character.name || `char_${characterId}`;
        console.log(`[Recall] 切换到角色: ${currentCharacterId}`);
    } else if (context.groupId) {
        currentCharacterId = `group_${context.groupId}`;
        console.log(`[Recall] 切换到群组: ${currentCharacterId}`);
    } else {
        currentCharacterId = 'default';
    }
    
    loadMemories();
    loadForeshadowings();
}

/**
 * 生成前 - 注入记忆上下文
 */
async function onBeforeGeneration() {
    if (!pluginSettings.enabled || !pluginSettings.autoInject || !isConnected) {
        return;
    }
    
    try {
        const context = SillyTavern.getContext();
        const chat = context.chat;
        
        if (!chat || chat.length === 0) return;
        
        // 获取最后几条消息作为查询
        const recentMessages = chat.slice(-3).map(m => m.mes).join(' ');
        const memoryContext = await getMemoryContext(recentMessages);
        
        if (memoryContext) {
            // 通过扩展设置注入记忆
            console.log('[Recall] 已准备记忆上下文，长度:', memoryContext.length);
        }
    } catch (e) {
        console.warn('[Recall] 注入记忆上下文失败:', e);
    }
}

/**
 * 加载记忆列表
 */
async function loadMemories() {
    if (!isConnected) return;
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${encodeURIComponent(currentCharacterId || 'default')}&limit=${pluginSettings.maxMemories}`
        );
        const data = await response.json();
        displayMemories(data.memories || []);
    } catch (e) {
        console.error('[Recall] 加载记忆失败:', e);
    }
}

/**
 * 显示记忆列表
 */
function displayMemories(memories) {
    const listEl = document.getElementById('recall-memory-list');
    if (!listEl) return;
    
    if (!memories || memories.length === 0) {
        listEl.innerHTML = '<p class="recall-empty">暂无记忆</p>';
        return;
    }
    
    listEl.innerHTML = memories.map(m => `
        <div class="recall-memory-item" data-id="${m.id}">
            <p class="recall-memory-content">${escapeHtml(m.content || m.memory || '')}</p>
            <div class="recall-memory-meta">
                ${m.score ? `<span class="recall-score">相关度: ${(m.score * 100).toFixed(0)}%</span>` : ''}
                <button class="recall-btn-small recall-delete-memory" data-id="${m.id}">删除</button>
            </div>
        </div>
    `).join('');
    
    // 绑定删除事件
    listEl.querySelectorAll('.recall-delete-memory').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.target.dataset.id;
            await deleteMemory(id);
        });
    });
}

/**
 * 删除记忆
 */
async function deleteMemory(memoryId) {
    try {
        await fetch(`${pluginSettings.apiUrl}/v1/memories/${memoryId}?user_id=${encodeURIComponent(currentCharacterId || 'default')}`, {
            method: 'DELETE'
        });
        loadMemories();
    } catch (e) {
        console.error('[Recall] 删除记忆失败:', e);
    }
}

/**
 * 加载伏笔列表
 */
async function loadForeshadowings() {
    if (!isConnected) return;
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing`);
        const data = await response.json();
        displayForeshadowings(data);
    } catch (e) {
        console.error('[Recall] 加载伏笔失败:', e);
    }
}

/**
 * 显示伏笔列表
 */
function displayForeshadowings(foreshadowings) {
    const listEl = document.getElementById('recall-foreshadowing-list');
    if (!listEl) return;
    
    if (!foreshadowings || foreshadowings.length === 0) {
        listEl.innerHTML = '<p class="recall-empty">暂无伏笔</p>';
        return;
    }
    
    listEl.innerHTML = foreshadowings.map(f => `
        <div class="recall-foreshadowing-item" data-id="${f.id}">
            <span class="recall-foreshadowing-status">${f.status === 'planted' ? '🌱' : '🌿'}</span>
            <p class="recall-foreshadowing-content">${escapeHtml(f.content)}</p>
            <div class="recall-foreshadowing-meta">
                <span>重要性: ${(f.importance * 100).toFixed(0)}%</span>
                <button class="recall-btn-small recall-resolve-foreshadowing" data-id="${f.id}">解决</button>
            </div>
        </div>
    `).join('');
}

/**
 * 获取要注入的记忆上下文
 */
async function getMemoryContext(query) {
    if (!pluginSettings.enabled || !pluginSettings.autoInject || !isConnected) {
        return '';
    }
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/context`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                user_id: currentCharacterId || 'default',
                max_tokens: 1000,
                include_recent: 3
            })
        });
        
        const data = await response.json();
        return data.context || '';
    } catch (e) {
        console.warn('[Recall] 获取记忆上下文失败:', e);
        return '';
    }
}

/**
 * HTML 转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 导出供 SillyTavern 使用
window.RecallPlugin = {
    getMemoryContext,
    loadMemories,
    loadForeshadowings,
    isConnected: () => isConnected,
    settings: pluginSettings
};

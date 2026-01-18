/**
 * Recall Memory Plugin for SillyTavern
 * 
 * 为 SillyTavern 提供智能记忆管理功能。
 * 
 * 安全说明：
 * - 此插件完全独立运行，不修改 SillyTavern 核心代码
 * - 所有错误都被捕获，不会影响 ST 正常运行
 * - 删除 recall-memory 文件夹即可完全卸载
 */

// 使用 IIFE 避免污染全局命名空间
(function() {
    'use strict';
    
    // 插件配置
    const defaultSettings = {
        enabled: true,
        apiUrl: 'http://127.0.0.1:18888',
        autoInject: true,
        maxMemories: 10,
        injectPosition: 'before_system',
        showPanel: true,
        language: 'zh-CN',
        filterThinking: true,  // 过滤AI思考过程
        previewLength: 200,    // 记忆预览字数
        autoChunkLongText: true,  // 自动分段长文本
        chunkSize: 2000        // 分段大小（字符数）
    };
    
    /**
     * 过滤掉AI回复中的思考过程
     * 支持多种常见格式：<thinking>, <thought>, <reasoning>, 【思考】等
     */
    function filterThinkingContent(text) {
        if (!text) return text;
        
        let filtered = text;
        
        // 过滤 XML 风格的思考标签
        const xmlPatterns = [
            /<thinking>[\s\S]*?<\/thinking>/gi,
            /<thought>[\s\S]*?<\/thought>/gi,
            /<reasoning>[\s\S]*?<\/reasoning>/gi,
            /<think>[\s\S]*?<\/think>/gi,
            /<reflection>[\s\S]*?<\/reflection>/gi,
            /<inner_thought>[\s\S]*?<\/inner_thought>/gi,
            /<internal>[\s\S]*?<\/internal>/gi,
        ];
        
        // 过滤中文风格的思考标记
        const chinesePatterns = [
            /【思考】[\s\S]*?【\/思考】/g,
            /【思考过程】[\s\S]*?【\/思考过程】/g,
            /\[思考\][\s\S]*?\[\/思考\]/g,
            /（思考：[\s\S]*?）/g,
            /\(思考：[\s\S]*?\)/g,
        ];
        
        // 过滤代码块中的思考（某些模型会这样输出）
        const codeBlockPatterns = [
            /```thinking[\s\S]*?```/gi,
            /```thought[\s\S]*?```/gi,
        ];
        
        const allPatterns = [...xmlPatterns, ...chinesePatterns, ...codeBlockPatterns];
        
        for (const pattern of allPatterns) {
            filtered = filtered.replace(pattern, '');
        }
        
        // 清理多余的空行
        filtered = filtered.replace(/\n{3,}/g, '\n\n').trim();
        
        return filtered;
    }

    // 插件状态
    let pluginSettings = { ...defaultSettings };
    let isConnected = false;
    let currentCharacterId = null;
    let isInitialized = false;

    /**
     * 安全执行函数 - 捕获所有错误，不影响 ST
     */
    function safeExecute(fn, errorMsg = 'Recall 插件错误') {
        return async function(...args) {
            try {
                return await fn.apply(this, args);
            } catch (e) {
                console.warn(`[Recall] ${errorMsg}:`, e.message);
                return null;
            }
        };
    }

    /**
     * 初始化插件
     */
    jQuery(async () => {
        try {
            console.log('[Recall] 插件初始化...');
            
            // 检查 SillyTavern 是否就绪
            if (typeof SillyTavern === 'undefined' || !SillyTavern.getContext) {
                console.warn('[Recall] SillyTavern 未就绪，插件将不会加载');
                return;
            }
            
            const context = SillyTavern.getContext();
            
            // 加载设置
            loadSettings();
            
            // 创建UI（安全模式）
            safeCreateUI();
            
            // 注册事件监听（安全模式）
            safeRegisterEventHandlers(context);
            
            // 检查连接（不阻塞）
            checkConnection().catch(() => {});
            
            isInitialized = true;
            console.log('[Recall] 插件初始化完成');
        } catch (e) {
            console.error('[Recall] 插件初始化失败，但不影响 SillyTavern:', e.message);
        }
    });

/**
 * 加载设置
 */
function loadSettings() {
    try {
        const saved = localStorage.getItem('recall_settings');
        if (saved) {
            pluginSettings = { ...defaultSettings, ...JSON.parse(saved) };
        }
    } catch (e) {
        console.warn('[Recall] 加载设置失败，使用默认值:', e.message);
        pluginSettings = { ...defaultSettings };
    }
}

/**
 * 保存设置
 */
function saveSettings() {
    try {
        localStorage.setItem('recall_settings', JSON.stringify(pluginSettings));
    } catch (e) {
        console.warn('[Recall] 保存设置失败:', e.message);
    }
}

/**
 * 安全创建 UI
 */
function safeCreateUI() {
    try {
        createUI();
    } catch (e) {
        console.warn('[Recall] 创建 UI 失败，插件功能受限:', e.message);
    }
}

/**
 * 创建UI - 使用 SillyTavern 标准折叠面板样式
 */
function createUI() {
    // 主扩展面板 HTML（折叠式）
    const extensionHtml = `
        <div id="recall-extension" class="inline-drawer">
            <div class="inline-drawer-toggle inline-drawer-header">
                <b>🧠 Recall 记忆系统</b>
                <div class="inline-drawer-icon fa-solid fa-circle-chevron-down"></div>
            </div>
            <div class="inline-drawer-content">
                <!-- 连接状态栏 -->
                <div id="recall-status-bar" class="recall-status-bar">
                    <span id="recall-connection-indicator" class="recall-indicator recall-indicator-disconnected"></span>
                    <span id="recall-connection-text">未连接</span>
                    <span id="recall-character-badge" class="recall-character-badge" style="display:none"></span>
                </div>
                
                <!-- 标签页导航 -->
                <div class="recall-tabs">
                    <button class="recall-tab active" data-tab="memories">📚 记忆</button>
                    <button class="recall-tab" data-tab="foreshadowing">🎭 伏笔</button>
                    <button class="recall-tab" data-tab="settings">⚙️ 设置</button>
                </div>
                
                <!-- 记忆标签页 -->
                <div id="recall-tab-memories" class="recall-tab-content active">
                    <div class="recall-stats-row">
                        <span>📊 记忆数: <strong id="recall-memory-count">0</strong></span>
                        <div class="recall-stats-actions">
                            <button id="recall-refresh-btn" class="recall-icon-btn" title="刷新">🔄</button>
                        </div>
                    </div>
                    
                    <div class="recall-search-bar">
                        <input type="text" id="recall-search-input" placeholder="🔍 搜索记忆..." class="text_pole">
                        <button id="recall-search-btn" class="menu_button" title="搜索">
                            <i class="fa-solid fa-magnifying-glass"></i>
                        </button>
                    </div>
                    
                    <div id="recall-memory-list" class="recall-memory-list">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">📭</div>
                            <p>暂无记忆</p>
                            <small>对话时会自动记录</small>
                        </div>
                    </div>
                    
                    <div id="recall-load-more-container" class="recall-load-more" style="display:none;">
                        <button id="recall-load-more-btn" class="menu_button">加载更多...</button>
                    </div>
                    
                    <div class="recall-add-bar">
                        <input type="text" id="recall-add-input" placeholder="✏️ 手动添加记忆..." class="text_pole">
                        <button id="recall-add-btn" class="menu_button menu_button_icon" title="添加">
                            <i class="fa-solid fa-plus"></i>
                        </button>
                    </div>
                    
                    <div class="recall-danger-section">
                        <button id="recall-clear-all-btn" class="menu_button menu_button_icon recall-danger-btn">
                            <i class="fa-solid fa-trash"></i>
                            <span>清空当前角色记忆</span>
                        </button>
                    </div>
                </div>
                
                <!-- 伏笔标签页 -->
                <div id="recall-tab-foreshadowing" class="recall-tab-content">
                    <div id="recall-foreshadowing-list" class="recall-foreshadowing-list">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">🎭</div>
                            <p>暂无伏笔</p>
                            <small>埋下故事线索</small>
                        </div>
                    </div>
                    
                    <div class="recall-add-bar">
                        <input type="text" id="recall-foreshadowing-input" placeholder="🎭 埋下新伏笔..." class="text_pole">
                        <button id="recall-foreshadowing-btn" class="menu_button menu_button_icon" title="埋下">
                            <i class="fa-solid fa-seedling"></i>
                        </button>
                    </div>
                </div>
                
                <!-- 设置标签页 -->
                <div id="recall-tab-settings" class="recall-tab-content">
                    <div class="recall-setting-group">
                        <label class="recall-setting-label">
                            <input type="checkbox" id="recall-enabled" ${pluginSettings.enabled ? 'checked' : ''}>
                            <span>启用记忆功能</span>
                        </label>
                    </div>
                    
                    <div class="recall-setting-group">
                        <label class="recall-setting-title">API 地址</label>
                        <input type="text" id="recall-api-url" value="${pluginSettings.apiUrl}" 
                               placeholder="http://127.0.0.1:18888" class="text_pole">
                    </div>
                    
                    <div class="recall-setting-group">
                        <label class="recall-setting-label">
                            <input type="checkbox" id="recall-auto-inject" ${pluginSettings.autoInject ? 'checked' : ''}>
                            <span>自动注入记忆到上下文</span>
                        </label>
                    </div>
                    
                    <div class="recall-setting-group">
                        <label class="recall-setting-label">
                            <input type="checkbox" id="recall-filter-thinking" ${pluginSettings.filterThinking ? 'checked' : ''}>
                            <span>过滤AI思考过程</span>
                        </label>
                        <div class="recall-setting-hint">只保存AI的最终回复，不保存&lt;thinking&gt;等思考内容</div>
                    </div>
                    
                    <div class="recall-setting-group">
                        <label class="recall-setting-label">
                            <input type="checkbox" id="recall-auto-chunk" ${pluginSettings.autoChunkLongText ? 'checked' : ''}>
                            <span>长文本自动分段</span>
                        </label>
                        <div class="recall-setting-hint">超长回复(>${pluginSettings.chunkSize || 2000}字)自动分成多条记忆保存</div>
                    </div>
                    
                    <div class="recall-setting-group">
                        <label class="recall-setting-title">分段大小 (字符数)</label>
                        <input type="number" id="recall-chunk-size" value="${pluginSettings.chunkSize || 2000}" 
                               min="500" max="10000" step="500" class="text_pole">
                    </div>
                    
                    <div class="recall-setting-group">
                        <label class="recall-setting-title">预览字数</label>
                        <input type="number" id="recall-preview-length" value="${pluginSettings.previewLength || 200}" 
                               min="50" max="500" step="50" class="text_pole">
                        <div class="recall-setting-hint">记忆列表中显示的文字数量，可展开查看全文</div>
                    </div>
                    
                    <div class="recall-setting-group">
                        <label class="recall-setting-title">最大注入记忆数</label>
                        <input type="number" id="recall-max-memories" value="${pluginSettings.maxMemories}" 
                               min="1" max="50" class="text_pole">
                    </div>
                    
                    <div class="recall-setting-actions">
                        <button id="recall-test-connection" class="menu_button">
                            <i class="fa-solid fa-plug"></i>
                            <span>测试连接</span>
                        </button>
                        <button id="recall-save-settings" class="menu_button menu_button_icon">
                            <i class="fa-solid fa-save"></i>
                            <span>保存设置</span>
                        </button>
                    </div>
                    
                    <div class="recall-info-box">
                        <div class="recall-info-title">💡 使用提示</div>
                        <ul>
                            <li>确保 Recall 服务已启动</li>
                            <li>切换角色会自动加载对应记忆</li>
                            <li>记忆会随对话自动积累</li>
                            <li>长文本会自动分段，确保完整分析</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // 插入到扩展设置区域
    const extensionContainer = document.getElementById('extensions_settings');
    if (extensionContainer) {
        extensionContainer.insertAdjacentHTML('beforeend', extensionHtml);
    }
    
    // 绑定标签页切换
    document.querySelectorAll('.recall-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            
            // 切换标签按钮状态
            document.querySelectorAll('.recall-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // 切换内容面板
            document.querySelectorAll('.recall-tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`recall-tab-${tabName}`)?.classList.add('active');
        });
    });
    
    // 绑定折叠面板点击 - 只切换 open 类，图标旋转由 CSS 控制
    const drawerToggle = document.querySelector('#recall-extension .inline-drawer-toggle');
    if (drawerToggle) {
        drawerToggle.addEventListener('click', () => {
            const drawer = document.getElementById('recall-extension');
            drawer?.classList.toggle('open');
        });
    }
    
    // 绑定事件
    document.getElementById('recall-save-settings')?.addEventListener('click', safeExecute(onSaveSettings, '保存设置失败'));
    document.getElementById('recall-test-connection')?.addEventListener('click', safeExecute(onTestConnection, '测试连接失败'));
    document.getElementById('recall-search-btn')?.addEventListener('click', safeExecute(onSearch, '搜索失败'));
    document.getElementById('recall-add-btn')?.addEventListener('click', safeExecute(onAddMemory, '添加记忆失败'));
    document.getElementById('recall-foreshadowing-btn')?.addEventListener('click', safeExecute(onPlantForeshadowing, '埋下伏笔失败'));
    document.getElementById('recall-clear-all-btn')?.addEventListener('click', safeExecute(onClearAllMemories, '清空记忆失败'));
    document.getElementById('recall-refresh-btn')?.addEventListener('click', safeExecute(loadMemories, '刷新失败'));
    document.getElementById('recall-load-more-btn')?.addEventListener('click', safeExecute(onLoadMoreMemories, '加载更多失败'));
    
    // 回车键快捷搜索
    document.getElementById('recall-search-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') onSearch();
    });
    document.getElementById('recall-add-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') onAddMemory();
    });
    document.getElementById('recall-foreshadowing-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') onPlantForeshadowing();
    });
}

/**
 * 安全注册事件处理器
 */
function safeRegisterEventHandlers(context) {
    try {
        registerEventHandlers(context);
    } catch (e) {
        console.warn('[Recall] 注册事件失败，自动记忆功能不可用:', e.message);
    }
}

/**
 * 注册事件处理器
 */
function registerEventHandlers(context) {
    const { eventSource, event_types } = context;
    
    if (eventSource && event_types) {
        // 使用安全包装的事件处理器
        eventSource.on(event_types.MESSAGE_SENT, safeExecute(onMessageSent, '处理发送消息失败'));
        eventSource.on(event_types.MESSAGE_RECEIVED, safeExecute(onMessageReceived, '处理接收消息失败'));
        eventSource.on(event_types.CHAT_CHANGED, safeExecute(onChatChanged, '处理聊天切换失败'));
        eventSource.on(event_types.GENERATION_AFTER_COMMANDS, safeExecute(onBeforeGeneration, '准备记忆上下文失败'));
        
        console.log('[Recall] 事件监听器已注册');
        
        // 初始化时立即检测当前角色并加载记忆
        setTimeout(() => {
            initializeCurrentCharacter();
        }, 500);
    } else {
        console.warn('[Recall] SillyTavern 事件系统不可用，自动记忆功能将不可用');
    }
}

/**
 * 初始化当前角色 - 页面加载/刷新时调用
 */
function initializeCurrentCharacter() {
    try {
        const context = SillyTavern.getContext();
        const characterId = context.characterId;
        const character = characterId !== undefined ? context.characters[characterId] : null;
        
        if (character) {
            currentCharacterId = character.name || `char_${characterId}`;
            console.log(`[Recall] 初始化角色: ${currentCharacterId}`);
        } else if (context.groupId) {
            currentCharacterId = `group_${context.groupId}`;
            console.log(`[Recall] 初始化群组: ${currentCharacterId}`);
        } else {
            // 尝试从 chat 中获取
            const chat = context.chat;
            if (chat && chat.length > 0) {
                const firstNonUserMsg = chat.find(m => !m.is_user && !m.is_system);
                if (firstNonUserMsg && firstNonUserMsg.name) {
                    currentCharacterId = firstNonUserMsg.name;
                    console.log(`[Recall] 从聊天记录识别角色: ${currentCharacterId}`);
                }
            }
            
            if (!currentCharacterId) {
                currentCharacterId = 'default';
                console.log('[Recall] 未检测到角色，使用 default');
            }
        }
        
        // 更新UI显示
        updateCharacterBadge();
        
        // 加载该角色的记忆
        if (isConnected) {
            loadMemories();
            loadForeshadowings();
        }
    } catch (e) {
        console.warn('[Recall] 初始化角色失败:', e);
        currentCharacterId = 'default';
    }
}

/**
 * 检查API连接
 */
async function checkConnection() {
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/health`);
        if (response.ok) {
            const wasConnected = isConnected;
            isConnected = true;
            updateConnectionStatus(true);
            console.log('[Recall] API 连接成功');
            
            // 如果是首次连接成功，加载记忆
            if (!wasConnected && currentCharacterId) {
                loadMemories();
                loadForeshadowings();
            }
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
    const indicator = document.getElementById('recall-connection-indicator');
    const text = document.getElementById('recall-connection-text');
    
    if (indicator) {
        indicator.className = `recall-indicator ${connected ? 'recall-indicator-connected' : 'recall-indicator-disconnected'}`;
    }
    if (text) {
        text.textContent = connected ? '已连接' : '未连接';
    }
}

/**
 * 保存设置
 */
function onSaveSettings() {
    pluginSettings.enabled = document.getElementById('recall-enabled')?.checked ?? true;
    pluginSettings.apiUrl = document.getElementById('recall-api-url')?.value ?? defaultSettings.apiUrl;
    pluginSettings.autoInject = document.getElementById('recall-auto-inject')?.checked ?? true;
    pluginSettings.filterThinking = document.getElementById('recall-filter-thinking')?.checked ?? true;
    pluginSettings.autoChunkLongText = document.getElementById('recall-auto-chunk')?.checked ?? true;
    pluginSettings.chunkSize = parseInt(document.getElementById('recall-chunk-size')?.value) || 2000;
    pluginSettings.previewLength = parseInt(document.getElementById('recall-preview-length')?.value) || 200;
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
                user_id: currentCharacterId || 'default',
                importance: 0.5
            })
        });
        
        const result = await response.json();
        if (result.id) {
            document.getElementById('recall-foreshadowing-input').value = '';
            loadForeshadowings();
            console.log(`[Recall] 伏笔已埋下 (角色: ${currentCharacterId})`);
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
 * 智能分段长文本
 * 在段落、句号处分割，避免断在句子中间
 */
function chunkLongText(text, maxSize = 2000) {
    if (text.length <= maxSize) return [text];
    
    const chunks = [];
    let remaining = text;
    
    while (remaining.length > 0) {
        if (remaining.length <= maxSize) {
            chunks.push(remaining);
            break;
        }
        
        // 查找分割点（优先级：段落 > 句号 > 逗号 > 强制）
        let splitPoint = maxSize;
        
        // 1. 尝试在段落处分割
        const paragraphBreak = remaining.lastIndexOf('\n\n', maxSize);
        if (paragraphBreak > maxSize * 0.5) {
            splitPoint = paragraphBreak + 2;
        } else {
            // 2. 尝试在句号处分割
            const sentenceEnd = Math.max(
                remaining.lastIndexOf('。', maxSize),
                remaining.lastIndexOf('！', maxSize),
                remaining.lastIndexOf('？', maxSize),
                remaining.lastIndexOf('. ', maxSize),
                remaining.lastIndexOf('! ', maxSize),
                remaining.lastIndexOf('? ', maxSize)
            );
            if (sentenceEnd > maxSize * 0.5) {
                splitPoint = sentenceEnd + 1;
            } else {
                // 3. 尝试在逗号处分割
                const commaBreak = Math.max(
                    remaining.lastIndexOf('，', maxSize),
                    remaining.lastIndexOf(', ', maxSize)
                );
                if (commaBreak > maxSize * 0.7) {
                    splitPoint = commaBreak + 1;
                }
                // 4. 否则强制在 maxSize 处分割
            }
        }
        
        chunks.push(remaining.substring(0, splitPoint).trim());
        remaining = remaining.substring(splitPoint).trim();
    }
    
    return chunks;
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
        
        // 过滤掉思考过程，只保留最终结果
        let contentToSave = message.mes;
        if (pluginSettings.filterThinking) {
            contentToSave = filterThinkingContent(message.mes);
            if (contentToSave !== message.mes) {
                console.log('[Recall] 已过滤AI思考过程');
            }
        }
        
        // 如果过滤后内容为空，则跳过保存
        if (!contentToSave || contentToSave.trim().length === 0) {
            console.log('[Recall] 过滤后内容为空，跳过保存');
            return;
        }
        
        // 长文本分段处理
        const chunkSize = pluginSettings.chunkSize || 2000;
        const shouldChunk = pluginSettings.autoChunkLongText && contentToSave.length > chunkSize;
        const chunks = shouldChunk ? chunkLongText(contentToSave, chunkSize) : [contentToSave];
        
        if (chunks.length > 1) {
            console.log(`[Recall] 长文本(${contentToSave.length}字)分成${chunks.length}段保存`);
        }
        
        // 保存所有分段
        const timestamp = Date.now();
        for (let i = 0; i < chunks.length; i++) {
            const chunk = chunks[i];
            const isMultiPart = chunks.length > 1;
            
            await fetch(`${pluginSettings.apiUrl}/v1/memories`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content: chunk,
                    user_id: currentCharacterId || 'default',
                    metadata: { 
                        role: 'assistant', 
                        source: 'sillytavern',
                        character: message.name || 'AI',
                        timestamp: timestamp,
                        // 分段信息
                        ...(isMultiPart && {
                            chunk_index: i + 1,
                            chunk_total: chunks.length,
                            original_length: contentToSave.length
                        })
                    }
                })
            });
        }
        
        console.log(`[Recall] 已保存AI响应 (${chunks.length}段, 共${contentToSave.length}字)`);
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
    
    // 重置分页状态
    currentMemoryOffset = 0;
    
    try {
        // 获取记忆列表
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${encodeURIComponent(currentCharacterId || 'default')}&limit=${MEMORIES_PER_PAGE}`
        );
        const data = await response.json();
        
        // 更新统计信息
        updateStats(data.count || (data.memories ? data.memories.length : 0));
        
        // 更新角色名显示
        updateCharacterBadge();
        
        // 显示记忆
        displayMemories(data.memories || []);
        
        // 检查是否有更多
        hasMoreMemories = data.memories && data.memories.length >= MEMORIES_PER_PAGE;
        updateLoadMoreButton();
        
    } catch (e) {
        console.error('[Recall] 加载记忆失败:', e);
    }
}

/**
 * 更新统计信息
 */
function updateStats(count) {
    const countEl = document.getElementById('recall-memory-count');
    if (countEl) {
        countEl.textContent = count;
    }
}

/**
 * 更新角色名徽章
 */
function updateCharacterBadge() {
    const badgeEl = document.getElementById('recall-character-badge');
    if (badgeEl && currentCharacterId && currentCharacterId !== 'default') {
        badgeEl.textContent = `👤 ${currentCharacterId}`;
        badgeEl.style.display = 'inline-block';
    } else if (badgeEl) {
        badgeEl.style.display = 'none';
    }
}

/**
 * 显示记忆列表
 */
function displayMemories(memories) {
    const listEl = document.getElementById('recall-memory-list');
    if (!listEl) return;
    
    if (!memories || memories.length === 0) {
        listEl.innerHTML = `
            <div class="recall-empty-state">
                <div class="recall-empty-icon">📭</div>
                <p>暂无记忆</p>
                <small>对话时会自动记录</small>
            </div>
        `;
        return;
    }
    
    listEl.innerHTML = memories.map(m => createMemoryItemHtml(m)).join('');
    
    // 绑定删除事件
    listEl.querySelectorAll('.recall-delete-memory').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const button = e.currentTarget;
            const id = button.dataset.id;
            if (id && confirm('确定删除这条记忆吗？')) {
                await deleteMemory(id);
            }
        });
    });
    
    // 绑定展开/收起事件
    listEl.querySelectorAll('.recall-expand-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            // 直接从按钮向上查找父元素，而不是用 data-id 选择器
            const item = btn.closest('.recall-memory-item');
            if (!item) return;
            
            const isExpanded = item.dataset.expanded === 'true';
            const preview = item.querySelector('.recall-memory-preview');
            const full = item.querySelector('.recall-memory-full');
            
            if (isExpanded) {
                // 收起
                preview.style.display = '';
                if (full) full.style.display = 'none';
                btn.textContent = '📖 展开全文';
                item.dataset.expanded = 'false';
                item.classList.remove('expanded');
            } else {
                // 展开
                preview.style.display = 'none';
                if (full) full.style.display = '';
                btn.textContent = '📕 收起';
                item.dataset.expanded = 'true';
                item.classList.add('expanded');
            }
        });
    });
}

/**
 * 删除记忆
 */
async function deleteMemory(memoryId) {
    if (!memoryId) {
        console.error('[Recall] 删除失败: memoryId 为空');
        return;
    }
    
    try {
        console.log(`[Recall] 正在删除记忆: ${memoryId}`);
        const url = `${pluginSettings.apiUrl}/v1/memories/${encodeURIComponent(memoryId)}?user_id=${encodeURIComponent(currentCharacterId || 'default')}`;
        
        const response = await fetch(url, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            console.log(`[Recall] 删除成功: ${memoryId}`);
            loadMemories();
        } else {
            const errData = await response.json().catch(() => ({}));
            console.error(`[Recall] 删除失败: ${response.status}`, errData);
            alert(`删除失败: ${errData.detail || response.statusText}`);
        }
    } catch (e) {
        console.error('[Recall] 删除记忆失败:', e);
        alert('删除失败: ' + e.message);
    }
}

/**
 * 清空当前角色的所有记忆
 */
async function onClearAllMemories() {
    if (!isConnected || !currentCharacterId) {
        alert('未连接或未选择角色');
        return;
    }
    
    const characterName = currentCharacterId;
    const memoryCount = document.getElementById('recall-memory-count')?.textContent || '?';
    
    // 确认对话框
    const confirmed = confirm(
        `⚠️ 危险操作！\n\n` +
        `确定要删除角色 "${characterName}" 的所有记忆吗？\n` +
        `当前记忆数: ${memoryCount}\n\n` +
        `此操作无法撤销！`
    );
    
    if (!confirmed) return;
    
    // 二次确认
    const doubleConfirm = confirm(
        `再次确认：删除 "${characterName}" 的全部记忆？`
    );
    
    if (!doubleConfirm) return;
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${encodeURIComponent(characterName)}&confirm=true`,
            { method: 'DELETE' }
        );
        
        const result = await response.json();
        
        if (result.success) {
            alert(`✓ 已删除 ${result.deleted_count} 条记忆`);
            loadMemories();
        } else {
            alert(`删除失败: ${result.detail || '未知错误'}`);
        }
    } catch (e) {
        console.error('[Recall] 清空记忆失败:', e);
        alert('清空记忆失败: ' + e.message);
    }
}

// 用于分页加载的状态
let currentMemoryOffset = 0;
let hasMoreMemories = false;
const MEMORIES_PER_PAGE = 20;

/**
 * 加载更多记忆
 */
async function onLoadMoreMemories() {
    if (!isConnected) return;
    
    try {
        currentMemoryOffset += MEMORIES_PER_PAGE;
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${encodeURIComponent(currentCharacterId || 'default')}&limit=${MEMORIES_PER_PAGE}&offset=${currentMemoryOffset}`
        );
        const data = await response.json();
        
        if (data.memories && data.memories.length > 0) {
            appendMemories(data.memories);
            hasMoreMemories = data.memories.length >= MEMORIES_PER_PAGE;
        } else {
            hasMoreMemories = false;
        }
        
        updateLoadMoreButton();
    } catch (e) {
        console.error('[Recall] 加载更多记忆失败:', e);
    }
}

/**
 * 追加记忆到列表
 */
function appendMemories(memories) {
    const listEl = document.getElementById('recall-memory-list');
    if (!listEl || !memories || memories.length === 0) return;
    
    const html = memories.map(m => createMemoryItemHtml(m)).join('');
    listEl.insertAdjacentHTML('beforeend', html);
    
    // 绑定新添加项的删除事件
    listEl.querySelectorAll('.recall-delete-memory:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', async (e) => {
            const button = e.currentTarget;
            const id = button.dataset.id;
            if (id && confirm('确定删除这条记忆吗？')) {
                await deleteMemory(id);
            }
        });
    });
}

/**
 * 创建单条记忆的 HTML
 */
function createMemoryItemHtml(m) {
    const content = m.content || m.memory || '';
    // ID 在 metadata.id 中，兼容旧格式 m.id
    const memoryId = m.metadata?.id || m.id || '';
    const previewLength = pluginSettings.previewLength || 200;
    const isLong = content.length > previewLength;
    const preview = isLong ? content.substring(0, previewLength) + '...' : content;
    const roleRaw = m.metadata?.role || '';
    const roleIcon = roleRaw === 'user' ? '👤' : roleRaw === 'assistant' ? '🤖' : '📝';
    const roleName = roleRaw === 'user' ? '用户' : roleRaw === 'assistant' ? 'AI' : '手动';
    const roleClass = roleRaw === 'user' ? 'user' : roleRaw === 'assistant' ? 'assistant' : '';
    const time = m.metadata?.timestamp ? formatTime(m.metadata.timestamp) : (m.created_at ? formatTime(m.created_at) : '');
    const charCount = content.length;
    
    return `
        <div class="recall-memory-item ${isLong ? 'expandable' : ''}" data-id="${memoryId}" data-expanded="false">
            <div class="recall-memory-header">
                <span class="recall-memory-role ${roleClass}">${roleIcon} ${roleName}</span>
                <span class="recall-memory-meta">
                    <span class="recall-memory-chars">${charCount}字</span>
                    <span class="recall-memory-time">${time}</span>
                </span>
            </div>
            <div class="recall-memory-content-wrapper">
                <p class="recall-memory-content recall-memory-preview">${escapeHtml(preview)}</p>
                ${isLong ? `<p class="recall-memory-content recall-memory-full" style="display:none">${escapeHtml(content)}</p>` : ''}
            </div>
            <div class="recall-memory-footer">
                <div class="recall-memory-footer-left">
                    ${m.score ? `<span class="recall-memory-score">📊 ${(m.score * 100).toFixed(0)}%</span>` : ''}
                    ${isLong ? `<button class="recall-expand-btn" data-id="${memoryId}">📖 展开全文</button>` : ''}
                </div>
                <button class="recall-delete-btn recall-delete-memory" data-id="${memoryId}">🗑️</button>
            </div>
        </div>
    `;
}

/**
 * 格式化时间
 */
function formatTime(timestamp) {
    try {
        const date = new Date(timestamp * 1000 || timestamp);
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
        if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
        
        return date.toLocaleDateString();
    } catch {
        return '';
    }
}

/**
 * 更新"加载更多"按钮状态
 */
function updateLoadMoreButton() {
    const container = document.getElementById('recall-load-more-container');
    if (container) {
        container.style.display = hasMoreMemories ? 'block' : 'none';
    }
}

/**
 * 加载伏笔列表
 */
async function loadForeshadowings() {
    if (!isConnected) return;
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing?user_id=${userId}`);
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
        listEl.innerHTML = `
            <div class="recall-empty-state">
                <div class="recall-empty-icon">🎭</div>
                <p>暂无伏笔</p>
                <small>埋下故事线索</small>
            </div>
        `;
        return;
    }
    
    listEl.innerHTML = foreshadowings.map(f => `
        <div class="recall-foreshadowing-item" data-id="${f.id}">
            <div class="recall-memory-header">
                <span class="recall-memory-role">${f.status === 'planted' ? '🌱 已埋下' : '🌿 已解决'}</span>
                <span class="recall-memory-time">重要性: ${(f.importance * 100).toFixed(0)}%</span>
            </div>
            <p class="recall-foreshadowing-content">${escapeHtml(f.content)}</p>
            <div class="recall-memory-footer">
                <span></span>
                ${f.status === 'planted' ? `<button class="recall-delete-btn recall-resolve-foreshadowing" data-id="${f.id}">✓ 解决</button>` : '<span class="recall-memory-score">已完成</span>'}
            </div>
        </div>
    `).join('');
    
    // 绑定解决按钮事件
    listEl.querySelectorAll('.recall-resolve-foreshadowing').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const button = e.currentTarget;
            const id = button.dataset.id;
            if (id && confirm('确定将此伏笔标记为已解决吗？')) {
                await resolveForeshadowing(id);
            }
        });
    });
}

/**
 * 解决伏笔
 */
async function resolveForeshadowing(foreshadowingId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}/resolve?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resolution: '用户手动标记为已解决' })
        });
        
        if (response.ok) {
            loadForeshadowings();
            console.log(`[Recall] 伏笔已解决 (角色: ${currentCharacterId})`);
        } else {
            console.error('[Recall] 解决伏笔失败');
        }
    } catch (e) {
        console.error('[Recall] 解决伏笔失败:', e);
    }
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
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 导出供外部使用（安全方式）
window.RecallPlugin = {
    getMemoryContext: safeExecute(getMemoryContext, '获取记忆上下文失败'),
    loadMemories: safeExecute(loadMemories, '加载记忆失败'),
    loadForeshadowings: safeExecute(loadForeshadowings, '加载伏笔失败'),
    isConnected: () => isConnected,
    isInitialized: () => isInitialized,
    getSettings: () => ({ ...pluginSettings })
};

})(); // IIFE 结束
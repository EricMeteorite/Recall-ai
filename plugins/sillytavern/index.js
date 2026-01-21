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
        apiUrl: '',  // 留空，首次使用时智能检测
        autoInject: true,
        maxMemories: 10,
        maxContextTokens: 2000,     // 记忆注入的最大token数，根据你的AI模型调整
        injectPosition: 'in_chat',  // 'in_chat' 或 'before_system'
        injectDepth: 1,             // 注入深度，0=最新位置，1=倒数第一条后
        showPanel: true,
        language: 'zh-CN',
        filterThinking: true,  // 过滤AI思考过程
        previewLength: 200,    // 记忆预览字数
        autoChunkLongText: true,  // 自动分段长文本
        chunkSize: 2000        // 分段大小（字符数）
    };
    
    /**
     * 智能检测 Recall API 地址
     * 优先级：
     * 1. 与当前页面同源（如果 ST 和 Recall 在同一服务器）
     * 2. localhost:18888（本地开发）
     * 3. 127.0.0.1:18888（本地开发备用）
     */
    function detectApiUrl() {
        const currentHost = window.location.hostname;
        const currentProtocol = window.location.protocol;
        
        // 如果是通过域名访问（不是 localhost/127.0.0.1）
        // 假设 Recall 服务也部署在同一台服务器，端口 18888
        if (currentHost && currentHost !== 'localhost' && currentHost !== '127.0.0.1') {
            // 优先使用 http（Recall 默认不启用 https）
            return `http://${currentHost}:18888`;
        }
        
        // 本地开发环境
        return 'http://127.0.0.1:18888';
    }
    
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
            const parsed = JSON.parse(saved);
            pluginSettings = { ...defaultSettings, ...parsed };
            
            // 如果保存的设置没有 apiUrl 或是空的，自动检测
            if (!pluginSettings.apiUrl) {
                pluginSettings.apiUrl = detectApiUrl();
                saveSettings();  // 保存检测到的地址
                console.log('[Recall] 自动检测到 API 地址:', pluginSettings.apiUrl);
            }
        } else {
            // 首次使用，自动检测 API 地址
            pluginSettings = { ...defaultSettings };
            pluginSettings.apiUrl = detectApiUrl();
            saveSettings();
            console.log('[Recall] 首次使用，自动设置 API 地址:', pluginSettings.apiUrl);
        }
    } catch (e) {
        console.warn('[Recall] 加载设置失败，使用默认值:', e.message);
        pluginSettings = { ...defaultSettings };
        pluginSettings.apiUrl = detectApiUrl();
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
                <div class="inline-drawer-icon fa-solid fa-circle-chevron-down down"></div>
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
                    <button class="recall-tab" data-tab="contexts">📌 条件</button>
                    <button class="recall-tab" data-tab="foreshadowing">🎭 伏笔</button>
                    <button class="recall-tab" data-tab="core-settings">⚠️ 规则</button>
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
                
                <!-- 持久条件标签页 -->
                <div id="recall-tab-contexts" class="recall-tab-content">
                    <div class="recall-stats-row">
                        <span>📌 持久条件: <strong id="recall-context-count">0</strong></span>
                        <div class="recall-stats-actions">
                            <button id="recall-refresh-contexts-btn" class="recall-icon-btn" title="刷新">🔄</button>
                            <button id="recall-consolidate-contexts-btn" class="recall-icon-btn" title="压缩合并">📦</button>
                        </div>
                    </div>
                    
                    <div class="recall-setting-hint" style="margin-bottom:10px;">
                        持久条件是已确立的背景设定，会自动注入到每次对话中。
                        如：用户身份、技术环境、角色设定等。
                    </div>
                    
                    <div id="recall-context-list" class="recall-context-list">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">📌</div>
                            <p>暂无持久条件</p>
                            <small>对话中自动提取或手动添加</small>
                        </div>
                    </div>
                    
                    <div class="recall-add-bar">
                        <select id="recall-context-type-select" class="text_pole" style="width:auto;min-width:100px;">
                            <option value="user_identity">👤 身份</option>
                            <option value="user_goal">🎯 目标</option>
                            <option value="user_preference">❤️ 偏好</option>
                            <option value="environment">💻 环境</option>
                            <option value="project">📁 项目</option>
                            <option value="character_trait">🎭 角色</option>
                            <option value="world_setting">🌍 世界观</option>
                            <option value="relationship">🤝 关系</option>
                            <option value="constraint">⚠️ 约束</option>
                            <option value="custom">📝 自定义</option>
                        </select>
                        <input type="text" id="recall-context-input" placeholder="添加持久条件..." class="text_pole" style="flex:1;">
                        <button id="recall-add-context-btn" class="menu_button menu_button_icon" title="添加">
                            <i class="fa-solid fa-plus"></i>
                        </button>
                    </div>
                </div>
                
                <!-- 伏笔标签页 -->
                <div id="recall-tab-foreshadowing" class="recall-tab-content">
                    <div class="recall-stats-row">
                        <span>🎭 活跃伏笔: <strong id="recall-foreshadowing-count">0</strong></span>
                        <div class="recall-stats-actions">
                            <button id="recall-refresh-foreshadowing-btn" class="recall-icon-btn" title="刷新">🔄</button>
                            <button id="recall-analyze-foreshadowing-btn" class="recall-icon-btn" title="手动分析">🔍</button>
                        </div>
                    </div>
                    
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
                
                <!-- 绝对规则标签页（Recall 独有功能，不与 ST 重复） -->
                <div id="recall-tab-core-settings" class="recall-tab-content">
                    <div class="recall-info-box" style="margin-bottom:12px;">
                        <div class="recall-info-title">💡 关于绝对规则</div>
                        <ul>
                            <li>绝对规则是 AI <strong>必须遵守</strong>的硬性约束</li>
                            <li>角色卡、世界观、写作风格请使用 <strong>SillyTavern 自带功能</strong></li>
                            <li>此功能是 ST 没有的<strong>补充功能</strong>，用于强制 AI 遵守某些规则</li>
                        </ul>
                    </div>
                    
                    <div class="recall-settings-section">
                        <div class="recall-settings-section-title">⚠️ 绝对规则（每行一条）</div>
                        <div class="recall-setting-hint">这些规则会被强制注入，AI 必须遵守</div>
                        <textarea id="recall-core-rules" class="text_pole recall-textarea" 
                            placeholder="绝对不能违反的规则，每行一条
例如：
角色不会主动伤害无辜的人
角色说话时不会使用脏话
保持角色设定的一致性
不要在回复中使用emoji
不要打破第四面墙" rows="8"></textarea>
                    </div>
                    
                    <div class="recall-setting-actions" style="margin-top:10px;">
                        <button id="recall-load-core-settings" class="menu_button">
                            <i class="fa-solid fa-refresh"></i>
                            <span>刷新</span>
                        </button>
                        <button id="recall-save-core-settings" class="menu_button menu_button_icon">
                            <i class="fa-solid fa-save"></i>
                            <span>保存规则</span>
                        </button>
                    </div>
                </div>
                
                <!-- 设置标签页 -->
                <div id="recall-tab-settings" class="recall-tab-content">
                    <!-- 基本设置 -->
                    <div class="recall-settings-section">
                        <div class="recall-settings-section-title">🔧 基本设置</div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-label">
                                <input type="checkbox" id="recall-enabled" ${pluginSettings.enabled ? 'checked' : ''}>
                                <span>启用记忆功能</span>
                            </label>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">API 地址</label>
                            <input type="text" id="recall-api-url" value="${pluginSettings.apiUrl}" 
                                   placeholder="自动检测或手动输入" class="text_pole">
                            <div class="recall-setting-hint">💡 远程访问时需修改为服务器地址（如 http://你的域名:18888）</div>
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
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">最大注入记忆数</label>
                            <input type="number" id="recall-max-memories" value="${pluginSettings.maxMemories}" 
                                   min="1" max="50" class="text_pole">
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">记忆上下文Token预算</label>
                            <input type="number" id="recall-max-context-tokens" value="${pluginSettings.maxContextTokens || 2000}" 
                                   min="500" max="32000" step="500" class="text_pole">
                            <div class="recall-setting-hint">根据你的AI模型调整。4K模型建议1500，8K建议3000，128K可设更高</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">注入位置</label>
                            <select id="recall-inject-position" class="text_pole">
                                <option value="in_chat" ${pluginSettings.injectPosition === 'in_chat' ? 'selected' : ''}>在聊天历史中 (推荐)</option>
                                <option value="before_system" ${pluginSettings.injectPosition === 'before_system' ? 'selected' : ''}>在系统提示区域</option>
                            </select>
                            <div class="recall-setting-hint">推荐"在聊天历史中"，记忆会更自然地融入对话</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">注入深度</label>
                            <input type="number" id="recall-inject-depth" value="${pluginSettings.injectDepth || 1}" 
                                   min="0" max="10" class="text_pole">
                            <div class="recall-setting-hint">0=最新位置，1=倒数第一条消息后，数字越大位置越靠前</div>
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
                    </div>
                    
                    <!-- Embedding API 配置 -->
                    <div class="recall-settings-section recall-api-section">
                        <div class="recall-settings-section-title">
                            🔗 Embedding API 配置
                            <span class="recall-api-status" id="recall-embedding-status">未知</span>
                        </div>
                        <div class="recall-setting-hint" style="margin-top:-5px;margin-bottom:10px;">用于语义搜索和相似度匹配（OpenAI 兼容接口）</div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">API Key</label>
                            <div class="recall-api-key-input">
                                <input type="password" id="recall-embedding-api-key" class="text_pole" 
                                       placeholder="sk-xxxxxxxx">
                                <button class="recall-toggle-key-btn" data-target="recall-embedding-api-key" title="显示/隐藏">👁</button>
                            </div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">API 地址</label>
                            <input type="text" id="recall-embedding-api-base" class="text_pole" 
                                   placeholder="https://api.siliconflow.cn/v1">
                            <div class="recall-setting-hint">硅基流动: https://api.siliconflow.cn/v1</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">模型名称</label>
                            <div class="recall-model-select-wrapper">
                                <select id="recall-embedding-model" class="text_pole">
                                    <option value="">-- 点击获取模型列表 --</option>
                                    <option value="__custom__">✏️ 自定义模型...</option>
                                </select>
                                <button id="recall-refresh-embedding-models" class="menu_button menu_button_icon" title="获取模型列表">
                                    <i class="fa-solid fa-refresh"></i>
                                </button>
                            </div>
                            <input type="text" id="recall-embedding-model-custom" class="text_pole" 
                                   placeholder="输入自定义模型名称" style="display:none;margin-top:5px;">
                            <div class="recall-setting-hint">填写 API Key 和地址后点击刷新按钮获取可用模型</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">向量维度</label>
                            <input type="number" id="recall-embedding-dimension" class="text_pole" 
                                   placeholder="点击测试连接自动检测">
                            <div class="recall-setting-hint">💡 可手动填写，或点击"测试连接"自动检测</div>
                        </div>
                        
                        <div class="recall-setting-actions">
                            <button id="recall-test-embedding" class="menu_button">
                                <i class="fa-solid fa-flask-vial"></i>
                                <span>测试 Embedding 连接</span>
                            </button>
                            <button id="recall-save-embedding" class="menu_button menu_button_icon">
                                <i class="fa-solid fa-save"></i>
                                <span>保存配置</span>
                            </button>
                        </div>
                    </div>
                    
                    <!-- LLM API 配置 -->
                    <div class="recall-settings-section recall-api-section">
                        <div class="recall-settings-section-title">
                            🤖 LLM API 配置
                            <span class="recall-api-status" id="recall-llm-status">未知</span>
                        </div>
                        <div class="recall-setting-hint" style="margin-top:-5px;margin-bottom:10px;">用于伏笔分析、智能总结等高级功能（可选）</div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">API Key</label>
                            <div class="recall-api-key-input">
                                <input type="password" id="recall-llm-api-key" class="text_pole" 
                                       placeholder="sk-xxxxxxxx">
                                <button class="recall-toggle-key-btn" data-target="recall-llm-api-key" title="显示/隐藏">👁</button>
                            </div>
                            <div class="recall-setting-hint">支持 OpenAI、Claude、硅基流动等多种 LLM</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">API 地址（可选）</label>
                            <input type="text" id="recall-llm-api-base" class="text_pole" 
                                   placeholder="留空使用 OpenAI 官方地址">
                            <div class="recall-setting-hint">硅基流动: https://api.siliconflow.cn/v1</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">模型名称</label>
                            <div class="recall-model-select-wrapper">
                                <select id="recall-llm-model" class="text_pole">
                                    <option value="">-- 点击获取模型列表 --</option>
                                    <option value="__custom__">✏️ 自定义模型...</option>
                                </select>
                                <button id="recall-refresh-llm-models" class="menu_button menu_button_icon" title="获取模型列表">
                                    <i class="fa-solid fa-refresh"></i>
                                </button>
                            </div>
                            <input type="text" id="recall-llm-model-custom" class="text_pole" 
                                   placeholder="输入自定义模型名称" style="display:none;margin-top:5px;">
                            <div class="recall-setting-hint">填写 API Key 和地址后点击刷新按钮获取可用模型</div>
                        </div>
                        
                        <div class="recall-setting-actions">
                            <button id="recall-test-llm" class="menu_button">
                                <i class="fa-solid fa-flask-vial"></i>
                                <span>测试 LLM 连接</span>
                            </button>
                            <button id="recall-save-llm" class="menu_button menu_button_icon">
                                <i class="fa-solid fa-save"></i>
                                <span>保存配置</span>
                            </button>
                        </div>
                    </div>
                    
                    <!-- 伏笔分析器配置 -->
                    <div class="recall-settings-section recall-api-section">
                        <div class="recall-settings-section-title">
                            🎭 伏笔分析器配置
                            <span class="recall-api-status" id="recall-analyzer-status">未知</span>
                        </div>
                        <div class="recall-setting-hint" style="margin-top:-5px;margin-bottom:10px;">控制 LLM 自动分析伏笔的行为（需要配置 LLM API）</div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-checkbox-label">
                                <input type="checkbox" id="recall-llm-enabled">
                                <span>启用 LLM 分析</span>
                            </label>
                            <div class="recall-setting-hint">开启后，对话时会自动使用 LLM 分析伏笔</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">分析触发间隔</label>
                            <input type="number" id="recall-trigger-interval" class="text_pole" 
                                   min="1" max="100" value="10" placeholder="10">
                            <div class="recall-setting-hint">每隔几轮对话触发一次 LLM 分析（1=每轮都分析，10=每10轮分析一次）</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-checkbox-label">
                                <input type="checkbox" id="recall-auto-plant">
                                <span>自动埋下伏笔</span>
                            </label>
                            <div class="recall-setting-hint">LLM 检测到潜在伏笔时自动记录</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-checkbox-label">
                                <input type="checkbox" id="recall-auto-resolve">
                                <span>自动解决伏笔</span>
                            </label>
                            <div class="recall-setting-hint">LLM 检测到伏笔被回收时自动标记为已解决</div>
                        </div>
                        
                        <div class="recall-setting-actions">
                            <button id="recall-load-analyzer-config" class="menu_button">
                                <i class="fa-solid fa-refresh"></i>
                                <span>刷新配置</span>
                            </button>
                            <button id="recall-save-analyzer-config" class="menu_button menu_button_icon">
                                <i class="fa-solid fa-save"></i>
                                <span>保存配置</span>
                            </button>
                        </div>
                    </div>
                    
                    <!-- 容量限制配置 -->
                    <div class="recall-settings-section recall-api-section">
                        <div class="recall-settings-section-title">
                            📊 容量限制配置
                        </div>
                        <div class="recall-setting-hint" style="margin-top:-5px;margin-bottom:10px;">控制持久条件和伏笔的数量上限、衰减和去重行为</div>
                        
                        <!-- 持久条件限制 -->
                        <div class="recall-setting-group" style="margin-bottom:15px;">
                            <div style="font-weight:bold;margin-bottom:8px;">📌 持久条件</div>
                            
                            <div class="recall-setting-row" style="display:flex;gap:10px;margin-bottom:8px;">
                                <div style="flex:1;">
                                    <label class="recall-setting-title">每类型上限</label>
                                    <input type="number" id="recall-context-max-per-type" class="text_pole" 
                                           min="1" max="100" value="30" placeholder="30">
                                </div>
                                <div style="flex:1;">
                                    <label class="recall-setting-title">总数上限</label>
                                    <input type="number" id="recall-context-max-total" class="text_pole" 
                                           min="1" max="500" value="100" placeholder="100">
                                </div>
                            </div>
                            
                            <div class="recall-setting-row" style="display:flex;gap:10px;margin-bottom:8px;">
                                <div style="flex:1;">
                                    <label class="recall-setting-title">衰减开始天数</label>
                                    <input type="number" id="recall-context-decay-days" class="text_pole" 
                                           min="1" max="365" value="7" placeholder="7">
                                </div>
                                <div style="flex:1;">
                                    <label class="recall-setting-title">衰减比例</label>
                                    <input type="number" id="recall-context-decay-rate" class="text_pole" 
                                           min="0.01" max="0.5" step="0.01" value="0.1" placeholder="0.1">
                                </div>
                            </div>
                            
                            <div class="recall-setting-group">
                                <label class="recall-setting-title">最低置信度（低于此自动归档）</label>
                                <input type="number" id="recall-context-min-confidence" class="text_pole" 
                                       min="0.1" max="0.9" step="0.05" value="0.3" placeholder="0.3">
                            </div>
                        </div>
                        
                        <!-- 伏笔限制 -->
                        <div class="recall-setting-group" style="margin-bottom:15px;">
                            <div style="font-weight:bold;margin-bottom:8px;">🎭 伏笔系统</div>
                            
                            <div class="recall-setting-row" style="display:flex;gap:10px;">
                                <div style="flex:1;">
                                    <label class="recall-setting-title">召回数量</label>
                                    <input type="number" id="recall-foreshadowing-max-return" class="text_pole" 
                                           min="1" max="20" value="5" placeholder="5">
                                    <div class="recall-setting-hint">每次注入到上下文的伏笔数量</div>
                                </div>
                                <div style="flex:1;">
                                    <label class="recall-setting-title">活跃上限</label>
                                    <input type="number" id="recall-foreshadowing-max-active" class="text_pole" 
                                           min="10" max="200" value="50" placeholder="50">
                                    <div class="recall-setting-hint">超过则自动归档旧伏笔</div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- 智能去重 -->
                        <div class="recall-setting-group" style="margin-bottom:15px;">
                            <div style="font-weight:bold;margin-bottom:8px;">🔄 智能去重</div>
                            
                            <div class="recall-setting-group">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-dedup-embedding-enabled" checked>
                                    <span>启用语义去重</span>
                                </label>
                                <div class="recall-setting-hint">基于 Embedding 检测相似内容（需配置 Embedding API）</div>
                            </div>
                            
                            <div class="recall-setting-row" style="display:flex;gap:10px;">
                                <div style="flex:1;">
                                    <label class="recall-setting-title">高相似度阈值</label>
                                    <input type="number" id="recall-dedup-high-threshold" class="text_pole" 
                                           min="0.8" max="0.99" step="0.01" value="0.92" placeholder="0.92">
                                    <div class="recall-setting-hint">≥此值视为重复，自动跳过</div>
                                </div>
                                <div style="flex:1;">
                                    <label class="recall-setting-title">低相似度阈值</label>
                                    <input type="number" id="recall-dedup-low-threshold" class="text_pole" 
                                           min="0.5" max="0.9" step="0.01" value="0.75" placeholder="0.75">
                                    <div class="recall-setting-hint">≥此值提示可能重复</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="recall-setting-actions">
                            <button id="recall-load-capacity-config" class="menu_button">
                                <i class="fa-solid fa-refresh"></i>
                                <span>刷新配置</span>
                            </button>
                            <button id="recall-save-capacity-config" class="menu_button menu_button_icon">
                                <i class="fa-solid fa-save"></i>
                                <span>保存配置</span>
                            </button>
                        </div>
                    </div>
                    
                    <!-- 系统管理 -->
                    <div class="recall-settings-section recall-api-section">
                        <div class="recall-settings-section-title">
                            🛠️ 系统管理
                        </div>
                        
                        <div class="recall-setting-actions" style="flex-wrap:wrap;gap:5px;">
                            <button id="recall-reload-config" class="menu_button" title="热更新后端配置">
                                <i class="fa-solid fa-rotate"></i>
                                <span>热更新配置</span>
                            </button>
                            <button id="recall-consolidate-memories" class="menu_button" title="整合记忆">
                                <i class="fa-solid fa-compress"></i>
                                <span>整合记忆</span>
                            </button>
                            <button id="recall-show-stats" class="menu_button" title="查看统计">
                                <i class="fa-solid fa-chart-bar"></i>
                                <span>系统统计</span>
                            </button>
                        </div>
                        
                        <div id="recall-stats-display" class="recall-stats-display" style="display:none;margin-top:10px;padding:10px;background:#1a1a1a;border-radius:5px;">
                            <div class="recall-stats-title">📊 系统统计</div>
                            <div id="recall-stats-content"></div>
                        </div>
                    </div>
                    
                    <div class="recall-info-box">
                        <div class="recall-info-title">💡 使用提示</div>
                        <ul>
                            <li>确保 Recall 服务已启动</li>
                            <li>切换角色会自动加载对应记忆</li>
                            <li>Embedding API 用于语义搜索（推荐配置）</li>
                            <li>LLM API 用于伏笔分析（可选配置）</li>
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
            
            // 根据标签页加载对应数据
            if (tabName === 'contexts' && isConnected) {
                loadPersistentContexts();
            } else if (tabName === 'foreshadowing' && isConnected) {
                loadForeshadowings();
            } else if (tabName === 'core-settings' && isConnected) {
                loadCoreSettings();
            }
        });
    });
    
    // 折叠面板由 SillyTavern 原生处理，不需要自己绑定事件
    // SillyTavern 会自动处理 .inline-drawer-toggle 的点击
    
    // 绑定事件
    document.getElementById('recall-save-settings')?.addEventListener('click', safeExecute(onSaveSettings, '保存设置失败'));
    document.getElementById('recall-test-connection')?.addEventListener('click', safeExecute(onTestConnection, '测试连接失败'));
    document.getElementById('recall-search-btn')?.addEventListener('click', safeExecute(onSearch, '搜索失败'));
    document.getElementById('recall-add-btn')?.addEventListener('click', safeExecute(onAddMemory, '添加记忆失败'));
    document.getElementById('recall-foreshadowing-btn')?.addEventListener('click', safeExecute(onPlantForeshadowing, '埋下伏笔失败'));
    document.getElementById('recall-clear-all-btn')?.addEventListener('click', safeExecute(onClearAllMemories, '清空记忆失败'));
    document.getElementById('recall-refresh-btn')?.addEventListener('click', safeExecute(loadMemories, '刷新失败'));
    document.getElementById('recall-load-more-btn')?.addEventListener('click', safeExecute(onLoadMoreMemories, '加载更多失败'));
    
    // 持久条件相关事件绑定
    document.getElementById('recall-add-context-btn')?.addEventListener('click', safeExecute(onAddPersistentContext, '添加持久条件失败'));
    document.getElementById('recall-refresh-contexts-btn')?.addEventListener('click', safeExecute(loadPersistentContexts, '刷新持久条件失败'));
    document.getElementById('recall-consolidate-contexts-btn')?.addEventListener('click', safeExecute(consolidatePersistentContexts, '压缩持久条件失败'));
    document.getElementById('recall-context-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') safeExecute(onAddPersistentContext, '添加持久条件失败')();
    });
    
    // API 配置相关事件绑定
    document.getElementById('recall-test-embedding')?.addEventListener('click', safeExecute(onTestEmbedding, '测试 Embedding 失败'));
    document.getElementById('recall-save-embedding')?.addEventListener('click', safeExecute(onSaveEmbeddingConfig, '保存 Embedding 配置失败'));
    document.getElementById('recall-test-llm')?.addEventListener('click', safeExecute(onTestLLM, '测试 LLM 失败'));
    document.getElementById('recall-save-llm')?.addEventListener('click', safeExecute(onSaveLLMConfig, '保存 LLM 配置失败'));
    
    // 伏笔分析器配置事件绑定
    document.getElementById('recall-load-analyzer-config')?.addEventListener('click', safeExecute(loadForeshadowingAnalyzerConfig, '加载伏笔分析器配置失败'));
    document.getElementById('recall-save-analyzer-config')?.addEventListener('click', safeExecute(onSaveForeshadowingAnalyzerConfig, '保存伏笔分析器配置失败'));
    
    // 伏笔标签页的新按钮
    document.getElementById('recall-refresh-foreshadowing-btn')?.addEventListener('click', safeExecute(loadForeshadowings, '刷新伏笔失败'));
    document.getElementById('recall-analyze-foreshadowing-btn')?.addEventListener('click', safeExecute(triggerForeshadowingAnalysis, '触发伏笔分析失败'));
    
    // 核心设定相关事件绑定
    document.getElementById('recall-load-core-settings')?.addEventListener('click', safeExecute(loadCoreSettings, '加载核心设定失败'));
    document.getElementById('recall-save-core-settings')?.addEventListener('click', safeExecute(saveCoreSettings, '保存核心设定失败'));
    
    // 容量限制配置相关事件绑定
    document.getElementById('recall-load-capacity-config')?.addEventListener('click', safeExecute(loadCapacityConfig, '加载容量限制配置失败'));
    document.getElementById('recall-save-capacity-config')?.addEventListener('click', safeExecute(saveCapacityConfig, '保存容量限制配置失败'));
    
    // 系统管理相关事件绑定
    document.getElementById('recall-reload-config')?.addEventListener('click', safeExecute(reloadServerConfig, '热更新配置失败'));
    document.getElementById('recall-consolidate-memories')?.addEventListener('click', safeExecute(consolidateMemories, '整合记忆失败'));
    document.getElementById('recall-show-stats')?.addEventListener('click', safeExecute(showSystemStats, '获取统计信息失败'));
    
    // 刷新模型列表按钮事件绑定
    document.getElementById('recall-refresh-embedding-models')?.addEventListener('click', safeExecute(loadEmbeddingModels, '获取 Embedding 模型列表失败'));
    document.getElementById('recall-refresh-llm-models')?.addEventListener('click', safeExecute(loadLLMModels, '获取 LLM 模型列表失败'));
    
    // API Key 显示/隐藏切换
    document.querySelectorAll('.recall-toggle-key-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetId = btn.dataset.target;
            const input = document.getElementById(targetId);
            if (input) {
                if (input.type === 'password') {
                    input.type = 'text';
                    btn.textContent = '🔒';
                } else {
                    input.type = 'password';
                    btn.textContent = '👁';
                }
            }
        });
    });
    
    // 模型选择框事件绑定
    bindModelSelectEvents('recall-embedding-model', 'recall-embedding-model-custom', 'recall-embedding-dimension');
    bindModelSelectEvents('recall-llm-model', 'recall-llm-model-custom', null);
    
    // 初始化加载 API 配置
    loadApiConfig();
    
    // 初始化加载伏笔分析器配置
    loadForeshadowingAnalyzerConfig();
    
    // 初始化加载容量限制配置
    loadCapacityConfig();
    
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
 * 加载 API 配置
 */
async function loadApiConfig() {
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config/full`);
        const config = await response.json();
        
        if (config.embedding) {
            // 加载 Embedding 配置
            const emb = config.embedding;
            document.getElementById('recall-embedding-api-key').value = emb.api_key || '';
            document.getElementById('recall-embedding-api-base').value = emb.api_base || '';
            
            // 处理模型选择：先尝试选中已有选项，否则显示自定义输入
            setModelSelectValue('recall-embedding-model', 'recall-embedding-model-custom', emb.model || '');
            
            // 维度：如果已配置则显示，否则留空让用户通过测试连接自动检测
            const dimValue = emb.dimension && emb.dimension !== '未配置' ? emb.dimension : '';
            document.getElementById('recall-embedding-dimension').value = dimValue;
            
            // 更新状态指示器
            updateEmbeddingStatus(emb.api_key_status);
        }
        
        if (config.llm) {
            // 加载 LLM 配置
            const llm = config.llm;
            document.getElementById('recall-llm-api-key').value = llm.api_key || '';
            document.getElementById('recall-llm-api-base').value = llm.api_base || '';
            
            // 处理模型选择
            setModelSelectValue('recall-llm-model', 'recall-llm-model-custom', llm.model || '');
            
            // 更新状态指示器
            updateLLMStatus(llm.api_key_status);
        }
        
        console.log('[Recall] API 配置加载完成');
    } catch (e) {
        console.warn('[Recall] 加载 API 配置失败:', e);
    }
}

/**
 * 加载容量限制配置
 */
async function loadCapacityConfig() {
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config`);
        const config = await response.json();
        
        if (config.capacity_limits) {
            const limits = config.capacity_limits;
            
            // 持久条件配置
            if (limits.context) {
                document.getElementById('recall-context-max-per-type').value = limits.context.max_per_type || 30;
                document.getElementById('recall-context-max-total').value = limits.context.max_total || 100;
                document.getElementById('recall-context-decay-days').value = limits.context.decay_days || 7;
                document.getElementById('recall-context-decay-rate').value = limits.context.decay_rate || 0.1;
                document.getElementById('recall-context-min-confidence').value = limits.context.min_confidence || 0.3;
            }
            
            // 伏笔配置
            if (limits.foreshadowing) {
                document.getElementById('recall-foreshadowing-max-return').value = limits.foreshadowing.max_return || 5;
                document.getElementById('recall-foreshadowing-max-active').value = limits.foreshadowing.max_active || 50;
            }
            
            // 去重配置
            if (limits.dedup) {
                document.getElementById('recall-dedup-embedding-enabled').checked = limits.dedup.embedding_enabled !== false;
                document.getElementById('recall-dedup-high-threshold').value = limits.dedup.high_threshold || 0.92;
                document.getElementById('recall-dedup-low-threshold').value = limits.dedup.low_threshold || 0.75;
            }
        }
        
        showToast('容量限制配置已加载', 'success');
        console.log('[Recall] 容量限制配置加载完成');
    } catch (e) {
        console.warn('[Recall] 加载容量限制配置失败:', e);
        showToast('加载容量限制配置失败: ' + e.message, 'error');
    }
}

/**
 * 保存容量限制配置
 */
async function saveCapacityConfig() {
    try {
        const configData = {
            // 持久条件配置
            context_max_per_type: parseInt(document.getElementById('recall-context-max-per-type').value) || 30,
            context_max_total: parseInt(document.getElementById('recall-context-max-total').value) || 100,
            context_decay_days: parseInt(document.getElementById('recall-context-decay-days').value) || 7,
            context_decay_rate: parseFloat(document.getElementById('recall-context-decay-rate').value) || 0.1,
            context_min_confidence: parseFloat(document.getElementById('recall-context-min-confidence').value) || 0.3,
            // 伏笔配置
            foreshadowing_max_return: parseInt(document.getElementById('recall-foreshadowing-max-return').value) || 5,
            foreshadowing_max_active: parseInt(document.getElementById('recall-foreshadowing-max-active').value) || 50,
            // 去重配置
            dedup_embedding_enabled: document.getElementById('recall-dedup-embedding-enabled').checked,
            dedup_high_threshold: parseFloat(document.getElementById('recall-dedup-high-threshold').value) || 0.92,
            dedup_low_threshold: parseFloat(document.getElementById('recall-dedup-low-threshold').value) || 0.75
        };
        
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        const result = await response.json();
        
        if (result.success !== false) {
            showToast('容量限制配置已保存', 'success');
            console.log('[Recall] 容量限制配置保存成功:', result);
            
            // 热更新配置
            await fetch(`${pluginSettings.apiUrl}/v1/config/reload`, { method: 'POST' });
        } else {
            showToast('保存失败: ' + (result.message || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('[Recall] 保存容量限制配置失败:', e);
        showToast('保存容量限制配置失败: ' + e.message, 'error');
    }
}

/**
 * 设置模型选择框的值
 * 如果值在选项中存在则选中，否则切换到自定义输入
 */
function setModelSelectValue(selectId, customInputId, value) {
    const select = document.getElementById(selectId);
    const customInput = document.getElementById(customInputId);
    if (!select || !customInput) return;
    
    if (!value) {
        select.value = '';
        customInput.style.display = 'none';
        customInput.value = '';
        return;
    }
    
    // 检查值是否在选项中
    const options = Array.from(select.options).map(o => o.value);
    if (options.includes(value)) {
        select.value = value;
        customInput.style.display = 'none';
        customInput.value = '';
    } else {
        // 使用自定义输入
        select.value = '__custom__';
        customInput.style.display = 'block';
        customInput.value = value;
    }
}

/**
 * 获取模型选择框的实际值
 */
function getModelSelectValue(selectId, customInputId) {
    const select = document.getElementById(selectId);
    const customInput = document.getElementById(customInputId);
    if (!select) return '';
    
    if (select.value === '__custom__' && customInput) {
        return customInput.value.trim();
    }
    return select.value;
}

/**
 * 绑定模型选择框事件
 */
function bindModelSelectEvents(selectId, customInputId, dimensionInputId) {
    const select = document.getElementById(selectId);
    const customInput = document.getElementById(customInputId);
    
    if (!select || !customInput) return;
    
    // 模型维度映射
    const modelDimensions = {
        // SiliconFlow
        'BAAI/bge-m3': 1024,
        'BAAI/bge-large-zh-v1.5': 1024,
        'BAAI/bge-large-en-v1.5': 1024,
        'netease-youdao/bce-embedding-base_v1': 768,
        // OpenAI
        'text-embedding-3-small': 1536,
        'text-embedding-3-large': 3072,
        'text-embedding-ada-002': 1536,
        // Ollama
        'nomic-embed-text': 768,
        'mxbai-embed-large': 1024,
        'all-minilm': 384,
    };
    
    select.addEventListener('change', () => {
        if (select.value === '__custom__') {
            customInput.style.display = 'block';
            customInput.focus();
        } else {
            customInput.style.display = 'none';
            customInput.value = '';
            
            // 自动设置维度（仅对 Embedding 模型）
            if (dimensionInputId && modelDimensions[select.value]) {
                const dimInput = document.getElementById(dimensionInputId);
                if (dimInput) {
                    dimInput.value = modelDimensions[select.value];
                }
            }
        }
    });
}

/**
 * 动态获取 Embedding 模型列表
 */
async function loadEmbeddingModels() {
    const select = document.getElementById('recall-embedding-model');
    const refreshBtn = document.getElementById('recall-refresh-embedding-models');
    if (!select) return;
    
    // 显示加载状态
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }
    
    // 保存当前值
    const currentValue = getModelSelectValue('recall-embedding-model', 'recall-embedding-model-custom');
    
    try {
        // 使用插件设置的 API URL
        const url = `${pluginSettings.apiUrl}/v1/config/models/embedding`;
        
        console.log('[Recall] 获取 Embedding 模型列表:', url);
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('[Recall] Embedding 模型列表响应:', data);
        
        if (data.success && data.models && data.models.length > 0) {
            // 清空并重新填充选项
            select.innerHTML = '<option value="">-- 选择模型 --</option>';
            
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.id;
                select.appendChild(option);
            });
            
            // 添加自定义选项
            const customOption = document.createElement('option');
            customOption.value = '__custom__';
            customOption.textContent = '✏️ 自定义模型...';
            select.appendChild(customOption);
            
            // 恢复之前选择的值
            if (currentValue) {
                setModelSelectValue('recall-embedding-model', 'recall-embedding-model-custom', currentValue);
            }
            
            toastr.success(`成功获取 ${data.models.length} 个 Embedding 模型`, 'Recall');
        } else {
            toastr.warning(data.message || '未获取到模型列表，请检查 API 配置', 'Recall');
        }
    } catch (error) {
        console.error('Failed to load embedding models:', error);
        toastr.error(`获取模型列表失败: ${error.message}`, 'Recall');
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="fa-solid fa-refresh"></i>';
        }
    }
}

/**
 * 动态获取 LLM 模型列表
 */
async function loadLLMModels() {
    const select = document.getElementById('recall-llm-model');
    const refreshBtn = document.getElementById('recall-refresh-llm-models');
    if (!select) return;
    
    // 显示加载状态
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }
    
    // 保存当前值
    const currentValue = getModelSelectValue('recall-llm-model', 'recall-llm-model-custom');
    
    try {
        // 使用插件设置的 API URL
        const url = `${pluginSettings.apiUrl}/v1/config/models/llm`;
        
        console.log('[Recall] 获取 LLM 模型列表:', url);
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('[Recall] LLM 模型列表响应:', data);
        
        if (data.success && data.models && data.models.length > 0) {
            // 清空并重新填充选项
            select.innerHTML = '<option value="">-- 选择模型 --</option>';
            
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.id;
                select.appendChild(option);
            });
            
            // 添加自定义选项
            const customOption = document.createElement('option');
            customOption.value = '__custom__';
            customOption.textContent = '✏️ 自定义模型...';
            select.appendChild(customOption);
            
            // 恢复之前选择的值
            if (currentValue) {
                setModelSelectValue('recall-llm-model', 'recall-llm-model-custom', currentValue);
            }
            
            toastr.success(`成功获取 ${data.models.length} 个 LLM 模型`, 'Recall');
        } else {
            toastr.warning(data.message || '未获取到模型列表，请检查 API 配置', 'Recall');
        }
    } catch (error) {
        console.error('Failed to load LLM models:', error);
        toastr.error(`获取模型列表失败: ${error.message}`, 'Recall');
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="fa-solid fa-refresh"></i>';
        }
    }
}

/**
 * 更新 Embedding 状态指示器
 */
function updateEmbeddingStatus(status) {
    const statusEl = document.getElementById('recall-embedding-status');
    if (!statusEl) return;
    
    if (status === '已配置') {
        statusEl.textContent = '已配置';
        statusEl.className = 'recall-api-status recall-status-configured';
    } else {
        statusEl.textContent = '未配置';
        statusEl.className = 'recall-api-status recall-status-unconfigured';
    }
}

/**
 * 更新 LLM 状态指示器
 */
function updateLLMStatus(status) {
    const statusEl = document.getElementById('recall-llm-status');
    if (!statusEl) return;
    
    if (status === '已配置') {
        statusEl.textContent = '已配置';
        statusEl.className = 'recall-api-status recall-status-configured';
    } else {
        statusEl.textContent = '未配置';
        statusEl.className = 'recall-api-status recall-status-unconfigured';
    }
}

/**
 * 测试 Embedding 连接
 */
async function onTestEmbedding() {
    const testBtn = document.getElementById('recall-test-embedding');
    const originalText = testBtn.innerHTML;
    testBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 测试中...';
    testBtn.disabled = true;
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config/test`);
        const result = await response.json();
        
        if (result.success) {
            // 自动填充检测到的维度到输入框（不自动保存，由用户手动保存）
            if (result.dimension) {
                const dimInput = document.getElementById('recall-embedding-dimension');
                if (dimInput) {
                    dimInput.value = result.dimension;
                }
            }
            
            alert(`✅ Embedding 连接成功！\n\n模型: ${result.model}\n维度: ${result.dimension} (已填充，请保存配置)\n延迟: ${result.latency_ms}ms`);
            updateEmbeddingStatusDirect(true);
        } else {
            alert(`❌ Embedding 连接失败\n\n${result.message}`);
            updateEmbeddingStatusDirect(false);
        }
    } catch (e) {
        alert(`❌ 测试失败: ${e.message}`);
    } finally {
        testBtn.innerHTML = originalText;
        testBtn.disabled = false;
    }
}

/**
 * 直接更新 Embedding 状态
 */
function updateEmbeddingStatusDirect(success) {
    const statusEl = document.getElementById('recall-embedding-status');
    if (statusEl) {
        statusEl.textContent = success ? '已配置' : '未配置';
        statusEl.className = 'recall-api-status ' + (success ? 'recall-status-configured' : 'recall-status-unconfigured');
    }
}

/**
 * 测试 LLM 连接
 */
async function onTestLLM() {
    const testBtn = document.getElementById('recall-test-llm');
    const originalText = testBtn.innerHTML;
    testBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 测试中...';
    testBtn.disabled = true;
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config/test/llm`);
        const result = await response.json();
        
        if (result.success) {
            alert(`✅ LLM 连接成功！\n\n模型: ${result.model}\n延迟: ${result.latency_ms}ms\n响应: ${result.response}`);
            updateLLMStatus('已配置');
        } else {
            alert(`❌ LLM 连接失败\n\n${result.message}`);
            updateLLMStatus('未配置');
        }
    } catch (e) {
        alert(`❌ 测试失败: ${e.message}`);
    } finally {
        testBtn.innerHTML = originalText;
        testBtn.disabled = false;
    }
}

/**
 * 保存 Embedding 配置
 */
async function onSaveEmbeddingConfig() {
    const embKey = document.getElementById('recall-embedding-api-key').value.trim();
    const embBase = document.getElementById('recall-embedding-api-base').value.trim();
    const embModel = getModelSelectValue('recall-embedding-model', 'recall-embedding-model-custom');
    const embDim = document.getElementById('recall-embedding-dimension').value.trim();
    
    const configData = {};
    
    // 只有当输入的不是掩码值时才更新 API Key
    if (embKey && !embKey.includes('*')) {
        configData.embedding_api_key = embKey;
    }
    if (embBase) configData.embedding_api_base = embBase;
    if (embModel) configData.embedding_model = embModel;
    if (embDim) configData.embedding_dimension = parseInt(embDim);
    
    if (Object.keys(configData).length === 0) {
        alert('请填写配置项');
        return;
    }
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(`✅ Embedding 配置已保存\n\n已更新: ${result.updated_fields.join(', ')}`);
            // 重新加载配置
            loadApiConfig();
        } else {
            alert(`❌ 保存失败: ${result.message}`);
        }
    } catch (e) {
        alert(`❌ 保存失败: ${e.message}`);
    }
}

/**
 * 保存 LLM 配置
 */
async function onSaveLLMConfig() {
    const llmKey = document.getElementById('recall-llm-api-key').value.trim();
    const llmBase = document.getElementById('recall-llm-api-base').value.trim();
    const llmModel = getModelSelectValue('recall-llm-model', 'recall-llm-model-custom');
    
    const configData = {};
    
    // 只有当输入的不是掩码值时才更新 API Key
    if (llmKey && !llmKey.includes('****')) {
        configData.llm_api_key = llmKey;
    }
    if (llmBase) configData.llm_api_base = llmBase;
    if (llmModel) configData.llm_model = llmModel;
    
    if (Object.keys(configData).length === 0) {
        alert('请填写配置项');
        return;
    }
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(`✅ LLM 配置已保存\n\n已更新: ${result.updated_fields.join(', ')}`);
            // 重新加载配置
            loadApiConfig();
        } else {
            alert(`❌ 保存失败: ${result.message}`);
        }
    } catch (e) {
        alert(`❌ 保存失败: ${e.message}`);
    }
}

/**
 * 加载伏笔分析器配置
 */
async function loadForeshadowingAnalyzerConfig() {
    const statusEl = document.getElementById('recall-analyzer-status');
    
    try {
        if (!pluginSettings.apiUrl) {
            if (statusEl) {
                statusEl.textContent = '未配置';
                statusEl.className = 'recall-api-status recall-status-error';
            }
            return;
        }
        
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/analyzer/config`);
        const result = await response.json();
        
        // 新的 API 返回 {success: true, config: {...}}
        if (result.success && result.config) {
            const config = result.config;
            
            // 填充表单
            const llmEnabledEl = document.getElementById('recall-llm-enabled');
            const triggerIntervalEl = document.getElementById('recall-trigger-interval');
            const autoPlantEl = document.getElementById('recall-auto-plant');
            const autoResolveEl = document.getElementById('recall-auto-resolve');
            
            if (llmEnabledEl) llmEnabledEl.checked = config.llm_enabled === true;
            if (triggerIntervalEl) triggerIntervalEl.value = config.trigger_interval || 10;
            if (autoPlantEl) autoPlantEl.checked = config.auto_plant !== false; // 默认 true
            if (autoResolveEl) autoResolveEl.checked = config.auto_resolve === true; // 默认 false
            
            // 更新状态显示
            if (statusEl) {
                if (config.llm_enabled) {
                    statusEl.textContent = 'LLM 模式';
                    statusEl.className = 'recall-api-status recall-status-ok';
                } else if (config.llm_configured) {
                    statusEl.textContent = '已就绪';
                    statusEl.className = 'recall-api-status recall-status-warning';
                } else {
                    statusEl.textContent = '未配置 LLM';
                    statusEl.className = 'recall-api-status recall-status-error';
                }
            }
            
            console.log('[Recall] 伏笔分析器配置已加载:', config);
        } else {
            if (statusEl) {
                statusEl.textContent = '加载失败';
                statusEl.className = 'recall-api-status recall-status-error';
            }
        }
    } catch (e) {
        console.error('[Recall] 加载伏笔分析器配置失败:', e);
        if (statusEl) {
            statusEl.textContent = '连接失败';
            statusEl.className = 'recall-api-status recall-status-error';
        }
    }
}

/**
 * 保存伏笔分析器配置
 */
async function onSaveForeshadowingAnalyzerConfig() {
    const llmEnabled = document.getElementById('recall-llm-enabled').checked;
    const triggerInterval = parseInt(document.getElementById('recall-trigger-interval').value) || 10;
    const autoPlant = document.getElementById('recall-auto-plant').checked;
    const autoResolve = document.getElementById('recall-auto-resolve').checked;
    
    // 验证触发间隔
    if (triggerInterval < 1 || triggerInterval > 100) {
        alert('❌ 分析触发间隔必须在 1-100 之间');
        return;
    }
    
    const configData = {
        llm_enabled: llmEnabled,
        trigger_interval: triggerInterval,
        auto_plant: autoPlant,
        auto_resolve: autoResolve
    };
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/analyzer/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            const modeText = llmEnabled ? 'LLM 自动分析' : '手动模式';
            alert(`✅ 伏笔分析器配置已保存\n\n模式: ${modeText}\n触发间隔: 每 ${triggerInterval} 轮\n自动埋伏笔: ${autoPlant ? '是' : '否'}\n自动解决: ${autoResolve ? '是' : '否'}`);
            
            // 刷新配置显示
            loadForeshadowingAnalyzerConfig();
        } else {
            alert(`❌ 保存失败: ${result.message}`);
        }
    } catch (e) {
        alert(`❌ 保存失败: ${e.message}`);
    }
}

// ==================== 绝对规则功能（ST 补充功能） ====================

/**
 * 加载绝对规则
 * 注：角色卡/世界观/写作风格请使用 SillyTavern 自带功能
 */
async function loadCoreSettings() {
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/core-settings`);
        if (response.ok) {
            const data = await response.json();
            
            // 只加载绝对规则（其他设定请用 ST 自带功能）
            const rulesArray = data.absolute_rules || [];
            document.getElementById('recall-core-rules').value = rulesArray.join('\n');
            
            console.log('[Recall] 绝对规则已加载');
        } else {
            console.error('[Recall] 加载绝对规则失败:', response.status);
        }
    } catch (e) {
        console.error('[Recall] 加载绝对规则失败:', e);
    }
}

/**
 * 保存绝对规则
 * 注：只更新 absolute_rules 字段，不覆盖其他设定
 * 后端 API 支持部分更新，未传递的字段不会被清空
 */
async function saveCoreSettings() {
    const rulesText = document.getElementById('recall-core-rules').value.trim();
    
    // 解析绝对规则（每行一条，过滤空行）
    const absoluteRules = rulesText
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);
    
    // 只发送 absolute_rules 字段，不影响其他设定
    const settingsData = {
        absolute_rules: absoluteRules.length > 0 ? absoluteRules : []
    };
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/core-settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsData)
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`✅ 绝对规则已保存\n\n共 ${(result.absolute_rules || []).length} 条规则`);
            console.log('[Recall] 绝对规则已保存');
        } else {
            const error = await response.json().catch(() => ({}));
            alert(`❌ 保存绝对规则失败: ${error.detail || '未知错误'}`);
        }
    } catch (e) {
        alert(`❌ 保存绝对规则失败: ${e.message}`);
    }
}

// ==================== 伏笔分析触发 ====================

/**
 * 手动触发伏笔分析
 */
async function triggerForeshadowingAnalysis() {
    const userId = encodeURIComponent(currentCharacterId || 'default');
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/analyze/trigger?user_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            
            let message = '🔍 伏笔分析完成\n\n';
            
            if (result.triggered) {
                if (result.new_foreshadowings && result.new_foreshadowings.length > 0) {
                    message += `✨ 发现 ${result.new_foreshadowings.length} 个新伏笔\n`;
                    result.new_foreshadowings.forEach((f, i) => {
                        message += `  ${i + 1}. ${f.content || f}\n`;
                    });
                } else {
                    message += '未发现新伏笔\n';
                }
                
                if (result.potentially_resolved && result.potentially_resolved.length > 0) {
                    message += `\n🎯 可能已解决的伏笔: ${result.potentially_resolved.length} 个\n`;
                }
            } else {
                message += '分析器未触发（可能 LLM 未配置或无足够对话内容）';
                if (result.error) {
                    message += `\n错误: ${result.error}`;
                }
            }
            
            alert(message);
            
            // 刷新伏笔列表
            loadForeshadowings();
        } else {
            const error = await response.json().catch(() => ({}));
            alert(`❌ 触发伏笔分析失败: ${error.detail || '未知错误'}`);
        }
    } catch (e) {
        alert(`❌ 触发伏笔分析失败: ${e.message}`);
    }
}

// ==================== 系统管理功能 ====================

/**
 * 热更新服务端配置
 */
async function reloadServerConfig() {
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config/reload`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`✅ 配置已热更新\n\n${result.message || '配置重新加载成功'}`);
            
            // 重新加载前端配置
            loadApiConfig();
        } else {
            const error = await response.json().catch(() => ({}));
            alert(`❌ 热更新失败: ${error.detail || '未知错误'}`);
        }
    } catch (e) {
        alert(`❌ 热更新失败: ${e.message}`);
    }
}

/**
 * 整合记忆
 */
async function consolidateMemories() {
    const userId = encodeURIComponent(currentCharacterId || 'default');
    
    if (!confirm('确定要整合当前角色的记忆吗？\n\n这将触发记忆整合流程，可能需要一些时间。')) {
        return;
    }
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/consolidate?user_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`✅ 记忆整合完成\n\n${result.message || '整合成功'}`);
            
            // 刷新记忆列表
            loadMemories();
        } else {
            const error = await response.json().catch(() => ({}));
            alert(`❌ 整合失败: ${error.detail || '未知错误'}`);
        }
    } catch (e) {
        alert(`❌ 整合失败: ${e.message}`);
    }
}

/**
 * 显示系统统计
 */
async function showSystemStats() {
    const statsDisplay = document.getElementById('recall-stats-display');
    const statsContent = document.getElementById('recall-stats-content');
    
    if (!statsDisplay || !statsContent) return;
    
    // 切换显示状态
    if (statsDisplay.style.display === 'none') {
        statsDisplay.style.display = 'block';
        statsContent.innerHTML = '<div style="text-align:center;padding:10px;">⏳ 加载中...</div>';
        
        try {
            const response = await fetch(`${pluginSettings.apiUrl}/v1/stats`);
            
            if (response.ok) {
                const stats = await response.json();
                
                let html = '<div class="recall-stats-grid">';
                
                // 全局统计
                const globalStats = stats.global || {};
                html += `<div class="recall-stat-item"><span class="recall-stat-label">总记忆数</span><span class="recall-stat-value">${globalStats.total_memories || 0}</span></div>`;
                html += `<div class="recall-stat-item"><span class="recall-stat-label">活跃伏笔</span><span class="recall-stat-value">${globalStats.active_foreshadowings || 0}</span></div>`;
                html += `<div class="recall-stat-item"><span class="recall-stat-label">实体数</span><span class="recall-stat-value">${globalStats.consolidated_entities || 0}</span></div>`;
                html += `<div class="recall-stat-item"><span class="recall-stat-label">作用域</span><span class="recall-stat-value">${globalStats.total_scopes || 1}</span></div>`;
                
                // 模式信息
                if (stats.lightweight !== undefined) {
                    html += `<div class="recall-stat-item"><span class="recall-stat-label">运行模式</span><span class="recall-stat-value">${stats.lightweight ? '轻量' : '完整'}</span></div>`;
                }
                
                // 索引状态
                const indexStats = stats.indexes || {};
                const indexCount = [indexStats.entity_index, indexStats.inverted_index, indexStats.vector_index, indexStats.ngram_index].filter(Boolean).length;
                html += `<div class="recall-stat-item"><span class="recall-stat-label">活跃索引</span><span class="recall-stat-value">${indexCount}/4</span></div>`;
                
                html += '</div>';
                
                statsContent.innerHTML = html;
            } else {
                statsContent.innerHTML = '<div style="color:#ff6b6b;">❌ 获取统计信息失败</div>';
            }
        } catch (e) {
            statsContent.innerHTML = `<div style="color:#ff6b6b;">❌ ${e.message}</div>`;
        }
    } else {
        statsDisplay.style.display = 'none';
    }
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
            loadPersistentContexts();
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
    console.log('[Recall] 正在连接:', pluginSettings.apiUrl);
    
    // 检查是否有混合内容问题 (HTTPS 页面请求 HTTP API)
    const isPageHttps = window.location.protocol === 'https:';
    const isApiHttp = pluginSettings.apiUrl.startsWith('http://');
    if (isPageHttps && isApiHttp) {
        console.warn('[Recall] ⚠️ 检测到混合内容问题：当前页面是 HTTPS，但 API 地址是 HTTP');
        console.warn('[Recall] 浏览器可能会阻止此请求。请考虑：1) 使用 Nginx 反代并启用 HTTPS；2) 使用 HTTP 访问 SillyTavern');
    }
    
    try {
        // 添加超时控制（5秒）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        const response = await fetch(`${pluginSettings.apiUrl}/health`, {
            signal: controller.signal,
            mode: 'cors'
        });
        clearTimeout(timeoutId);
        
        if (response.ok) {
            const wasConnected = isConnected;
            isConnected = true;
            updateConnectionStatus(true);
            console.log('[Recall] API 连接成功');
            
            // 如果是首次连接成功
            if (!wasConnected) {
                // 加载 API 配置（从服务器获取已配置的值）
                loadApiConfig();
                
                // 加载记忆
                if (currentCharacterId) {
                    loadMemories();
                    loadForeshadowings();
                }
                
                // 【新增】同步本地缓存的记忆（解决离线期间的保存）
                memorySaveQueue.syncLocalStorage();
            }
        } else {
            throw new Error(`API 响应异常: ${response.status}`);
        }
    } catch (e) {
        isConnected = false;
        updateConnectionStatus(false);
        
        let errMsg = e.message;
        let helpTip = '';
        
        if (e.name === 'AbortError') {
            errMsg = '连接超时（5秒）';
            helpTip = '请检查 Recall 服务是否启动';
        } else if (e.name === 'TypeError' && e.message.includes('Failed to fetch')) {
            errMsg = '无法连接';
            // 提供针对性的帮助信息
            const currentHost = window.location.hostname;
            if (isPageHttps && isApiHttp) {
                helpTip = `浏览器阻止了混合内容请求。建议：使用 http://${currentHost} 访问 SillyTavern`;
            } else if (pluginSettings.apiUrl.includes('127.0.0.1') || pluginSettings.apiUrl.includes('localhost')) {
                if (currentHost !== 'localhost' && currentHost !== '127.0.0.1') {
                    helpTip = `当前从 ${currentHost} 访问，但 API 指向本地。请到设置中修改 API 地址为 http://${currentHost}:18888`;
                } else {
                    helpTip = '请确认 Recall 服务已启动（python -m recall.server）';
                }
            } else {
                helpTip = '请检查 Recall 服务是否启动，以及网络连接是否正常';
            }
        }
        
        console.error(`[Recall] API 连接失败 (${pluginSettings.apiUrl}): ${errMsg}`);
        if (helpTip) {
            console.warn(`[Recall] 💡 提示: ${helpTip}`);
        }
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
    
    // 处理 API URL：如果用户清空了，自动检测
    const inputUrl = document.getElementById('recall-api-url')?.value?.trim();
    pluginSettings.apiUrl = inputUrl || detectApiUrl();
    
    pluginSettings.autoInject = document.getElementById('recall-auto-inject')?.checked ?? true;
    pluginSettings.filterThinking = document.getElementById('recall-filter-thinking')?.checked ?? true;
    pluginSettings.autoChunkLongText = document.getElementById('recall-auto-chunk')?.checked ?? true;
    pluginSettings.chunkSize = parseInt(document.getElementById('recall-chunk-size')?.value) || 2000;
    pluginSettings.previewLength = parseInt(document.getElementById('recall-preview-length')?.value) || 200;
    pluginSettings.maxMemories = parseInt(document.getElementById('recall-max-memories')?.value) || 10;
    pluginSettings.maxContextTokens = parseInt(document.getElementById('recall-max-context-tokens')?.value) || 2000;
    pluginSettings.injectPosition = document.getElementById('recall-inject-position')?.value || 'in_chat';
    pluginSettings.injectDepth = parseInt(document.getElementById('recall-inject-depth')?.value) || 1;
    
    saveSettings();
    
    // 更新输入框显示检测到的地址
    const apiUrlInput = document.getElementById('recall-api-url');
    if (apiUrlInput) apiUrlInput.value = pluginSettings.apiUrl;
    
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
        
        // 搜索结果不分页，隐藏"加载更多"按钮
        hasMoreMemories = false;
        updateLoadMoreButton();
        
        // 更新显示的数量（搜索结果数）
        updateStats(results.length);
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
 * 添加持久条件
 */
async function onAddPersistentContext() {
    const content = document.getElementById('recall-context-input')?.value;
    const contextType = document.getElementById('recall-context-type-select')?.value || 'custom';
    
    if (!content || !isConnected) return;
    
    await addPersistentContext(content, contextType);
    document.getElementById('recall-context-input').value = '';
}

/**
 * 通知伏笔分析器处理新的一轮对话
 * 【非阻塞】: 使用 fire-and-forget 模式，不等待服务器响应
 * 服务器会在后台异步执行 LLM 分析，不阻塞 UI
 * @param {string} content 消息内容
 * @param {string} role 角色 ('user' 或 'assistant')
 */
function notifyForeshadowingAnalyzer(content, role) {
    // Fire-and-forget: 发送请求但不等待响应
    fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/analyze/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            content: content,
            role: role,
            user_id: currentCharacterId || 'default'
        })
    }).then(response => {
        if (!response.ok) {
            console.debug('[Recall] 伏笔分析通知发送失败:', response.status);
        }
        // 不处理响应内容，服务器会在后台异步处理
        // 如果需要刷新伏笔列表，可以通过定时器或手动刷新
    }).catch(e => {
        // 静默失败，不影响主流程
        console.debug('[Recall] 伏笔分析器通知失败:', e.message);
    });
}

// ==================== 记忆保存队列（解决 API 限流问题） ====================

/**
 * 记忆保存队列 - 防止 API 限流
 * 使用队列 + 延迟批量处理，减少 API 调用次数
 */
const memorySaveQueue = {
    queue: [],           // 待保存的记忆队列
    isProcessing: false, // 是否正在处理
    minInterval: 1000,   // 最小处理间隔（毫秒）
    lastSaveTime: 0,     // 上次保存时间
    retryQueue: [],      // 重试队列（保存失败的记忆）
    maxRetries: 3,       // 最大重试次数
    
    /**
     * 添加记忆到队列
     * @param {Object} memory 记忆对象 {content, user_id, metadata}
     * @returns {Promise} 完成时 resolve
     */
    add(memory) {
        return new Promise((resolve, reject) => {
            this.queue.push({
                memory,
                resolve,
                reject,
                retries: 0,
                addedAt: Date.now()
            });
            this._scheduleProcess();
        });
    },
    
    /**
     * 调度处理
     */
    _scheduleProcess() {
        if (this.isProcessing) return;
        
        const now = Date.now();
        const timeSinceLastSave = now - this.lastSaveTime;
        const delay = Math.max(0, this.minInterval - timeSinceLastSave);
        
        setTimeout(() => this._process(), delay);
    },
    
    /**
     * 处理队列中的记忆
     */
    async _process() {
        if (this.isProcessing || this.queue.length === 0) return;
        
        this.isProcessing = true;
        this.lastSaveTime = Date.now();
        
        // 取出一条记忆
        const item = this.queue.shift();
        
        try {
            const response = await fetch(`${pluginSettings.apiUrl}/v1/memories`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(item.memory)
            });
            
            if (response.ok) {
                // 【修复】解析服务器返回的实际结果，检查是否真的保存成功
                const result = await response.json();
                if (result.success) {
                    item.resolve({ success: true, id: result.id });
                    console.log('[Recall] 记忆保存成功（队列处理）');
                } else {
                    // 服务器返回成功状态码，但业务上未保存（如重复内容）
                    item.resolve({ success: false, message: result.message });
                    console.log('[Recall] 记忆跳过:', result.message);
                }
            } else if (response.status === 429) {
                // API 限流，延长间隔并重试
                console.warn('[Recall] API 限流，将延迟重试');
                this.minInterval = Math.min(this.minInterval * 2, 10000); // 最多 10 秒
                item.retries++;
                if (item.retries < this.maxRetries) {
                    this.queue.unshift(item); // 放回队首
                } else {
                    // 保存到本地存储，等待下次启动时重试
                    this._saveToLocalStorage(item.memory);
                    item.resolve({ success: false, queued: true });
                }
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (e) {
            console.warn('[Recall] 记忆保存失败:', e.message);
            item.retries++;
            if (item.retries < this.maxRetries) {
                this.queue.push(item); // 放回队尾
            } else {
                // 保存到本地存储
                this._saveToLocalStorage(item.memory);
                item.resolve({ success: false, queued: true });
            }
        }
        
        this.isProcessing = false;
        
        // 继续处理队列
        if (this.queue.length > 0) {
            this._scheduleProcess();
        }
    },
    
    /**
     * 保存到本地存储（离线备份）
     */
    _saveToLocalStorage(memory) {
        try {
            const key = 'recall_pending_memories';
            const pending = JSON.parse(localStorage.getItem(key) || '[]');
            pending.push({
                ...memory,
                savedAt: Date.now()
            });
            // 最多保存 100 条
            if (pending.length > 100) {
                pending.shift();
            }
            localStorage.setItem(key, JSON.stringify(pending));
            console.log('[Recall] 记忆已缓存到本地，等待后续同步');
        } catch (e) {
            console.warn('[Recall] 本地缓存保存失败:', e);
        }
    },
    
    /**
     * 同步本地缓存的记忆
     */
    async syncLocalStorage() {
        try {
            const key = 'recall_pending_memories';
            const pending = JSON.parse(localStorage.getItem(key) || '[]');
            if (pending.length === 0) return;
            
            console.log(`[Recall] 发现 ${pending.length} 条待同步的本地记忆`);
            
            for (const memory of pending) {
                this.add(memory);
            }
            
            // 清空本地缓存
            localStorage.removeItem(key);
        } catch (e) {
            console.warn('[Recall] 同步本地缓存失败:', e);
        }
    }
};

/**
 * 消息发送时
 * 【优化】使用队列保存，不阻塞消息发送
 */
async function onMessageSent(messageIndex) {
    if (!pluginSettings.enabled || !isConnected) return;
    
    try {
        const context = SillyTavern.getContext();
        const chat = context.chat;
        const message = chat[messageIndex];
        
        if (!message || !message.mes) return;
        
        // 【关键改动】使用队列保存，不阻塞
        // 先将记忆加入队列，立即返回让消息显示
        memorySaveQueue.add({
            content: message.mes,
            user_id: currentCharacterId || 'default',
            metadata: { 
                role: 'user', 
                source: 'sillytavern',
                timestamp: Date.now()
            }
        }).then(result => {
            if (result.success) {
                console.log('[Recall] 已保存用户消息');
                // 【修复】只有记忆保存成功（非重复）才触发伏笔分析
                notifyForeshadowingAnalyzer(message.mes, 'user');
            } else if (result.queued) {
                console.log('[Recall] 用户消息已加入队列/本地缓存');
            } else {
                console.log('[Recall] 用户消息跳过（重复）');
            }
        });
    } catch (e) {
        console.warn('[Recall] 处理用户消息失败:', e);
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
 * 【优化】使用队列保存，不阻塞 AI 响应显示
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
        
        // 【修复】使用队列保存，并跟踪第一段的保存结果来决定是否触发伏笔分析
        const timestamp = Date.now();
        let firstChunkPromise = null;
        
        for (let i = 0; i < chunks.length; i++) {
            const chunk = chunks[i];
            const isMultiPart = chunks.length > 1;
            
            const promise = memorySaveQueue.add({
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
            });
            
            // 保存第一段的 Promise
            if (i === 0) {
                firstChunkPromise = promise;
            }
        }
        
        console.log(`[Recall] AI响应已加入保存队列 (${chunks.length}段, 共${contentToSave.length}字)`);
        
        // 【修复】等待第一段保存结果，只有成功（非重复）才触发伏笔分析
        if (firstChunkPromise) {
            firstChunkPromise.then(result => {
                if (result.success) {
                    // 记忆保存成功（非重复），触发伏笔分析
                    notifyForeshadowingAnalyzer(contentToSave, 'assistant');
                } else {
                    console.log('[Recall] AI响应跳过伏笔分析（重复内容）');
                }
            });
        }
    } catch (e) {
        console.warn('[Recall] 处理AI响应失败:', e);
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
    loadPersistentContexts();
}

/**
 * 生成前 - 注入记忆上下文
 * 使用 SillyTavern 的 setExtensionPrompt API 将记忆注入到 AI 提示词中
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
        
        if (memoryContext && memoryContext.trim().length > 0) {
            // 使用 SillyTavern 的 setExtensionPrompt API 注入记忆
            // position: 0 = IN_PROMPT (在系统提示后), 1 = IN_CHAT (在聊天历史中)
            // depth: 注入深度，0 表示最近的消息位置
            // scan: 是否参与世界信息扫描
            // role: 0 = SYSTEM, 1 = USER, 2 = ASSISTANT
            
            const position = getInjectionPosition();
            const depth = getInjectionDepth();
            
            context.setExtensionPrompt(
                'recall_memory',      // 唯一标识符
                memoryContext,         // 要注入的文本
                position,              // 注入位置
                depth,                 // 注入深度
                false,                 // 不参与 WI 扫描
                0                      // SYSTEM 角色
            );
            
            console.log('[Recall] 记忆已注入到提示词，长度:', memoryContext.length, '位置:', position, '深度:', depth);
        } else {
            // 如果没有记忆，清除之前的注入
            context.setExtensionPrompt('recall_memory', '', 0, 0, false, 0);
        }
    } catch (e) {
        console.warn('[Recall] 注入记忆上下文失败:', e);
    }
}

/**
 * 根据设置获取注入位置
 * @returns {number} 注入位置常量
 */
function getInjectionPosition() {
    switch (pluginSettings.injectPosition) {
        case 'in_chat':
            return 1;  // IN_CHAT - 在聊天历史中
        case 'before_system':
        case 'after_system':
        default:
            return 0;  // IN_PROMPT - 在系统提示区域
    }
}

/**
 * 根据设置获取注入深度
 * @returns {number} 注入深度
 */
function getInjectionDepth() {
    // depth 表示从最新消息算起的位置
    // 0 = 最新位置（在最后一条消息之后）
    // 1 = 倒数第二条消息后
    // 建议使用 1-4 的深度来确保记忆在相关上下文附近
    return pluginSettings.injectDepth || 1;
}

/**
 * 加载记忆列表
 */
async function loadMemories() {
    if (!isConnected) return;
    
    // 重置分页状态
    currentMemoryOffset = 0;
    
    try {
        // 添加超时控制（10秒）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);
        
        // 获取记忆列表（明确传入 offset=0）
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${encodeURIComponent(currentCharacterId || 'default')}&limit=${MEMORIES_PER_PAGE}&offset=0`,
            { signal: controller.signal }
        );
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        // 更新统计信息（使用 total 总数，而不是当前页的 count）
        updateStats(data.total || data.count || (data.memories ? data.memories.length : 0));
        
        // 更新角色名显示
        updateCharacterBadge();
        
        // 显示记忆
        displayMemories(data.memories || []);
        
        // 检查是否有更多（用 total 和 offset+count 比较，而不是简单判断返回数量）
        const loadedCount = (data.offset || 0) + (data.count || 0);
        hasMoreMemories = loadedCount < (data.total || 0);
        updateLoadMoreButton();
        
        console.log('[Recall] 记忆加载完成:', { count: data.count, total: data.total, hasMore: hasMoreMemories });
        
    } catch (e) {
        if (e.name === 'AbortError') {
            console.warn('[Recall] 加载记忆超时');
        } else {
            console.error('[Recall] 加载记忆失败:', e);
        }
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
let isLoadingMore = false;  // 防止重复点击
const MEMORIES_PER_PAGE = 20;

/**
 * 加载更多记忆
 */
async function onLoadMoreMemories() {
    if (!isConnected || isLoadingMore) return;
    
    isLoadingMore = true;
    const loadMoreBtn = document.getElementById('recall-load-more-btn');
    if (loadMoreBtn) loadMoreBtn.textContent = '加载中...';
    
    try {
        currentMemoryOffset += MEMORIES_PER_PAGE;
        
        // 添加超时控制（10秒）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);
        
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${encodeURIComponent(currentCharacterId || 'default')}&limit=${MEMORIES_PER_PAGE}&offset=${currentMemoryOffset}`,
            { signal: controller.signal }
        );
        clearTimeout(timeoutId);
        
        // 检查响应状态
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('[Recall] 加载更多响应:', { offset: currentMemoryOffset, count: data.count, total: data.total });
        
        if (data.memories && data.memories.length > 0) {
            appendMemories(data.memories);
            // 检查是否有更多（用 total 和 offset+count 比较）
            const loadedCount = (data.offset || 0) + (data.count || 0);
            hasMoreMemories = loadedCount < (data.total || 0);
        } else {
            hasMoreMemories = false;
        }
        
        updateLoadMoreButton();
    } catch (e) {
        console.error('[Recall] 加载更多记忆失败:', e);
        // 出错时回滚 offset
        currentMemoryOffset -= MEMORIES_PER_PAGE;
        // 显示错误提示
        const errMsg = e.name === 'AbortError' ? '请求超时，请检查网络连接' : e.message;
        toastr?.warning?.(`加载更多失败: ${errMsg}`, 'Recall') || console.warn(`加载更多失败: ${errMsg}`);
    } finally {
        isLoadingMore = false;
        // 重新获取按钮元素（防止 DOM 被重建导致引用失效）
        const btn = document.getElementById('recall-load-more-btn');
        if (btn) btn.textContent = '加载更多...';
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
            e.stopPropagation();
            const button = e.currentTarget;
            const id = button.dataset.id;
            if (id && confirm('确定删除这条记忆吗？')) {
                await deleteMemory(id);
            }
        });
    });
    
    // 绑定新添加项的展开/收起事件
    listEl.querySelectorAll('.recall-expand-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
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
        // 添加超时控制（8秒）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);
        
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing?user_id=${userId}`, {
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        displayForeshadowings(data);
        
        // 更新活跃伏笔计数
        const countEl = document.getElementById('recall-foreshadowing-count');
        if (countEl) {
            const activeCount = Array.isArray(data) ? data.filter(f => f.status === 'planted' || f.status === 'developing').length : 0;
            countEl.textContent = activeCount;
        }
    } catch (e) {
        const errMsg = e.name === 'AbortError' ? '请求超时' : e.message;
        console.error('[Recall] 加载伏笔失败:', errMsg);
    }
}

/**
 * 加载持久条件列表
 */
async function loadPersistentContexts() {
    if (!isConnected) return;
    
    try {
        // 添加超时控制（8秒）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);
        
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts?user_id=${userId}`, {
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        displayPersistentContexts(data);
        
        // 更新计数
        const countEl = document.getElementById('recall-context-count');
        if (countEl) countEl.textContent = data.length;
    } catch (e) {
        const errMsg = e.name === 'AbortError' ? '请求超时' : e.message;
        console.error('[Recall] 加载持久条件失败:', errMsg);
    }
}

/**
 * 显示持久条件列表
 */
function displayPersistentContexts(contexts) {
    const listEl = document.getElementById('recall-context-list');
    if (!listEl) return;
    
    if (!contexts || contexts.length === 0) {
        listEl.innerHTML = `
            <div class="recall-empty-state">
                <div class="recall-empty-icon">📌</div>
                <p>暂无持久条件</p>
                <small>对话中自动提取或手动添加</small>
            </div>
        `;
        return;
    }
    
    const typeNames = {
        'user_identity': '👤 身份',
        'user_goal': '🎯 目标',
        'user_preference': '❤️ 偏好',
        'environment': '💻 环境',
        'project': '📁 项目',
        'character_trait': '🎭 角色',
        'world_setting': '🌍 世界观',
        'relationship': '🤝 关系',
        'assumption': '💭 假设',
        'constraint': '⚠️ 约束',
        'custom': '📝 自定义'
    };
    
    listEl.innerHTML = contexts.map(ctx => `
        <div class="recall-context-item" data-id="${ctx.id}">
            <div class="recall-context-header">
                <span class="recall-context-type-badge ${ctx.context_type}">${typeNames[ctx.context_type] || ctx.context_type}</span>
                <span class="recall-context-confidence">置信度: ${(ctx.confidence * 100).toFixed(0)}%</span>
            </div>
            <p class="recall-context-content">${escapeHtml(ctx.content)}</p>
            <div class="recall-context-footer">
                <span>使用 ${ctx.use_count} 次</span>
                <button class="recall-delete-btn recall-remove-context" data-id="${ctx.id}">✕ 移除</button>
            </div>
        </div>
    `).join('');
    
    // 绑定移除按钮事件
    listEl.querySelectorAll('.recall-remove-context').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const button = e.currentTarget;
            const id = button.dataset.id;
            if (id && confirm('确定要移除这个持久条件吗？')) {
                await removePersistentContext(id);
            }
        });
    });
}

/**
 * 添加持久条件
 */
async function addPersistentContext(content, contextType) {
    if (!isConnected || !content.trim()) return;
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content.trim(),
                context_type: contextType,
                user_id: currentCharacterId || 'default'
            })
        });
        
        if (response.ok) {
            loadPersistentContexts();
            console.log(`[Recall] 持久条件已添加 (角色: ${currentCharacterId})`);
        } else {
            console.error('[Recall] 添加持久条件失败');
        }
    } catch (e) {
        console.error('[Recall] 添加持久条件失败:', e);
    }
}

/**
 * 移除持久条件
 */
async function removePersistentContext(contextId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}?user_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadPersistentContexts();
            console.log(`[Recall] 持久条件已移除 (角色: ${currentCharacterId})`);
        } else {
            console.error('[Recall] 移除持久条件失败');
        }
    } catch (e) {
        console.error('[Recall] 移除持久条件失败:', e);
    }
}

/**
 * 压缩合并持久条件
 */
async function consolidatePersistentContexts() {
    if (!isConnected) return;
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/consolidate?user_id=${userId}&force=true`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            loadPersistentContexts();
            if (result.reduced > 0) {
                console.log(`[Recall] 持久条件已压缩，减少了 ${result.reduced} 个`);
            } else {
                console.log('[Recall] 无需压缩');
            }
        }
    } catch (e) {
        console.error('[Recall] 压缩持久条件失败:', e);
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
    
    // 状态映射
    const statusDisplay = {
        'planted': '🌱 已埋下',
        'developing': '🌿 发展中',
        'resolved': '✓ 已解决',
        'abandoned': '✕ 已放弃'
    };
    
    listEl.innerHTML = foreshadowings.map(f => {
        const isActive = f.status === 'planted' || f.status === 'developing';
        return `
        <div class="recall-foreshadowing-item ${f.status}" data-id="${f.id}">
            <div class="recall-memory-header">
                <span class="recall-memory-role">${statusDisplay[f.status] || f.status}</span>
                <span class="recall-memory-time">重要性: ${(f.importance * 100).toFixed(0)}%</span>
            </div>
            <p class="recall-foreshadowing-content">${escapeHtml(f.content)}</p>
            <div class="recall-memory-footer">
                <span></span>
                <div class="recall-foreshadowing-actions">
                    ${isActive ? `<button class="recall-action-btn recall-resolve-foreshadowing" data-id="${f.id}" title="标记为已解决">✓ 解决</button>` : ''}
                    ${isActive ? `<button class="recall-delete-btn recall-abandon-foreshadowing" data-id="${f.id}" title="放弃此伏笔">✕ 删除</button>` : '<span class="recall-memory-score">已完成</span>'}
                </div>
            </div>
        </div>
        `;
    }).join('');
    
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
    
    // 绑定删除/放弃按钮事件
    listEl.querySelectorAll('.recall-abandon-foreshadowing').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const button = e.currentTarget;
            const id = button.dataset.id;
            if (id && confirm('确定要放弃此伏笔吗？\n放弃后伏笔将被标记为"已放弃"状态。')) {
                await abandonForeshadowing(id);
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
 * 放弃/删除伏笔
 */
async function abandonForeshadowing(foreshadowingId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}?user_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadForeshadowings();
            console.log(`[Recall] 伏笔已放弃 (角色: ${currentCharacterId})`);
        } else {
            const error = await response.json().catch(() => ({}));
            console.error('[Recall] 放弃伏笔失败:', error.detail || '未知错误');
        }
    } catch (e) {
        console.error('[Recall] 放弃伏笔失败:', e);
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
                max_tokens: pluginSettings.maxContextTokens || 2000,
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
    loadPersistentContexts: safeExecute(loadPersistentContexts, '加载持久条件失败'),
    isConnected: () => isConnected,
    isInitialized: () => isInitialized,
    getSettings: () => ({ ...pluginSettings })
};

})(); // IIFE 结束
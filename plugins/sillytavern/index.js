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
     * 
     * 支持两种部署模式：
     * 1. 端口模式: http://域名:18888（直接暴露端口）
     * 2. 路径模式: http://域名/recall（通过 Nginx 等反向代理）
     * 
     * 检测优先级：
     * 1. 尝试 /recall 路径（反向代理模式）
     * 2. 尝试 :18888 端口（直接端口模式）
     * 3. localhost:18888（本地开发）
     */
    function detectApiUrl() {
        const currentHost = window.location.hostname;
        const currentProtocol = window.location.protocol;
        const currentPort = window.location.port;
        
        // 本地开发环境
        if (!currentHost || currentHost === 'localhost' || currentHost === '127.0.0.1') {
            return 'http://127.0.0.1:18888';
        }
        
        // 通过域名访问，构建基础 URL
        // 优先使用路径模式（适配反向代理）
        const baseUrl = `${currentProtocol}//${currentHost}${currentPort ? ':' + currentPort : ''}`;
        return `${baseUrl}/recall`;
    }
    
    /**
     * 探测 API 地址是否可用
     */
    async function probeApiUrl(url) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 3000);
            
            const response = await fetch(`${url}/health`, {
                method: 'GET',
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            return response.ok;
        } catch (e) {
            return false;
        }
    }
    
    /**
     * 智能连接：自动探测可用的 API 地址
     */
    async function smartConnect() {
        const currentHost = window.location.hostname;
        const currentProtocol = window.location.protocol;
        const currentPort = window.location.port;
        
        // 本地环境直接使用默认地址
        if (!currentHost || currentHost === 'localhost' || currentHost === '127.0.0.1') {
            return 'http://127.0.0.1:18888';
        }
        
        const baseUrl = `${currentProtocol}//${currentHost}${currentPort ? ':' + currentPort : ''}`;
        
        // 候选 URL 列表（按优先级）
        const candidates = [
            `${baseUrl}/recall`,              // 路径模式（反向代理）
            `http://${currentHost}:18888`,    // 端口模式（HTTP）
            `https://${currentHost}:18888`,   // 端口模式（HTTPS）
        ];
        
        for (const url of candidates) {
            console.log(`[Recall] 探测 API 地址: ${url}`);
            if (await probeApiUrl(url)) {
                console.log(`[Recall] ✓ 找到可用地址: ${url}`);
                return url;
            }
        }
        
        // 都失败，返回第一个候选（让用户手动配置）
        console.log(`[Recall] ✗ 未找到可用地址，使用默认: ${candidates[0]}`);
        return candidates[0];
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
     * 🔧 调试函数：测试 API 连接
     * 可在浏览器控制台执行: window.recallDebug.testApi()
     */
    window.recallDebug = {
        testApi: async function(endpoint = '/v1/persistent-contexts') {
            const userId = encodeURIComponent(currentCharacterId || 'default');
            const url = `${pluginSettings.apiUrl}${endpoint}?user_id=${userId}&character_id=${userId}`;
            console.log(`[Recall Debug] 测试 API: ${url}`);
            console.log(`[Recall Debug] 当前角色: ${currentCharacterId}`);
            console.log(`[Recall Debug] isConnected: ${isConnected}`);
            
            const startTime = Date.now();
            try {
                const response = await fetch(url, { mode: 'cors' });
                const elapsed = Date.now() - startTime;
                console.log(`[Recall Debug] 响应状态: ${response.status}, 耗时: ${elapsed}ms`);
                const data = await response.json();
                console.log(`[Recall Debug] 响应数据:`, data);
                return { success: true, elapsed, data };
            } catch (e) {
                const elapsed = Date.now() - startTime;
                console.error(`[Recall Debug] 请求失败:`, e);
                console.error(`[Recall Debug] 耗时: ${elapsed}ms`);
                return { success: false, elapsed, error: e.message };
            }
        },
        getState: function() {
            return {
                apiUrl: pluginSettings.apiUrl,
                isConnected,
                currentCharacterId,
                isInitialized
            };
        }
    };

    /**
     * 安全的 toastr 包装对象
     * 避免在 toastr 未加载时报错
     */
    const safeToastr = {
        success: (msg, title, options) => {
            if (typeof toastr !== 'undefined' && toastr.success) {
                toastr.success(msg, title, options);
            } else {
                console.log(`[Recall] ✓ ${title || 'Success'}: ${msg}`);
            }
        },
        error: (msg, title, options) => {
            if (typeof toastr !== 'undefined' && toastr.error) {
                toastr.error(msg, title, options);
            } else {
                console.error(`[Recall] ✗ ${title || 'Error'}: ${msg}`);
            }
        },
        warning: (msg, title, options) => {
            if (typeof toastr !== 'undefined' && toastr.warning) {
                toastr.warning(msg, title, options);
            } else {
                console.warn(`[Recall] ⚠ ${title || 'Warning'}: ${msg}`);
            }
        },
        info: (msg, title, options) => {
            if (typeof toastr !== 'undefined' && toastr.info) {
                toastr.info(msg, title, options);
            } else {
                console.info(`[Recall] ℹ ${title || 'Info'}: ${msg}`);
            }
        }
    };

    /**
     * 后台任务追踪器
     * 用于在前端面板显示后台操作的进度
     */
    const taskTracker = {
        tasks: new Map(),  // taskId -> {type, title, detail, status, startTime}
        taskIdCounter: 0,
        
        /**
         * 添加任务
         * @param {string} type - 任务类型: 'memory_save', 'foreshadowing_analysis', 'sync', 'config_load'
         * @param {string} title - 任务标题
         * @param {string} detail - 详情（可选）
         * @returns {number} taskId
         */
        add(type, title, detail = '') {
            const taskId = ++this.taskIdCounter;
            this.tasks.set(taskId, {
                type,
                title,
                detail,
                status: 'running',  // 'pending', 'running', 'success', 'error'
                startTime: Date.now()
            });
            this._updateUI();
            return taskId;
        },
        
        /**
         * 更新任务状态
         */
        update(taskId, updates) {
            const task = this.tasks.get(taskId);
            if (task) {
                Object.assign(task, updates);
                this._updateUI();
            }
        },
        
        /**
         * 完成任务
         */
        complete(taskId, success = true, detail = '') {
            const task = this.tasks.get(taskId);
            if (task) {
                task.status = success ? 'success' : 'error';
                if (detail) task.detail = detail;
                this._updateUI();
                
                // 成功的任务 2 秒后移除，失败的任务 5 秒后移除
                setTimeout(() => {
                    this.tasks.delete(taskId);
                    this._updateUI();
                }, success ? 2000 : 5000);
            }
        },
        
        /**
         * 获取当前活跃任务数
         */
        getActiveCount() {
            let count = 0;
            for (const task of this.tasks.values()) {
                if (task.status === 'pending' || task.status === 'running') {
                    count++;
                }
            }
            return count;
        },
        
        /**
         * 更新 UI
         */
        _updateUI() {
            const indicator = document.getElementById('recall-tasks-indicator');
            const countEl = document.getElementById('recall-tasks-count');
            const listEl = document.getElementById('recall-tasks-list');
            
            if (!indicator) return;
            
            const activeCount = this.getActiveCount();
            const totalCount = this.tasks.size;
            
            // 更新指示器
            if (totalCount > 0) {
                indicator.style.display = 'inline-flex';
                if (countEl) countEl.textContent = activeCount > 0 ? activeCount : '✓';
            } else {
                indicator.style.display = 'none';
            }
            
            // 更新任务列表
            if (listEl) {
                if (this.tasks.size === 0) {
                    listEl.innerHTML = '<div class="recall-task-empty">暂无后台任务</div>';
                } else {
                    const taskHtml = [];
                    for (const [id, task] of this.tasks) {
                        const icon = this._getIcon(task.type, task.status);
                        const statusText = this._getStatusText(task.status);
                        const elapsed = Math.round((Date.now() - task.startTime) / 1000);
                        
                        taskHtml.push(`
                            <div class="recall-task-item" data-task-id="${id}">
                                <span class="recall-task-icon ${task.status === 'running' ? 'spinning' : ''}">${icon}</span>
                                <div class="recall-task-content">
                                    <div class="recall-task-title">${task.title}</div>
                                    ${task.detail ? `<div class="recall-task-detail">${task.detail}</div>` : ''}
                                </div>
                                <span class="recall-task-status ${task.status}">${statusText}${task.status === 'running' ? ` ${elapsed}s` : ''}</span>
                            </div>
                        `);
                    }
                    listEl.innerHTML = taskHtml.join('');
                }
            }
        },
        
        _getIcon(type, status) {
            if (status === 'success') return '✓';
            if (status === 'error') return '✗';
            
            switch (type) {
                case 'memory-save': return '💾';
                case 'foreshadow': return '🔮';
                case 'sync': return '🔄';
                case 'config': return '⚙️';
                case 'load': return '📥';
                default: return '📋';
            }
        },
        
        _getStatusText(status) {
            switch (status) {
                case 'pending': return '等待';
                case 'running': return '处理中';
                case 'success': return '完成';
                case 'error': return '失败';
                default: return status;
            }
        }
    };

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
            
            // 检查保存的 apiUrl 是否与当前访问的服务器匹配
            // 如果不匹配，说明可能是从其他设备同步过来的旧设置，需要重新检测
            const currentHost = window.location.hostname;
            const savedUrl = pluginSettings.apiUrl || '';
            const savedHost = savedUrl.match(/\/\/([^:/]+)/)?.[1] || '';
            
            // 如果保存的地址与当前访问的服务器不同，重新检测
            // 例如：保存的是 utophoria.top 但现在访问的是 192.168.1.100
            if (!pluginSettings.apiUrl || 
                (savedHost && savedHost !== currentHost && 
                 savedHost !== 'localhost' && savedHost !== '127.0.0.1' &&
                 currentHost !== 'localhost' && currentHost !== '127.0.0.1')) {
                const newUrl = detectApiUrl();
                console.log(`[Recall] API 地址不匹配，重新检测: ${savedUrl} -> ${newUrl}`);
                pluginSettings.apiUrl = newUrl;
                saveSettings();
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
                    <!-- 后台任务指示器（点击展开详情） -->
                    <span id="recall-tasks-indicator" class="recall-tasks-indicator" style="display:none" title="点击查看后台任务">
                        <i class="fa-solid fa-spinner fa-spin"></i>
                        <span id="recall-tasks-count">0</span>
                    </span>
                </div>
                
                <!-- 后台任务面板（默认隐藏） -->
                <div id="recall-tasks-panel" class="recall-tasks-panel">
                    <div class="recall-tasks-header">
                        <span>📋 后台任务</span>
                        <button id="recall-tasks-close" class="recall-icon-btn" title="关闭">✕</button>
                    </div>
                    <div id="recall-tasks-list" class="recall-tasks-list">
                        <div class="recall-task-empty">暂无后台任务</div>
                    </div>
                </div>
                
                <!-- 标签页导航 -->
                <div class="recall-tabs recall-tabs-scrollable">
                    <button class="recall-tab active" data-tab="memories">📚 记忆</button>
                    <button class="recall-tab" data-tab="entities">🏷️ 实体</button>
                    <button class="recall-tab" data-tab="contexts">📌 条件</button>
                    <button class="recall-tab" data-tab="foreshadowing">🎭 伏笔</button>
                    <button class="recall-tab" data-tab="contradictions">⚔️ 矛盾</button>
                    <button class="recall-tab" data-tab="temporal">⏱️ 时态</button>
                    <button class="recall-tab" data-tab="graph">🕸️ 图谱</button>
                    <button class="recall-tab" data-tab="episodes">📖 片段</button>
                    <button class="recall-tab" data-tab="search">🔍 搜索</button>
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
                
                <!-- 实体管理标签页 -->
                <div id="recall-tab-entities" class="recall-tab-content">
                    <div class="recall-stats-row">
                        <span>🏷️ 实体数: <strong id="recall-entity-count">0</strong></span>
                        <div class="recall-stats-actions">
                            <button id="recall-refresh-entities-btn" class="recall-icon-btn" title="刷新">🔄</button>
                        </div>
                    </div>
                    
                    <div class="recall-search-bar">
                        <input type="text" id="recall-entity-search-input" placeholder="🔍 搜索实体..." class="text_pole">
                        <select id="recall-entity-type-filter" class="text_pole" style="width:auto;min-width:80px;">
                            <option value="">全部类型</option>
                            <option value="PERSON">👤 人物</option>
                            <option value="LOCATION">📍 地点</option>
                            <option value="ORGANIZATION">🏢 组织</option>
                            <option value="OBJECT">📦 物品</option>
                            <option value="EVENT">📅 事件</option>
                            <option value="CONCEPT">💡 概念</option>
                        </select>
                    </div>
                    
                    <div id="recall-entity-list" class="recall-entity-list">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">🏷️</div>
                            <p>暂无实体</p>
                            <small>对话时会自动提取实体</small>
                        </div>
                    </div>
                    
                    <!-- 实体详情面板（点击实体展开） -->
                    <div id="recall-entity-detail-panel" class="recall-entity-detail-panel" style="display:none;">
                        <div class="recall-entity-detail-header">
                            <span id="recall-entity-detail-name">实体名称</span>
                            <button id="recall-entity-detail-close" class="recall-icon-btn">✕</button>
                        </div>
                        <div class="recall-entity-detail-content">
                            <div class="recall-entity-detail-section">
                                <div class="recall-entity-detail-label">类型</div>
                                <div id="recall-entity-detail-type">-</div>
                            </div>
                            <div class="recall-entity-detail-section">
                                <div class="recall-entity-detail-label">摘要</div>
                                <div id="recall-entity-detail-summary">-</div>
                                <button id="recall-generate-entity-summary" class="menu_button" style="margin-top:5px;">
                                    <i class="fa-solid fa-wand-magic-sparkles"></i> 生成摘要
                                </button>
                            </div>
                            <div class="recall-entity-detail-section">
                                <div class="recall-entity-detail-label">相关实体</div>
                                <div id="recall-entity-detail-relations">-</div>
                            </div>
                            <div class="recall-entity-detail-section">
                                <div class="recall-entity-detail-label">出现次数</div>
                                <div id="recall-entity-detail-count">-</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 持久条件标签页 -->
                <div id="recall-tab-contexts" class="recall-tab-content">
                    <!-- 子标签切换 -->
                    <div class="recall-sub-tabs">
                        <button class="recall-sub-tab active" data-subtab="contexts-active">活跃 (<span id="recall-context-count">0</span>)</button>
                        <button class="recall-sub-tab" data-subtab="contexts-archived">归档 (<span id="recall-context-archived-count">0</span>)</button>
                    </div>
                    
                    <!-- 活跃持久条件 -->
                    <div id="recall-subtab-contexts-active" class="recall-subtab-content active">
                        <div class="recall-stats-row">
                            <span>📌 活跃持久条件</span>
                            <div class="recall-stats-actions">
                                <button id="recall-refresh-contexts-btn" class="recall-icon-btn" title="刷新">🔄</button>
                                <button id="recall-consolidate-contexts-btn" class="recall-icon-btn" title="压缩合并">📦</button>
                                <button id="recall-clear-contexts-btn" class="recall-icon-btn recall-danger-icon" title="清空全部">🗑️</button>
                            </div>
                        </div>
                        
                        <div class="recall-setting-hint" style="margin-bottom:10px;">
                            持久条件是已确立的背景设定，会自动注入到每次对话中。
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
                    
                    <!-- 归档持久条件 -->
                    <div id="recall-subtab-contexts-archived" class="recall-subtab-content">
                        <div class="recall-stats-row">
                            <span>📦 归档持久条件</span>
                            <div class="recall-stats-actions">
                                <button id="recall-refresh-archived-contexts-btn" class="recall-icon-btn" title="刷新">🔄</button>
                                <button id="recall-clear-archived-contexts-btn" class="recall-icon-btn recall-danger-icon" title="清空归档">🗑️</button>
                            </div>
                        </div>
                        
                        <!-- 搜索和筛选 -->
                        <div class="recall-archive-toolbar">
                            <input type="text" id="recall-contexts-archive-search" placeholder="搜索..." class="text_pole" style="flex:1;">
                            <select id="recall-contexts-archive-filter" class="text_pole" style="width:auto;">
                                <option value="">全部类型</option>
                                <option value="user_identity">👤 身份</option>
                                <option value="user_goal">🎯 目标</option>
                                <option value="user_preference">❤️ 偏好</option>
                                <option value="environment">💻 环境</option>
                                <option value="project">📁 项目</option>
                                <option value="character_trait">🎭 角色</option>
                                <option value="world_setting">🌍 世界观</option>
                                <option value="relationship">🤝 关系</option>
                                <option value="custom">📝 自定义</option>
                            </select>
                            <select id="recall-contexts-archive-pagesize" class="text_pole" style="width:auto;">
                                <option value="20">20条/页</option>
                                <option value="50">50条/页</option>
                                <option value="100">100条/页</option>
                            </select>
                        </div>
                        
                        <div id="recall-archived-context-list" class="recall-context-list">
                            <div class="recall-empty-state">
                                <div class="recall-empty-icon">📦</div>
                                <p>暂无归档条件</p>
                            </div>
                        </div>
                        
                        <!-- 分页 -->
                        <div id="recall-contexts-archive-pagination" class="recall-pagination"></div>
                    </div>
                </div>
                
                <!-- 伏笔标签页 -->
                <div id="recall-tab-foreshadowing" class="recall-tab-content">
                    <!-- 子标签切换 -->
                    <div class="recall-sub-tabs">
                        <button class="recall-sub-tab active" data-subtab="foreshadowing-active">活跃 (<span id="recall-foreshadowing-count">0</span>)</button>
                        <button class="recall-sub-tab" data-subtab="foreshadowing-archived">归档 (<span id="recall-foreshadowing-archived-count">0</span>)</button>
                    </div>
                    
                    <!-- 活跃伏笔 -->
                    <div id="recall-subtab-foreshadowing-active" class="recall-subtab-content active">
                        <div class="recall-stats-row">
                            <span>🎭 活跃伏笔</span>
                            <div class="recall-stats-actions">
                                <button id="recall-refresh-foreshadowing-btn" class="recall-icon-btn" title="刷新">🔄</button>
                                <button id="recall-analyze-foreshadowing-btn" class="recall-icon-btn" title="手动分析">🔍</button>
                                <button id="recall-clear-foreshadowing-btn" class="recall-icon-btn recall-danger-icon" title="清空全部">🗑️</button>
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
                    
                    <!-- 归档伏笔 -->
                    <div id="recall-subtab-foreshadowing-archived" class="recall-subtab-content">
                        <div class="recall-stats-row">
                            <span>📦 归档伏笔</span>
                            <div class="recall-stats-actions">
                                <button id="recall-refresh-archived-foreshadowing-btn" class="recall-icon-btn" title="刷新">🔄</button>
                                <button id="recall-clear-archived-foreshadowing-btn" class="recall-icon-btn recall-danger-icon" title="清空归档">🗑️</button>
                            </div>
                        </div>
                        
                        <!-- 搜索和筛选 -->
                        <div class="recall-archive-toolbar">
                            <input type="text" id="recall-foreshadowing-archive-search" placeholder="搜索..." class="text_pole" style="flex:1;">
                            <select id="recall-foreshadowing-archive-filter" class="text_pole" style="width:auto;">
                                <option value="">全部状态</option>
                                <option value="resolved">✅ 已解决</option>
                                <option value="abandoned">❌ 已放弃</option>
                            </select>
                            <select id="recall-foreshadowing-archive-pagesize" class="text_pole" style="width:auto;">
                                <option value="20">20条/页</option>
                                <option value="50">50条/页</option>
                                <option value="100">100条/页</option>
                            </select>
                        </div>
                        
                        <div id="recall-archived-foreshadowing-list" class="recall-foreshadowing-list">
                            <div class="recall-empty-state">
                                <div class="recall-empty-icon">📦</div>
                                <p>暂无归档伏笔</p>
                            </div>
                        </div>
                        
                        <!-- 分页 -->
                        <div id="recall-foreshadowing-archive-pagination" class="recall-pagination"></div>
                    </div>
                </div>
                
                <!-- 矛盾检测标签页 -->
                <div id="recall-tab-contradictions" class="recall-tab-content">
                    <div class="recall-stats-row">
                        <span>⚔️ 矛盾数: <strong id="recall-contradiction-count">0</strong></span>
                        <div class="recall-stats-actions">
                            <button id="recall-refresh-contradictions-btn" class="recall-icon-btn" title="刷新">🔄</button>
                        </div>
                    </div>
                    
                    <div class="recall-setting-hint" style="margin-bottom:10px;">
                        系统自动检测到的事实矛盾，需要人工确认并解决。
                    </div>
                    
                    <div class="recall-filter-bar">
                        <select id="recall-contradiction-status-filter" class="text_pole" style="width:auto;">
                            <option value="">全部状态</option>
                            <option value="pending">⏳ 待处理</option>
                            <option value="resolved">✅ 已解决</option>
                            <option value="ignored">🚫 已忽略</option>
                        </select>
                    </div>
                    
                    <div id="recall-contradiction-list" class="recall-contradiction-list">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">⚔️</div>
                            <p>暂无矛盾</p>
                            <small>系统会自动检测事实冲突</small>
                        </div>
                    </div>
                    
                    <!-- 矛盾详情面板 -->
                    <div id="recall-contradiction-detail-panel" class="recall-contradiction-detail-panel" style="display:none;">
                        <div class="recall-entity-detail-header">
                            <span>矛盾详情</span>
                            <button id="recall-contradiction-detail-close" class="recall-icon-btn">✕</button>
                        </div>
                        <div class="recall-contradiction-detail-content">
                            <div class="recall-contradiction-fact">
                                <div class="recall-contradiction-fact-label">📄 事实 A</div>
                                <div id="recall-contradiction-fact-a">-</div>
                            </div>
                            <div class="recall-contradiction-vs">VS</div>
                            <div class="recall-contradiction-fact">
                                <div class="recall-contradiction-fact-label">📄 事实 B</div>
                                <div id="recall-contradiction-fact-b">-</div>
                            </div>
                            <div class="recall-contradiction-actions">
                                <button id="recall-resolve-keep-a" class="menu_button">保留 A</button>
                                <button id="recall-resolve-keep-b" class="menu_button">保留 B</button>
                                <button id="recall-resolve-keep-both" class="menu_button">保留两者</button>
                                <button id="recall-resolve-ignore" class="menu_button">忽略</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 时态查询标签页 -->
                <div id="recall-tab-temporal" class="recall-tab-content">
                    <div class="recall-info-box" style="margin-bottom:10px;">
                        <div class="recall-info-title">⏱️ 时态知识图谱</div>
                        <p>追踪事实随时间的变化，支持按时间点/范围查询历史状态。</p>
                    </div>
                    
                    <div class="recall-temporal-controls">
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">查询实体时间线</label>
                            <div class="recall-search-bar">
                                <input type="text" id="recall-temporal-entity-input" placeholder="输入实体名称..." class="text_pole">
                                <button id="recall-temporal-timeline-btn" class="menu_button" title="查询时间线">
                                    <i class="fa-solid fa-clock-rotate-left"></i>
                                </button>
                            </div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">时间范围查询</label>
                            <div class="recall-temporal-range">
                                <input type="datetime-local" id="recall-temporal-start" class="text_pole">
                                <span>至</span>
                                <input type="datetime-local" id="recall-temporal-end" class="text_pole">
                                <button id="recall-temporal-range-btn" class="menu_button" title="查询">
                                    <i class="fa-solid fa-search"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="recall-stats-row" style="margin-top:10px;">
                        <span>📊 时态统计</span>
                        <button id="recall-temporal-stats-btn" class="recall-icon-btn" title="刷新统计">🔄</button>
                    </div>
                    
                    <div id="recall-temporal-stats" class="recall-temporal-stats">
                        <div class="recall-stat-item"><span>时态记录数:</span> <strong id="recall-temporal-record-count">-</strong></div>
                        <div class="recall-stat-item"><span>时间跨度:</span> <strong id="recall-temporal-span">-</strong></div>
                    </div>
                    
                    <div id="recall-temporal-results" class="recall-temporal-results">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">⏱️</div>
                            <p>输入实体名称查询时间线</p>
                        </div>
                    </div>
                </div>
                
                <!-- 知识图谱标签页 -->
                <div id="recall-tab-graph" class="recall-tab-content">
                    <div class="recall-info-box" style="margin-bottom:10px;">
                        <div class="recall-info-title">🕸️ 知识图谱</div>
                        <p>可视化实体关系网络，探索图遍历和社区结构。</p>
                    </div>
                    
                    <div class="recall-graph-controls">
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">图遍历查询</label>
                            <div class="recall-search-bar">
                                <input type="text" id="recall-graph-entity-input" placeholder="输入起始实体..." class="text_pole">
                                <select id="recall-graph-depth" class="text_pole" style="width:auto;">
                                    <option value="1">深度 1</option>
                                    <option value="2" selected>深度 2</option>
                                    <option value="3">深度 3</option>
                                </select>
                                <button id="recall-graph-traverse-btn" class="menu_button" title="遍历">
                                    <i class="fa-solid fa-project-diagram"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="recall-stats-row" style="margin-top:10px;">
                        <span>🏘️ 社区检测</span>
                        <button id="recall-graph-communities-btn" class="recall-icon-btn" title="检测社区">🔍</button>
                    </div>
                    
                    <div id="recall-graph-results" class="recall-graph-results">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">🕸️</div>
                            <p>输入实体名称开始图遍历</p>
                        </div>
                    </div>
                    
                    <div id="recall-communities-list" class="recall-communities-list" style="display:none;">
                        <div class="recall-setting-title" style="margin-top:10px;">检测到的社区</div>
                        <div id="recall-communities-content"></div>
                    </div>
                </div>
                
                <!-- Episode 片段标签页 -->
                <div id="recall-tab-episodes" class="recall-tab-content">
                    <div class="recall-episode-header">
                        <span class="recall-episode-count-badge">📖 片段数: <span id="recall-episode-count">0</span></span>
                        <button id="recall-refresh-episodes-btn" class="menu_button menu_button_icon" title="刷新">
                            <i class="fa-solid fa-refresh"></i>
                        </button>
                    </div>
                    
                    <div class="recall-setting-hint" style="margin-bottom:10px;">
                        对话会自动组织成有意义的片段（Episode），帮助理解对话的上下文流程
                    </div>
                    
                    <div id="recall-episode-list" class="recall-episode-list">
                        <div class="recall-empty-state">
                            <div class="recall-empty-icon">📖</div>
                            <p>加载中...</p>
                        </div>
                    </div>
                    
                    <!-- Episode 详情面板 -->
                    <div id="recall-episode-detail-panel" class="recall-episode-detail-panel" style="display:none;">
                        <div class="recall-episode-detail-header">
                            <span class="recall-episode-detail-title">片段详情</span>
                            <button id="recall-episode-detail-close" class="recall-icon-btn">✕</button>
                        </div>
                        <div class="recall-episode-detail-content">
                            <div class="recall-episode-detail-row">
                                <span class="recall-episode-detail-label">ID:</span>
                                <span id="recall-episode-detail-id" class="recall-episode-detail-value">-</span>
                            </div>
                            <div class="recall-episode-detail-row">
                                <span class="recall-episode-detail-label">开始:</span>
                                <span id="recall-episode-detail-start" class="recall-episode-detail-value">-</span>
                            </div>
                            <div class="recall-episode-detail-row">
                                <span class="recall-episode-detail-label">结束:</span>
                                <span id="recall-episode-detail-end" class="recall-episode-detail-value">-</span>
                            </div>
                            <div class="recall-episode-detail-row">
                                <span class="recall-episode-detail-label">记忆数:</span>
                                <span id="recall-episode-detail-memory-count" class="recall-episode-detail-value">-</span>
                            </div>
                            <div style="margin-top:10px;">
                                <div class="recall-setting-title">包含的记忆</div>
                                <div id="recall-episode-memories" class="recall-episode-memories"></div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 高级搜索标签页 -->
                <div id="recall-tab-search" class="recall-tab-content">
                    <div class="recall-search-section">
                        <div class="recall-setting-title">🔍 高级搜索</div>
                        <div class="recall-setting-hint" style="margin-bottom:10px;">
                            提供比基础语义搜索更强大的搜索能力
                        </div>
                        
                        <!-- 搜索类型选择 -->
                        <div class="recall-search-type-tabs">
                            <button class="recall-search-type-tab active" data-type="hybrid">🔀 混合搜索</button>
                            <button class="recall-search-type-tab" data-type="fulltext">📝 全文搜索</button>
                            <button class="recall-search-type-tab" data-type="semantic">🧠 语义搜索</button>
                        </div>
                        
                        <div class="recall-advanced-search-bar">
                            <input type="text" id="recall-advanced-search-input" class="text_pole" 
                                   placeholder="输入搜索内容...">
                            <button id="recall-advanced-search-btn" class="menu_button">
                                <i class="fa-solid fa-search"></i> 搜索
                            </button>
                        </div>
                        
                        <!-- 搜索选项 -->
                        <div class="recall-search-options">
                            <div class="recall-search-option">
                                <label class="recall-setting-title">结果数量</label>
                                <input type="number" id="recall-search-limit" class="text_pole" 
                                       value="10" min="1" max="50" style="width:80px;">
                            </div>
                            <div class="recall-search-option" id="recall-hybrid-weight-option">
                                <label class="recall-setting-title">语义权重</label>
                                <input type="range" id="recall-hybrid-weight" min="0" max="1" step="0.1" value="0.6">
                                <span id="recall-hybrid-weight-value">0.6</span>
                            </div>
                        </div>
                        
                        <div class="recall-search-hints">
                            <div class="recall-setting-hint">
                                <strong>混合搜索:</strong> 结合语义+全文，RRF融合排序，效果最好<br>
                                <strong>全文搜索:</strong> 精确关键词匹配，适合搜索特定术语<br>
                                <strong>语义搜索:</strong> 理解含义相似度，适合模糊查询
                            </div>
                        </div>
                    </div>
                    
                    <div class="recall-search-results-section">
                        <div class="recall-setting-title" style="margin-top:15px;">
                            搜索结果 <span id="recall-search-result-count">(0)</span>
                        </div>
                        <div id="recall-advanced-search-results" class="recall-advanced-search-results">
                            <div class="recall-empty-state">
                                <div class="recall-empty-icon">🔍</div>
                                <p>输入关键词开始搜索</p>
                            </div>
                        </div>
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
                        <div id="recall-rule-mode-hint" class="recall-setting-hint" style="margin-top:8px; padding:6px; background:var(--SmartThemeBlurTintColor); border-radius:4px;">
                            🔍 检测模式: <span id="recall-rule-mode-text">检查中...</span>
                        </div>
                    </div>
                    
                    <div class="recall-settings-section">
                        <div class="recall-settings-section-title">⚠️ 绝对规则（每行一条）</div>
                        <div class="recall-setting-hint">这些规则会被强制注入，AI 必须遵守。保存内容时会自动检测违规并提醒。</div>
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
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-title">Embedding 模式</label>
                            <select id="recall-embedding-mode" class="text_pole">
                                <option value="">自动选择</option>
                                <option value="custom">自定义 API（推荐）</option>
                                <option value="siliconflow">硅基流动</option>
                                <option value="openai">OpenAI</option>
                                <option value="local">本地模型</option>
                                <option value="none">禁用（仅关键词搜索）</option>
                            </select>
                            <div class="recall-setting-hint">选择 Embedding 后端，自定义 API 适用于中转站等</div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <div style="font-weight:bold;margin-bottom:8px;">⚡ API 速率限制</div>
                            <div class="recall-setting-row" style="display:flex;gap:10px;">
                                <div style="flex:1;">
                                    <label class="recall-setting-title">最大请求数</label>
                                    <input type="number" id="recall-embedding-rate-limit" class="text_pole" 
                                           placeholder="60" min="1" max="1000">
                                </div>
                                <div style="flex:1;">
                                    <label class="recall-setting-title">时间窗口（秒）</label>
                                    <input type="number" id="recall-embedding-rate-window" class="text_pole" 
                                           placeholder="60" min="1" max="3600">
                                </div>
                            </div>
                            <div class="recall-setting-hint">限制 API 调用频率，适合免费或有配额限制的 API</div>
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
                    
                    <!-- v4.0/v4.1 高级功能配置 -->
                    <div class="recall-settings-section recall-api-section">
                        <div class="recall-settings-section-title">
                            🚀 高级功能配置 (v4.0+)
                        </div>
                        <div class="recall-setting-hint" style="margin-top:-5px;margin-bottom:10px;">这些是服务端配置，修改后需要点击"保存到服务器"生效</div>
                        
                        <!-- 核心功能开关 -->
                        <div class="recall-setting-group" style="margin-bottom:15px;">
                            <div style="font-weight:bold;margin-bottom:8px;">🔧 核心功能</div>
                            
                            <div class="recall-setting-group" style="margin-bottom:8px;">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-temporal-graph-enabled">
                                    <span>时态知识图谱</span>
                                </label>
                                <div class="recall-setting-hint">启用时间维度的知识图谱，追踪实体随时间的变化</div>
                            </div>
                            
                            <div class="recall-setting-group" style="margin-bottom:8px;">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-contradiction-detection-enabled">
                                    <span>矛盾检测</span>
                                </label>
                                <div class="recall-setting-hint">自动检测记忆中的事实冲突</div>
                            </div>
                            
                            <div class="recall-setting-group" style="margin-bottom:8px;">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-entity-summary-enabled">
                                    <span>实体摘要生成</span>
                                </label>
                                <div class="recall-setting-hint">允许 LLM 为实体生成描述摘要</div>
                            </div>
                        </div>
                        
                        <!-- 检索层配置 -->
                        <div class="recall-setting-group" style="margin-bottom:15px;">
                            <div style="font-weight:bold;margin-bottom:8px;">🔍 检索层配置 (11层检索系统)</div>
                            
                            <div class="recall-setting-group" style="margin-bottom:8px;">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-retrieval-l2-temporal">
                                    <span>L2 时态过滤</span>
                                </label>
                                <div class="recall-setting-hint">根据时间范围筛选记忆</div>
                            </div>
                            
                            <div class="recall-setting-group" style="margin-bottom:8px;">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-retrieval-l4-entity">
                                    <span>L4 实体聚焦</span>
                                </label>
                                <div class="recall-setting-hint">基于实体相关性提升检索效果</div>
                            </div>
                            
                            <div class="recall-setting-group" style="margin-bottom:8px;">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-retrieval-l5-graph">
                                    <span>L5 知识图谱扩展</span>
                                </label>
                                <div class="recall-setting-hint">通过实体关系图扩展检索范围</div>
                            </div>
                        </div>
                        
                        <div class="recall-setting-actions">
                            <button id="recall-load-advanced-config" class="menu_button">
                                <i class="fa-solid fa-refresh"></i>
                                <span>刷新配置</span>
                            </button>
                            <button id="recall-save-advanced-config" class="menu_button menu_button_icon">
                                <i class="fa-solid fa-save"></i>
                                <span>保存到服务器</span>
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
                            
                            <div class="recall-setting-group" style="margin-bottom:8px;">
                                <label class="recall-setting-title">条件提取触发间隔</label>
                                <input type="number" id="recall-context-trigger-interval" class="text_pole" 
                                       min="1" max="100" value="5" placeholder="5">
                                <div class="recall-setting-hint">每隔几轮对话触发一次 LLM 条件提取（1=每轮都提取，5=每5轮提取一次）</div>
                            </div>
                            
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
                        
                        <!-- 上下文构建（100%不遗忘保证） -->
                        <div class="recall-setting-group" style="margin-bottom:15px;">
                            <div style="font-weight:bold;margin-bottom:8px;">🧠 上下文构建 <span style="color:#4caf50;font-size:11px;">(100%不遗忘保证)</span></div>
                            
                            <div class="recall-setting-row" style="display:flex;gap:10px;margin-bottom:10px;">
                                <div style="flex:1;">
                                    <label class="recall-setting-title">对话提取轮次</label>
                                    <input type="number" id="recall-context-max-context-turns" class="text_pole" 
                                           min="5" max="100" value="20" placeholder="20">
                                    <div class="recall-setting-hint">持久条件/伏笔提取的对话范围</div>
                                </div>
                                <div style="flex:1;">
                                    <label class="recall-setting-title">最近对话轮次</label>
                                    <input type="number" id="recall-build-context-include-recent" class="text_pole" 
                                           min="5" max="50" value="10" placeholder="10">
                                    <div class="recall-setting-hint">注入上下文的最近对话数</div>
                                </div>
                            </div>
                            
                            <div class="recall-setting-group">
                                <label class="recall-checkbox-label">
                                    <input type="checkbox" id="recall-proactive-reminder-enabled" checked>
                                    <span>启用主动提醒</span>
                                </label>
                                <div class="recall-setting-hint">长期未提及的重要信息会主动提醒 AI</div>
                            </div>
                            
                            <div style="margin-top:8px;">
                                <label class="recall-setting-title">提醒触发轮次</label>
                                <input type="number" id="recall-proactive-reminder-turns" class="text_pole" 
                                       min="10" max="200" value="50" placeholder="50">
                                <div class="recall-setting-hint">高重要性条件阈值减半</div>
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
                            <button id="recall-rebuild-vector-index" class="menu_button" title="重建向量索引">
                                <i class="fa-solid fa-database"></i>
                                <span>重建向量索引</span>
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
            } else if (tabName === 'entities' && isConnected) {
                loadEntities();
            } else if (tabName === 'contradictions' && isConnected) {
                loadContradictions();
            } else if (tabName === 'temporal' && isConnected) {
                loadTemporalStats();
            } else if (tabName === 'graph' && isConnected) {
                // 图谱标签页初始不加载，等用户输入查询
            } else if (tabName === 'episodes' && isConnected) {
                loadEpisodes();
            } else if (tabName === 'search' && isConnected) {
                // 搜索标签页初始不加载，等用户输入查询
            }
        });
    });
    
    // 折叠面板由 SillyTavern 原生处理，不需要自己绑定事件
    // SillyTavern 会自动处理 .inline-drawer-toggle 的点击
    
    // 辅助函数：防抖
    function debounce(fn, delay) {
        let timer = null;
        return function(...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
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
    
    // 后台任务面板事件
    document.getElementById('recall-tasks-indicator')?.addEventListener('click', () => {
        const panel = document.getElementById('recall-tasks-panel');
        if (panel) {
            panel.classList.toggle('visible');
        }
    });
    document.getElementById('recall-tasks-close')?.addEventListener('click', () => {
        const panel = document.getElementById('recall-tasks-panel');
        if (panel) {
            panel.classList.remove('visible');
        }
    });
    
    // 子标签页切换
    document.querySelectorAll('.recall-sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const subtab = tab.dataset.subtab;
            const parent = tab.closest('.recall-tab-content');
            
            // 切换子标签按钮状态
            parent.querySelectorAll('.recall-sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            // 切换子内容面板
            parent.querySelectorAll('.recall-subtab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`recall-subtab-${subtab}`)?.classList.add('active');
            
            // 根据子标签加载数据
            if (subtab === 'contexts-archived' && isConnected) {
                loadArchivedContexts();
            } else if (subtab === 'foreshadowing-archived' && isConnected) {
                loadArchivedForeshadowings();
            }
        });
    });
    
    // 持久条件相关事件绑定
    document.getElementById('recall-add-context-btn')?.addEventListener('click', safeExecute(onAddPersistentContext, '添加持久条件失败'));
    document.getElementById('recall-refresh-contexts-btn')?.addEventListener('click', safeExecute(loadPersistentContexts, '刷新持久条件失败'));
    document.getElementById('recall-consolidate-contexts-btn')?.addEventListener('click', safeExecute(consolidatePersistentContexts, '压缩持久条件失败'));
    document.getElementById('recall-clear-contexts-btn')?.addEventListener('click', safeExecute(onClearAllContexts, '清空持久条件失败'));
    document.getElementById('recall-context-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') safeExecute(onAddPersistentContext, '添加持久条件失败')();
    });
    
    // 归档持久条件事件绑定
    document.getElementById('recall-refresh-archived-contexts-btn')?.addEventListener('click', safeExecute(loadArchivedContexts, '刷新归档失败'));
    document.getElementById('recall-clear-archived-contexts-btn')?.addEventListener('click', safeExecute(onClearAllArchivedContexts, '清空归档失败'));
    document.getElementById('recall-contexts-archive-search')?.addEventListener('input', debounce(() => loadArchivedContexts(1), 500));
    document.getElementById('recall-contexts-archive-filter')?.addEventListener('change', () => loadArchivedContexts(1));
    document.getElementById('recall-contexts-archive-pagesize')?.addEventListener('change', () => loadArchivedContexts(1));
    
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
    document.getElementById('recall-clear-foreshadowing-btn')?.addEventListener('click', safeExecute(onClearAllForeshadowings, '清空伏笔失败'));
    
    // 归档伏笔事件绑定
    document.getElementById('recall-refresh-archived-foreshadowing-btn')?.addEventListener('click', safeExecute(loadArchivedForeshadowings, '刷新归档失败'));
    document.getElementById('recall-clear-archived-foreshadowing-btn')?.addEventListener('click', safeExecute(onClearAllArchivedForeshadowings, '清空归档失败'));
    document.getElementById('recall-foreshadowing-archive-search')?.addEventListener('input', debounce(() => loadArchivedForeshadowings(1), 500));
    document.getElementById('recall-foreshadowing-archive-filter')?.addEventListener('change', () => loadArchivedForeshadowings(1));
    document.getElementById('recall-foreshadowing-archive-pagesize')?.addEventListener('change', () => loadArchivedForeshadowings(1));
    
    // 核心设定相关事件绑定
    document.getElementById('recall-load-core-settings')?.addEventListener('click', safeExecute(loadCoreSettings, '加载核心设定失败'));
    document.getElementById('recall-save-core-settings')?.addEventListener('click', safeExecute(saveCoreSettings, '保存核心设定失败'));
    
    // 重建向量索引
    document.getElementById('recall-rebuild-vector-index')?.addEventListener('click', safeExecute(onRebuildVectorIndex, '重建向量索引失败'));
    
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
    
    // ========== v4.0/v4.1 新功能事件绑定 ==========
    
    // 实体管理事件绑定
    document.getElementById('recall-refresh-entities-btn')?.addEventListener('click', safeExecute(loadEntities, '刷新实体失败'));
    document.getElementById('recall-entity-search-input')?.addEventListener('input', debounce(() => loadEntities(), 500));
    document.getElementById('recall-entity-type-filter')?.addEventListener('change', () => loadEntities());
    document.getElementById('recall-entity-detail-close')?.addEventListener('click', () => {
        document.getElementById('recall-entity-detail-panel').style.display = 'none';
    });
    document.getElementById('recall-generate-entity-summary')?.addEventListener('click', safeExecute(generateEntitySummary, '生成摘要失败'));
    
    // 矛盾检测事件绑定
    document.getElementById('recall-refresh-contradictions-btn')?.addEventListener('click', safeExecute(loadContradictions, '刷新矛盾失败'));
    document.getElementById('recall-contradiction-status-filter')?.addEventListener('change', () => loadContradictions());
    document.getElementById('recall-contradiction-detail-close')?.addEventListener('click', () => {
        document.getElementById('recall-contradiction-detail-panel').style.display = 'none';
    });
    document.getElementById('recall-resolve-keep-a')?.addEventListener('click', () => resolveContradiction('keep_first'));
    document.getElementById('recall-resolve-keep-b')?.addEventListener('click', () => resolveContradiction('keep_second'));
    document.getElementById('recall-resolve-keep-both')?.addEventListener('click', () => resolveContradiction('keep_both'));
    document.getElementById('recall-resolve-ignore')?.addEventListener('click', () => resolveContradiction('ignore'));
    
    // 时态查询事件绑定
    document.getElementById('recall-temporal-timeline-btn')?.addEventListener('click', safeExecute(queryEntityTimeline, '查询时间线失败'));
    document.getElementById('recall-temporal-range-btn')?.addEventListener('click', safeExecute(queryTemporalRange, '时间范围查询失败'));
    document.getElementById('recall-temporal-stats-btn')?.addEventListener('click', safeExecute(loadTemporalStats, '加载时态统计失败'));
    document.getElementById('recall-temporal-entity-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') queryEntityTimeline();
    });
    
    // 知识图谱事件绑定
    document.getElementById('recall-graph-traverse-btn')?.addEventListener('click', safeExecute(traverseGraph, '图遍历失败'));
    document.getElementById('recall-graph-communities-btn')?.addEventListener('click', safeExecute(loadCommunities, '社区检测失败'));
    document.getElementById('recall-graph-entity-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') traverseGraph();
    });
    
    // 高级功能配置事件绑定
    document.getElementById('recall-load-advanced-config')?.addEventListener('click', safeExecute(loadAdvancedConfig, '加载高级配置失败'));
    document.getElementById('recall-save-advanced-config')?.addEventListener('click', safeExecute(saveAdvancedConfig, '保存高级配置失败'));
    
    // Episode 片段事件绑定
    document.getElementById('recall-refresh-episodes-btn')?.addEventListener('click', safeExecute(loadEpisodes, '刷新片段失败'));
    document.getElementById('recall-episode-detail-close')?.addEventListener('click', () => {
        document.getElementById('recall-episode-detail-panel').style.display = 'none';
    });
    
    // 高级搜索事件绑定
    document.getElementById('recall-advanced-search-btn')?.addEventListener('click', safeExecute(performAdvancedSearch, '搜索失败'));
    document.getElementById('recall-advanced-search-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performAdvancedSearch();
    });
    document.getElementById('recall-hybrid-weight')?.addEventListener('input', (e) => {
        document.getElementById('recall-hybrid-weight-value').textContent = e.target.value;
    });
    
    // 搜索类型切换
    document.querySelectorAll('.recall-search-type-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.recall-search-type-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            // 混合搜索时显示权重选项（使用空字符串恢复CSS默认flex布局）
            const weightOption = document.getElementById('recall-hybrid-weight-option');
            if (weightOption) {
                weightOption.style.display = tab.dataset.type === 'hybrid' ? '' : 'none';
            }
        });
    });
    
    // 注意：API 配置加载移到 checkConnection 成功后执行
    // 避免在 API 未就绪时静默失败
    
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
    const taskId = taskTracker.add('config', '加载 API 配置');
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
            
            // 加载模式
            if (emb.mode) {
                document.getElementById('recall-embedding-mode').value = emb.mode;
            }
            
            // 加载速率限制
            if (emb.rate_limit) {
                document.getElementById('recall-embedding-rate-limit').value = emb.rate_limit;
            }
            if (emb.rate_window) {
                document.getElementById('recall-embedding-rate-window').value = emb.rate_window;
            }
            
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
        
        // 加载高级功能配置 (v4.0/v4.1)
        const temporalGraphEl = document.getElementById('recall-temporal-graph-enabled');
        const contradictionEl = document.getElementById('recall-contradiction-detection-enabled');
        const entitySummaryEl = document.getElementById('recall-entity-summary-enabled');
        
        if (temporalGraphEl) temporalGraphEl.checked = config.TEMPORAL_GRAPH_ENABLED ?? true;
        if (contradictionEl) contradictionEl.checked = config.CONTRADICTION_DETECTION_ENABLED ?? true;
        if (entitySummaryEl) entitySummaryEl.checked = config.ENTITY_SUMMARY_ENABLED ?? true;
        
        // 检索层配置
        const l2El = document.getElementById('recall-retrieval-l2-temporal');
        const l4El = document.getElementById('recall-retrieval-l4-entity');
        const l5El = document.getElementById('recall-retrieval-l5-graph');
        
        if (l2El) l2El.checked = config.RETRIEVAL_L2_TEMPORAL_ENABLED ?? true;
        if (l4El) l4El.checked = config.RETRIEVAL_L4_ENTITY_ENABLED ?? true;
        if (l5El) l5El.checked = config.RETRIEVAL_L5_GRAPH_ENABLED ?? true;
        
        console.log('[Recall] API 配置加载完成');
        taskTracker.complete(taskId, true);
    } catch (e) {
        console.warn('[Recall] 加载 API 配置失败:', e);
        taskTracker.complete(taskId, false, e.message);
    }
}

/**
 * 加载容量限制配置
 */
async function loadCapacityConfig() {
    const taskId = taskTracker.add('config', '加载容量限制配置');
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config`);
        const config = await response.json();
        
        if (config.capacity_limits) {
            const limits = config.capacity_limits;
            
            // 持久条件配置
            if (limits.context) {
                const triggerIntervalEl = document.getElementById('recall-context-trigger-interval');
                const maxPerTypeEl = document.getElementById('recall-context-max-per-type');
                const maxTotalEl = document.getElementById('recall-context-max-total');
                const decayDaysEl = document.getElementById('recall-context-decay-days');
                const decayRateEl = document.getElementById('recall-context-decay-rate');
                const minConfidenceEl = document.getElementById('recall-context-min-confidence');
                
                if (triggerIntervalEl) triggerIntervalEl.value = limits.context.trigger_interval || 5;
                if (maxPerTypeEl) maxPerTypeEl.value = limits.context.max_per_type || 30;
                if (maxTotalEl) maxTotalEl.value = limits.context.max_total || 100;
                if (decayDaysEl) decayDaysEl.value = limits.context.decay_days || 7;
                if (decayRateEl) decayRateEl.value = limits.context.decay_rate || 0.1;
                if (minConfidenceEl) minConfidenceEl.value = limits.context.min_confidence || 0.3;
            }
            
            // 伏笔配置
            if (limits.foreshadowing) {
                const maxReturnEl = document.getElementById('recall-foreshadowing-max-return');
                const maxActiveEl = document.getElementById('recall-foreshadowing-max-active');
                if (maxReturnEl) maxReturnEl.value = limits.foreshadowing.max_return || 5;
                if (maxActiveEl) maxActiveEl.value = limits.foreshadowing.max_active || 50;
            }
            
            // 去重配置
            if (limits.dedup) {
                const dedupEmbeddingEl = document.getElementById('recall-dedup-embedding-enabled');
                const highThresholdEl = document.getElementById('recall-dedup-high-threshold');
                const lowThresholdEl = document.getElementById('recall-dedup-low-threshold');
                if (dedupEmbeddingEl) dedupEmbeddingEl.checked = limits.dedup.embedding_enabled !== false;
                if (highThresholdEl) highThresholdEl.value = limits.dedup.high_threshold || 0.92;
                if (lowThresholdEl) lowThresholdEl.value = limits.dedup.low_threshold || 0.75;
            }
            
            // 上下文构建配置（100%不遗忘保证）
            if (limits.build_context) {
                const maxContextTurnsEl = document.getElementById('recall-context-max-context-turns');
                const includeRecentEl = document.getElementById('recall-build-context-include-recent');
                const proactiveReminderEl = document.getElementById('recall-proactive-reminder-enabled');
                const reminderTurnsEl = document.getElementById('recall-proactive-reminder-turns');
                if (maxContextTurnsEl) maxContextTurnsEl.value = limits.build_context.max_context_turns || 20;
                if (includeRecentEl) includeRecentEl.value = limits.build_context.include_recent || 10;
                if (proactiveReminderEl) proactiveReminderEl.checked = limits.build_context.proactive_reminder_enabled !== false;
                if (reminderTurnsEl) reminderTurnsEl.value = limits.build_context.proactive_reminder_turns || 50;
            }
        }
        
        safeToastr.success('容量限制配置已加载', 'Recall');
        console.log('[Recall] 容量限制配置加载完成');
        taskTracker.complete(taskId, true);
    } catch (e) {
        console.warn('[Recall] 加载容量限制配置失败:', e);
        safeToastr.error('加载容量限制配置失败: ' + e.message, 'Recall');
        taskTracker.complete(taskId, false, e.message);
    }
}

/**
 * 保存容量限制配置
 */
async function saveCapacityConfig() {
    try {
        const configData = {
            // 持久条件配置
            context_trigger_interval: parseInt(document.getElementById('recall-context-trigger-interval')?.value) || 5,
            context_max_per_type: parseInt(document.getElementById('recall-context-max-per-type')?.value) || 30,
            context_max_total: parseInt(document.getElementById('recall-context-max-total')?.value) || 100,
            context_decay_days: parseInt(document.getElementById('recall-context-decay-days')?.value) || 7,
            context_decay_rate: parseFloat(document.getElementById('recall-context-decay-rate')?.value) || 0.1,
            context_min_confidence: parseFloat(document.getElementById('recall-context-min-confidence')?.value) || 0.3,
            // 伏笔配置
            foreshadowing_max_return: parseInt(document.getElementById('recall-foreshadowing-max-return')?.value) || 5,
            foreshadowing_max_active: parseInt(document.getElementById('recall-foreshadowing-max-active')?.value) || 50,
            // 去重配置
            dedup_embedding_enabled: document.getElementById('recall-dedup-embedding-enabled')?.checked ?? true,
            dedup_high_threshold: parseFloat(document.getElementById('recall-dedup-high-threshold')?.value) || 0.92,
            dedup_low_threshold: parseFloat(document.getElementById('recall-dedup-low-threshold')?.value) || 0.75,
            // 上下文构建配置（100%不遗忘保证）
            context_max_context_turns: parseInt(document.getElementById('recall-context-max-context-turns')?.value) || 20,
            build_context_include_recent: parseInt(document.getElementById('recall-build-context-include-recent')?.value) || 10,
            proactive_reminder_enabled: document.getElementById('recall-proactive-reminder-enabled')?.checked ?? true,
            proactive_reminder_turns: parseInt(document.getElementById('recall-proactive-reminder-turns')?.value) || 50
        };
        
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        const result = await response.json();
        
        if (result.success !== false) {
            safeToastr.success('容量限制配置已保存', 'Recall');
            console.log('[Recall] 容量限制配置保存成功:', result);
            
            // 热更新配置
            await fetch(`${pluginSettings.apiUrl}/v1/config/reload`, { method: 'POST' });
        } else {
            safeToastr.error('保存失败: ' + (result.message || '未知错误'), 'Recall');
        }
    } catch (e) {
        console.error('[Recall] 保存容量限制配置失败:', e);
        safeToastr.error('保存容量限制配置失败: ' + e.message, 'Recall');
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
            
            safeToastr.success(`成功获取 ${data.models.length} 个 Embedding 模型`, 'Recall');
        } else {
            safeToastr.warning(data.message || '未获取到模型列表，请检查 API 配置', 'Recall');
        }
    } catch (error) {
        console.error('Failed to load embedding models:', error);
        safeToastr.error(`获取模型列表失败: ${error.message}`, 'Recall');
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
            
            safeToastr.success(`成功获取 ${data.models.length} 个 LLM 模型`, 'Recall');
        } else {
            safeToastr.warning(data.message || '未获取到模型列表，请检查 API 配置', 'Recall');
        }
    } catch (error) {
        console.error('Failed to load LLM models:', error);
        safeToastr.error(`获取模型列表失败: ${error.message}`, 'Recall');
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
            // 获取当前已保存的维度
            const dimInput = document.getElementById('recall-embedding-dimension');
            const currentDim = dimInput ? parseInt(dimInput.value) : 0;
            const newDim = result.dimension;
            
            // 自动填充检测到的维度到输入框（不自动保存，由用户手动保存）
            if (newDim && dimInput) {
                dimInput.value = newDim;
            }
            
            let message = `✅ Embedding 连接成功！\n\n模型: ${result.model}\n维度: ${newDim} (已填充，请保存配置)\n延迟: ${result.latency_ms}ms`;
            
            // 检测维度变化，警告用户需要重建索引
            if (currentDim > 0 && newDim && currentDim !== newDim) {
                message += `\n\n⚠️ 警告：检测到 Embedding 维度变化！\n旧维度: ${currentDim}\n新维度: ${newDim}\n\n如果已有记忆数据，切换模型后需要重建向量索引，否则搜索功能将无法正常工作。`;
                safeToastr.warning(`Embedding 维度从 ${currentDim} 变更为 ${newDim}，已有数据可能需要重建索引`, 'Recall', { timeOut: 10000 });
            }
            
            alert(message);
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
    const embMode = document.getElementById('recall-embedding-mode').value;
    const embRateLimit = document.getElementById('recall-embedding-rate-limit').value.trim();
    const embRateWindow = document.getElementById('recall-embedding-rate-window').value.trim();
    
    const configData = {};
    
    // 只有当输入的不是掩码值时才更新 API Key（服务器返回 xxxx****xxxx 格式）
    if (embKey && !embKey.includes('****')) {
        configData.embedding_api_key = embKey;
    }
    if (embBase) configData.embedding_api_base = embBase;
    if (embModel) configData.embedding_model = embModel;
    if (embDim) configData.embedding_dimension = parseInt(embDim);
    if (embMode) configData.recall_embedding_mode = embMode;
    if (embRateLimit) configData.embedding_rate_limit = parseInt(embRateLimit);
    if (embRateWindow) configData.embedding_rate_window = parseInt(embRateWindow);
    
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
    const taskId = taskTracker.add('config', '加载伏笔分析器配置');
    
    try {
        if (!pluginSettings.apiUrl) {
            if (statusEl) {
                statusEl.textContent = '未配置';
                statusEl.className = 'recall-api-status recall-status-error';
            }
            taskTracker.complete(taskId, false, '未配置');
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
            taskTracker.complete(taskId, true);
        } else {
            if (statusEl) {
                statusEl.textContent = '加载失败';
                statusEl.className = 'recall-api-status recall-status-error';
            }
            taskTracker.complete(taskId, false, '加载失败');
        }
    } catch (e) {
        console.error('[Recall] 加载伏笔分析器配置失败:', e);
        if (statusEl) {
            statusEl.textContent = '连接失败';
            statusEl.className = 'recall-api-status recall-status-error';
        }
        taskTracker.complete(taskId, false, e.message);
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
            
            // 显示检测模式
            const modeTextEl = document.getElementById('recall-rule-mode-text');
            if (modeTextEl) {
                if (data.rule_detection_mode === 'llm') {
                    modeTextEl.innerHTML = '<span style="color:var(--SmartThemeQuoteColor);">✨ LLM 语义检测已启用</span>';
                } else {
                    modeTextEl.innerHTML = '<span style="color:var(--SmartThemeEmColor);">⚠️ 未配置 LLM，规则检测未生效</span>（配置 LLM_API_KEY 后生效）';
                }
            }
            
            console.log('[Recall] 绝对规则已加载, 检测模式:', data.rule_detection_mode || 'unknown');
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
            
            // 更新检测模式显示
            const modeTextEl = document.getElementById('recall-rule-mode-text');
            if (modeTextEl && result.rule_detection_mode) {
                if (result.rule_detection_mode === 'llm') {
                    modeTextEl.innerHTML = '<span style="color:var(--SmartThemeQuoteColor);">✨ LLM 语义检测已启用</span>';
                } else {
                    modeTextEl.innerHTML = '<span style="color:var(--SmartThemeEmColor);">⚠️ 未配置 LLM，规则检测未生效</span>（配置 LLM_API_KEY 后生效）';
                }
            }
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
    const characterId = encodeURIComponent(currentCharacterId || 'default');
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/analyze/trigger?user_id=${userId}&character_id=${characterId}`, {
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
    
    // 显示加载状态
    const btn = document.getElementById('recall-consolidate-memories');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 整合中...';
    }
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/consolidate?user_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            safeToastr.success(result.message || '记忆整合完成', 'Recall');
            
            // 刷新记忆列表
            loadMemories();
        } else {
            const error = await response.json().catch(() => ({}));
            safeToastr.error(`整合失败: ${error.detail || '未知错误'}`, 'Recall');
        }
    } catch (e) {
        safeToastr.error(`整合失败: ${e.message}`, 'Recall');
    } finally {
        // 恢复按钮状态
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
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
                
                // 模式信息（支持新旧字段名）
                const isLiteMode = stats.lite ?? stats.lightweight;
                if (isLiteMode !== undefined) {
                    html += `<div class="recall-stat-item"><span class="recall-stat-label">运行模式</span><span class="recall-stat-value">${isLiteMode ? 'Lite' : 'Local'}</span></div>`;
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
                
                // 加载伏笔分析器配置
                loadForeshadowingAnalyzerConfig();
                
                // 加载容量限制配置
                loadCapacityConfig();
                
                // 加载记忆和持久条件
                if (currentCharacterId) {
                    loadMemories();
                    loadForeshadowings();
                    loadPersistentContexts();
                }
                
                // 【新增】同步本地缓存的记忆（解决离线期间的保存）
                memorySaveQueue.syncLocalStorage();
            }
        } else {
            throw new Error(`API 响应异常: ${response.status}`);
        }
    } catch (e) {
        // 首次连接失败，尝试智能探测其他地址（只探测一次）
        if (!checkConnection._hasProbed) {
            checkConnection._hasProbed = true;
            console.log('[Recall] 当前地址连接失败，尝试智能探测...');
            const newUrl = await smartConnect();
            
            if (newUrl !== pluginSettings.apiUrl) {
                console.log(`[Recall] 切换到新地址: ${newUrl}`);
                pluginSettings.apiUrl = newUrl;
                saveSettings();
                
                // 更新 UI 显示
                const urlInput = document.getElementById('recall-api-url');
                if (urlInput) urlInput.value = newUrl;
                
                // 用新地址重试连接（重置标记，允许新地址再试一次）
                checkConnection._hasProbed = false;
                return checkConnection();
            }
        }
        
        // 智能探测也失败了
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
                    helpTip = `当前从 ${currentHost} 访问，但 API 指向本地。请到设置中修改 API 地址`;
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
    
    const userId = currentCharacterId || 'default';
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/memories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content,
                user_id: userId,
                metadata: {
                    role: 'manual',
                    source: 'sillytavern',
                    character_id: userId
                }
            })
        });
        
        const result = await response.json();
        if (result.success) {
            document.getElementById('recall-add-input').value = '';
            loadMemories();
            
            // 显示一致性检查警告（如果有）
            if (result.consistency_warnings && result.consistency_warnings.length > 0) {
                const warningMsg = result.consistency_warnings.join('\n');
                console.warn('[Recall] 一致性检查警告:', warningMsg);
                // 使用 safeToastr 显示警告
                safeToastr.warning(warningMsg, '一致性检查警告', { timeOut: 8000 });
            }
        } else {
            // 显示保存失败的原因
            console.log('[Recall] 记忆未保存:', result.message);
            if (result.message) {
                safeToastr.info(result.message, 'Recall', { timeOut: 3000 });
            }
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
    
    const userId = currentCharacterId || 'default';
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content,
                user_id: userId,
                character_id: userId,
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
    const userId = currentCharacterId || 'default';
    
    // 添加任务跟踪
    const taskId = taskTracker.add('foreshadow', '伏笔分析', role === 'user' ? '用户消息' : 'AI回复');
    
    fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/analyze/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            content: content,
            role: role,
            user_id: userId,
            character_id: userId
        })
    }).then(response => {
        if (!response.ok) {
            console.debug('[Recall] 伏笔分析通知发送失败:', response.status);
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
        } else {
            taskTracker.complete(taskId, true);
        }
        // 不处理响应内容，服务器会在后台异步处理
        // 如果需要刷新伏笔列表，可以通过定时器或手动刷新
    }).catch(e => {
        // 静默失败，不影响主流程
        console.debug('[Recall] 伏笔分析器通知失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
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
        
        // 添加任务跟踪
        const taskId = taskTracker.add('memory-save', '保存记忆', `队列剩余: ${this.queue.length}`);
        
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
                    item.resolve({ 
                        success: true, 
                        id: result.id,
                        consistency_warnings: result.consistency_warnings || []
                    });
                    console.log('[Recall] 记忆保存成功（队列处理）');
                    taskTracker.complete(taskId, true);
                    
                    // 显示一致性检查警告（如果有）
                    if (result.consistency_warnings && result.consistency_warnings.length > 0) {
                        console.warn('[Recall] 一致性检查警告:', result.consistency_warnings);
                        // 使用 safeToastr 显示警告，不阻塞流程
                        const warningMsg = result.consistency_warnings.join('\n');
                        safeToastr.warning(warningMsg, '一致性检查警告', { timeOut: 8000 });
                    }
                } else {
                    // 服务器返回成功状态码，但业务上未保存（如重复内容）
                    item.resolve({ success: false, message: result.message });
                    console.log('[Recall] 记忆跳过:', result.message);
                    taskTracker.complete(taskId, true, result.message);
                }
            } else if (response.status === 429) {
                // API 限流，延长间隔并重试
                console.warn('[Recall] API 限流，将延迟重试');
                this.minInterval = Math.min(this.minInterval * 2, 10000); // 最多 10 秒
                item.retries++;
                if (item.retries < this.maxRetries) {
                    this.queue.unshift(item); // 放回队首
                    taskTracker.complete(taskId, true, '限流重试');
                } else {
                    // 保存到本地存储，等待下次启动时重试
                    this._saveToLocalStorage(item.memory);
                    item.resolve({ success: false, queued: true });
                    safeToastr.warning('记忆暂存到本地，将在重新连接后同步', 'Recall', { timeOut: 5000 });
                    taskTracker.complete(taskId, false, '已暂存本地');
                }
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (e) {
            console.warn('[Recall] 记忆保存失败:', e.message);
            item.retries++;
            if (item.retries < this.maxRetries) {
                this.queue.push(item); // 放回队尾
                taskTracker.complete(taskId, true, '重试中');
            } else {
                // 保存到本地存储
                this._saveToLocalStorage(item.memory);
                item.resolve({ success: false, queued: true });
                safeToastr.warning('记忆保存失败，已暂存到本地', 'Recall', { timeOut: 5000 });
                taskTracker.complete(taskId, false, '保存失败');
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
        let taskId = null;
        try {
            const key = 'recall_pending_memories';
            const pending = JSON.parse(localStorage.getItem(key) || '[]');
            if (pending.length === 0) return;
            
            console.log(`[Recall] 发现 ${pending.length} 条待同步的本地记忆`);
            
            taskId = taskTracker.add('sync', '同步本地缓存', `${pending.length} 条记忆`);
            
            for (const memory of pending) {
                this.add(memory);
            }
            
            // 清空本地缓存
            localStorage.removeItem(key);
            taskTracker.complete(taskId, true);
        } catch (e) {
            console.warn('[Recall] 同步本地缓存失败:', e);
            if (taskId) taskTracker.complete(taskId, false, e.message);
        }
    }
};

/**
 * 消息发送时
 * 【优化】使用队列保存，不阻塞消息发送
 */
async function onMessageSent(messageIndex) {
    console.log(`[Recall] MESSAGE_SENT 事件触发, messageIndex=${messageIndex}, enabled=${pluginSettings.enabled}, connected=${isConnected}`);
    
    if (!pluginSettings.enabled || !isConnected) {
        console.log('[Recall] 消息保存跳过: 插件未启用或未连接');
        return;
    }
    
    try {
        const context = SillyTavern.getContext();
        const chat = context.chat;
        const message = chat[messageIndex];
        
        console.log(`[Recall] 获取到消息:`, {
            hasMessage: !!message,
            hasMes: message?.mes ? true : false,
            mesLength: message?.mes?.length,
            mesPreview: message?.mes?.substring(0, 50),
            isUser: message?.is_user,
            characterId: currentCharacterId
        });
        
        if (!message || !message.mes) {
            console.log('[Recall] 消息为空，跳过');
            return;
        }
        
        // 【关键改动】使用队列保存，不阻塞
        // 先将记忆加入队列，立即返回让消息显示
        console.log(`[Recall] 正在将用户消息加入保存队列: "${message.mes.substring(0, 50)}..."`);
        
        memorySaveQueue.add({
            content: message.mes,
            user_id: currentCharacterId || 'default',
            metadata: { 
                role: 'user', 
                source: 'sillytavern',
                character_id: currentCharacterId || 'default',
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
                console.log('[Recall] 用户消息跳过（重复）:', result.message);
            }
        }).catch(err => {
            console.error('[Recall] 消息保存队列错误:', err);
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
                    character_id: currentCharacterId || 'default',
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
    
    // 清除旧角色的记忆注入，避免残留
    try {
        if (context.setExtensionPrompt) {
            context.setExtensionPrompt('recall_memory', '', 0, 0, false, 0);
            console.log('[Recall] 已清除旧角色的记忆注入');
        }
    } catch (e) {
        console.warn('[Recall] 清除旧注入失败:', e);
    }
    
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
        btn.setAttribute('data-bound', 'true');
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
 * 添加防重入机制，避免多次并发请求
 * 当角色变化时，取消之前的请求
 */
let _loadForeshadowingsLoading = false;
let _loadForeshadowingsController = null;
let _loadForeshadowingsForUser = null;
let _loadForeshadowingsRequestId = 0;  // 请求ID，用于识别当前有效请求
async function loadForeshadowings() {
    if (!isConnected) return;
    
    const userId = encodeURIComponent(currentCharacterId || 'default');
    
    // 如果正在加载同一个角色的数据，跳过
    if (_loadForeshadowingsLoading && _loadForeshadowingsForUser === userId) {
        console.log('[Recall] 伏笔正在加载中（同一角色），跳过重复请求');
        return;
    }
    
    // 如果正在加载不同角色的数据，取消之前的请求
    if (_loadForeshadowingsLoading && _loadForeshadowingsForUser !== userId) {
        console.log(`[Recall] 角色已切换 (${_loadForeshadowingsForUser} -> ${userId})，取消之前的伏笔请求`);
        if (_loadForeshadowingsController) {
            _loadForeshadowingsController.abort();
            _loadForeshadowingsController = null;
        }
        _loadForeshadowingsLoading = false;
    }
    
    _loadForeshadowingsLoading = true;
    _loadForeshadowingsForUser = userId;
    const currentRequestId = ++_loadForeshadowingsRequestId;  // 生成唯一请求ID
    const startTime = Date.now();
    
    try {
        // 添加超时控制（30秒，避免网络延迟导致误报）
        const controller = new AbortController();  // 使用局部变量
        _loadForeshadowingsController = controller;
        const timeoutId = setTimeout(() => {
            console.log(`[Recall] 伏笔请求超时 (requestId=${currentRequestId})，触发 abort`);
            controller.abort();  // 使用局部变量
        }, 30000);
        
        const url = `${pluginSettings.apiUrl}/v1/foreshadowing?user_id=${userId}&character_id=${userId}`;
        console.log(`[Recall] 开始加载伏笔 (requestId=${currentRequestId}):`, url);
        
        // 添加诊断：记录 fetch 开始时间
        const fetchStartTime = Date.now();
        console.log(`[Recall] 伏笔 fetch 开始 @ ${new Date().toISOString()}`);
        
        const response = await fetch(url, {
            signal: controller.signal,
            mode: 'cors'  // 显式设置 CORS 模式
        });
        clearTimeout(timeoutId);
        
        console.log(`[Recall] 伏笔 fetch 响应到达，耗时 ${Date.now() - fetchStartTime}ms`);
        
        // 检查是否是当前有效的请求
        if (_loadForeshadowingsRequestId !== currentRequestId) {
            console.log('[Recall] 伏笔请求完成但已被新请求取代，忽略结果');
            return;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log(`[Recall] 伏笔数据: ${data.length} 条，耗时 ${Date.now() - startTime}ms`);
        
        displayForeshadowings(data);
        
        // 更新活跃伏笔计数
        const countEl = document.getElementById('recall-foreshadowing-count');
        if (countEl) {
            const activeCount = Array.isArray(data) ? data.filter(f => f.status === 'planted' || f.status === 'developing').length : 0;
            countEl.textContent = activeCount;
        }
        
        // 同时加载归档数量（只获取计数）- 添加超时控制
        try {
            const archivedController = new AbortController();
            const archivedTimeout = setTimeout(() => archivedController.abort(), 5000);
            const archivedRes = await fetch(
                `${pluginSettings.apiUrl}/v1/foreshadowing/archived?user_id=${userId}&character_id=${userId}&page=1&page_size=1`,
                { signal: archivedController.signal }
            );
            clearTimeout(archivedTimeout);
            if (archivedRes.ok) {
                const archivedData = await archivedRes.json();
                const archivedCountEl = document.getElementById('recall-foreshadowing-archived-count');
                if (archivedCountEl) archivedCountEl.textContent = archivedData.total || 0;
            }
        } catch (archivedErr) {
            // 忽略归档计数加载失败
        }
        
        console.log(`[Recall] 伏笔加载完成，总耗时 ${Date.now() - startTime}ms`);
        _loadForeshadowingsLoading = false;
        _loadForeshadowingsController = null;
    } catch (e) {
        // 检查是否是当前有效的请求
        if (_loadForeshadowingsRequestId !== currentRequestId) {
            console.log(`[Recall] 伏笔请求异常但已被新请求取代 (requestId=${currentRequestId})，忽略`);
            return;
        }
        
        // 详细的错误诊断
        const elapsed = Date.now() - startTime;
        let errMsg;
        if (e.name === 'AbortError') {
            errMsg = `请求超时（30s）`;
            console.error(`[Recall] 伏笔请求超时:`, {
                requestId: currentRequestId,
                userId: userId,
                elapsed: elapsed,
                errorName: e.name,
                errorMessage: e.message
            });
        } else {
            errMsg = e.message || String(e);
            console.error(`[Recall] 加载伏笔失败:`, {
                requestId: currentRequestId,
                userId: userId,
                elapsed: elapsed,
                errorName: e.name,
                errorMessage: e.message,
                errorStack: e.stack
            });
        }
        
        _loadForeshadowingsLoading = false;
        _loadForeshadowingsController = null;
    }
}

/**
 * 清空全部伏笔
 */
async function onClearAllForeshadowings() {
    if (!isConnected) {
        alert('请先连接 Recall 服务');
        return;
    }
    
    const confirmMsg = currentCharacterId 
        ? `确定要清空「${currentCharacterId}」的所有伏笔吗？\n\n此操作不可恢复！`
        : '确定要清空所有伏笔吗？\n\n此操作不可恢复！';
    
    if (!confirm(confirmMsg)) return;
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            loadForeshadowings();
            console.log(`[Recall] 已清空 ${result.count} 个伏笔 (角色: ${currentCharacterId})`);
        } else {
            console.error('[Recall] 清空伏笔失败');
        }
    } catch (e) {
        console.error('[Recall] 清空伏笔失败:', e);
    }
}

/**
 * 加载持久条件列表
 * 添加防重入机制，避免多次并发请求
 * 当角色变化时，取消之前的请求
 */
let _loadPersistentContextsLoading = false;
let _loadPersistentContextsController = null;
let _loadPersistentContextsForUser = null;
let _loadPersistentContextsRequestId = 0;      // 请求ID，用于识别当前有效请求
let _loadPersistentContextsTaskId = null;      // 当前的 taskId
async function loadPersistentContexts() {
    if (!isConnected) {
        console.log('[Recall] 未连接，跳过加载持久条件');
        return;
    }
    
    const userId = encodeURIComponent(currentCharacterId || 'default');
    
    // 如果正在加载同一个角色的数据，跳过
    if (_loadPersistentContextsLoading && _loadPersistentContextsForUser === userId) {
        console.log('[Recall] 持久条件正在加载中（同一角色），跳过重复请求');
        return;
    }
    
    // 如果正在加载不同角色的数据，取消之前的请求
    if (_loadPersistentContextsLoading && _loadPersistentContextsForUser !== userId) {
        console.log(`[Recall] 角色已切换 (${_loadPersistentContextsForUser} -> ${userId})，取消之前的请求`);
        
        // 显式完成旧的 taskId
        if (_loadPersistentContextsTaskId !== null) {
            taskTracker.complete(_loadPersistentContextsTaskId, true, '已切换角色');
            _loadPersistentContextsTaskId = null;
        }
        
        if (_loadPersistentContextsController) {
            _loadPersistentContextsController.abort();
            _loadPersistentContextsController = null;
        }
        _loadPersistentContextsLoading = false;
    }
    
    _loadPersistentContextsLoading = true;
    _loadPersistentContextsForUser = userId;
    const currentRequestId = ++_loadPersistentContextsRequestId;  // 生成唯一请求ID
    
    const taskId = taskTracker.add('load', '加载持久条件');
    _loadPersistentContextsTaskId = taskId;
    const startTime = Date.now();
    
    try {
        // 添加超时控制（30秒）
        const controller = new AbortController();  // 使用局部变量，避免闭包问题
        _loadPersistentContextsController = controller;
        const timeoutId = setTimeout(() => {
            console.log(`[Recall] 持久条件请求超时 (requestId=${currentRequestId})，触发 abort`);
            controller.abort();  // 使用局部变量
        }, 30000);
        
        const url = `${pluginSettings.apiUrl}/v1/persistent-contexts?user_id=${userId}&character_id=${userId}`;
        console.log(`[Recall] 开始加载持久条件 (requestId=${currentRequestId}):`, url);
        
        // 添加诊断：记录 fetch 开始时间
        const fetchStartTime = Date.now();
        console.log(`[Recall] fetch 开始 @ ${new Date().toISOString()}`);
        
        const response = await fetch(url, {
            signal: controller.signal,
            mode: 'cors'  // 显式设置 CORS 模式
        });
        clearTimeout(timeoutId);
        
        console.log(`[Recall] fetch 响应到达，耗时 ${Date.now() - fetchStartTime}ms`);
        
        // 检查是否是当前有效的请求
        if (_loadPersistentContextsRequestId !== currentRequestId) {
            console.log('[Recall] 持久条件请求完成但已被新请求取代，忽略结果');
            // taskId 已在角色切换时被完成，无需再处理
            return;
        }
        
        console.log(`[Recall] 持久条件 fetch 完成，状态: ${response.status}，耗时 ${Date.now() - startTime}ms`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log(`[Recall] 持久条件数据: ${data.length} 条`);
        
        displayPersistentContexts(data);
        
        // 更新活跃计数
        const countEl = document.getElementById('recall-context-count');
        if (countEl) countEl.textContent = data.length;
        
        // 同时加载归档数量（只获取计数）- 添加超时控制
        try {
            const archivedController = new AbortController();
            const archivedTimeout = setTimeout(() => archivedController.abort(), 5000);
            
            const archivedRes = await fetch(
                `${pluginSettings.apiUrl}/v1/persistent-contexts/archived?user_id=${userId}&character_id=${userId}&page=1&page_size=1`,
                { signal: archivedController.signal }
            );
            clearTimeout(archivedTimeout);
            
            if (archivedRes.ok) {
                const archivedData = await archivedRes.json();
                const archivedCountEl = document.getElementById('recall-context-archived-count');
                if (archivedCountEl) archivedCountEl.textContent = archivedData.total || 0;
            }
        } catch (archivedErr) {
            console.log('[Recall] 归档计数加载失败（忽略）:', archivedErr.message);
        }
        
        console.log(`[Recall] 持久条件加载完成，总耗时 ${Date.now() - startTime}ms`);
        taskTracker.complete(taskId, true);
        _loadPersistentContextsLoading = false;
        _loadPersistentContextsController = null;
        _loadPersistentContextsTaskId = null;
    } catch (e) {
        // 检查是否是当前有效的请求
        if (_loadPersistentContextsRequestId !== currentRequestId) {
            console.log(`[Recall] 持久条件请求异常但已被新请求取代 (requestId=${currentRequestId})，忽略`);
            // taskId 已在角色切换时被完成，无需再处理
            return;
        }
        
        // 详细的错误诊断
        const elapsed = Date.now() - startTime;
        let errMsg;
        if (e.name === 'AbortError') {
            errMsg = `请求超时（30s）`;
            console.error(`[Recall] 持久条件请求超时:`, {
                requestId: currentRequestId,
                userId: userId,
                elapsed: elapsed,
                errorName: e.name,
                errorMessage: e.message
            });
        } else {
            errMsg = e.message || String(e);
            console.error(`[Recall] 加载持久条件失败:`, {
                requestId: currentRequestId,
                userId: userId,
                elapsed: elapsed,
                errorName: e.name,
                errorMessage: e.message,
                errorStack: e.stack
            });
        }
        
        taskTracker.complete(taskId, false, errMsg);
        _loadPersistentContextsLoading = false;
        _loadPersistentContextsController = null;
        _loadPersistentContextsTaskId = null;
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
    
    // 存储上下文数据用于编辑
    window._recallContextsData = {};
    contexts.forEach(ctx => {
        window._recallContextsData[ctx.id] = ctx;
    });
    
    listEl.innerHTML = contexts.map(ctx => `
        <div class="recall-context-item" data-id="${ctx.id}">
            <div class="recall-context-header">
                <span class="recall-context-type-badge ${ctx.context_type}">${typeNames[ctx.context_type] || ctx.context_type}</span>
                <span class="recall-context-confidence">置信度: ${(ctx.confidence * 100).toFixed(0)}%</span>
            </div>
            <p class="recall-context-content">${escapeHtml(ctx.content)}</p>
            <div class="recall-context-footer">
                <span>使用 ${ctx.use_count} 次</span>
                <div style="display:flex;gap:4px;">
                    <button class="recall-action-btn recall-edit-context" data-id="${ctx.id}" title="编辑">✏️</button>
                    <button class="recall-action-btn recall-archive-context" data-id="${ctx.id}" title="归档">📦</button>
                    <button class="recall-delete-btn recall-remove-context" data-id="${ctx.id}" title="删除">✕</button>
                </div>
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
    
    // 绑定编辑按钮事件
    listEl.querySelectorAll('.recall-edit-context').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const id = e.currentTarget.dataset.id;
            const ctx = window._recallContextsData[id];
            if (ctx) showEditContextModal(ctx);
        });
    });
    
    // 绑定归档按钮事件
    listEl.querySelectorAll('.recall-archive-context').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            if (confirm('确定要归档这个持久条件吗？')) {
                await archiveContext(id);
            }
        });
    });
}

/**
 * 添加持久条件
 */
async function addPersistentContext(content, contextType) {
    if (!isConnected || !content.trim()) return;
    
    const userId = currentCharacterId || 'default';
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: content.trim(),
                context_type: contextType,
                user_id: userId,
                character_id: userId
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
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}?user_id=${userId}&character_id=${userId}`, {
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
 * 清空全部持久条件
 */
async function onClearAllContexts() {
    if (!isConnected) {
        alert('请先连接 Recall 服务');
        return;
    }
    
    const confirmMsg = currentCharacterId 
        ? `确定要清空「${currentCharacterId}」的所有持久条件吗？\n\n此操作不可恢复！`
        : '确定要清空所有持久条件吗？\n\n此操作不可恢复！';
    
    if (!confirm(confirmMsg)) return;
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            loadPersistentContexts();
            console.log(`[Recall] 已清空 ${result.count} 个持久条件 (角色: ${currentCharacterId})`);
        } else {
            console.error('[Recall] 清空持久条件失败');
        }
    } catch (e) {
        console.error('[Recall] 清空持久条件失败:', e);
    }
}

// ==================== 归档管理功能 ====================

// 归档分页状态
let archivedContextsPage = 1;
let archivedForeshadowingsPage = 1;

/**
 * 加载归档的持久条件
 */
async function loadArchivedContexts(page = archivedContextsPage) {
    if (!isConnected) return;
    
    const searchEl = document.getElementById('recall-contexts-archive-search');
    const filterEl = document.getElementById('recall-contexts-archive-filter');
    const pageSizeEl = document.getElementById('recall-contexts-archive-pagesize');
    
    const search = searchEl?.value || '';
    const contextType = filterEl?.value || '';
    const pageSize = parseInt(pageSizeEl?.value || '20');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        let url = `${pluginSettings.apiUrl}/v1/persistent-contexts/archived?user_id=${userId}&character_id=${userId}&page=${page}&page_size=${pageSize}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (contextType) url += `&context_type=${encodeURIComponent(contextType)}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        archivedContextsPage = data.page;
        
        displayArchivedContexts(data.items);
        renderContextsPagination(data);
        
        // 更新归档计数
        const countEl = document.getElementById('recall-context-archived-count');
        if (countEl) countEl.textContent = data.total;
    } catch (e) {
        console.error('[Recall] 加载归档持久条件失败:', e);
    }
}

/**
 * 显示归档持久条件列表
 */
function displayArchivedContexts(items) {
    const listEl = document.getElementById('recall-archived-context-list');
    if (!listEl) return;
    
    if (!items || items.length === 0) {
        listEl.innerHTML = `
            <div class="recall-empty-state">
                <div class="recall-empty-icon">📦</div>
                <p>暂无归档条件</p>
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
    
    const reasonNames = {
        'low_confidence': '置信度低',
        'type_overflow': '类型数量超限',
        'total_overflow': '总数量超限',
        'manual': '手动归档'
    };
    
    listEl.innerHTML = items.map(ctx => `
        <div class="recall-context-item archived" data-id="${ctx.id}">
            <div class="recall-context-header">
                <span class="recall-context-type-badge ${ctx.context_type}">${typeNames[ctx.context_type] || ctx.context_type}</span>
                <span class="recall-context-confidence">置信度: ${(ctx.confidence * 100).toFixed(0)}%</span>
            </div>
            <p class="recall-context-content">${escapeHtml(ctx.content)}</p>
            <div class="recall-archive-info">
                归档时间: ${new Date(ctx.archived_at * 1000).toLocaleString()}
                <span class="recall-archive-reason">${reasonNames[ctx.archive_reason] || ctx.archive_reason}</span>
            </div>
            <div class="recall-context-footer">
                <span>使用 ${ctx.use_count || 0} 次</span>
                <div style="display:flex;gap:4px;">
                    <button class="recall-action-btn recall-restore-context" data-id="${ctx.id}" title="恢复">↩️ 恢复</button>
                    <button class="recall-delete-btn recall-delete-archived-context" data-id="${ctx.id}" title="彻底删除">✕ 删除</button>
                </div>
            </div>
        </div>
    `).join('');
    
    // 绑定事件
    listEl.querySelectorAll('.recall-restore-context').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            await restoreArchivedContext(id);
        });
    });
    
    listEl.querySelectorAll('.recall-delete-archived-context').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            if (confirm('确定要彻底删除这个归档条件吗？\n\n此操作不可恢复！')) {
                await deleteArchivedContext(id);
            }
        });
    });
}

/**
 * 渲染持久条件归档分页
 */
function renderContextsPagination(data) {
    const paginationEl = document.getElementById('recall-contexts-archive-pagination');
    if (!paginationEl) return;
    
    if (data.total_pages <= 1) {
        paginationEl.innerHTML = '';
        return;
    }
    
    let html = '';
    html += `<button ${data.page <= 1 ? 'disabled' : ''} onclick="RecallPlugin.loadArchivedContexts(${data.page - 1})">‹</button>`;
    
    // 显示页码
    const maxPages = 5;
    let startPage = Math.max(1, data.page - Math.floor(maxPages / 2));
    let endPage = Math.min(data.total_pages, startPage + maxPages - 1);
    startPage = Math.max(1, endPage - maxPages + 1);
    
    if (startPage > 1) {
        html += `<button onclick="RecallPlugin.loadArchivedContexts(1)">1</button>`;
        if (startPage > 2) html += '<span class="recall-pagination-info">...</span>';
    }
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="${i === data.page ? 'active' : ''}" onclick="RecallPlugin.loadArchivedContexts(${i})">${i}</button>`;
    }
    
    if (endPage < data.total_pages) {
        if (endPage < data.total_pages - 1) html += '<span class="recall-pagination-info">...</span>';
        html += `<button onclick="RecallPlugin.loadArchivedContexts(${data.total_pages})">${data.total_pages}</button>`;
    }
    
    html += `<button ${data.page >= data.total_pages ? 'disabled' : ''} onclick="RecallPlugin.loadArchivedContexts(${data.page + 1})">›</button>`;
    html += `<span class="recall-pagination-info">${data.total} 条</span>`;
    
    paginationEl.innerHTML = html;
}

/**
 * 恢复归档的持久条件
 */
async function restoreArchivedContext(contextId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}/restore?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadArchivedContexts();
            loadPersistentContexts();
            console.log(`[Recall] 已恢复归档条件: ${contextId}`);
        } else {
            console.error('[Recall] 恢复归档条件失败');
        }
    } catch (e) {
        console.error('[Recall] 恢复归档条件失败:', e);
    }
}

/**
 * 彻底删除归档的持久条件
 */
async function deleteArchivedContext(contextId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/archived/${contextId}?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadArchivedContexts();
            console.log(`[Recall] 已彻底删除归档条件: ${contextId}`);
        } else {
            console.error('[Recall] 删除归档条件失败');
        }
    } catch (e) {
        console.error('[Recall] 删除归档条件失败:', e);
    }
}

/**
 * 清空所有归档的持久条件
 */
async function onClearAllArchivedContexts() {
    if (!isConnected) {
        alert('请先连接 Recall 服务');
        return;
    }
    
    if (!confirm('确定要清空所有归档的持久条件吗？\n\n此操作不可恢复！')) return;
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/archived?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            loadArchivedContexts();
            console.log(`[Recall] 已清空 ${result.count} 个归档条件`);
        }
    } catch (e) {
        console.error('[Recall] 清空归档条件失败:', e);
    }
}

/**
 * 手动归档活跃的持久条件
 */
async function archiveContext(contextId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}/archive?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadPersistentContexts();
            loadArchivedContexts();
            console.log(`[Recall] 已归档条件: ${contextId}`);
        }
    } catch (e) {
        console.error('[Recall] 归档条件失败:', e);
    }
}

/**
 * 加载归档的伏笔
 */
async function loadArchivedForeshadowings(page = archivedForeshadowingsPage) {
    if (!isConnected) return;
    
    const searchEl = document.getElementById('recall-foreshadowing-archive-search');
    const filterEl = document.getElementById('recall-foreshadowing-archive-filter');
    const pageSizeEl = document.getElementById('recall-foreshadowing-archive-pagesize');
    
    const search = searchEl?.value || '';
    const status = filterEl?.value || '';
    const pageSize = parseInt(pageSizeEl?.value || '20');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        let url = `${pluginSettings.apiUrl}/v1/foreshadowing/archived?user_id=${userId}&character_id=${userId}&page=${page}&page_size=${pageSize}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        archivedForeshadowingsPage = data.page;
        
        displayArchivedForeshadowings(data.items);
        renderForeshadowingsPagination(data);
        
        // 更新归档计数
        const countEl = document.getElementById('recall-foreshadowing-archived-count');
        if (countEl) countEl.textContent = data.total;
    } catch (e) {
        console.error('[Recall] 加载归档伏笔失败:', e);
    }
}

/**
 * 显示归档伏笔列表
 */
function displayArchivedForeshadowings(items) {
    const listEl = document.getElementById('recall-archived-foreshadowing-list');
    if (!listEl) return;
    
    if (!items || items.length === 0) {
        listEl.innerHTML = `
            <div class="recall-empty-state">
                <div class="recall-empty-icon">📦</div>
                <p>暂无归档伏笔</p>
            </div>
        `;
        return;
    }
    
    const statusNames = {
        'resolved': '✅ 已解决',
        'abandoned': '❌ 已放弃'
    };
    
    const reasonNames = {
        'resolved': '已解决',
        'abandoned': '已放弃',
        'overflow': '数量超限',
        'manual': '手动归档'
    };
    
    listEl.innerHTML = items.map(fsh => `
        <div class="recall-foreshadowing-item archived ${fsh.status}" data-id="${fsh.id}">
            <div class="recall-foreshadowing-header">
                <span class="recall-foreshadowing-status">${statusNames[fsh.status] || fsh.status}</span>
                <span class="recall-foreshadowing-importance">重要性: ${(fsh.importance * 100).toFixed(0)}%</span>
            </div>
            <p class="recall-foreshadowing-content">${escapeHtml(fsh.content)}</p>
            ${fsh.resolution ? `<p class="recall-foreshadowing-resolution">解决: ${escapeHtml(fsh.resolution)}</p>` : ''}
            <div class="recall-archive-info">
                归档时间: ${new Date(fsh.archived_at * 1000).toLocaleString()}
                <span class="recall-archive-reason">${reasonNames[fsh.archive_reason] || fsh.archive_reason}</span>
            </div>
            <div class="recall-foreshadowing-footer">
                <div style="display:flex;gap:4px;">
                    <button class="recall-action-btn recall-restore-foreshadowing" data-id="${fsh.id}" title="恢复">↩️ 恢复</button>
                    <button class="recall-delete-btn recall-delete-archived-foreshadowing" data-id="${fsh.id}" title="彻底删除">✕ 删除</button>
                </div>
            </div>
        </div>
    `).join('');
    
    // 绑定事件
    listEl.querySelectorAll('.recall-restore-foreshadowing').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            await restoreArchivedForeshadowing(id);
        });
    });
    
    listEl.querySelectorAll('.recall-delete-archived-foreshadowing').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            if (confirm('确定要彻底删除这个归档伏笔吗？\n\n此操作不可恢复！')) {
                await deleteArchivedForeshadowing(id);
            }
        });
    });
}

/**
 * 渲染伏笔归档分页
 */
function renderForeshadowingsPagination(data) {
    const paginationEl = document.getElementById('recall-foreshadowing-archive-pagination');
    if (!paginationEl) return;
    
    if (data.total_pages <= 1) {
        paginationEl.innerHTML = '';
        return;
    }
    
    let html = '';
    html += `<button ${data.page <= 1 ? 'disabled' : ''} onclick="RecallPlugin.loadArchivedForeshadowings(${data.page - 1})">‹</button>`;
    
    const maxPages = 5;
    let startPage = Math.max(1, data.page - Math.floor(maxPages / 2));
    let endPage = Math.min(data.total_pages, startPage + maxPages - 1);
    startPage = Math.max(1, endPage - maxPages + 1);
    
    if (startPage > 1) {
        html += `<button onclick="RecallPlugin.loadArchivedForeshadowings(1)">1</button>`;
        if (startPage > 2) html += '<span class="recall-pagination-info">...</span>';
    }
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="${i === data.page ? 'active' : ''}" onclick="RecallPlugin.loadArchivedForeshadowings(${i})">${i}</button>`;
    }
    
    if (endPage < data.total_pages) {
        if (endPage < data.total_pages - 1) html += '<span class="recall-pagination-info">...</span>';
        html += `<button onclick="RecallPlugin.loadArchivedForeshadowings(${data.total_pages})">${data.total_pages}</button>`;
    }
    
    html += `<button ${data.page >= data.total_pages ? 'disabled' : ''} onclick="RecallPlugin.loadArchivedForeshadowings(${data.page + 1})">›</button>`;
    html += `<span class="recall-pagination-info">${data.total} 条</span>`;
    
    paginationEl.innerHTML = html;
}

/**
 * 恢复归档的伏笔
 */
async function restoreArchivedForeshadowing(foreshadowingId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}/restore?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadArchivedForeshadowings();
            loadForeshadowings();
            console.log(`[Recall] 已恢复归档伏笔: ${foreshadowingId}`);
        } else {
            console.error('[Recall] 恢复归档伏笔失败');
        }
    } catch (e) {
        console.error('[Recall] 恢复归档伏笔失败:', e);
    }
}

/**
 * 彻底删除归档的伏笔
 */
async function deleteArchivedForeshadowing(foreshadowingId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/archived/${foreshadowingId}?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadArchivedForeshadowings();
            console.log(`[Recall] 已彻底删除归档伏笔: ${foreshadowingId}`);
        } else {
            console.error('[Recall] 删除归档伏笔失败');
        }
    } catch (e) {
        console.error('[Recall] 删除归档伏笔失败:', e);
    }
}

/**
 * 清空所有归档的伏笔
 */
async function onClearAllArchivedForeshadowings() {
    if (!isConnected) {
        alert('请先连接 Recall 服务');
        return;
    }
    
    if (!confirm('确定要清空所有归档的伏笔吗？\n\n此操作不可恢复！')) return;
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/archived?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            loadArchivedForeshadowings();
            console.log(`[Recall] 已清空 ${result.count} 个归档伏笔`);
        }
    } catch (e) {
        console.error('[Recall] 清空归档伏笔失败:', e);
    }
}

/**
 * 手动归档活跃的伏笔
 */
async function archiveForeshadowing(foreshadowingId) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}/archive?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadForeshadowings();
            loadArchivedForeshadowings();
            console.log(`[Recall] 已归档伏笔: ${foreshadowingId}`);
        }
    } catch (e) {
        console.error('[Recall] 归档伏笔失败:', e);
    }
}

// ==================== 编辑功能 ====================

/**
 * 显示编辑持久条件的模态框
 */
function showEditContextModal(ctx) {
    const typeOptions = [
        { value: 'user_identity', label: '👤 身份' },
        { value: 'user_goal', label: '🎯 目标' },
        { value: 'user_preference', label: '❤️ 偏好' },
        { value: 'environment', label: '💻 环境' },
        { value: 'project', label: '📁 项目' },
        { value: 'character_trait', label: '🎭 角色' },
        { value: 'world_setting', label: '🌍 世界观' },
        { value: 'relationship', label: '🤝 关系' },
        { value: 'constraint', label: '⚠️ 约束' },
        { value: 'custom', label: '📝 自定义' }
    ];
    
    const modal = document.createElement('div');
    modal.className = 'recall-edit-modal';
    modal.innerHTML = `
        <div class="recall-edit-modal-content">
            <div class="recall-edit-modal-title">✏️ 编辑持久条件</div>
            
            <div class="recall-edit-form-group">
                <label>内容</label>
                <textarea id="recall-edit-ctx-content">${escapeHtml(ctx.content)}</textarea>
            </div>
            
            <div class="recall-edit-form-group">
                <label>类型</label>
                <select id="recall-edit-ctx-type">
                    ${typeOptions.map(opt => `<option value="${opt.value}" ${ctx.context_type === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}
                </select>
            </div>
            
            <div class="recall-edit-form-group">
                <label>置信度 (${(ctx.confidence * 100).toFixed(0)}%)</label>
                <input type="range" id="recall-edit-ctx-confidence" min="0" max="1" step="0.01" value="${ctx.confidence}">
            </div>
            
            <div class="recall-edit-form-group">
                <label>关键词 (逗号分隔)</label>
                <input type="text" id="recall-edit-ctx-keywords" value="${(ctx.keywords || []).join(', ')}">
            </div>
            
            <div class="recall-edit-modal-actions">
                <button class="recall-edit-cancel" onclick="this.closest('.recall-edit-modal').remove()">取消</button>
                <button class="recall-edit-save" id="recall-edit-ctx-save">保存</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // 置信度滑块实时显示
    const rangeEl = modal.querySelector('#recall-edit-ctx-confidence');
    const labelEl = modal.querySelectorAll('.recall-edit-form-group label')[2]; // 第三个 label 是置信度
    rangeEl.addEventListener('input', () => {
        labelEl.textContent = `置信度 (${(rangeEl.value * 100).toFixed(0)}%)`;
    });
    
    // 保存事件
    modal.querySelector('#recall-edit-ctx-save').addEventListener('click', async () => {
        const content = modal.querySelector('#recall-edit-ctx-content').value.trim();
        const contextType = modal.querySelector('#recall-edit-ctx-type').value;
        const confidence = parseFloat(modal.querySelector('#recall-edit-ctx-confidence').value);
        const keywordsStr = modal.querySelector('#recall-edit-ctx-keywords').value;
        const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];
        
        if (!content) {
            alert('内容不能为空');
            return;
        }
        
        await updateContext(ctx.id, { content, context_type: contextType, confidence, keywords });
        modal.remove();
    });
    
    // 点击遮罩关闭
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

/**
 * 更新持久条件
 */
async function updateContext(contextId, updates) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const url = `${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}?user_id=${userId}&character_id=${userId}`;
        console.log(`[Recall] 更新条件请求: ${url}`, updates);
        
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log(`[Recall] 已更新条件: ${contextId}`, result);
            safeToastr.success('持久条件已更新', 'Recall');
            loadPersistentContexts();
        } else {
            const errorText = await response.text();
            console.error('[Recall] 更新条件失败:', response.status, errorText);
            safeToastr.error(`更新失败: ${response.status} ${errorText}`, 'Recall');
        }
    } catch (e) {
        console.error('[Recall] 更新条件失败:', e);
        safeToastr.error(`更新失败: ${e.message}`, 'Recall');
    }
}

/**
 * 显示编辑伏笔的模态框
 */
function showEditForeshadowingModal(fsh) {
    const statusOptions = [
        { value: 'planted', label: '🌱 已埋下' },
        { value: 'developing', label: '🌿 发展中' },
        { value: 'resolved', label: '✅ 已解决' },
        { value: 'abandoned', label: '❌ 已放弃' }
    ];
    
    const modal = document.createElement('div');
    modal.className = 'recall-edit-modal';
    modal.innerHTML = `
        <div class="recall-edit-modal-content">
            <div class="recall-edit-modal-title">✏️ 编辑伏笔</div>
            
            <div class="recall-edit-form-group">
                <label>内容</label>
                <textarea id="recall-edit-fsh-content">${escapeHtml(fsh.content)}</textarea>
            </div>
            
            <div class="recall-edit-form-group">
                <label>状态</label>
                <select id="recall-edit-fsh-status">
                    ${statusOptions.map(opt => `<option value="${opt.value}" ${fsh.status === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}
                </select>
            </div>
            
            <div class="recall-edit-form-group">
                <label>重要性 (${(fsh.importance * 100).toFixed(0)}%)</label>
                <input type="range" id="recall-edit-fsh-importance" min="0" max="1" step="0.01" value="${fsh.importance}">
            </div>
            
            <div class="recall-edit-form-group">
                <label>提示 (每行一个)</label>
                <textarea id="recall-edit-fsh-hints" rows="3">${(fsh.hints || []).join('\n')}</textarea>
            </div>
            
            <div class="recall-edit-form-group">
                <label>解决方案</label>
                <input type="text" id="recall-edit-fsh-resolution" value="${fsh.resolution || ''}">
            </div>
            
            <div class="recall-edit-modal-actions">
                <button class="recall-edit-cancel" onclick="this.closest('.recall-edit-modal').remove()">取消</button>
                <button class="recall-edit-save" id="recall-edit-fsh-save">保存</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // 重要性滑块实时显示
    const rangeEl = modal.querySelector('#recall-edit-fsh-importance');
    const labelEl = modal.querySelectorAll('.recall-edit-form-group label')[2];
    rangeEl.addEventListener('input', () => {
        labelEl.textContent = `重要性 (${(rangeEl.value * 100).toFixed(0)}%)`;
    });
    
    // 保存事件
    modal.querySelector('#recall-edit-fsh-save').addEventListener('click', async () => {
        const content = modal.querySelector('#recall-edit-fsh-content').value.trim();
        const status = modal.querySelector('#recall-edit-fsh-status').value;
        const importance = parseFloat(modal.querySelector('#recall-edit-fsh-importance').value);
        const hintsStr = modal.querySelector('#recall-edit-fsh-hints').value;
        const hints = hintsStr ? hintsStr.split('\n').map(h => h.trim()).filter(h => h) : [];
        const resolution = modal.querySelector('#recall-edit-fsh-resolution').value.trim() || null;
        
        if (!content) {
            alert('内容不能为空');
            return;
        }
        
        await updateForeshadowing(fsh.id, { content, status, importance, hints, resolution });
        modal.remove();
    });
    
    // 点击遮罩关闭
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

/**
 * 更新伏笔
 */
async function updateForeshadowing(foreshadowingId, updates) {
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}?user_id=${userId}&character_id=${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        
        if (response.ok) {
            loadForeshadowings();
            console.log(`[Recall] 已更新伏笔: ${foreshadowingId}`);
        } else {
            console.error('[Recall] 更新伏笔失败');
        }
    } catch (e) {
        console.error('[Recall] 更新伏笔失败:', e);
    }
}

// 将分页函数暴露到命名空间，避免全局污染
window.RecallPlugin = window.RecallPlugin || {};
window.RecallPlugin.loadArchivedContexts = loadArchivedContexts;
window.RecallPlugin.loadArchivedForeshadowings = loadArchivedForeshadowings;

/**
 * 压缩合并持久条件
 */
async function consolidatePersistentContexts() {
    if (!isConnected) return;
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/consolidate?user_id=${userId}&character_id=${userId}&force=true`, {
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
 * 重建向量索引
 */
async function onRebuildVectorIndex() {
    if (!isConnected) {
        alert('请先连接 Recall 服务');
        return;
    }
    
    // 确认对话框
    const confirmMsg = currentCharacterId 
        ? `确定要重建「${currentCharacterId}」的向量索引吗？\n\n这将从现有记忆重新生成向量索引，用于修复语义搜索问题。` 
        : '确定要重建所有用户的向量索引吗？\n\n这将从现有记忆重新生成向量索引，用于修复语义搜索问题。';
    
    if (!confirm(confirmMsg)) return;
    
    const btn = document.getElementById('recall-rebuild-vector-index');
    const originalText = btn?.innerHTML;
    
    try {
        // 显示加载状态
        if (btn) {
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>重建中...</span>';
            btn.disabled = true;
        }
        
        const userId = currentCharacterId ? encodeURIComponent(currentCharacterId) : '';
        const url = userId 
            ? `${pluginSettings.apiUrl}/v1/indexes/rebuild-vector?user_id=${userId}`
            : `${pluginSettings.apiUrl}/v1/indexes/rebuild-vector`;
        
        const response = await fetch(url, { method: 'POST' });
        const result = await response.json();
        
        if (result.success) {
            alert(`✅ 向量索引重建完成！\n\n成功索引: ${result.indexed_count}/${result.total_memories} 条记忆`);
            console.log('[Recall] 向量索引重建完成:', result);
        } else {
            alert(`❌ 重建失败: ${result.message}`);
            console.error('[Recall] 向量索引重建失败:', result);
        }
    } catch (e) {
        console.error('[Recall] 重建向量索引失败:', e);
        alert('重建向量索引失败: ' + e.message);
    } finally {
        // 恢复按钮状态
        if (btn && originalText) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
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
    
    // 存储伏笔数据用于编辑
    window._recallForeshadowingsData = {};
    foreshadowings.forEach(f => {
        window._recallForeshadowingsData[f.id] = f;
    });
    
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
                    <button class="recall-action-btn recall-edit-foreshadowing" data-id="${f.id}" title="编辑">✏️</button>
                    ${isActive ? `<button class="recall-action-btn recall-archive-foreshadowing" data-id="${f.id}" title="归档">📦</button>` : ''}
                    ${isActive ? `<button class="recall-action-btn recall-resolve-foreshadowing" data-id="${f.id}" title="标记为已解决">✓</button>` : ''}
                    ${isActive ? `<button class="recall-delete-btn recall-abandon-foreshadowing" data-id="${f.id}" title="放弃此伏笔">✕</button>` : '<span class="recall-memory-score">已完成</span>'}
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
    
    // 绑定编辑按钮事件
    listEl.querySelectorAll('.recall-edit-foreshadowing').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const id = e.currentTarget.dataset.id;
            const fsh = window._recallForeshadowingsData[id];
            if (fsh) showEditForeshadowingModal(fsh);
        });
    });
    
    // 绑定归档按钮事件
    listEl.querySelectorAll('.recall-archive-foreshadowing').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            if (confirm('确定要归档这个伏笔吗？')) {
                await archiveForeshadowing(id);
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
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}/resolve?user_id=${userId}&character_id=${userId}`, {
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
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}?user_id=${userId}&character_id=${userId}`, {
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

// ============================================================================
// v4.0/v4.1 新功能 API 函数
// ============================================================================

// 当前选中的实体和矛盾（用于详情面板）
let currentSelectedEntity = null;
let currentSelectedContradiction = null;

/**
 * 加载实体列表
 */
async function loadEntities() {
    const userId = currentCharacterId || 'default';
    const searchInput = document.getElementById('recall-entity-search-input');
    const typeFilter = document.getElementById('recall-entity-type-filter');
    const search = searchInput?.value?.trim() || '';
    const entityType = typeFilter?.value || '';
    
    try {
        let url = `${pluginSettings.apiUrl}/v1/entities?user_id=${encodeURIComponent(userId)}&limit=100`;
        if (entityType) url += `&entity_type=${encodeURIComponent(entityType)}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        let entities = data.entities || data || [];
        
        // 客户端搜索过滤
        if (search) {
            entities = entities.filter(e => 
                (e.name || '').toLowerCase().includes(search.toLowerCase())
            );
        }
        
        // 更新计数
        document.getElementById('recall-entity-count').textContent = entities.length;
        
        // 渲染列表
        const listEl = document.getElementById('recall-entity-list');
        if (!listEl) return;
        
        if (entities.length === 0) {
            listEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">🏷️</div>
                    <p>暂无实体</p>
                    <small>对话时会自动提取实体</small>
                </div>
            `;
            return;
        }
        
        listEl.innerHTML = entities.map(e => createEntityItemHtml(e)).join('');
        
        // 绑定实体点击事件
        listEl.querySelectorAll('.recall-entity-item').forEach(item => {
            item.addEventListener('click', () => {
                const entityName = item.dataset.name;
                showEntityDetail(entityName);
            });
        });
        
    } catch (e) {
        console.warn('[Recall] 加载实体失败:', e);
        safeToastr.error('加载实体失败: ' + e.message);
    }
}

/**
 * 创建单个实体项 HTML
 */
function createEntityItemHtml(entity) {
    const name = entity.name || entity.entity_name || '-';
    const type = entity.entity_type || entity.type || 'UNKNOWN';
    const count = entity.mention_count || entity.count || 0;
    const typeIcon = getEntityTypeIcon(type);
    
    return `
        <div class="recall-entity-item" data-name="${escapeHtml(name)}">
            <span class="recall-entity-icon">${typeIcon}</span>
            <div class="recall-entity-info">
                <div class="recall-entity-name">${escapeHtml(name)}</div>
                <div class="recall-entity-meta">${type} · 出现 ${count} 次</div>
            </div>
        </div>
    `;
}

/**
 * 获取实体类型图标
 */
function getEntityTypeIcon(type) {
    const icons = {
        'PERSON': '👤',
        'LOCATION': '📍',
        'ORGANIZATION': '🏢',
        'OBJECT': '📦',
        'EVENT': '📅',
        'CONCEPT': '💡',
        'TIME': '⏰',
        'UNKNOWN': '❓'
    };
    return icons[type?.toUpperCase()] || '🏷️';
}

/**
 * 显示实体详情
 */
async function showEntityDetail(entityName) {
    const userId = currentCharacterId || 'default';
    currentSelectedEntity = entityName;
    
    try {
        // 获取实体详情
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/entities/${encodeURIComponent(entityName)}?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const entity = await response.json();
        
        // 获取相关实体
        let relatedEntities = [];
        try {
            const relatedResponse = await fetch(
                `${pluginSettings.apiUrl}/v1/entities/${encodeURIComponent(entityName)}/related?user_id=${encodeURIComponent(userId)}`
            );
            if (relatedResponse.ok) {
                const relatedData = await relatedResponse.json();
                relatedEntities = relatedData.related || relatedData || [];
            }
        } catch (e) {
            console.warn('[Recall] 获取相关实体失败:', e);
        }
        
        // 填充详情面板
        document.getElementById('recall-entity-detail-name').textContent = entityName;
        document.getElementById('recall-entity-detail-type').textContent = entity.entity_type || entity.type || '-';
        document.getElementById('recall-entity-detail-summary').textContent = entity.summary || '暂无摘要';
        document.getElementById('recall-entity-detail-count').textContent = entity.mention_count || entity.count || '-';
        
        // 显示相关实体
        if (relatedEntities.length > 0) {
            const relatedHtml = relatedEntities.slice(0, 10).map(r => {
                const name = r.name || r.entity_name || r;
                const relation = r.relation || r.relation_type || '';
                return `<span class="recall-related-entity" data-name="${escapeHtml(name)}">${escapeHtml(name)}${relation ? ` (${relation})` : ''}</span>`;
            }).join(' ');
            document.getElementById('recall-entity-detail-relations').innerHTML = relatedHtml;
            
            // 绑定相关实体点击事件
            document.querySelectorAll('.recall-related-entity').forEach(el => {
                el.addEventListener('click', () => {
                    showEntityDetail(el.dataset.name);
                });
            });
        } else {
            document.getElementById('recall-entity-detail-relations').textContent = '暂无关系';
        }
        
        // 显示面板
        document.getElementById('recall-entity-detail-panel').style.display = 'block';
        
    } catch (e) {
        console.warn('[Recall] 获取实体详情失败:', e);
        safeToastr.error('获取实体详情失败: ' + e.message);
    }
}

/**
 * 生成实体摘要
 */
async function generateEntitySummary() {
    if (!currentSelectedEntity) return;
    
    const userId = currentCharacterId || 'default';
    const btn = document.getElementById('recall-generate-entity-summary');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 生成中...';
    btn.disabled = true;
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/entities/${encodeURIComponent(currentSelectedEntity)}/generate-summary?user_id=${encodeURIComponent(userId)}`,
            { method: 'POST' }
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();
        
        document.getElementById('recall-entity-detail-summary').textContent = result.summary || '生成失败';
        safeToastr.success('摘要已生成');
        
    } catch (e) {
        console.warn('[Recall] 生成摘要失败:', e);
        safeToastr.error('生成摘要失败: ' + e.message);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

/**
 * 加载矛盾列表
 */
async function loadContradictions() {
    const userId = currentCharacterId || 'default';
    const statusFilter = document.getElementById('recall-contradiction-status-filter');
    const status = statusFilter?.value || '';
    
    try {
        let url = `${pluginSettings.apiUrl}/v1/contradictions?user_id=${encodeURIComponent(userId)}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        const contradictions = data.contradictions || data || [];
        
        // 更新计数
        document.getElementById('recall-contradiction-count').textContent = contradictions.length;
        
        // 渲染列表
        const listEl = document.getElementById('recall-contradiction-list');
        if (!listEl) return;
        
        if (contradictions.length === 0) {
            listEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">⚔️</div>
                    <p>暂无矛盾</p>
                    <small>系统会自动检测事实冲突</small>
                </div>
            `;
            return;
        }
        
        listEl.innerHTML = contradictions.map(c => createContradictionItemHtml(c)).join('');
        
        // 绑定矛盾点击事件
        listEl.querySelectorAll('.recall-contradiction-item').forEach(item => {
            item.addEventListener('click', () => {
                const contradictionId = item.dataset.id;
                const contradiction = contradictions.find(c => (c.id || c.contradiction_id) === contradictionId);
                if (contradiction) showContradictionDetail(contradiction);
            });
        });
        
    } catch (e) {
        console.warn('[Recall] 加载矛盾失败:', e);
        safeToastr.error('加载矛盾失败: ' + e.message);
    }
}

/**
 * 创建单个矛盾项 HTML
 */
function createContradictionItemHtml(contradiction) {
    const id = contradiction.id || contradiction.contradiction_id || '';
    const status = contradiction.status || 'pending';
    const factA = contradiction.fact_a || contradiction.statement_a || '';
    const factB = contradiction.fact_b || contradiction.statement_b || '';
    const statusIcon = status === 'pending' ? '⏳' : status === 'resolved' ? '✅' : '🚫';
    
    return `
        <div class="recall-contradiction-item" data-id="${id}">
            <div class="recall-contradiction-header">
                <span class="recall-contradiction-status">${statusIcon} ${status}</span>
            </div>
            <div class="recall-contradiction-preview">
                <div class="recall-contradiction-fact-preview">${escapeHtml(factA.substring(0, 50))}...</div>
                <div class="recall-contradiction-vs-preview">⚔️</div>
                <div class="recall-contradiction-fact-preview">${escapeHtml(factB.substring(0, 50))}...</div>
            </div>
        </div>
    `;
}

/**
 * 显示矛盾详情
 */
function showContradictionDetail(contradiction) {
    currentSelectedContradiction = contradiction;
    
    const factAEl = document.getElementById('recall-contradiction-fact-a');
    const factBEl = document.getElementById('recall-contradiction-fact-b');
    const panelEl = document.getElementById('recall-contradiction-detail-panel');
    
    if (factAEl) {
        factAEl.textContent = contradiction.fact_a || contradiction.statement_a || '-';
    }
    if (factBEl) {
        factBEl.textContent = contradiction.fact_b || contradiction.statement_b || '-';
    }
    if (panelEl) {
        panelEl.style.display = 'block';
    }
}

/**
 * 解决矛盾
 */
async function resolveContradiction(resolution) {
    if (!currentSelectedContradiction) return;
    
    const userId = currentCharacterId || 'default';
    const contradictionId = currentSelectedContradiction.id || currentSelectedContradiction.contradiction_id;
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/contradictions/${encodeURIComponent(contradictionId)}/resolve?user_id=${encodeURIComponent(userId)}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ resolution })
            }
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        safeToastr.success('矛盾已解决');
        document.getElementById('recall-contradiction-detail-panel').style.display = 'none';
        currentSelectedContradiction = null;
        loadContradictions();
        
    } catch (e) {
        console.warn('[Recall] 解决矛盾失败:', e);
        safeToastr.error('解决矛盾失败: ' + e.message);
    }
}

/**
 * 加载时态统计
 */
async function loadTemporalStats() {
    const userId = currentCharacterId || 'default';
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/temporal/stats?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const stats = await response.json();
        
        document.getElementById('recall-temporal-record-count').textContent = 
            stats.total_records || stats.record_count || 0;
        document.getElementById('recall-temporal-span').textContent = 
            stats.time_span || stats.span || '-';
        
    } catch (e) {
        console.warn('[Recall] 加载时态统计失败:', e);
    }
}

/**
 * 查询实体时间线
 */
async function queryEntityTimeline() {
    const entityInput = document.getElementById('recall-temporal-entity-input');
    const entityName = entityInput?.value?.trim();
    
    if (!entityName) {
        safeToastr.warning('请输入实体名称');
        return;
    }
    
    const userId = currentCharacterId || 'default';
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/temporal/timeline/${encodeURIComponent(entityName)}?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const timeline = data.timeline || data.events || data || [];
        
        // 渲染时间线
        const resultsEl = document.getElementById('recall-temporal-results');
        if (!resultsEl) return;
        
        if (timeline.length === 0) {
            resultsEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">⏱️</div>
                    <p>未找到时间线数据</p>
                </div>
            `;
            return;
        }
        
        resultsEl.innerHTML = `
            <div class="recall-timeline">
                ${timeline.map(event => `
                    <div class="recall-timeline-item">
                        <div class="recall-timeline-time">${formatTimelineDate(event.timestamp || event.time)}</div>
                        <div class="recall-timeline-content">${escapeHtml(event.fact || event.content || event.description || '-')}</div>
                    </div>
                `).join('')}
            </div>
        `;
        
    } catch (e) {
        console.warn('[Recall] 查询时间线失败:', e);
        safeToastr.error('查询时间线失败: ' + e.message);
    }
}

/**
 * 时间范围查询
 */
async function queryTemporalRange() {
    const startInput = document.getElementById('recall-temporal-start');
    const endInput = document.getElementById('recall-temporal-end');
    const startTime = startInput?.value;
    const endTime = endInput?.value;
    
    if (!startTime || !endTime) {
        safeToastr.warning('请选择时间范围');
        return;
    }
    
    const userId = currentCharacterId || 'default';
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/temporal/range`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: userId,
                    start_time: new Date(startTime).toISOString(),
                    end_time: new Date(endTime).toISOString()
                })
            }
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const facts = data.facts || data.results || data || [];
        
        // 渲染结果
        const resultsEl = document.getElementById('recall-temporal-results');
        if (!resultsEl) return;
        
        if (facts.length === 0) {
            resultsEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">⏱️</div>
                    <p>该时间范围内无记录</p>
                </div>
            `;
            return;
        }
        
        resultsEl.innerHTML = `
            <div class="recall-temporal-facts">
                ${facts.map(f => `
                    <div class="recall-temporal-fact-item">
                        <div class="recall-temporal-fact-time">${formatTimelineDate(f.timestamp || f.time)}</div>
                        <div class="recall-temporal-fact-content">${escapeHtml(f.fact || f.content || '-')}</div>
                    </div>
                `).join('')}
            </div>
        `;
        
    } catch (e) {
        console.warn('[Recall] 时间范围查询失败:', e);
        safeToastr.error('时间范围查询失败: ' + e.message);
    }
}

/**
 * 格式化时间线日期
 */
function formatTimelineDate(timestamp) {
    if (!timestamp) return '-';
    try {
        const date = new Date(timestamp);
        return date.toLocaleString();
    } catch {
        return String(timestamp);
    }
}

/**
 * 图遍历
 */
async function traverseGraph() {
    const entityInput = document.getElementById('recall-graph-entity-input');
    const depthSelect = document.getElementById('recall-graph-depth');
    const entityName = entityInput?.value?.trim();
    const depth = parseInt(depthSelect?.value || '2');
    
    if (!entityName) {
        safeToastr.warning('请输入起始实体');
        return;
    }
    
    const userId = currentCharacterId || 'default';
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/graph/traverse`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: userId,
                    start_entity: entityName,
                    max_depth: depth,
                    direction: 'both'
                })
            }
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const nodes = data.nodes || [];
        const edges = data.edges || data.relations || [];
        
        // 渲染结果
        const resultsEl = document.getElementById('recall-graph-results');
        if (!resultsEl) return;
        
        if (nodes.length === 0) {
            resultsEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">🕸️</div>
                    <p>未找到相关节点</p>
                </div>
            `;
            return;
        }
        
        resultsEl.innerHTML = `
            <div class="recall-graph-info">
                <div class="recall-stat-item">节点数: <strong>${nodes.length}</strong></div>
                <div class="recall-stat-item">边数: <strong>${edges.length}</strong></div>
            </div>
            <div class="recall-graph-nodes">
                ${nodes.map(n => `
                    <div class="recall-graph-node" data-name="${escapeHtml(n.name || n)}">
                        ${getEntityTypeIcon(n.type || 'UNKNOWN')} ${escapeHtml(n.name || n)}
                    </div>
                `).join('')}
            </div>
            <div class="recall-graph-edges">
                <div class="recall-setting-title" style="margin-top:10px;">关系列表</div>
                ${edges.slice(0, 20).map(e => `
                    <div class="recall-graph-edge">
                        ${escapeHtml(e.source || e.from)} → <em>${escapeHtml(e.relation || e.type || '相关')}</em> → ${escapeHtml(e.target || e.to)}
                    </div>
                `).join('')}
                ${edges.length > 20 ? `<div class="recall-more-hint">还有 ${edges.length - 20} 条关系...</div>` : ''}
            </div>
        `;
        
        // 绑定节点点击事件
        resultsEl.querySelectorAll('.recall-graph-node').forEach(node => {
            node.addEventListener('click', () => {
                entityInput.value = node.dataset.name;
                traverseGraph();
            });
        });
        
    } catch (e) {
        console.warn('[Recall] 图遍历失败:', e);
        safeToastr.error('图遍历失败: ' + e.message);
    }
}

/**
 * 加载社区检测结果
 */
async function loadCommunities() {
    const userId = currentCharacterId || 'default';
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/graph/communities?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const communities = data.communities || data || [];
        
        const listEl = document.getElementById('recall-communities-list');
        const contentEl = document.getElementById('recall-communities-content');
        if (!listEl || !contentEl) return;
        
        if (communities.length === 0) {
            contentEl.innerHTML = '<div class="recall-setting-hint">未检测到社区结构</div>';
        } else {
            contentEl.innerHTML = communities.map((c, i) => `
                <div class="recall-community-item">
                    <div class="recall-community-header">🏘️ 社区 ${i + 1} (${c.members?.length || c.size || 0} 成员)</div>
                    <div class="recall-community-members">
                        ${(c.members || c.entities || []).slice(0, 10).map(m => 
                            `<span class="recall-community-member">${escapeHtml(m)}</span>`
                        ).join(' ')}
                        ${(c.members || c.entities || []).length > 10 ? '...' : ''}
                    </div>
                </div>
            `).join('');
        }
        
        listEl.style.display = 'block';
        
    } catch (e) {
        console.warn('[Recall] 加载社区失败:', e);
        safeToastr.error('社区检测失败: ' + e.message);
    }
}

/**
 * 加载高级功能配置 (v4.0/v4.1)
 */
async function loadAdvancedConfig() {
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config/full`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const config = await response.json();
        
        // 核心功能开关
        const temporalGraphEl = document.getElementById('recall-temporal-graph-enabled');
        const contradictionEl = document.getElementById('recall-contradiction-detection-enabled');
        const entitySummaryEl = document.getElementById('recall-entity-summary-enabled');
        
        if (temporalGraphEl) temporalGraphEl.checked = config.TEMPORAL_GRAPH_ENABLED ?? true;
        if (contradictionEl) contradictionEl.checked = config.CONTRADICTION_DETECTION_ENABLED ?? true;
        if (entitySummaryEl) entitySummaryEl.checked = config.ENTITY_SUMMARY_ENABLED ?? true;
        
        // 检索层配置
        const l2El = document.getElementById('recall-retrieval-l2-temporal');
        const l4El = document.getElementById('recall-retrieval-l4-entity');
        const l5El = document.getElementById('recall-retrieval-l5-graph');
        
        if (l2El) l2El.checked = config.RETRIEVAL_L2_TEMPORAL_ENABLED ?? true;
        if (l4El) l4El.checked = config.RETRIEVAL_L4_ENTITY_ENABLED ?? true;
        if (l5El) l5El.checked = config.RETRIEVAL_L5_GRAPH_ENABLED ?? true;
        
        safeToastr.success('高级配置已加载');
        
    } catch (e) {
        console.warn('[Recall] 加载高级配置失败:', e);
        safeToastr.error('加载高级配置失败: ' + e.message);
    }
}

/**
 * 保存高级功能配置到服务器
 */
async function saveAdvancedConfig() {
    try {
        const config = {
            // 核心功能开关
            TEMPORAL_GRAPH_ENABLED: document.getElementById('recall-temporal-graph-enabled')?.checked ?? true,
            CONTRADICTION_DETECTION_ENABLED: document.getElementById('recall-contradiction-detection-enabled')?.checked ?? true,
            ENTITY_SUMMARY_ENABLED: document.getElementById('recall-entity-summary-enabled')?.checked ?? true,
            
            // 检索层配置
            RETRIEVAL_L2_TEMPORAL_ENABLED: document.getElementById('recall-retrieval-l2-temporal')?.checked ?? true,
            RETRIEVAL_L4_ENTITY_ENABLED: document.getElementById('recall-retrieval-l4-entity')?.checked ?? true,
            RETRIEVAL_L5_GRAPH_ENABLED: document.getElementById('recall-retrieval-l5-graph')?.checked ?? true
        };
        
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const result = await response.json();
        
        if (result.success || result.status === 'ok') {
            safeToastr.success('高级配置已保存到服务器');
        } else {
            throw new Error(result.message || '保存失败');
        }
        
    } catch (e) {
        console.warn('[Recall] 保存高级配置失败:', e);
        safeToastr.error('保存高级配置失败: ' + e.message);
    }
}

// ============================================================================
// Episode 片段管理函数
// ============================================================================

let currentSelectedEpisode = null;

/**
 * 加载 Episode 列表
 */
async function loadEpisodes() {
    const userId = currentCharacterId || 'default';
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/episodes?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        const episodes = data.episodes || data || [];
        
        // 更新计数
        document.getElementById('recall-episode-count').textContent = episodes.length;
        
        // 渲染列表
        const listEl = document.getElementById('recall-episode-list');
        if (!listEl) return;
        
        if (episodes.length === 0) {
            listEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">📖</div>
                    <p>暂无对话片段</p>
                    <small>对话时会自动组织成片段</small>
                </div>
            `;
            return;
        }
        
        listEl.innerHTML = episodes.map(ep => createEpisodeItemHtml(ep)).join('');
        
        // 绑定点击事件
        listEl.querySelectorAll('.recall-episode-item').forEach(item => {
            item.addEventListener('click', () => {
                const episodeId = item.dataset.id;
                const episode = episodes.find(e => (e.uuid || e.id || e.episode_id) === episodeId);
                if (episode) showEpisodeDetail(episode);
            });
        });
        
    } catch (e) {
        console.warn('[Recall] 加载 Episode 失败:', e);
        safeToastr.error('加载片段失败: ' + e.message);
    }
}

/**
 * 创建 Episode 项 HTML
 */
function createEpisodeItemHtml(episode) {
    const id = episode.uuid || episode.id || episode.episode_id || '';
    const startTime = formatTimelineDate(episode.start_time || episode.created_at);
    const endTime = formatTimelineDate(episode.end_time || episode.updated_at);
    const memoryCount = episode.memory_count || episode.memories?.length || 0;
    const summary = episode.summary || episode.title || `片段 ${id.substring(0, 8)}...`;
    
    return `
        <div class="recall-episode-item" data-id="${escapeHtml(id)}">
            <div class="recall-episode-icon">📖</div>
            <div class="recall-episode-info">
                <div class="recall-episode-title">${escapeHtml(summary)}</div>
                <div class="recall-episode-meta">
                    ${startTime} ~ ${endTime} · ${memoryCount} 条记忆
                </div>
            </div>
        </div>
    `;
}

/**
 * 显示 Episode 详情
 */
async function showEpisodeDetail(episode) {
    currentSelectedEpisode = episode;
    const episodeId = episode.uuid || episode.id || episode.episode_id;
    
    document.getElementById('recall-episode-detail-id').textContent = episodeId;
    document.getElementById('recall-episode-detail-start').textContent = 
        formatTimelineDate(episode.start_time || episode.created_at);
    document.getElementById('recall-episode-detail-end').textContent = 
        formatTimelineDate(episode.end_time || episode.updated_at);
    document.getElementById('recall-episode-detail-memory-count').textContent = 
        episode.memory_count || episode.memories?.length || 0;
    
    // 加载 Episode 详情（包含记忆列表）
    try {
        const userId = currentCharacterId || 'default';
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/episodes/${encodeURIComponent(episodeId)}?user_id=${encodeURIComponent(userId)}`
        );
        
        if (response.ok) {
            const detail = await response.json();
            const memories = detail.memories || [];
            
            const memoriesEl = document.getElementById('recall-episode-memories');
            if (memoriesEl) {
                if (memories.length === 0) {
                    memoriesEl.innerHTML = '<div class="recall-setting-hint">无关联记忆</div>';
                } else {
                    memoriesEl.innerHTML = memories.slice(0, 10).map(m => `
                        <div class="recall-episode-memory-item">
                            <div class="recall-episode-memory-role">${m.role === 'user' ? '👤' : '🤖'}</div>
                            <div class="recall-episode-memory-content">${escapeHtml((m.content || '').substring(0, 100))}...</div>
                        </div>
                    `).join('');
                    
                    if (memories.length > 10) {
                        memoriesEl.innerHTML += `<div class="recall-more-hint">还有 ${memories.length - 10} 条记忆...</div>`;
                    }
                }
            }
        }
    } catch (e) {
        console.warn('[Recall] 加载 Episode 详情失败:', e);
    }
    
    document.getElementById('recall-episode-detail-panel').style.display = 'block';
}

// ============================================================================
// 高级搜索函数
// ============================================================================

/**
 * 执行高级搜索
 */
async function performAdvancedSearch() {
    const query = document.getElementById('recall-advanced-search-input')?.value?.trim();
    
    if (!query) {
        safeToastr.warning('请输入搜索内容');
        return;
    }
    
    const userId = currentCharacterId || 'default';
    const limit = parseInt(document.getElementById('recall-search-limit')?.value || '10');
    const activeTab = document.querySelector('.recall-search-type-tab.active');
    const searchType = activeTab?.dataset?.type || 'hybrid';
    const hybridWeight = parseFloat(document.getElementById('recall-hybrid-weight')?.value || '0.6');
    
    try {
        let url, body;
        
        if (searchType === 'fulltext') {
            // 全文搜索
            url = `${pluginSettings.apiUrl}/v1/search/fulltext`;
            body = {
                query: query,
                user_id: userId,
                limit: limit
            };
        } else if (searchType === 'hybrid') {
            // 混合搜索
            url = `${pluginSettings.apiUrl}/v1/search/hybrid`;
            body = {
                query: query,
                user_id: userId,
                limit: limit,
                semantic_weight: hybridWeight
            };
        } else {
            // 语义搜索（使用基础搜索接口）
            url = `${pluginSettings.apiUrl}/v1/memories/search`;
            body = {
                query: query,
                user_id: userId,
                top_k: limit
            };
        }
        
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        const results = data.results || data.memories || data || [];
        
        // 更新结果计数
        document.getElementById('recall-search-result-count').textContent = `(${results.length})`;
        
        // 渲染结果
        const resultsEl = document.getElementById('recall-advanced-search-results');
        if (!resultsEl) return;
        
        if (results.length === 0) {
            resultsEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">🔍</div>
                    <p>未找到匹配结果</p>
                    <small>尝试其他关键词或搜索类型</small>
                </div>
            `;
            return;
        }
        
        resultsEl.innerHTML = results.map(r => createSearchResultItemHtml(r, searchType)).join('');
        
    } catch (e) {
        console.warn('[Recall] 高级搜索失败:', e);
        safeToastr.error('搜索失败: ' + e.message);
    }
}

/**
 * 创建搜索结果项 HTML
 */
function createSearchResultItemHtml(result, searchType) {
    const content = result.content || result.text || '';
    const role = result.role || result.metadata?.role || 'unknown';
    const score = result.score || result.similarity || result.relevance || 0;
    const scorePercent = (score * 100).toFixed(1);
    const roleIcon = role === 'user' ? '👤' : role === 'assistant' ? '🤖' : '📄';
    
    // 根据搜索类型显示不同的分数标签
    let scoreLabel = '';
    if (searchType === 'hybrid') {
        scoreLabel = `RRF: ${scorePercent}%`;
    } else if (searchType === 'fulltext') {
        scoreLabel = `匹配: ${scorePercent}%`;
    } else {
        scoreLabel = `相似: ${scorePercent}%`;
    }
    
    return `
        <div class="recall-search-result-item">
            <div class="recall-search-result-header">
                <span class="recall-search-result-role">${roleIcon} ${role}</span>
                <span class="recall-search-result-score">${scoreLabel}</span>
            </div>
            <div class="recall-search-result-content">${escapeHtml(content.substring(0, 300))}${content.length > 300 ? '...' : ''}</div>
        </div>
    `;
}

/**
 * 获取要注入的记忆上下文
 */
async function getMemoryContext(query) {
    if (!pluginSettings.enabled || !pluginSettings.autoInject || !isConnected) {
        return '';
    }
    
    const userId = currentCharacterId || 'default';
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/context`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                user_id: userId,
                character_id: userId,
                max_tokens: pluginSettings.maxContextTokens || 2000,
                include_recent: 3,
                include_core_facts: true
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
 * HTML 转义（高性能版本）
 */
function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// 导出供外部使用（安全方式）
// 注意：保留之前设置的分页函数
window.RecallPlugin = window.RecallPlugin || {};
window.RecallPlugin.getMemoryContext = safeExecute(getMemoryContext, '获取记忆上下文失败');
window.RecallPlugin.loadMemories = safeExecute(loadMemories, '加载记忆失败');
window.RecallPlugin.loadForeshadowings = safeExecute(loadForeshadowings, '加载伏笔失败');
window.RecallPlugin.loadPersistentContexts = safeExecute(loadPersistentContexts, '加载持久条件失败');
window.RecallPlugin.isConnected = () => isConnected;
window.RecallPlugin.isInitialized = () => isInitialized;
window.RecallPlugin.getSettings = () => ({ ...pluginSettings });

})(); // IIFE 结束
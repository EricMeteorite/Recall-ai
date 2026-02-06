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
    
    // ========== 立即暴露全局函数，供内联 onclick 使用 ==========
    // 必须在 IIFE 开始时就定义，因为 HTML 中的 onclick 属性需要它
    window.recallTabClick = function(tabName) {
        console.warn(`🔥🔥🔥 [Recall] window.recallTabClick 被调用! tabName=${tabName}`);
        // 实际实现稍后注入
        if (window._recallTabClickImpl) {
            window._recallTabClickImpl(tabName);
        } else {
            console.error('[Recall] _recallTabClickImpl 未定义!');
        }
    };
    console.log('[Recall] window.recallTabClick 已在 IIFE 开始时定义');
    
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
        chunkSize: 2000,       // 分段大小（字符数）
        maxDisplayEntities: 100,  // 实体列表显示上限
        customFilterSelectors: [],  // 用户自定义的思考内容过滤选择器
        useTurnApi: true       // v4.2: 使用 Turn API 批量保存（性能优化）
    };
    
    // v4.2: 缓存等待配对的用户消息
    let pendingUserMessage = null;
    let pendingUserMessageTimestamp = 0;
    
    // v4.2: 防止 Turn API 重复处理
    let turnApiInProgress = false;  // Turn API 正在处理中
    let lastTurnApiMessageId = null;  // 上一次 Turn API 处理的消息 ID
    
    /**
     * 远程日志上报 - 将前端日志发送到后端 start.log
     * 这样用户可以在一个地方看到完整的前后端日志链
     */
    const remoteLog = {
        _queue: [],
        _sending: false,
        _enabled: true,
        
        // 发送日志到后端
        async _send(level, message, source = 'plugin') {
            // 始终在本地 console 输出（无论远程是否可用）
            const consoleMethod = level === 'error' ? console.error : 
                                  level === 'warn' ? console.warn : console.log;
            consoleMethod(`[Recall] ${message}`);
            
            // 检查远程日志是否可用（pluginSettings 可能还未初始化）
            if (!this._enabled) return;
            if (typeof pluginSettings === 'undefined' || !pluginSettings?.apiUrl) return;
            
            // 加入队列
            this._queue.push({ level, message, source, timestamp: Date.now() });
            
            // 异步批量发送，避免阻塞
            if (!this._sending) {
                this._sending = true;
                setTimeout(() => this._flush(), 100);
            }
        },
        
        async _flush() {
            if (this._queue.length === 0) {
                this._sending = false;
                return;
            }
            
            // 再次检查 pluginSettings 是否可用
            if (typeof pluginSettings === 'undefined' || !pluginSettings?.apiUrl) {
                this._sending = false;
                return;
            }
            
            const items = this._queue.splice(0, 10); // 每次最多发送10条
            
            for (const item of items) {
                try {
                    await fetch(`${pluginSettings.apiUrl}/v1/log`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(item)
                    });
                } catch (e) {
                    // 静默失败，不影响主流程
                }
            }
            
            // 如果还有剩余，继续发送
            if (this._queue.length > 0) {
                setTimeout(() => this._flush(), 100);
            } else {
                this._sending = false;
            }
        },
        
        // 便捷方法
        debug(msg) { this._send('debug', msg); },
        info(msg) { this._send('info', msg); },
        warn(msg) { this._send('warn', msg); },
        error(msg) { this._send('error', msg); },
        
        // 带来源的方法
        turn(msg) { this._send('info', msg, 'turn'); },
        turnError(msg) { this._send('error', msg, 'turn'); },
        memory(msg) { this._send('info', msg, 'memory'); },
        memoryError(msg) { this._send('error', msg, 'memory'); }
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

    // 【新增】待处理的AI消息队列（等待渲染完成）
    const pendingAIMessages = new Map();
    
    // 【新增】选择器学习模式状态
    let selectorLearningMode = false;
    let learningModeCleanup = null;
    let learningModeTimeout = null;  // 用于取消自动停止的 timeout
    
    /**
     * 开始选择器学习模式
     */
    function startSelectorLearning() {
        if (selectorLearningMode) return;
        selectorLearningMode = true;
        
        // 【重要】自动收起扩展设置面板，让用户能看到聊天区域
        const recallExtension = document.getElementById('recall-extension');
        if (recallExtension) {
            const drawerContent = recallExtension.querySelector('.inline-drawer-content');
            const drawerIcon = recallExtension.querySelector('.inline-drawer-icon');
            if (drawerContent) {
                drawerContent.style.display = 'none';
            }
            if (drawerIcon) {
                drawerIcon.classList.remove('up');
                drawerIcon.classList.add('down');
            }
        }
        
        // 同时收起整个扩展侧边栏（如果是移动端或窄屏）
        const extensionsMenu = document.getElementById('extensionsMenu');
        if (extensionsMenu && extensionsMenu.classList.contains('openDrawer')) {
            extensionsMenu.classList.remove('openDrawer');
        }
        
        const statusEl = document.getElementById('recall-learning-status');
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.className = 'recall-learning-status active';
            statusEl.textContent = '🎯 学习模式已开启 - 点击聊天中的思考区域 (ESC取消)';
        }
        
        // 创建顶部提示条（更醒目）
        const banner = document.createElement('div');
        banner.className = 'recall-learning-banner';
        banner.id = 'recall-learning-banner';
        banner.innerHTML = `
            <div class="recall-learning-banner-content">
                <span class="recall-learning-banner-icon">🎯</span>
                <span class="recall-learning-banner-text">
                    <strong>选择器学习模式</strong><br>
                    <small>点击要过滤的元素，可连续添加多个，按 ESC 或点击右侧按钮退出</small>
                </span>
            </div>
            <div class="recall-learning-banner-result" id="recall-learning-result" style="display:none;">
                <span class="recall-learning-result-label">已学习:</span>
                <code class="recall-learning-result-selector"></code>
            </div>
            <button id="recall-cancel-learning" class="recall-learning-cancel-btn">✕ 完成</button>
        `;
        document.body.appendChild(banner);
        
        // 获取聊天区域
        const chatArea = document.getElementById('chat');
        if (!chatArea) {
            showLearningError('找不到聊天区域');
            // 需要手动清理已创建的 banner
            const existingBanner = document.getElementById('recall-learning-banner');
            if (existingBanner) existingBanner.remove();
            selectorLearningMode = false;
            const statusEl2 = document.getElementById('recall-learning-status');
            if (statusEl2) statusEl2.style.display = 'none';
            return;
        }
        
        // 辅助函数：安全获取 className 字符串
        function getClassNameString(el) {
            if (!el || !el.className) return '';
            if (typeof el.className === 'string') return el.className;
            if (el.className.baseVal) return el.className.baseVal;
            return '';
        }
        
        // 鼠标移动高亮
        const onMouseOver = (e) => {
            if (!selectorLearningMode) return;
            const target = e.target;
            // 只高亮聊天消息内的元素
            if (chatArea.contains(target) && target.closest('.mes_text')) {
                // 移除之前的高亮
                document.querySelectorAll('.recall-learning-highlight').forEach(el => {
                    el.classList.remove('recall-learning-highlight');
                });
                target.classList.add('recall-learning-highlight');
            }
        };
        
        const onMouseOut = (e) => {
            if (!selectorLearningMode) return;
            e.target.classList.remove('recall-learning-highlight');
        };
        
        // 点击选择
        const onClick = (e) => {
            if (!selectorLearningMode) return;
            const target = e.target;
            
            // 检查是否点击了取消按钮
            if (target.id === 'recall-cancel-learning' || target.closest('#recall-cancel-learning')) {
                e.preventDefault();
                e.stopPropagation();
                stopSelectorLearning(true);  // 完成时打开面板
                return;
            }
            
            // 只处理聊天消息内的元素
            if (chatArea.contains(target) && target.closest('.mes_text')) {
                e.preventDefault();
                e.stopPropagation();
                
                const mesText = target.closest('.mes_text');
                
                // 【重要】允许选择任何元素
                let targetElement = target;
                
                // 如果是 mes_text 本身，提示用户需要更具体的选择
                if (targetElement === mesText) {
                    showLearningError('请点击更具体的元素，而不是整个消息区域');
                    return;
                }
                
                // 生成选择器 - 尝试智能选择器，失败则用 fallback
                let selector = generateSmartSelector(targetElement);
                if (!selector) {
                    selector = generateFallbackSelector(targetElement, mesText);
                }
                
                // 现在 selector 一定有值（fallback 保证返回）
                if (selector) {
                    addLearnedSelector(selector, targetElement);
                }
            }
        };
        
        // ESC 取消
        const onKeyDown = (e) => {
            if (e.key === 'Escape') {
                stopSelectorLearning(true);  // 完成时打开面板，让用户看到已添加的选择器
            }
        };
        
        // 添加事件监听
        document.addEventListener('mouseover', onMouseOver, true);
        document.addEventListener('mouseout', onMouseOut, true);
        document.addEventListener('click', onClick, true);
        document.addEventListener('keydown', onKeyDown);
        
        // 保存清理函数
        learningModeCleanup = () => {
            document.removeEventListener('mouseover', onMouseOver, true);
            document.removeEventListener('mouseout', onMouseOut, true);
            document.removeEventListener('click', onClick, true);
            document.removeEventListener('keydown', onKeyDown);
            
            // 移除高亮
            document.querySelectorAll('.recall-learning-highlight').forEach(el => {
                el.classList.remove('recall-learning-highlight');
            });
            document.querySelectorAll('.recall-selected-element').forEach(el => {
                el.classList.remove('recall-selected-element');
            });
            
            // 移除提示条
            const existingBanner = document.getElementById('recall-learning-banner');
            if (existingBanner) existingBanner.remove();
        };
    }
    
    /**
     * 停止选择器学习模式
     * @param {boolean} reopenPanel - 是否重新打开设置面板（学习成功后需要）
     */
    function stopSelectorLearning(reopenPanel = false) {
        selectorLearningMode = false;
        
        // 取消自动停止的 timeout
        if (learningModeTimeout) {
            clearTimeout(learningModeTimeout);
            learningModeTimeout = null;
        }
        
        if (learningModeCleanup) {
            learningModeCleanup();
            learningModeCleanup = null;
        }
        
        // 备用清理：确保 banner 被移除（即使 cleanup 函数未设置）
        const existingBanner = document.getElementById('recall-learning-banner');
        if (existingBanner) existingBanner.remove();
        
        // 备用清理：移除可能残留的高亮样式
        document.querySelectorAll('.recall-learning-highlight, .recall-selected-element').forEach(el => {
            el.classList.remove('recall-learning-highlight', 'recall-selected-element');
        });
        
        const statusEl = document.getElementById('recall-learning-status');
        if (statusEl) {
            statusEl.style.display = 'none';
        }
        
        // 【新增】如果有新增选择器，重新展开设置面板让用户看到结果
        if (reopenPanel) {
            const recallExtension = document.getElementById('recall-extension');
            if (recallExtension) {
                const drawerContent = recallExtension.querySelector('.inline-drawer-content');
                const drawerIcon = recallExtension.querySelector('.inline-drawer-icon');
                if (drawerContent) {
                    drawerContent.style.display = 'block';
                }
                if (drawerIcon) {
                    drawerIcon.classList.remove('down');
                    drawerIcon.classList.add('up');
                }
                
                // 滚动到选择器区域
                const selectorGroup = document.getElementById('recall-selector-learning-group');
                if (selectorGroup) {
                    setTimeout(() => {
                        selectorGroup.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }, 100);
                }
            }
        }
    }
    
    /**
     * 智能生成选择器
     * 优先使用类名，避免使用太具体的选择器
     */
    function generateSmartSelector(element) {
        if (!element) return null;
        
        // 辅助函数：安全获取 className 字符串
        function getClassNameStr(el) {
            if (!el || !el.className) return '';
            if (typeof el.className === 'string') return el.className;
            if (el.className.baseVal) return el.className.baseVal;  // SVG 元素
            return '';
        }
        
        // 辅助函数：转义 CSS 选择器中的特殊字符
        function escapeCssSelector(str) {
            return str.replace(/([!"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, '\\$1');
        }
        
        // 辅助函数：检查类名是否可用于选择器（不包含特殊字符）
        function isValidClassName(className) {
            // 跳过包含特殊字符的类名（如 Tailwind 的 hover:xxx）
            return className && !/[!"#$%&'()*+,./:;<=>?@[\\\]^`{|}~]/.test(className);
        }
        
        const selectors = [];
        const elementClassStr = getClassNameStr(element);
        
        // 1. 优先使用有意义的类名
        if (elementClassStr) {
            const classes = elementClassStr.split(/\s+/).filter(c => c && c.length > 2);
            // 过滤掉我们自己添加的类和一些通用类，以及包含特殊字符的类
            const meaningfulClasses = classes.filter(c => 
                isValidClassName(c) &&
                !c.startsWith('recall-') && 
                !['mes_text', 'mes', 'mes_block'].includes(c) &&
                !/^(active|show|hide|visible|hidden|open|closed)$/i.test(c)
            );
            
            if (meaningfulClasses.length > 0) {
                // 使用最具体的类名
                selectors.push('.' + meaningfulClasses.join('.'));
            }
        }
        
        // 2. 使用 ID（如果有）
        if (element.id && !element.id.startsWith('recall-') && isValidClassName(element.id)) {
            selectors.push('#' + element.id);
        }
        
        // 3. 尝试父元素 + 当前元素的组合
        const parent = element.parentElement;
        const parentClassStr = getClassNameStr(parent);
        if (parentClassStr) {
            const parentClasses = parentClassStr.split(/\s+/).filter(c => 
                c && c.length > 2 && isValidClassName(c) && 
                !c.startsWith('recall-') && 
                !['mes_text', 'mes', 'mes_block'].includes(c)
            );
            
            if (parentClasses.length > 0 && elementClassStr) {
                const childClasses = elementClassStr.split(/\s+/).filter(c => 
                    c && c.length > 2 && isValidClassName(c) && !c.startsWith('recall-')
                );
                if (childClasses.length > 0) {
                    selectors.push('.' + parentClasses[0] + ' .' + childClasses[0]);
                }
            }
        }
        
        // 4. 使用标签名 + 类名
        if (element.tagName && elementClassStr) {
            const classes = elementClassStr.split(/\s+/).filter(c => 
                c && c.length > 2 && isValidClassName(c) && !c.startsWith('recall-')
            );
            if (classes.length > 0) {
                selectors.push(element.tagName.toLowerCase() + '.' + classes[0]);
            }
        }
        
        // 返回第一个有效的选择器
        for (const selector of selectors) {
            try {
                // 验证选择器有效性
                document.querySelector(selector);
                return selector;
            } catch (e) {
                continue;
            }
        }
        
        return null;
    }
    
    /**
     * 为没有类名的元素生成备用选择器
     * 基于标签名和在父元素中的位置
     */
    function generateFallbackSelector(element, mesText) {
        if (!element || !element.tagName) return null;
        
        // 辅助函数：获取元素在同类型兄弟中的索引
        function getNthOfTypeIndex(el) {
            if (!el.parentElement) return 1;
            const siblings = Array.from(el.parentElement.children).filter(c => c.tagName === el.tagName);
            return siblings.indexOf(el) + 1;
        }
        
        // 辅助函数：获取元素在所有兄弟中的索引
        function getNthChildIndex(el) {
            if (!el.parentElement) return 1;
            return Array.from(el.parentElement.children).indexOf(el) + 1;
        }
        
        // 辅助函数：安全获取类名字符串
        function getClassNameStr(el) {
            if (!el || !el.className) return '';
            if (typeof el.className === 'string') return el.className;
            if (el.className.baseVal) return el.className.baseVal;
            return '';
        }
        
        const tagName = element.tagName.toLowerCase();
        const selectors = [];
        
        // 1. 尝试使用父元素的类名 + 子元素标签
        const parent = element.parentElement;
        if (parent && parent !== mesText) {
            const parentClassStr = getClassNameStr(parent);
            if (parentClassStr) {
                const parentClasses = parentClassStr.split(/\s+/).filter(c => 
                    c && c.length > 2 && 
                    !c.startsWith('recall-') &&
                    !['mes_text', 'mes', 'mes_block'].includes(c)
                );
                if (parentClasses.length > 0) {
                    // .parent-class > tagname
                    selectors.push('.' + parentClasses[0] + ' > ' + tagName);
                    // .parent-class tagname (更宽松)
                    selectors.push('.' + parentClasses[0] + ' ' + tagName);
                }
            }
            
            // 2. 使用父元素标签 + 当前元素标签
            const parentTag = parent.tagName.toLowerCase();
            if (!['div', 'span'].includes(parentTag)) {
                selectors.push(parentTag + ' > ' + tagName);
            }
        }
        
        // 3. 直接使用标签名（如果是比较特殊的标签）
        const specificTags = ['details', 'summary', 'pre', 'code', 'blockquote', 'figure', 'figcaption'];
        if (specificTags.includes(tagName)) {
            selectors.push(tagName);
        }
        
        // 4. 使用 nth-of-type 选择器
        const nthIndex = getNthOfTypeIndex(element);
        if (parent && parent !== mesText) {
            const parentClassStr = getClassNameStr(parent);
            if (parentClassStr) {
                const parentClasses = parentClassStr.split(/\s+/).filter(c => 
                    c && c.length > 2 && !c.startsWith('recall-')
                );
                if (parentClasses.length > 0) {
                    selectors.push('.' + parentClasses[0] + ' > ' + tagName + ':nth-of-type(' + nthIndex + ')');
                }
            }
        }
        
        // 5. 【保底】使用 .mes_text > tagname:nth-of-type(n) 或 .mes_text tagname:nth-child(n)
        // 这个选择器一定能工作
        selectors.push('.mes_text ' + tagName + ':nth-of-type(' + nthIndex + ')');
        selectors.push('.mes_text > *:nth-child(' + getNthChildIndex(element) + ')');
        
        // 6. 最终保底：直接用标签名
        selectors.push(tagName);
        
        // 返回第一个有效的选择器
        for (const selector of selectors) {
            try {
                document.querySelector(selector);
                return selector;
            } catch (e) {
                continue;
            }
        }
        
        // 这里不应该到达，但如果到达了，返回标签名
        return tagName;
    }

    /**
     * 添加学习到的选择器
     */
    function addLearnedSelector(selector, element) {
        // 确保 customFilterSelectors 是数组
        if (!Array.isArray(pluginSettings.customFilterSelectors)) {
            pluginSettings.customFilterSelectors = [];
        }
        
        // 检查是否已存在
        if (pluginSettings.customFilterSelectors.includes(selector)) {
            showLearningResultInBanner(`${selector} (已存在)`, true);
            showLearningSuccess(`选择器已存在: ${selector}`);
            // 【改进】不自动停止，允许用户继续添加其他选择器
            return;
        }
        
        // 【新增】检查选择器是否过于通用，给出警告
        const tooGenericSelectors = ['div', 'span', 'p', 'a', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'details', 'summary', 'pre', 'code'];
        const isToGeneric = tooGenericSelectors.includes(selector.toLowerCase());
        
        // 添加选择器
        pluginSettings.customFilterSelectors.push(selector);
        saveSettings();
        
        // 更新 UI
        updateLearnedSelectorsUI();
        
        // 高亮选中的元素
        element.classList.remove('recall-learning-highlight');
        element.classList.add('recall-selected-element');
        
        // 【重要】在 banner 中显示学习到的选择器
        showLearningResultInBanner(selector, true);
        
        // 显示成功（如果选择器过于通用，显示警告）
        const count = pluginSettings.customFilterSelectors.length;
        if (isToGeneric) {
            showLearningSuccess(`⚠️ 已添加 (${count}个): ${selector} - 此选择器较为通用，可能会影响所有消息中的相似元素`);
        } else {
            showLearningSuccess(`已添加 (${count}个): ${selector}`);
        }
        
        // 【改进】不自动停止学习模式，允许用户连续添加多个选择器
        // 用户需要按 ESC 或点击取消按钮来退出学习模式
    }
    
    /**
     * 在 banner 中显示学习结果
     */
    function showLearningResultInBanner(selector, isSuccess) {
        const resultEl = document.getElementById('recall-learning-result');
        const selectorEl = resultEl?.querySelector('.recall-learning-result-selector');
        if (resultEl && selectorEl) {
            resultEl.style.display = 'flex';
            resultEl.className = `recall-learning-banner-result ${isSuccess ? 'success' : 'error'}`;
            selectorEl.textContent = selector;
        }
        
        // 更新 banner 样式
        const banner = document.getElementById('recall-learning-banner');
        if (banner) {
            banner.classList.add(isSuccess ? 'success' : 'error');
        }
    }
    
    /**
     * 移除指定的选择器
     */
    function removeLearnedSelector(index) {
        if (!Array.isArray(pluginSettings.customFilterSelectors)) return;
        if (index < 0 || index >= pluginSettings.customFilterSelectors.length) return;
        
        pluginSettings.customFilterSelectors.splice(index, 1);
        saveSettings();
        updateLearnedSelectorsUI();
    }
    
    /**
     * 清空所有学习的选择器
     */
    function clearLearnedSelectors() {
        pluginSettings.customFilterSelectors = [];
        saveSettings();
        updateLearnedSelectorsUI();
    }
    
    /**
     * 更新学习选择器的 UI 显示
     */
    function updateLearnedSelectorsUI() {
        const container = document.getElementById('recall-learned-selectors');
        if (!container) return;
        
        const selectors = Array.isArray(pluginSettings.customFilterSelectors) 
            ? pluginSettings.customFilterSelectors 
            : [];
        
        if (selectors.length === 0) {
            container.innerHTML = '';
            return;
        }
        
        container.innerHTML = selectors.map((s, i) => `
            <div class="recall-selector-item" data-index="${i}">
                <span class="recall-selector-text">${escapeHtml(s)}</span>
                <button type="button" class="recall-selector-remove" data-index="${i}">×</button>
            </div>
        `).join('');
        
        // 绑定删除按钮事件
        container.querySelectorAll('.recall-selector-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();  // 防止事件冒泡
                const idx = parseInt(e.currentTarget.dataset.index, 10);
                if (!isNaN(idx)) {
                    removeLearnedSelector(idx);
                }
            });
        });
    }
    
    /**
     * 显示学习成功提示
     */
    function showLearningSuccess(message) {
        const statusEl = document.getElementById('recall-learning-status');
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.className = 'recall-learning-status success';
            statusEl.textContent = '✅ ' + message;
        }
    }
    
    /**
     * 显示学习错误提示
     * @param {string} message - 错误信息
     * @param {boolean} autoStop - 是否自动停止学习模式（默认 false，让用户继续尝试）
     */
    function showLearningError(message, autoStop = false) {
        const statusEl = document.getElementById('recall-learning-status');
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.className = 'recall-learning-status error';
            statusEl.textContent = '❌ ' + message;
        }
        
        // 在 banner 中显示错误（但不改变 banner 整体颜色，只显示消息）
        const resultEl = document.getElementById('recall-learning-result');
        const selectorEl = resultEl?.querySelector('.recall-learning-result-selector');
        if (resultEl && selectorEl) {
            resultEl.style.display = 'flex';
            resultEl.className = 'recall-learning-banner-result error';
            const labelEl = resultEl.querySelector('.recall-learning-result-label');
            if (labelEl) labelEl.textContent = '提示:';
            selectorEl.textContent = message;
            
            // 3秒后隐藏错误提示，让用户继续尝试
            setTimeout(() => {
                if (selectorLearningMode && resultEl) {
                    resultEl.style.display = 'none';
                    if (labelEl) labelEl.textContent = '已学习:';
                }
            }, 3000);
        }
        
        // 只有明确要求时才自动停止
        if (autoStop) {
            if (learningModeTimeout) {
                clearTimeout(learningModeTimeout);
            }
            learningModeTimeout = setTimeout(() => {
                stopSelectorLearning();
            }, 2000);
        }
    }

    /**
     * 处理渲染完成的消息
     * 在 character_message_rendered 事件触发后调用
     */
    async function processPendingMessage(mesId) {
        // 【关键】统一转为数字类型，与 onMessageReceived 保持一致
        const messageIndex = typeof mesId === 'number' ? mesId : parseInt(mesId, 10);
        if (isNaN(messageIndex)) {
            console.warn('[Recall] processPendingMessage: 无效的 mesId:', mesId);
            return;
        }
        
        // 检查是否有待处理的消息
        if (!pendingAIMessages.has(messageIndex)) {
            return; // 这条消息不需要处理（可能不是通过 MESSAGE_RECEIVED 触发的）
        }
        
        const pendingData = pendingAIMessages.get(messageIndex);
        pendingAIMessages.delete(messageIndex);
        
        console.log(`[Recall] 处理渲染完成的消息 #${messageIndex}`);
        
        try {
            await saveAIMessageWithDOMExtraction(messageIndex, pendingData);
        } catch (e) {
            console.warn('[Recall] 处理渲染完成消息失败:', e);
        }
    }
    
    /**
     * 从DOM提取内容并保存AI消息
     */
    async function saveAIMessageWithDOMExtraction(messageIndex, messageData) {
        const { message } = messageData;
        
        let contentToSave = null;
        
        if (pluginSettings.filterThinking) {
            // 现在消息已经渲染完成，可以安全地从DOM提取
            const domText = getRenderedTextByIndex(messageIndex);
            
            // 【调试】打印 DOM 提取的原始结果
            console.log(`[Recall] DOM提取结果: ${domText ? domText.length + '字' : 'null'}`);
            if (domText) {
                console.log(`[Recall] DOM提取预览: ${domText.substring(0, 100)}...`);
            }
            
            if (domText && domText.trim().length > 0) {
                // 【新增】检测提取的内容是否包含大量 HTML 代码
                // 如果是，说明 HTML 没有被正确渲染，需要额外清理
                contentToSave = cleanHtmlArtifacts(domText);
                
                if (contentToSave !== domText) {
                    console.log('[Recall] ✓ 从DOM提取并清理了HTML残留');
                } else {
                    console.log('[Recall] ✓ 从DOM提取用户可见内容（渲染完成后）');
                }
            } else {
                // fallback：DOM提取失败，使用正则过滤
                contentToSave = filterThinkingContent(message.mes);
                // 同样需要清理 HTML 残留
                contentToSave = cleanHtmlArtifacts(contentToSave);
                
                if (contentToSave !== message.mes) {
                    console.log('[Recall] ⚠ DOM提取失败，已使用正则过滤+HTML清理');
                } else {
                    console.log('[Recall] ⚠ DOM提取失败，使用原始内容');
                }
            }
        } else {
            // 用户关闭了过滤功能，直接使用原始内容
            // 注意：这个分支理论上不会触发，因为调用者会检查 filterThinking
            contentToSave = message.mes;
            console.log('[Recall] 未启用智能提取，使用原始内容');
        }
        
        // 如果过滤后内容为空，跳过
        if (!contentToSave || contentToSave.trim().length === 0) {
            console.log('[Recall] 过滤后内容为空，跳过保存');
            return;
        }
        
        // v4.2: 复用 saveAIMessageDirect 以支持 Turn API
        // 之前这里直接使用 memorySaveQueue.add，完全绕过了 Turn API
        await saveAIMessageDirect(messageIndex, message, contentToSave);
    }
    
    /**
     * 【通用】清理文本中的 HTML 残留
     * 当 HTML 作为纯文本存在（未被浏览器渲染）时，需要清理这些代码
     * 这是一个通用方案，不针对任何特定预设
     */
    function cleanHtmlArtifacts(text) {
        if (!text) return text;
        
        let cleaned = text;
        const originalLength = cleaned.length;
        
        // 【关键】使用 DOM 解析来移除思考容器
        // 创建临时 DOM 元素来解析 HTML 结构
        try {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = cleaned;
            
            // 查找并移除所有"思考容器"
            // 【注意】这里使用更保守的选择器，因为这是 fallback 路径
            // 只移除明显是思考内容容器的元素，避免误删正常内容
            const thinkingSelectors = [
                // 思考内容容器（必须同时包含关键词和"content"）
                '[class*="think"][class*="content"]',
                '[class*="thought"][class*="content"]',
                '[class*="reasoning"][class*="content"]',
                '[class*="cot"][class*="content"]',
                '[class*="reflection"][class*="content"]',
                '[class*="inner"][class*="content"]',
                '[class*="monologue"][class*="content"]',
                // 折叠容器
                '[class*="collapse"][class*="content"]',
                '[class*="fold"][class*="content"]',
                // 通过 ID 匹配思考容器
                '[id*="think-content"]',
                '[id*="thought-content"]',
                '[id*="reasoning-content"]',
                '[id*="cot-content"]',
            ];
            
            // 【关键】添加用户自定义的选择器（一键学习功能）
            if (Array.isArray(pluginSettings.customFilterSelectors) && pluginSettings.customFilterSelectors.length > 0) {
                for (const selector of pluginSettings.customFilterSelectors) {
                    if (selector && typeof selector === 'string') {
                        thinkingSelectors.push(selector);
                    }
                }
            }
            
            let removedContainers = 0;
            for (const selector of thinkingSelectors) {
                try {
                    const elements = tempDiv.querySelectorAll(selector);
                    elements.forEach(el => {
                        el.remove();
                        removedContainers++;
                    });
                } catch (e) {
                    // 选择器可能无效，跳过
                }
            }
            
            if (removedContainers > 0) {
                console.log(`[Recall] 移除了 ${removedContainers} 个思考容器`);
                // 使用 DOM 解析后的纯文本，移除了思考容器
                cleaned = tempDiv.textContent || tempDiv.innerText || '';
            }
        } catch (e) {
            console.warn('[Recall] DOM解析失败，使用正则清理:', e);
        }
        
        // 检测是否包含完整 HTML 文档结构
        const hasHtmlDocument = /<!DOCTYPE\s+html/i.test(cleaned) || /<html[\s>]/i.test(cleaned);
        
        if (hasHtmlDocument) {
            console.log('[Recall] 检测到 HTML 文档结构，进行清理...');
            
            // 尝试提取 <body> 内的实际内容
            // 某些预设会输出完整 HTML 文档，我们只要 body 内的内容
            const bodyMatch = cleaned.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
            if (bodyMatch) {
                cleaned = bodyMatch[1];
            }
        }
        
        // 移除 <head> 标签及其内容（必须在处理其他标签之前）
        cleaned = cleaned.replace(/<head[^>]*>[\s\S]*?<\/head>/gi, '');
        
        // 移除 <style> 标签及其内容（纯文本形式）
        cleaned = cleaned.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
        
        // 移除 <script> 标签及其内容（纯文本形式）
        cleaned = cleaned.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
        
        // 移除 HTML 注释
        cleaned = cleaned.replace(/<!--[\s\S]*?-->/g, '');
        
        // 移除 <!DOCTYPE>, <html>, </html>, <body>, </body> 等标签
        cleaned = cleaned.replace(/<!DOCTYPE[^>]*>/gi, '');
        cleaned = cleaned.replace(/<\/?html[^>]*>/gi, '');
        cleaned = cleaned.replace(/<\/?body[^>]*>/gi, '');
        
        // 移除 SVG 内容（通常是装饰性的）
        cleaned = cleaned.replace(/<svg[^>]*>[\s\S]*?<\/svg>/gi, '');
        
        // 移除 <defs> 标签（SVG 定义）
        cleaned = cleaned.replace(/<defs[^>]*>[\s\S]*?<\/defs>/gi, '');
        
        // 移除 <filter> 标签（SVG 滤镜）
        cleaned = cleaned.replace(/<filter[^>]*>[\s\S]*?<\/filter>/gi, '');
        
        // 移除 <mask> 标签（SVG 遮罩）
        cleaned = cleaned.replace(/<mask[^>]*>[\s\S]*?<\/mask>/gi, '');
        
        // 移除内联 CSS 代码块（独立的 CSS 规则）
        // 匹配类似 .class-name { ... } 或 #id { ... } 的 CSS 规则
        cleaned = cleaned.replace(/^\s*[\.\#\*]?[\w\-\:\[\]=\"\']+\s*\{[^}]*\}\s*$/gm, '');
        
        // 移除 CSS 媒体查询块
        cleaned = cleaned.replace(/@media[^{]*\{[\s\S]*?\}\s*\}/gi, '');
        
        // 移除 CSS @keyframes 动画
        cleaned = cleaned.replace(/@keyframes[^{]*\{[\s\S]*?\}\s*\}/gi, '');
        
        // 移除 CSS 变量定义
        cleaned = cleaned.replace(/:root\s*\{[^}]*\}/gi, '');
        
        // 移除类似 CSS 属性的行（如 "width: 100%; height: 100%;"）
        // 只移除看起来明显是 CSS 的连续多行
        cleaned = cleaned.replace(/^\s*([\w\-]+\s*:\s*[^;]+;\s*)+$/gm, '');
        
        // 移除空的 div/span 容器标签（保留内容）
        cleaned = cleaned.replace(/<div[^>]*>\s*<\/div>/gi, '');
        cleaned = cleaned.replace(/<span[^>]*>\s*<\/span>/gi, '');
        
        // 【关键】移除所有剩余的 HTML 标签（但保留标签内的文本）
        // 这是最后一道防线，确保没有 HTML 标签残留
        
        // 先处理自闭合标签
        cleaned = cleaned.replace(/<br\s*\/?>/gi, '\n');
        cleaned = cleaned.replace(/<hr\s*\/?>/gi, '\n---\n');
        cleaned = cleaned.replace(/<img[^>]*?>/gi, '');
        cleaned = cleaned.replace(/<input[^>]*?>/gi, '');
        cleaned = cleaned.replace(/<meta[^>]*?>/gi, '');
        cleaned = cleaned.replace(/<link[^>]*?>/gi, '');
        
        // 【关键修复】移除所有 HTML 标签 - 使用更精确的正则
        // 匹配所有开始标签: <tagname ...> 或 <tagname>
        // 使用非贪婪匹配和更宽松的标签名匹配
        let previousCleaned;
        let iterations = 0;
        do {
            previousCleaned = cleaned;
            // 移除开始标签（带属性）
            cleaned = cleaned.replace(/<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>/g, '');
            // 移除结束标签
            cleaned = cleaned.replace(/<\/([a-zA-Z][a-zA-Z0-9]*)>/g, '\n');
            iterations++;
        } while (cleaned !== previousCleaned && iterations < 5);  // 循环直到没有更多标签
        
        // 【新增】移除常见的 UI 文字残留（通用）
        // 这些通常是折叠面板的按钮文字
        cleaned = cleaned.replace(/^\s*(收起|展开|展开全文|查看更多|显示更多|隐藏|折叠|Expand|Collapse|Show more|Hide|Read more)\s*$/gmi, '');
        
        // 移除孤立的通用语义关键词（只移除独立成行的）
        // 注意：不包含任何预设特定的名称
        cleaned = cleaned.replace(/^\s*(Think|Thinking|Thought|Reasoning|Reflection|思考|推理|思考过程)\s*$/gmi, '');
        
        // 清理 HTML 实体
        cleaned = cleaned.replace(/&nbsp;/gi, ' ');
        cleaned = cleaned.replace(/&lt;/gi, '<');
        cleaned = cleaned.replace(/&gt;/gi, '>');
        cleaned = cleaned.replace(/&amp;/gi, '&');
        cleaned = cleaned.replace(/&quot;/gi, '"');
        cleaned = cleaned.replace(/&#(\d+);/gi, (match, dec) => String.fromCharCode(dec));
        
        // 清理多余的空行和空白
        cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
        cleaned = cleaned.replace(/^\s+$/gm, ''); // 移除只有空白的行
        cleaned = cleaned.trim();
        
        // 如果清理后内容显著减少，记录日志
        if (originalLength > 0 && cleaned.length < originalLength * 0.5) {
            console.log(`[Recall] HTML清理: ${originalLength}字 → ${cleaned.length}字 (移除了${Math.round((1 - cleaned.length/originalLength) * 100)}%)`);
        }
        
        return cleaned;
    }

    /**
     * 从DOM元素中提取用户真正能看到的文本
     * 【通用方案】基于实际渲染状态判断，不依赖任何特定的CSS类名
     * @param {Element} element - 消息的.mes_text元素
     * @returns {string} 用户实际看到的纯文本
     */
    function extractVisibleTextFromDOM(element) {
        if (!element) return null;
        
        /**
         * 检查元素是否真正可见（基于计算样式）
         * 注意：不处理 details 元素的特殊逻辑，那在 extractText 中单独处理
         */
        function isBasicVisible(el) {
            if (!el || el.nodeType !== Node.ELEMENT_NODE) return true;
            
            try {
                const style = window.getComputedStyle(el);
                
                // 检查各种隐藏方式
                if (style.display === 'none') return false;
                if (style.visibility === 'hidden') return false;
                if (style.opacity === '0') return false;
                
                // 检查尺寸为0的情况（常见的隐藏技巧）
                if (parseFloat(style.height) === 0 && style.overflow === 'hidden') return false;
                if (parseFloat(style.width) === 0 && style.overflow === 'hidden') return false;
                
                return true;
            } catch (e) {
                // getComputedStyle 可能在某些情况下失败
                return true;
            }
        }
        
        /**
         * 递归提取可见文本
         * 递归保证：只有当父元素可见时，子元素才会被处理
         */
        function extractText(node) {
            // 文本节点：直接返回内容（父元素可见性已在上层检查）
            if (node.nodeType === Node.TEXT_NODE) {
                return node.textContent || '';
            }
            
            // 非元素节点：跳过
            if (node.nodeType !== Node.ELEMENT_NODE) {
                return '';
            }
            
            // 基本可见性检查
            if (!isBasicVisible(node)) {
                return '';
            }
            
            // 跳过不应提取的元素
            // 【重要】包含 PRE 和 CODE 标签，避免提取代码/思考内容
            const skipTags = ['IFRAME', 'SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'PRE', 'CODE', 'SVG', 'CANVAS'];
            if (skipTags.includes(node.tagName)) {
                return '';
            }
            
            // 跳过 aria-hidden="true" 的元素（无障碍隐藏）
            if (node.getAttribute('aria-hidden') === 'true') {
                return '';
            }
            
            // 【关键】首先检查用户自定义的过滤选择器
            // 这是最高优先级，用户通过"点击学习"添加的选择器
            if (Array.isArray(pluginSettings.customFilterSelectors) && pluginSettings.customFilterSelectors.length > 0) {
                for (const selector of pluginSettings.customFilterSelectors) {
                    try {
                        if (selector && typeof selector === 'string' && node.matches(selector)) {
                            return '';  // 跳过匹配的元素
                        }
                    } catch (e) {
                        // 选择器可能无效，跳过
                    }
                }
            }
            
            // 【关键】通用检测：跳过"思考/推理容器"
            // 检查元素的类名或ID是否包含思考相关的关键词
            // 注意：SVG 元素的 className 是 SVGAnimatedString，需要特殊处理
            let classNameStr = '';
            if (node.className) {
                if (typeof node.className === 'string') {
                    classNameStr = node.className;
                } else if (node.className.baseVal) {
                    classNameStr = node.className.baseVal;  // SVG 元素
                }
            }
            const className = classNameStr.toLowerCase();
            const idName = (node.id || '').toLowerCase();
            const combinedNames = className + ' ' + idName;
            
            // 思考容器的关键词（与 extractSemanticContent 保持一致）
            // 平衡策略：保留常见的思考容器关键词，但移除过于宽泛的（如 reason）
            const thinkingKeywords = [
                'think', 'thought', 'reasoning', 'reflection',  // 思考相关
                'cot', 'chain-of-thought',                       // CoT 相关
                'inner', 'internal',                             // 内部思考
                'hidden', 'collapsed', 'folded',                 // 隐藏/折叠状态
                'monologue'                                      // 独白
            ];
            
            // 【统一】使用与 extractSemanticContent 相同的直接包含检查
            // 如果类名或ID中包含任何思考关键词，则跳过
            const isThinkingContainer = thinkingKeywords.some(keyword => 
                combinedNames.includes(keyword)
            );
            
            if (isThinkingContainer) {
                // 跳过思考内容容器
                return '';
            }
            
            // 特殊处理：未展开的 <details> 元素
            // 只提取 <summary> 内容，跳过其他子元素
            if (node.tagName === 'DETAILS' && !node.hasAttribute('open')) {
                let text = '';
                for (const child of node.children) {
                    if (child.tagName === 'SUMMARY') {
                        text += extractText(child);
                        break;
                    }
                }
                return text + '\n';
            }
            
            // 【修复】检查是否在未展开的 details 中（且不是 summary 或其子元素）
            // 注意：这个检查只对非 details 元素生效（因为 details 在上面已经处理过了）
            if (node.tagName !== 'DETAILS') {
                const parentDetails = node.closest('details:not([open])');
                if (parentDetails) {
                    // 检查是否在 summary 内部
                    const parentSummary = node.closest('summary');
                    // 如果有 parentSummary 且它是这个 parentDetails 的子元素，则允许提取
                    if (!parentSummary || !parentDetails.contains(parentSummary)) {
                        return '';
                    }
                }
            }
            
            // 普通元素：递归处理所有子节点
            let text = '';
            for (const child of node.childNodes) {
                text += extractText(child);
            }
            
            // 在块级元素后添加换行
            try {
                const display = window.getComputedStyle(node).display;
                if (display === 'block' || display === 'flex' || display === 'grid' || 
                    node.tagName === 'BR' || node.tagName === 'P' || node.tagName === 'DIV' ||
                    node.tagName === 'LI' || node.tagName === 'H1' || node.tagName === 'H2' ||
                    node.tagName === 'H3' || node.tagName === 'H4' || node.tagName === 'H5' ||
                    node.tagName === 'H6' || node.tagName === 'BLOCKQUOTE' || node.tagName === 'PRE') {
                    text += '\n';
                }
            } catch (e) {
                // 忽略
            }
            
            return text;
        }
        
        // 提取可见文本
        let text = extractText(element);
        
        // 清理多余空白
        text = text.replace(/\n{3,}/g, '\n\n').trim();
        
        return text;
    }

    /**
     * 【核心】从 .mes_text 中提取语义内容
     * 
     * 【新方法】使用 DOM 克隆 + 移除思考容器的方式
     * 这种方法更简单可靠，不会遗漏任何内容
     * 
     * @param {Element} mesText - .mes_text 元素
     * @returns {string} 提取的语义内容文本
     */
    function extractSemanticContent(mesText) {
        if (!mesText) return '';
        
        // ★★★ 核心策略：正向提取用户可见的文本内容 ★★★
        // 支持的元素：<p>、<ul>、<ol>、<blockquote>、<h1>-<h6>、<details>（展开或 summary）
        // 无论使用什么预设都适用
        try {
            // 【辅助函数】获取清理后的完整文本（用于兜底和比较）
            function getCleanedFullText() {
                const clone = mesText.cloneNode(true);
                
                // 移除所有可能的隐藏/代码/思考容器
                const removeSelectors = [
                    'pre', 'code', 'iframe', 'script', 'style', 'svg', 'canvas',
                    '[class*="hidden"]', '[class*="think"]', '[class*="reasoning"]',
                    '[class*="TH-"]', '[class*="cot"]', '[class*="collapsed"]',
                    '[aria-hidden="true"]', '[hidden]'
                ].join(', ');
                
                const toRemove = clone.querySelectorAll(removeSelectors);
                for (const el of toRemove) {
                    el.remove();
                }
                
                let text = clone.textContent || '';
                text = text.replace(/[ \t]+/g, ' ');
                text = text.replace(/\n[ \t]+/g, '\n');
                text = text.replace(/[ \t]+\n/g, '\n');
                text = text.replace(/\n{3,}/g, '\n\n');
                text = text.trim();
                
                return text;
            }
            
            const textParts = [];
            
            // 1. 获取所有直接子元素中的常见正文标签
            //    使用 :scope > xxx 只选择直接子元素，避免选中嵌套在代码容器内的内容
            const contentSelectors = ':scope > p, :scope > ul, :scope > ol, :scope > blockquote, :scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > h5, :scope > h6';
            const directContent = mesText.querySelectorAll(contentSelectors);
            for (const el of directContent) {
                const text = el.textContent?.trim();
                if (text) {
                    textParts.push(text);
                }
            }
            
            // 2. 处理直接子元素中的 <details>
            //    - 展开的 details：提取全部内容
            //    - 未展开的 details：只提取 summary
            const directDetails = mesText.querySelectorAll(':scope > details');
            for (const details of directDetails) {
                if (details.hasAttribute('open')) {
                    // 展开状态：提取全部内容
                    const text = details.textContent?.trim();
                    if (text) {
                        textParts.push(text);
                    }
                } else {
                    // 未展开状态：只提取 summary
                    const summary = details.querySelector('summary');
                    if (summary) {
                        const text = summary.textContent?.trim();
                        if (text) {
                            textParts.push(text);
                        }
                    }
                }
            }
            
            // 3. 如果直接子元素没有找到内容，尝试更宽泛的选择
            //    但要排除在 pre、code、iframe 等内部的内容
            if (textParts.length === 0) {
                // 克隆并移除不需要的容器
                const clone = mesText.cloneNode(true);
                
                // 移除所有 pre、code、iframe、script、style 等
                const removeSelectors = 'pre, code, iframe, script, style, svg, canvas, [class*="hidden"], [class*="think"], [class*="reasoning"]';
                const toRemove = clone.querySelectorAll(removeSelectors);
                for (const el of toRemove) {
                    el.remove();
                }
                
                // 再次尝试获取内容元素
                const contentElements = clone.querySelectorAll('p, ul, ol, blockquote, h1, h2, h3, h4, h5, h6');
                for (const el of contentElements) {
                    const text = el.textContent?.trim();
                    if (text) {
                        textParts.push(text);
                    }
                }
            }
            
            // 4. 如果还是没有内容，最后尝试获取所有文本（排除隐藏内容）
            if (textParts.length === 0) {
                const fallbackText = getCleanedFullText();
                if (fallbackText) {
                    return fallbackText;
                }
            }
            
            // 5. 合并所有提取的文本
            let result = textParts.join('\n\n');
            result = result.replace(/[ \t]+/g, ' ');
            result = result.replace(/\n[ \t]+/g, '\n');
            result = result.replace(/[ \t]+\n/g, '\n');
            result = result.replace(/\n{3,}/g, '\n\n');
            result = result.trim();
            
            // 6. 【安全检查】如果提取的内容明显少于完整文本，使用兜底方案
            //    这可以防止混合内容（部分有标签、部分没有）导致的内容丢失
            const cleanedFullText = getCleanedFullText();
            // 条件：完整文本比提取内容长 20% 以上，且差距超过 5 字符
            if (result.length > 0 && cleanedFullText.length > result.length * 1.2 && cleanedFullText.length - result.length > 5) {
                // 说明可能有内容被遗漏，使用完整文本
                return cleanedFullText;
            }
            
            return result;
            
        } catch (e) {
            console.warn('[Recall] 语义提取失败:', e);
            return '';
        }
    }

    /**
     * 根据消息索引从DOM获取渲染后的文本
     * @param {number} messageIndex - 消息在chat数组中的索引
     * @returns {string|null} 渲染后的文本，如果获取失败则返回null
     */
    function getRenderedTextByIndex(messageIndex) {
        try {
            // SillyTavern使用mesid属性标识消息
            let mesElement = document.querySelector(`#chat .mes[mesid="${messageIndex}"] .mes_text`);
            if (!mesElement) {
                // 备用：尝试通过索引定位
                const allMessages = document.querySelectorAll('#chat .mes .mes_text');
                if (!allMessages[messageIndex]) {
                    return null;
                }
                mesElement = allMessages[messageIndex];
            }
            
            // 【优先】使用语义内容提取（更智能、更通用）
            const semanticText = extractSemanticContent(mesElement);
            
            if (semanticText && semanticText.trim().length > 0) {
                console.log('[Recall] ✓ 语义内容提取成功');
                return semanticText;
            }
            
            // 【备用】如果语义提取没有结果，回退到完整 DOM 遍历
            console.log('[Recall] ⚠ 语义提取无结果，使用完整DOM遍历');
            return extractVisibleTextFromDOM(mesElement);
            
        } catch (e) {
            console.warn('[Recall] DOM文本提取失败:', e);
            return null;
        }
    }

    /**
     * 过滤掉AI回复中的思考过程（作为fallback）
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
    
    // 加载状态标志（防止重复加载）
    let _loadMemoriesLoading = false;
    let _loadForeshadowingsLoading = false;
    let _loadPersistentContextsLoading = false;
    let _loadEntitiesLoading = false;
    let _loadContradictionsLoading = false;
    let _loadEpisodesLoading = false;
    
    // 数据已加载标志（追踪当前角色的数据是否已加载）
    let _memoriesLoaded = false;
    let _foreshadowingsLoaded = false;
    let _persistentContextsLoaded = false;
    let _entitiesLoaded = false;
    let _contradictionsLoaded = false;
    let _episodesLoaded = false;
    let _temporalStatsLoaded = false;
    
    // 请求ID（用于在角色切换时取消旧请求）
    let _loadMemoriesRequestId = 0;
    let _loadMemoriesController = null;
    let _loadMemoriesForUser = null;

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
                isInitialized,
                // 从全局变量获取加载状态（这些变量在 IIFE 外部定义）
                memories: {
                    loading: _loadMemoriesLoading,
                    loaded: _memoriesLoaded,
                    forUser: _loadMemoriesForUser,
                    requestId: _loadMemoriesRequestId
                },
                persistentContexts: {
                    loading: typeof _loadPersistentContextsLoading !== 'undefined' ? _loadPersistentContextsLoading : 'N/A',
                    forUser: typeof _loadPersistentContextsForUser !== 'undefined' ? _loadPersistentContextsForUser : 'N/A',
                    requestId: typeof _loadPersistentContextsRequestId !== 'undefined' ? _loadPersistentContextsRequestId : 'N/A',
                    taskId: typeof _loadPersistentContextsTaskId !== 'undefined' ? _loadPersistentContextsTaskId : 'N/A'
                },
                foreshadowings: {
                    loading: typeof _loadForeshadowingsLoading !== 'undefined' ? _loadForeshadowingsLoading : 'N/A',
                    forUser: typeof _loadForeshadowingsForUser !== 'undefined' ? _loadForeshadowingsForUser : 'N/A',
                    requestId: typeof _loadForeshadowingsRequestId !== 'undefined' ? _loadForeshadowingsRequestId : 'N/A'
                }
            };
        },
        // 手动触发加载持久条件
        loadContexts: function() {
            console.log('[Recall Debug] 手动触发 loadPersistentContexts');
            if (typeof loadPersistentContexts === 'function') {
                loadPersistentContexts();
            } else {
                console.error('[Recall Debug] loadPersistentContexts 函数不可用');
            }
        },
        // 重置加载状态（用于调试卡住的情况）
        resetLoadingState: function() {
            console.log('[Recall Debug] 重置加载状态');
            if (typeof _loadMemoriesLoading !== 'undefined') {
                _loadMemoriesLoading = false;
                _loadMemoriesController = null;
                _loadMemoriesForUser = null;
            }
            if (typeof _loadPersistentContextsLoading !== 'undefined') {
                _loadPersistentContextsLoading = false;
                _loadPersistentContextsController = null;
                _loadPersistentContextsForUser = null;
                _loadPersistentContextsTaskId = null;
            }
            if (typeof _loadForeshadowingsLoading !== 'undefined') {
                _loadForeshadowingsLoading = false;
                _loadForeshadowingsController = null;
                _loadForeshadowingsForUser = null;
            }
            console.log('[Recall Debug] 状态已重置');
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
            console.log(`[Recall] [TaskTracker] ADD: taskId=${taskId}, type=${type}, title=${title}`);
            this.tasks.set(taskId, {
                type,
                title,
                detail,
                status: 'running',  // 'pending', 'running', 'success', 'error'
                startTime: Date.now()
            });
            this._updateUI();
            // 启动自动刷新
            this.startAutoRefresh();
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
            console.log(`[Recall] [TaskTracker] COMPLETE: taskId=${taskId}, success=${success}, detail=${detail}`);
            const task = this.tasks.get(taskId);
            if (task) {
                task.status = success ? 'success' : 'error';
                if (detail) task.detail = detail;
                task.endTime = Date.now();
                this._updateUI();
                
                // 成功的任务 2 秒后移除，失败的任务 5 秒后移除
                setTimeout(() => {
                    this.tasks.delete(taskId);
                    this._updateUI();
                }, success ? 2000 : 5000);
            }
        },
        
        /**
         * 启动 UI 自动刷新（每秒更新运行时间显示）
         */
        startAutoRefresh() {
            if (this._refreshIntervalId) return;
            this._refreshIntervalId = setInterval(() => {
                if (this.getActiveCount() > 0) {
                    this._updateUI();
                }
            }, 1000);
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
                        // 如果是后端任务，使用专门的后端图标
                        const icon = task._backendType 
                            ? this._getBackendIcon(task._backendType) 
                            : this._getIcon(task.type, task.status);
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
                case 'backend': return '⚙️';  // 后端任务通用图标
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
        },
        
        // ========== 后端任务追踪 ==========
        _backendPollingIntervalId: null,
        _backendTasks: new Map(),  // 后端任务缓存
        _backendPollingInterval: 300,  // 轮询间隔（毫秒）
        
        /**
         * 启动后端任务轮询
         */
        startBackendPolling() {
            if (this._backendPollingIntervalId) return;
            
            console.log('[Recall] [TaskTracker] 启动后端任务轮询');
            this._backendPollingIntervalId = setInterval(() => {
                this._fetchBackendTasks();
            }, this._backendPollingInterval);
            
            // 立即执行一次
            this._fetchBackendTasks();
        },
        
        /**
         * 停止后端任务轮询
         */
        stopBackendPolling() {
            if (this._backendPollingIntervalId) {
                clearInterval(this._backendPollingIntervalId);
                this._backendPollingIntervalId = null;
                console.log('[Recall] [TaskTracker] 停止后端任务轮询');
            }
        },
        
        /**
         * 获取后端任务
         */
        async _fetchBackendTasks() {
            // 检查 API URL 是否已配置
            if (!pluginSettings.apiUrl) {
                return;
            }
            
            try {
                const response = await fetch(`${pluginSettings.apiUrl}/v1/tasks/active`, {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                if (!response.ok) return;
                
                const data = await response.json();
                if (!data.success || !data.tasks) return;
                
                // 更新后端任务缓存
                const newTaskIds = new Set();
                for (const backendTask of data.tasks) {
                    newTaskIds.add(backendTask.id);
                    
                    // 检查是否是新任务或状态变化
                    const existing = this._backendTasks.get(backendTask.id);
                    if (!existing || existing.status !== backendTask.status || existing.progress !== backendTask.progress) {
                        this._backendTasks.set(backendTask.id, backendTask);
                        this._syncBackendTaskToUI(backendTask);
                    }
                }
                
                // 移除已完成的后端任务
                for (const [id, task] of this._backendTasks) {
                    if (!newTaskIds.has(id)) {
                        this._backendTasks.delete(id);
                        // 从前端任务列表中移除对应的任务
                        for (const [frontendId, frontendTask] of this.tasks) {
                            if (frontendTask._backendTaskId === id) {
                                this.complete(frontendId, true, task.message || '完成');
                                break;
                            }
                        }
                    }
                }
                
                // 如果没有活动任务，停止轮询
                if (data.tasks.length === 0 && this.getActiveCount() === 0) {
                    this.stopBackendPolling();
                }
            } catch (e) {
                // 静默失败，不影响 UI
            }
        },
        
        /**
         * 同步后端任务到 UI
         */
        _syncBackendTaskToUI(backendTask) {
            // 查找是否已有对应的前端任务
            let frontendTaskId = null;
            for (const [id, task] of this.tasks) {
                if (task._backendTaskId === backendTask.id) {
                    frontendTaskId = id;
                    break;
                }
            }
            
            // 映射后端任务类型到前端显示类型
            const typeMap = {
                'dedup_check': 'backend',
                'entity_extraction': 'backend',
                'consistency_check': 'backend',
                'contradiction_detection': 'backend',
                'knowledge_graph': 'backend',
                'index_update': 'backend',
                'memory_save': 'backend',
                'foreshadow_analysis': 'backend',
                'context_extraction': 'backend',
                'llm_call': 'backend',
                'embedding': 'backend',
                'search': 'backend',
                'maintenance': 'backend'
            };
            
            // 映射后端状态到前端状态
            const statusMap = {
                'pending': 'pending',
                'running': 'running',
                'completed': 'success',
                'failed': 'error',
                'cancelled': 'error'
            };
            
            if (frontendTaskId) {
                // 更新现有任务
                this.update(frontendTaskId, {
                    detail: backendTask.message || '',
                    status: statusMap[backendTask.status] || 'running',
                    progress: backendTask.progress
                });
            } else if (backendTask.status === 'running' || backendTask.status === 'pending') {
                // 创建新的前端任务显示
                const taskId = ++this.taskIdCounter;
                this.tasks.set(taskId, {
                    type: typeMap[backendTask.type] || 'backend',
                    title: `[后端] ${backendTask.name}`,
                    detail: backendTask.message || '',
                    status: statusMap[backendTask.status] || 'running',
                    startTime: backendTask.started_at ? backendTask.started_at * 1000 : Date.now(),
                    progress: backendTask.progress,
                    _backendTaskId: backendTask.id,  // 标记为后端任务
                    _backendType: backendTask.type   // 保存后端任务类型用于图标显示
                });
                this._updateUI();
            }
        },
        
        /**
         * 获取后端任务图标
         */
        _getBackendIcon(backendType) {
            const iconMap = {
                'dedup_check': '🔍',
                'entity_extraction': '🏷️',
                'consistency_check': '⚖️',
                'contradiction_detection': '⚡',
                'knowledge_graph': '🕸️',
                'index_update': '📊',
                'memory_save': '💾',
                'foreshadow_analysis': '🔮',
                'context_extraction': '📋',
                'llm_call': '🤖',
                'embedding': '🧮',
                'search': '🔎',
                'maintenance': '🔧'
            };
            return iconMap[backendType] || '⚙️';
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

    // ============== 核心：标签点击处理函数 ==============
    // 防抖标志，防止 pointerdown 和其他事件重复触发
    let _lastTabClickTime = 0;
    let _lastTabClickName = '';
    const TAB_CLICK_DEBOUNCE = 300; // 300ms 内的同一标签重复点击会被忽略
    
    function handleRecallTabClick(tabName) {
        // 防抖处理 - 同一标签在短时间内只处理一次
        const now = Date.now();
        if (now - _lastTabClickTime < TAB_CLICK_DEBOUNCE && _lastTabClickName === tabName) {
            console.log(`[Recall] 标签点击被防抖过滤: ${tabName} (${now - _lastTabClickTime}ms)`);
            return;
        }
        _lastTabClickTime = now;
        _lastTabClickName = tabName;
        
        console.log(`[Recall] 标签点击: ${tabName}`);
        
        // 切换标签按钮状态（所有实例，包括弹窗中的）
        document.querySelectorAll('.recall-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll(`.recall-tab[data-tab="${tabName}"]`).forEach(t => t.classList.add('active'));
        
        // 切换内容面板（所有实例）
        document.querySelectorAll('.recall-tab-content').forEach(c => c.classList.remove('active'));
        document.querySelectorAll(`#recall-tab-${tabName}, [id="recall-tab-${tabName}"]`).forEach(c => c.classList.add('active'));
        
        // 根据标签页加载对应数据
        if (!isConnected) {
            console.log('[Recall] 未连接，跳过数据加载');
            return;
        }
        
        // 【优化】所有标签都只在数据未加载时才自动加载，避免重复请求
        switch(tabName) {
            case 'contexts': {
                if (!_persistentContextsLoaded && !_loadPersistentContextsLoading) {
                    loadPersistentContexts();
                }
                break;
            }
            case 'foreshadowing': {
                if (!_foreshadowingsLoaded && !_loadForeshadowingsLoading) {
                    loadForeshadowings();
                }
                break;
            }
            case 'memories': {
                if (!_memoriesLoaded && !_loadMemoriesLoading) {
                    loadMemories();
                }
                break;
            }
            case 'entities': {
                if (!_entitiesLoaded && !_loadEntitiesLoading) {
                    loadEntities();
                }
                break;
            }
            case 'contradictions': {
                if (!_contradictionsLoaded && !_loadContradictionsLoading) {
                    loadContradictions();
                }
                break;
            }
            case 'temporal': {
                if (!_temporalStatsLoaded) {
                    loadTemporalStats();
                }
                break;
            }
            case 'episodes': {
                if (!_episodesLoaded && !_loadEpisodesLoading) {
                    loadEpisodes();
                }
                break;
            }
            case 'core-settings':
                // 设置页面每次都需要加载最新配置
                loadCoreSettings();
                break;
        }
    }
    
    // 将实现注入到全局函数
    window._recallTabClickImpl = handleRecallTabClick;
    // 同时直接更新全局函数（双保险）
    window.recallTabClick = handleRecallTabClick;
    console.log('[Recall] handleRecallTabClick 已注入到 window._recallTabClickImpl 和 window.recallTabClick');
    
    // ============== 最终方案：window 级别 pointerdown 监听 ==============
    // click 事件可能被其他脚本拦截，使用 pointerdown 更可靠
    // 注意：只使用 pointerdown，不再使用 mousedown，避免重复触发
    
    let _lastTabClickEventTime = 0;  // 防止同一次点击的多个事件触发
    
    window.addEventListener('pointerdown', function(e) {
        const tab = e.target.closest('.recall-tab');
        if (tab) {
            // 防止同一次点击被多个事件重复处理
            const now = Date.now();
            if (now - _lastTabClickEventTime < 100) {
                console.log('[Recall] 标签点击事件被去重过滤');
                return;
            }
            _lastTabClickEventTime = now;
            
            console.log('🎯 [Recall] Window pointerdown 捕获到标签:', tab.dataset?.tab);
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            const tabName = tab.dataset?.tab || tab.getAttribute('data-tab');
            if (tabName) {
                handleRecallTabClick(tabName);
            }
        }
    }, true);  // 捕获阶段
    
    console.log('[Recall] Window 级别 pointerdown 监听已设置（已移除重复的 mousedown）');
    
    // 添加全局点击诊断（仅记录前 10 次）
    let clickLogCount = 0;
    window.addEventListener('pointerdown', function(e) {
        if (clickLogCount < 10) {
            clickLogCount++;
            console.log(`🔍 [全局点击 #${clickLogCount}]`, e.target.tagName, e.target.className?.substring?.(0, 30) || '', 'closest .recall-tab:', !!e.target.closest('.recall-tab'));
        }
    }, true);
    
    // ============== 暴露调试函数 ==============
    window.recallDebug = {
        listTabs: () => {
            const tabs = document.querySelectorAll('.recall-tab');
            console.log(`找到 ${tabs.length} 个 .recall-tab 元素:`);
            tabs.forEach((t, i) => {
                const rect = t.getBoundingClientRect();
                const inDialog = !!t.closest('dialog');
                const style = window.getComputedStyle(t);
                console.log(`  ${i}: data-tab="${t.dataset?.tab}", 在dialog=${inDialog}, 可见=${rect.width > 0}, pointer-events=${style.pointerEvents}, z-index=${style.zIndex}`);
            });
            return tabs;
        },
        clickTab: (name) => {
            console.log(`手动调用 handleRecallTabClick('${name}')`);
            handleRecallTabClick(name);
        },
        checkPointerEvents: () => {
            // 检查从 body 到 recall-tab 的整个路径上的 pointer-events
            const tab = document.querySelector('.recall-tab[data-tab="contexts"]');
            if (!tab) {
                console.log('未找到 contexts 标签');
                return;
            }
            let el = tab;
            console.log('检查 pointer-events 继承链:');
            while (el && el !== document.body) {
                const style = window.getComputedStyle(el);
                console.log(`  ${el.tagName}.${el.className?.substring?.(0, 20) || ''}: pointer-events=${style.pointerEvents}, display=${style.display}, visibility=${style.visibility}`);
                el = el.parentElement;
            }
        },
        simulateClick: () => {
            const tab = document.querySelector('.recall-tab[data-tab="contexts"]');
            if (tab) {
                console.log('模拟 pointerdown 事件...');
                const event = new PointerEvent('pointerdown', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                tab.dispatchEvent(event);
            }
        }
    };
    console.log('[Recall] 调试: recallDebug.listTabs(), recallDebug.clickTab("contexts"), recallDebug.checkPointerEvents(), recallDebug.simulateClick()');

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
            
            // v4.2: 调试日志 - 检查 Turn API 设置
            console.log('[Recall] 加载设置:', {
                useTurnApi: pluginSettings.useTurnApi,
                savedHadUseTurnApi: 'useTurnApi' in parsed,
                savedValue: parsed.useTurnApi,
                defaultValue: defaultSettings.useTurnApi
            });
            
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
                <!-- 注：移除了 onclick 处理器，统一由 window 级别 pointerdown 监听器处理，避免重复触发 -->
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
                            <option value="ORG">🏢 组织</option>
                            <option value="ITEM">📦 物品</option>
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
                                <span>智能内容提取</span>
                            </label>
                            <div class="recall-setting-hint">
                                ✨ 自动提取正文内容（p、列表、标题等语义标签）<br>
                                ✨ 自动跳过思考区域（details折叠面板、think类容器等）<br>
                                无需手动配置，适用于所有预设
                            </div>
                        </div>
                        
                        <!-- 选择器学习功能 -->
                        <div class="recall-setting-group" id="recall-selector-learning-group">
                            <label class="recall-setting-title">🎯 额外排除区域（可选）</label>
                            <div class="recall-setting-hint">如果智能提取仍包含不需要的内容，可点击学习额外排除</div>
                            <div class="recall-selector-buttons">
                                <button type="button" id="recall-learn-selector-btn" class="menu_button">
                                    🎯 点击学习
                                </button>
                                <button type="button" id="recall-clear-selectors-btn" class="menu_button">
                                    🗑️ 清空
                                </button>
                            </div>
                            <div id="recall-learned-selectors" class="recall-learned-selectors">
                                <!-- 内容由 updateLearnedSelectorsUI() 动态生成 -->
                            </div>
                            <div id="recall-learning-status" class="recall-learning-status" style="display:none;"></div>
                        </div>
                        
                        <div class="recall-setting-group">
                            <label class="recall-setting-label">
                                <input type="checkbox" id="recall-use-turn-api" ${pluginSettings.useTurnApi ? 'checked' : ''}>
                                <span>🚀 Turn API 性能优化 (v4.2)</span>
                            </label>
                            <div class="recall-setting-hint">将用户消息和AI回复合并成一次请求保存，减少 30-50% 处理时间</div>
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
                            <label class="recall-setting-title">实体显示上限</label>
                            <input type="number" id="recall-max-display-entities" value="${pluginSettings.maxDisplayEntities || 100}" 
                                   min="10" max="1000" step="10" class="text_pole">
                            <div class="recall-setting-hint">实体列表最多显示多少个，设置过高可能影响页面性能</div>
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
    
    // 使用捕获阶段的事件委托（某些父元素会阻止冒泡，所以必须用捕获阶段）
    if (!window._recallTabClickBound) {
        window._recallTabClickBound = true;
        document.addEventListener('click', function(e) {
            const tab = e.target.closest('.recall-tab');
            if (tab) {
                e.preventDefault();
                e.stopPropagation();
                const tabName = tab.dataset?.tab || tab.getAttribute('data-tab');
                if (tabName && window.recallTabClick) {
                    window.recallTabClick(tabName);
                }
            }
        }, true);  // 捕获阶段！
    }
    console.log('[Recall] UI 已创建');
    
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
    
    // 选择器学习按钮事件
    document.getElementById('recall-learn-selector-btn')?.addEventListener('click', () => {
        startSelectorLearning();
    });
    document.getElementById('recall-clear-selectors-btn')?.addEventListener('click', () => {
        if (confirm('确定要清空所有学习的选择器吗？')) {
            clearLearnedSelectors();
        }
    });
    // 【重要】初始化时加载已保存的选择器列表
    updateLearnedSelectorsUI();
    
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
        const panel = document.getElementById('recall-entity-detail-panel');
        if (panel) panel.style.display = 'none';
    });
    document.getElementById('recall-generate-entity-summary')?.addEventListener('click', safeExecute(generateEntitySummary, '生成摘要失败'));
    
    // 矛盾检测事件绑定
    document.getElementById('recall-refresh-contradictions-btn')?.addEventListener('click', safeExecute(loadContradictions, '刷新矛盾失败'));
    document.getElementById('recall-contradiction-status-filter')?.addEventListener('change', () => loadContradictions());
    document.getElementById('recall-contradiction-detail-close')?.addEventListener('click', () => {
        const panel = document.getElementById('recall-contradiction-detail-panel');
        if (panel) panel.style.display = 'none';
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
        const panel = document.getElementById('recall-episode-detail-panel');
        if (panel) panel.style.display = 'none';
    });
    
    // 高级搜索事件绑定
    document.getElementById('recall-advanced-search-btn')?.addEventListener('click', safeExecute(performAdvancedSearch, '搜索失败'));
    document.getElementById('recall-advanced-search-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performAdvancedSearch();
    });
    document.getElementById('recall-hybrid-weight')?.addEventListener('input', (e) => {
        const valueEl = document.getElementById('recall-hybrid-weight-value');
        if (valueEl) valueEl.textContent = e.target.value;
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
    const taskId = taskTracker.add('config', '保存容量限制配置');
    
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
            console.log('[Recall] 容量限制配置保存成功');
            
            // 热更新配置
            await fetch(`${pluginSettings.apiUrl}/v1/config/reload`, { method: 'POST' });
            taskTracker.complete(taskId, true);
        } else {
            const errMsg = result.message || '未知错误';
            safeToastr.error('保存失败: ' + errMsg, 'Recall');
            taskTracker.complete(taskId, false, errMsg);
        }
    } catch (e) {
        console.warn('[Recall] 保存容量限制配置失败:', e.message);
        safeToastr.error('保存容量限制配置失败: ' + e.message, 'Recall');
        taskTracker.complete(taskId, false, e.message);
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

// 加载状态标志，防止重复加载
let _loadCoreSettingsLoading = false;

/**
 * 加载绝对规则
 * 注：角色卡/世界观/写作风格请使用 SillyTavern 自带功能
 */
async function loadCoreSettings() {
    // 防止重复加载
    if (_loadCoreSettingsLoading) {
        console.log('[Recall] loadCoreSettings 正在加载中，跳过重复调用');
        return;
    }
    _loadCoreSettingsLoading = true;
    
    const taskId = taskTracker.add('load', '加载绝对规则');
    
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
            
            taskTracker.complete(taskId, true);
            console.log('[Recall] 绝对规则已加载, 检测模式:', data.rule_detection_mode || 'unknown');
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 加载绝对规则失败:', response.status);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 加载绝对规则失败:', e);
    } finally {
        _loadCoreSettingsLoading = false;
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
    
    const taskId = taskTracker.add('config', '保存绝对规则');
    
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
            
            taskTracker.complete(taskId, true);
        } else {
            const error = await response.json().catch(() => ({}));
            const errMsg = error.detail || '未知错误';
            alert(`❌ 保存绝对规则失败: ${errMsg}`);
            taskTracker.complete(taskId, false, errMsg);
        }
    } catch (e) {
        alert(`❌ 保存绝对规则失败: ${e.message}`);
        taskTracker.complete(taskId, false, e.message);
    }
}

// ==================== 伏笔分析触发 ====================

/**
 * 手动触发伏笔分析
 */
async function triggerForeshadowingAnalysis() {
    const userId = encodeURIComponent(currentCharacterId || 'default');
    const characterId = encodeURIComponent(currentCharacterId || 'default');
    
    const taskId = taskTracker.add('analyze', '触发伏笔分析');
    
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
                taskTracker.complete(taskId, true);
            } else {
                message += '分析器未触发（可能 LLM 未配置或无足够对话内容）';
                if (result.error) {
                    message += `\n错误: ${result.error}`;
                }
                taskTracker.complete(taskId, false, '分析器未触发');
            }
            
            alert(message);
            
            // 刷新伏笔列表
            loadForeshadowings();
        } else {
            const error = await response.json().catch(() => ({}));
            taskTracker.complete(taskId, false, error.detail || '未知错误');
            alert(`❌ 触发伏笔分析失败: ${error.detail || '未知错误'}`);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        alert(`❌ 触发伏笔分析失败: ${e.message}`);
    }
}

// ==================== 系统管理功能 ====================

/**
 * 热更新服务端配置
 */
async function reloadServerConfig() {
    const taskId = taskTracker.add('config', '热更新配置');
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/config/reload`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            taskTracker.complete(taskId, true);
            alert(`✅ 配置已热更新\n\n${result.message || '配置重新加载成功'}`);
            
            // 重新加载前端配置
            loadApiConfig();
        } else {
            const error = await response.json().catch(() => ({}));
            taskTracker.complete(taskId, false, error.detail || '未知错误');
            alert(`❌ 热更新失败: ${error.detail || '未知错误'}`);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('process', '整合记忆');
    
    try {
        const response = await fetch(`${pluginSettings.apiUrl}/v1/consolidate?user_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            taskTracker.complete(taskId, true);
            safeToastr.success(result.message || '记忆整合完成', 'Recall');
            
            // 刷新记忆列表
            loadMemories();
        } else {
            const error = await response.json().catch(() => ({}));
            taskTracker.complete(taskId, false, error.detail || '未知错误');
            safeToastr.error(`整合失败: ${error.detail || '未知错误'}`, 'Recall');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
        
        const taskId = taskTracker.add('load', '加载系统统计');
        
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
                taskTracker.complete(taskId, true);
            } else {
                statsContent.innerHTML = '<div style="color:#ff6b6b;">❌ 获取统计信息失败</div>';
                taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            }
        } catch (e) {
            statsContent.innerHTML = `<div style="color:#ff6b6b;">❌ ${e.message}</div>`;
            taskTracker.complete(taskId, false, e.message);
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
    
    // 诊断：打印所有相关事件类型
    console.log('[Recall] event_types:', {
        CHAT_CHANGED: event_types?.CHAT_CHANGED,
        CHAT_CREATED: event_types?.CHAT_CREATED,
        CHARACTER_MESSAGE_RENDERED: event_types?.CHARACTER_MESSAGE_RENDERED,
    });
    
    // 诊断：检查 eventSource 是否是 EventEmitter
    console.log('[Recall] eventSource:', eventSource);
    console.log('[Recall] eventSource.on 类型:', typeof eventSource?.on);
    
    if (eventSource && event_types) {
        // 使用安全包装的事件处理器
        eventSource.on(event_types.MESSAGE_SENT, safeExecute(onMessageSent, '处理发送消息失败'));
        eventSource.on(event_types.MESSAGE_RECEIVED, safeExecute(onMessageReceived, '处理接收消息失败'));
        eventSource.on(event_types.CHAT_CHANGED, safeExecute(onChatChanged, '处理聊天切换失败'));
        eventSource.on(event_types.GENERATION_AFTER_COMMANDS, safeExecute(onBeforeGeneration, '准备记忆上下文失败'));
        
        // 监听更多事件以捕获角色切换
        if (event_types.CHAT_CREATED) {
            eventSource.on(event_types.CHAT_CREATED, () => {
                console.log('[Recall] ▶▶▶ CHAT_CREATED 事件触发');
                safeExecute(onChatChanged, '处理新聊天创建失败')();
            });
        }
        
        // 诊断：直接监听多个事件
        eventSource.on('chat_id_changed', (...args) => {
            console.log('[Recall] ▶▶▶ chat_id_changed 事件触发，参数:', args);
        });
        eventSource.on('chat_created', () => {
            console.log('[Recall] ▶▶▶ chat_created 事件触发');
        });
        eventSource.on('character_message_rendered', (mesId) => {
            console.log('[Recall] ▶▶▶ character_message_rendered 事件触发，mesId:', mesId);
            // 【新增】消息渲染完成后，处理待保存的消息
            processPendingMessage(mesId);
        });
        
        console.log('[Recall] 事件监听器已注册');
        
        // 初始化时立即检测当前角色并加载记忆
        setTimeout(() => {
            initializeCurrentCharacter();
        }, 500);
        
        // 备用方案：轮询检测角色变化（每2秒检查一次）
        // 因为事件系统似乎不总是工作
        startCharacterPolling();
    } else {
        console.warn('[Recall] SillyTavern 事件系统不可用，启用轮询模式');
        // 即使事件系统不可用，也启动轮询
        startCharacterPolling();
    }
}

// 用于轮询检测的上一个角色ID
let _lastPolledCharacterId = null;

/**
 * 启动角色变化轮询检测
 */
function startCharacterPolling() {
    console.log('[Recall] 启动角色变化轮询检测');
    
    setInterval(() => {
        try {
            // 尝试多种方式获取当前角色
            const context = SillyTavern.getContext();
            
            // 方式1: 从 context
            const contextCharId = context.characterId;
            const contextChar = contextCharId !== undefined ? context.characters?.[contextCharId] : null;
            
            // 方式2: 从 SillyTavern 全局导出
            const this_chid = context.this_chid;
            const characters = context.characters ?? [];
            const name2 = context.name2;
            const selected_group = context.selected_group ?? context.groupId;
            
            // 方式3: 从 window 全局变量（SillyTavern 内部变量）
            const windowThisChid = window.this_chid;
            const windowCharacters = window.characters;
            const windowName2 = window.name2;
            const windowSelectedGroup = window.selected_group;
            
            // 方式4: 从 chat 数组获取角色名
            const chat = context.chat || [];
            const lastCharMsg = [...chat].reverse().find(m => !m.is_user && !m.is_system);
            const chatCharName = lastCharMsg?.name;
            
            // 方式5: 从多个 DOM 选择器获取（SillyTavern 特定选择器）
            const domSelectors = [
                // 聊天消息中的角色名
                '#chat .mes:not(.is_user) .name_text',
                '#chat .mes[is_system="false"] .name_text',
                // 角色信息面板
                '#character_popup .ch_name',
                '#selected_chat_pole .ch_name',
                '.selected_chat_block .ch_name',
                // 右侧面板角色名
                '#rm_button_selected_ch h2',
                '#rm_button_selected_ch .ch_name',
                // 角色卡选中状态
                '.character_select.selected .ch_name',
                '.character_select.is_fav .ch_name',
                // 顶部角色名显示
                '#character_name_block',
                '.mes_block .name_text',
            ];
            let charNameFromDOM = '';
            for (const sel of domSelectors) {
                try {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.textContent?.trim() || el.title?.trim() || '';
                        // 过滤无效值：空、默认值、模板占位符
                        if (text && 
                            text !== 'SillyTavern System' && 
                            text !== 'Assistant' &&
                            text !== 'User' &&
                            !text.includes('${') &&  // 过滤模板占位符
                            !text.includes('{{') &&  // 过滤 Handlebars 占位符
                            text.length > 0 &&
                            text.length < 100) {  // 角色名不应该太长
                            charNameFromDOM = text;
                            break;
                        }
                    }
                } catch (e) { /* 选择器可能无效 */ }
            }
            
            // 方式6: 检查是否在聊天界面（通过 DOM 状态）
            const chatContainer = document.querySelector('#chat');
            const hasChatMessages = chatContainer && chatContainer.querySelectorAll('.mes').length > 0;
            const inChatView = hasChatMessages || document.querySelector('#sheld')?.classList.contains('openDrawer');
            
            // 方式7: 从 SillyTavern 的 getCharacters() 获取选中的角色
            let selectedCharFromList = '';
            try {
                const selectedEl = document.querySelector('.character_select.selected');
                if (selectedEl) {
                    const nameEl = selectedEl.querySelector('.ch_name');
                    if (nameEl) {
                        selectedCharFromList = nameEl.textContent?.trim() || '';
                    }
                }
            } catch (e) { /* 忽略 */ }
            
            let detectedCharId = null;
            
            // 辅助函数：检查是否为有效角色名
            const isValidCharName = (name) => {
                return name && 
                       name !== 'SillyTavern System' && 
                       name !== 'Assistant' &&
                       name !== 'User' &&
                       !name.includes('${') &&
                       !name.includes('{{') &&
                       name.length > 0 &&
                       name.length < 100;
            };
            
            // 优先使用 window 全局变量
            if (windowThisChid !== undefined && windowCharacters?.[windowThisChid]) {
                const name = windowCharacters[windowThisChid].name;
                if (isValidCharName(name)) {
                    detectedCharId = name;
                }
            }
            // 其次使用 context.this_chid
            if (!detectedCharId && this_chid !== undefined && characters[this_chid]) {
                const name = characters[this_chid].name;
                if (isValidCharName(name)) {
                    detectedCharId = name;
                }
            }
            // 使用 name2（但排除默认值）
            if (!detectedCharId && isValidCharName(name2)) {
                detectedCharId = name2;
            }
            // 使用 window.name2
            if (!detectedCharId && isValidCharName(windowName2)) {
                detectedCharId = windowName2;
            }
            // 使用 context.characterId
            if (!detectedCharId && contextChar) {
                const name = contextChar.name;
                if (isValidCharName(name)) {
                    detectedCharId = name;
                }
            }
            // 使用群组ID
            if (!detectedCharId && (selected_group || windowSelectedGroup)) {
                detectedCharId = `group_${selected_group || windowSelectedGroup}`;
            }
            // 从聊天记录获取
            if (!detectedCharId && isValidCharName(chatCharName)) {
                detectedCharId = chatCharName;
            }
            // 从选中的角色卡获取
            if (!detectedCharId && isValidCharName(selectedCharFromList)) {
                detectedCharId = selectedCharFromList;
            }
            // 从 DOM 获取
            if (!detectedCharId && isValidCharName(charNameFromDOM)) {
                detectedCharId = charNameFromDOM;
            }
            // 默认
            if (!detectedCharId) {
                detectedCharId = 'default';
            }
            
            // 每次轮询都打印当前状态（用于诊断）
            console.log(`[Recall] [轮询] win.this_chid=${windowThisChid}, ctx.this_chid=${this_chid}, name2=${name2}, win.name2=${windowName2}, DOM=${charNameFromDOM}, selectedChar=${selectedCharFromList}, hasMsgs=${hasChatMessages}, detected=${detectedCharId}, last=${_lastPolledCharacterId}`);
            
            // 如果角色变化了
            if (detectedCharId && detectedCharId !== _lastPolledCharacterId) {
                console.log(`[Recall] [轮询] 检测到角色变化: ${_lastPolledCharacterId} -> ${detectedCharId}`);
                _lastPolledCharacterId = detectedCharId;
                
                // 触发角色切换处理
                if (currentCharacterId !== detectedCharId) {
                    console.log('[Recall] [轮询] 触发 onChatChanged');
                    onChatChanged();
                }
            }
        } catch (e) {
            console.warn('[Recall] [轮询] 错误:', e.message);
        }
    }, 1000); // 每1秒检查一次
}

/**
 * 初始化当前角色 - 页面加载/刷新时调用
 */
async function initializeCurrentCharacter() {
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
        // 【优化】使用 await 确保关键数据加载完成后再继续
        // 这避免了和保存队列竞争网络连接
        if (isConnected) {
            try {
                // 并行加载三种数据，等待全部完成
                await Promise.all([
                    loadMemories(),
                    loadForeshadowings(),
                    loadPersistentContexts()
                ]);
                console.log('[Recall] 初始化数据加载完成');
            } catch (e) {
                console.warn('[Recall] 初始化数据加载部分失败:', e);
            }
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
    remoteLog.info('正在连接: ' + pluginSettings.apiUrl);
    
    // 检查是否有混合内容问题 (HTTPS 页面请求 HTTP API)
    const isPageHttps = window.location.protocol === 'https:';
    const isApiHttp = pluginSettings.apiUrl.startsWith('http://');
    if (isPageHttps && isApiHttp) {
        remoteLog.warn('⚠️ 混合内容问题：HTTPS页面 + HTTP API，可能被浏览器阻止');
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
            remoteLog.info('API 连接成功');
            
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
            remoteLog.info('当前地址连接失败，尝试智能探测...');
            const newUrl = await smartConnect();
            
            if (newUrl !== pluginSettings.apiUrl) {
                remoteLog.info('切换到新地址: ' + newUrl);
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
    
    // v4.2: 如果用户关闭了 Turn API，清理相关状态
    const newUseTurnApi = document.getElementById('recall-use-turn-api')?.checked ?? true;
    if (!newUseTurnApi && pluginSettings.useTurnApi) {
        // 从开启变为关闭，清理状态
        lastTurnApiMessageId = null;
        pendingUserMessage = null;
        remoteLog.turn('Turn API 已关闭，清理相关状态');
    }
    pluginSettings.useTurnApi = newUseTurnApi;
    
    pluginSettings.autoChunkLongText = document.getElementById('recall-auto-chunk')?.checked ?? true;
    pluginSettings.chunkSize = parseInt(document.getElementById('recall-chunk-size')?.value) || 2000;
    pluginSettings.previewLength = parseInt(document.getElementById('recall-preview-length')?.value) || 200;
    pluginSettings.maxDisplayEntities = parseInt(document.getElementById('recall-max-display-entities')?.value) || 100;
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
    
    const taskId = taskTracker.add('search', '搜索记忆');
    
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
        taskTracker.complete(taskId, true);
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    const taskId = taskTracker.add('add', '添加记忆');
    
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
            taskTracker.complete(taskId, true);
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
            taskTracker.complete(taskId, false, result.message || '未保存');
            console.log('[Recall] 记忆未保存:', result.message);
            if (result.message) {
                safeToastr.info(result.message, 'Recall', { timeOut: 3000 });
            }
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    const taskId = taskTracker.add('add', '埋下伏笔');
    
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
            taskTracker.complete(taskId, true);
            loadForeshadowings();
            console.log(`[Recall] 伏笔已埋下 (角色: ${currentCharacterId})`);
        } else {
            taskTracker.complete(taskId, false, '未返回 ID');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    // 启动后端任务轮询（观察后端处理进度）
    taskTracker.startBackendPolling();
    
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
        
        // 启动后端任务轮询（观察后端处理进度）
        taskTracker.startBackendPolling();
        
        try {
            const apiUrl = `${pluginSettings.apiUrl}/v1/memories`;
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(item.memory)
            });
            
            // 读取响应体为文本，然后尝试解析 JSON
            const responseText = await response.text();
            let result;
            try {
                result = JSON.parse(responseText);
            } catch (parseError) {
                remoteLog.memoryError(`JSON解析失败 (HTTP ${response.status}): ${responseText.substring(0, 200)}`);
                throw new Error(`服务器返回非 JSON 响应`);
            }
            
            if (response.ok) {
                // 使用上面已解析的 result
                if (result.success) {
                    item.resolve({ 
                        success: true, 
                        id: result.id,
                        consistency_warnings: result.consistency_warnings || []
                    });
                    remoteLog.memory('记忆保存成功（队列处理）');
                    taskTracker.complete(taskId, true);
                    
                    // 显示一致性检查警告（如果有）
                    if (result.consistency_warnings && result.consistency_warnings.length > 0) {
                        remoteLog.warn('一致性检查警告: ' + result.consistency_warnings.join(', '));
                        // 使用 safeToastr 显示警告，不阻塞流程
                        const warningMsg = result.consistency_warnings.join('\n');
                        safeToastr.warning(warningMsg, '一致性检查警告', { timeOut: 8000 });
                    }
                } else {
                    // 服务器返回成功状态码，但业务上未保存（如重复内容）
                    item.resolve({ success: false, message: result.message });
                    remoteLog.memory('记忆跳过: ' + result.message);
                    taskTracker.complete(taskId, true, result.message);
                }
            } else if (response.status === 429) {
                // API 限流，延长间隔并重试
                remoteLog.warn('API限流，将延迟重试');
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
            remoteLog.memoryError('记忆保存失败: ' + e.message);
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
            remoteLog.memory('记忆已缓存到本地，等待后续同步');
        } catch (e) {
            remoteLog.memoryError('本地缓存保存失败: ' + e.message);
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
    remoteLog.memory(`MESSAGE_SENT idx=${messageIndex}, enabled=${pluginSettings.enabled}, connected=${isConnected}`);
    
    if (!pluginSettings.enabled || !isConnected) {
        remoteLog.memory('消息保存跳过: 插件未启用或未连接');
        return;
    }
    
    // 【一致性】统一转为数字类型
    const numericIndex = typeof messageIndex === 'number' ? messageIndex : parseInt(messageIndex, 10);
    if (isNaN(numericIndex)) {
        remoteLog.memoryError('onMessageSent: 无效的消息索引: ' + messageIndex);
        return;
    }
    
    try {
        const context = SillyTavern.getContext();
        const chat = context.chat;
        const message = chat[numericIndex];
        
        remoteLog.memory(`获取消息: hasMsg=${!!message?.mes}, len=${message?.mes?.length || 0}, preview="${(message?.mes || '').substring(0, 30)}"`);
        
        if (!message || !message.mes) {
            remoteLog.memory('消息为空，跳过');
            return;
        }
        
        // v4.2: 如果启用 Turn API，缓存用户消息等待 AI 回复
        if (pluginSettings.useTurnApi) {
            // 防止重复缓存同一条消息
            if (pendingUserMessage === message.mes) {
                remoteLog.turn('用户消息已缓存，跳过重复');
                return;
            }
            remoteLog.turn(`缓存用户消息: "${message.mes.substring(0, 40)}..."`);
            pendingUserMessage = message.mes;
            pendingUserMessageTimestamp = Date.now();
            return;  // 不立即保存，等待 AI 回复后一起发送
        }
        
        // 【传统模式】使用队列保存，不阻塞
        // 先将记忆加入队列，立即返回让消息显示
        remoteLog.memory(`用户消息加入队列: "${message.mes.substring(0, 40)}..."`);
        
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
                remoteLog.memory('已保存用户消息');
                // 【修复】只有记忆保存成功（非重复）才触发伏笔分析
                notifyForeshadowingAnalyzer(message.mes, 'user');
            } else if (result.queued) {
                remoteLog.memory('用户消息已加入队列/本地缓存');
            } else {
                remoteLog.memory('用户消息跳过（重复）: ' + result.message);
            }
        }).catch(err => {
            remoteLog.memoryError('消息保存队列错误: ' + err.message);
        });
    } catch (e) {
        remoteLog.memoryError('处理用户消息失败: ' + e.message);
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
 * 【重构】不直接处理，而是等待 character_message_rendered 事件
 */
async function onMessageReceived(messageIndex) {
    if (!pluginSettings.enabled || !isConnected) return;
    
    // 【关键】统一将 messageIndex 转为数字，确保 Map 键类型一致
    const numericIndex = typeof messageIndex === 'number' ? messageIndex : parseInt(messageIndex, 10);
    if (isNaN(numericIndex)) {
        console.warn('[Recall] 无效的消息索引:', messageIndex);
        return;
    }
    
    try {
        const context = SillyTavern.getContext();
        const chat = context.chat;
        const message = chat[numericIndex];
        
        if (!message || !message.mes) return;
        
        // 如果启用了思维链过滤，等待渲染完成后再处理
        if (pluginSettings.filterThinking) {
            // 将消息加入待处理队列，等待 character_message_rendered 事件
            pendingAIMessages.set(numericIndex, { message });
            console.log(`[Recall] AI消息 #${numericIndex} 已加入待处理队列，等待渲染完成...`);
            
            // 设置超时：如果 5 秒内没有收到渲染完成事件，就用 fallback 方案
            setTimeout(() => {
                if (pendingAIMessages.has(numericIndex)) {
                    console.log(`[Recall] ⚠ 消息 #${numericIndex} 渲染超时，使用 fallback 方案`);
                    pendingAIMessages.delete(numericIndex);
                    saveAIMessageFallback(numericIndex, message);
                }
            }, 5000);
        } else {
            // 用户关闭了过滤功能，直接保存原始内容
            saveAIMessageDirect(numericIndex, message, message.mes);
        }
    } catch (e) {
        console.warn('[Recall] 处理AI响应失败:', e);
    }
}

/**
 * Fallback：使用正则过滤保存消息
 */
async function saveAIMessageFallback(messageIndex, message) {
    let contentToSave = filterThinkingContent(message.mes);
    // 【新增】同样需要清理 HTML 残留
    contentToSave = cleanHtmlArtifacts(contentToSave);
    if (contentToSave !== message.mes) {
        console.log('[Recall] 使用正则过滤+HTML清理（fallback）');
    }
    await saveAIMessageDirect(messageIndex, message, contentToSave);
}

/**
 * 直接保存AI消息（已处理好的内容）
 */
async function saveAIMessageDirect(messageIndex, message, contentToSave) {
    // 【新增】最后一道防线：清理 HTML 残留
    contentToSave = cleanHtmlArtifacts(contentToSave);
    
    if (!contentToSave || contentToSave.trim().length === 0) {
        remoteLog.memory('内容为空，跳过保存');
        return;
    }
    
    // v4.2: 防止同一条消息被重复处理
    // 生成消息唯一标识（基于内容的哈希）
    const messageHash = contentToSave.substring(0, 100) + '_' + contentToSave.length;
    
    // v4.2: 如果 Turn API 正在处理中，检查是否是同一条消息
    if (turnApiInProgress) {
        if (lastTurnApiMessageId === messageHash) {
            remoteLog.turn('[DUP] Turn API 正在处理同一条消息，跳过本次调用');
            return;
        }
        // 如果是不同的消息，说明是新的一轮对话，不应该阻塞
        // 但这种情况不应该发生，因为 Turn API 会在完成前阻塞
        remoteLog.warn('Turn API 正在处理，但收到了不同的消息，可能是并发问题');
    }
    
    // v4.2: 如果 Turn API 启用，且这条消息已经被处理过，跳过（防止重复）
    // 注意：只在 useTurnApi=true 时检查，避免影响传统模式
    if (pluginSettings.useTurnApi && lastTurnApiMessageId === messageHash && !pendingUserMessage) {
        remoteLog.turn('[DUP] 消息已通过 Turn API 处理，跳过传统模式');
        return;
    }
    
    // v4.2: 调试日志
    remoteLog.memory(`saveAIMessageDirect: useTurnApi=${pluginSettings.useTurnApi}, hasPending=${!!pendingUserMessage}, inProgress=${turnApiInProgress}`);
    
    // v4.2: 如果启用 Turn API 且有缓存的用户消息，使用 Turn API
    if (pluginSettings.useTurnApi && pendingUserMessage) {
        const userMsg = pendingUserMessage;
        const userTimestamp = pendingUserMessageTimestamp;
        
        // 清空缓存
        pendingUserMessage = null;
        pendingUserMessageTimestamp = 0;
        
        // 设置处理中标志
        turnApiInProgress = true;
        lastTurnApiMessageId = messageHash;
        
        try {
            // 检查用户消息是否超时（超过 5 分钟可能不是同一轮对话）
            const timeout = 5 * 60 * 1000;  // 5 分钟
            if (Date.now() - userTimestamp > timeout) {
                remoteLog.turn('用户消息已超时(>5min)，分别保存');
                lastTurnApiMessageId = null;  // 清除，允许传统模式保存 AI 消息
                // 先保存用户消息（使用传统方式）
                memorySaveQueue.add({
                    content: userMsg,
                    user_id: currentCharacterId || 'default',
                    metadata: { 
                        role: 'user', 
                        source: 'sillytavern',
                        character_id: currentCharacterId || 'default',
                        timestamp: userTimestamp
                    }
                });
                // 继续使用传统方式保存 AI 回复（在 finally 之后）
            } else {
                // 使用 Turn API 批量保存
                const result = await saveTurnWithApi(userMsg, contentToSave, message.name);
                
                if (result.success) {
                    turnApiInProgress = false;  // 清除标志
                    // 注意：不清除 lastTurnApiMessageId，用于防止同一消息的重复调用
                    // 它会在下一轮不同消息时被覆盖
                    return;  // 成功，无需继续
                }
                
                if (result.fallback) {
                    // Turn API 失败，回退到传统方式
                    remoteLog.turn('[回退] 先保存用户消息');
                    lastTurnApiMessageId = null;  // 清除，允许传统模式保存
                    memorySaveQueue.add({
                        content: userMsg,
                        user_id: currentCharacterId || 'default',
                        metadata: { 
                            role: 'user', 
                            source: 'sillytavern',
                            character_id: currentCharacterId || 'default',
                            timestamp: userTimestamp
                        }
                    });
                    // 继续使用传统方式保存 AI 回复
                } else {
                    // 非回退失败（如重复），直接返回
                    turnApiInProgress = false;  // 清除标志
                    return;
                }
            }
        } finally {
            // 确保标志被清除（除非已经在上面清除了）
            turnApiInProgress = false;
        }
    }
    
    // 【传统模式】长文本分段处理
    const chunkSize = pluginSettings.chunkSize || 2000;
    const shouldChunk = pluginSettings.autoChunkLongText && contentToSave.length > chunkSize;
    const chunks = shouldChunk ? chunkLongText(contentToSave, chunkSize) : [contentToSave];
    
    if (chunks.length > 1) {
        remoteLog.memory(`长文本(${contentToSave.length}字)分成${chunks.length}段保存`);
    }
    
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
                ...(isMultiPart && {
                    chunk_index: i + 1,
                    chunk_total: chunks.length,
                    original_length: contentToSave.length
                })
            }
        });
        
        if (i === 0) {
            firstChunkPromise = promise;
        }
    }
    
    console.log(`[Recall] AI响应已加入保存队列 (${chunks.length}段, 共${contentToSave.length}字)`);
    
    if (firstChunkPromise) {
        firstChunkPromise.then(result => {
            if (result.success) {
                notifyForeshadowingAnalyzer(contentToSave, 'assistant');
            } else {
                console.log('[Recall] AI响应跳过伏笔分析（重复内容）');
            }
        }).catch(err => {
            console.warn('[Recall] 保存AI响应失败:', err);
        });
    }
}

/**
 * v4.2: 使用 Turn API 批量保存用户消息和AI回复
 * 
 * 性能优化：
 * - Embedding 复用：一次计算，多处使用（节省 2-4s）
 * - 合并 LLM 分析：矛盾检测+关系提取一次调用（节省 15-25s）
 * - 批量索引更新：减少 I/O 开销
 * 
 * @param {string} userMessage - 用户消息
 * @param {string} aiResponse - AI回复（已过滤思考内容）
 * @param {string} characterName - 角色名称（可选）
 */
async function saveTurnWithApi(userMessage, aiResponse, characterName = null) {
    if (!isConnected || !pluginSettings.enabled) {
        remoteLog.turn('未连接或已禁用，跳过');
        return { success: false, message: '未连接' };
    }
    
    const userId = currentCharacterId || 'default';
    const charId = characterName || currentCharacterId || 'default';
    
    // 生成消息签名用于追踪
    const msgHash = `${(userMessage.substring(0, 50) + aiResponse.substring(0, 50)).length}_${Date.now() % 10000}`;
    
    remoteLog.turn(`========== Turn API 开始 [${msgHash}] ==========`);
    remoteLog.turn(`user_id=${userId}, char=${charId}`);
    remoteLog.turn(`用户消息(${userMessage.length}字): "${userMessage.substring(0, 50)}..."`);
    remoteLog.turn(`AI回复(${aiResponse.length}字): "${aiResponse.substring(0, 50)}..."`);
    
    const taskId = taskTracker.add('turn-save', '批量保存对话', '使用 Turn API');
    taskTracker.startBackendPolling();
    
    try {
        const apiUrl = `${pluginSettings.apiUrl}/v1/memories/turn`;
        remoteLog.turn(`请求 URL: ${apiUrl}`);
        
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_message: userMessage,
                ai_response: aiResponse,
                user_id: userId,
                character_id: charId,
                metadata: {
                    source: 'sillytavern',
                    timestamp: Date.now()
                }
            })
        });
        
        // 检查 HTTP 状态码
        if (!response.ok) {
            const errorText = await response.text();
            remoteLog.turnError(`HTTP 错误 ${response.status}: ${errorText.substring(0, 200)}`);
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        // 读取响应体为文本，然后尝试解析 JSON
        const responseText = await response.text();
        let result;
        try {
            result = JSON.parse(responseText);
        } catch (parseError) {
            remoteLog.turnError(`JSON 解析失败: ${responseText.substring(0, 200)}`);
            throw new Error(`服务器返回非 JSON 响应`);
        }
        
        if (result.success) {
            taskTracker.complete(taskId, true);
            const procTime = result.processing_time_ms ? result.processing_time_ms.toFixed(0) : '?';
            remoteLog.turn(`[OK] 保存成功: user=${result.user_memory_id}, ai=${result.ai_memory_id}, 耗时=${procTime}ms`);
            
            // 显示一致性检查警告
            if (result.consistency_warnings && result.consistency_warnings.length > 0) {
                const warningMsg = result.consistency_warnings.join('\n');
                remoteLog.warn(`一致性警告: ${warningMsg}`);
                safeToastr.warning(warningMsg, '一致性检查警告', { timeOut: 8000 });
            }
            
            remoteLog.turn(`========== Turn API 完成 ==========`);
            
            // 触发伏笔分析（使用合并内容）
            notifyForeshadowingAnalyzer(userMessage + '\n' + aiResponse, 'turn');
            
            return { success: true, result };
        } else {
            taskTracker.complete(taskId, false, result.message || '保存失败');
            remoteLog.turn(`[SKIP] 跳过: ${result.message}`);
            remoteLog.turn(`========== Turn API 完成 ==========`);
            return { success: false, message: result.message };
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        remoteLog.turnError(`Turn API 调用失败: ${e.message}`);
        remoteLog.turnError(`请求 URL: ${pluginSettings.apiUrl}/v1/memories/turn`);
        remoteLog.turn(`========== Turn API 失败，回退传统模式 ==========`);
        
        // 显示错误通知，帮助用户诊断问题
        if (e.message.includes('非 JSON') || e.message.includes('Unexpected')) {
            safeToastr.error(
                `Turn API 返回了非 JSON 响应。请检查：\n1. 后端服务是否正常运行\n2. API URL 是否正确: ${pluginSettings.apiUrl}\n3. 反向代理是否正确配置`,
                'Recall API 错误',
                { timeOut: 10000 }
            );
        }
        
        // 回退到传统保存方式
        remoteLog.turn('回退到传统保存方式...');
        return { success: false, fallback: true, error: e.message };
    }
}

/**
 * 聊天切换时（角色/群组切换）
 */
async function onChatChanged() {
    remoteLog.info('▶▶▶ onChatChanged 被触发');
    
    // 获取当前角色信息
    const context = SillyTavern.getContext();
    const characterId = context.characterId;
    const character = characterId !== undefined ? context.characters[characterId] : null;
    
    remoteLog.info(`角色信息: id=${characterId}, name=${character?.name || 'null'}, group=${context.groupId || 'null'}`);
    
    // 清除旧角色的记忆注入，避免残留
    try {
        if (context.setExtensionPrompt) {
            context.setExtensionPrompt('recall_memory', '', 0, 0, false, 0);
            remoteLog.debug('已清除旧角色的记忆注入');
        }
    } catch (e) {
        remoteLog.warn('清除旧注入失败: ' + e.message);
    }
    
    // 【重要】角色切换时，清空所有列表数据，确保新角色数据能正确加载
    clearAllListsForCharacterSwitch();
    
    if (character) {
        currentCharacterId = character.name || `char_${characterId}`;
        remoteLog.info('切换到角色: ' + currentCharacterId);
    } else if (context.groupId) {
        currentCharacterId = `group_${context.groupId}`;
        remoteLog.info('切换到群组: ' + currentCharacterId);
    } else {
        currentCharacterId = 'default';
        remoteLog.info('未检测到角色，使用 default');
    }
    
    remoteLog.info('准备加载数据, connected=' + isConnected);
    // 【优化】使用 Promise.all 并行加载，避免阻塞
    try {
        await Promise.all([
            loadMemories(),
            loadForeshadowings(),
            loadPersistentContexts()
        ]);
        remoteLog.info('数据加载完成');
    } catch (e) {
        remoteLog.warn('部分数据加载失败: ' + e.message);
    }
}

/**
 * 角色切换时清空所有列表，重置 loading 标志和已加载标志
 */
function clearAllListsForCharacterSwitch() {
    // 【重要】清空待处理的AI消息队列，避免旧消息保存到新角色
    pendingAIMessages.clear();
    remoteLog.info('已清空待处理消息队列');
    
    // 【v4.2】清空 Turn API 相关状态，避免旧消息影响新角色
    pendingUserMessage = null;
    pendingUserMessageTimestamp = 0;
    lastTurnApiMessageId = null;
    turnApiInProgress = false;
    remoteLog.turn('已清空 Turn API 状态');
    
    // 【新增】停止选择器学习模式（如果正在进行）
    if (selectorLearningMode) {
        stopSelectorLearning();
    }
    
    // 重置所有 loading 标志
    _loadMemoriesLoading = false;
    _loadForeshadowingsLoading = false;
    _loadPersistentContextsLoading = false;
    _loadEntitiesLoading = false;
    _loadContradictionsLoading = false;
    _loadEpisodesLoading = false;
    
    // 取消进行中的请求并重置额外状态
    _loadMemoriesForUser = null;
    if (_loadMemoriesController) {
        _loadMemoriesController.abort();
        _loadMemoriesController = null;
    }
    
    // 注意：_loadForeshadowingsController 和 _loadPersistentContextsController 
    // 在函数内部已有角色切换检测，这里只需重置 forUser 即可
    // 它们会在下次调用时自动处理
    
    // 重置所有"已加载"标志（角色切换后需要重新加载数据）
    _memoriesLoaded = false;
    _foreshadowingsLoaded = false;
    _persistentContextsLoaded = false;
    _entitiesLoaded = false;
    _contradictionsLoaded = false;
    _episodesLoaded = false;
    _temporalStatsLoaded = false;
    
    // 清空记忆列表
    const memoryList = document.getElementById('recall-memory-list');
    if (memoryList) memoryList.innerHTML = '';
    
    // 清空伏笔列表
    const foreshadowingList = document.getElementById('recall-foreshadowing-list');
    if (foreshadowingList) foreshadowingList.innerHTML = '';
    
    // 清空条件列表
    const contextList = document.getElementById('recall-context-list');
    if (contextList) contextList.innerHTML = '';
    
    // 清空实体列表
    const entityList = document.getElementById('recall-entity-list');
    if (entityList) entityList.innerHTML = '';
    
    // 清空矛盾列表
    const contradictionList = document.getElementById('recall-contradiction-list');
    if (contradictionList) contradictionList.innerHTML = '';
    
    // 清空片段列表
    const episodeList = document.getElementById('recall-episode-list');
    if (episodeList) episodeList.innerHTML = '';
    
    // 重置时态统计
    const temporalCount = document.getElementById('recall-temporal-record-count');
    if (temporalCount) temporalCount.textContent = '-';
    
    console.log('[Recall] 已清空所有列表数据，准备加载新角色数据');
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
 * 添加防重入机制，避免多次并发请求
 * 当角色变化时，取消之前的请求
 */
async function loadMemories() {
    if (!isConnected) return;
    
    const userId = encodeURIComponent(currentCharacterId || 'default');
    
    // 如果正在加载同一个角色的数据，跳过
    if (_loadMemoriesLoading && _loadMemoriesForUser === userId) {
        console.log('[Recall] 记忆正在加载中（同一角色），跳过重复请求');
        return;
    }
    
    // 如果正在加载不同角色的数据，取消之前的请求
    if (_loadMemoriesLoading && _loadMemoriesForUser !== userId) {
        console.log(`[Recall] 角色已切换 (${_loadMemoriesForUser} -> ${userId})，取消之前的记忆请求`);
        if (_loadMemoriesController) {
            _loadMemoriesController.abort();
            _loadMemoriesController = null;
        }
        _loadMemoriesLoading = false;
    }
    
    _loadMemoriesLoading = true;
    _loadMemoriesForUser = userId;
    const currentRequestId = ++_loadMemoriesRequestId;
    
    // 重置分页状态
    currentMemoryOffset = 0;
    
    const taskId = taskTracker.add('load', '加载记忆列表');
    
    try {
        // 添加超时控制（10秒）
        const controller = new AbortController();
        _loadMemoriesController = controller;
        const timeoutId = setTimeout(() => {
            console.log('[Recall] 记忆请求超时，触发 abort');
            controller.abort();
        }, 10000);
        
        // 获取记忆列表（明确传入 offset=0）
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${userId}&limit=${MEMORIES_PER_PAGE}&offset=0`,
            { signal: controller.signal }
        );
        clearTimeout(timeoutId);
        
        // 检查请求是否已被新请求取代（角色切换等情况）
        if (_loadMemoriesRequestId !== currentRequestId) {
            console.log('[Recall] 记忆请求完成但已被新请求取代，忽略结果');
            taskTracker.complete(taskId, true, '已被新请求取代');
            // 注意：不重置 loading 标志，因为新请求正在执行
            return;
        }
        
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
        taskTracker.complete(taskId, true);
        _loadMemoriesLoading = false;
        _loadMemoriesController = null;
        _memoriesLoaded = true;  // 标记已加载
        
    } catch (e) {
        // 检查是否是当前有效的请求
        if (_loadMemoriesRequestId !== currentRequestId) {
            console.log(`[Recall] 记忆请求异常但已被新请求取代 (requestId=${currentRequestId})，忽略`);
            taskTracker.complete(taskId, true, '已被新请求取代');
            // 注意：不重置 loading 标志，因为新请求正在执行
            return;
        }
        
        const errMsg = e.name === 'AbortError' ? '请求超时（10s）' : e.message;
        console.warn('[Recall] 加载记忆失败:', errMsg);
        taskTracker.complete(taskId, false, errMsg);
        _loadMemoriesLoading = false;
        _loadMemoriesController = null;
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
    
    const taskId = taskTracker.add('delete', '删除记忆');
    
    try {
        console.log(`[Recall] 正在删除记忆: ${memoryId}`);
        const url = `${pluginSettings.apiUrl}/v1/memories/${encodeURIComponent(memoryId)}?user_id=${encodeURIComponent(currentCharacterId || 'default')}`;
        
        const response = await fetch(url, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            console.log(`[Recall] 删除成功: ${memoryId}`);
            taskTracker.complete(taskId, true);
            loadMemories();
        } else {
            const errData = await response.json().catch(() => ({}));
            console.error(`[Recall] 删除失败: ${response.status}`, errData);
            taskTracker.complete(taskId, false, errData.detail || response.statusText);
            alert(`删除失败: ${errData.detail || response.statusText}`);
        }
    } catch (e) {
        console.error('[Recall] 删除记忆失败:', e);
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('delete', '清空所有记忆');
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/memories?user_id=${encodeURIComponent(characterName)}&confirm=true`,
            { method: 'DELETE' }
        );
        
        const result = await response.json();
        
        if (result.success) {
            taskTracker.complete(taskId, true);
            alert(`✓ 已删除 ${result.deleted_count} 条记忆`);
            loadMemories();
        } else {
            taskTracker.complete(taskId, false, result.detail || '未知错误');
            alert(`删除失败: ${result.detail || '未知错误'}`);
        }
    } catch (e) {
        console.error('[Recall] 清空记忆失败:', e);
        taskTracker.complete(taskId, false, e.message);
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
    const currentRequestId = ++_loadForeshadowingsRequestId;
    const startTime = Date.now();
    
    const taskId = taskTracker.add('load', '加载伏笔列表');
    
    try {
        // 添加超时控制（30秒）
        const controller = new AbortController();
        _loadForeshadowingsController = controller;
        const timeoutId = setTimeout(() => {
            console.log('[Recall] 伏笔请求超时，触发 abort');
            controller.abort();
        }, 30000);
        
        const url = `${pluginSettings.apiUrl}/v1/foreshadowing?user_id=${userId}&character_id=${userId}`;
        
        const response = await fetch(url, {
            signal: controller.signal,
            mode: 'cors'
        });
        clearTimeout(timeoutId);
        
        // 检查是否是当前有效的请求
        if (_loadForeshadowingsRequestId !== currentRequestId) {
            console.log('[Recall] 伏笔请求完成但已被新请求取代，忽略结果');
            taskTracker.complete(taskId, true, '已被新请求取代');
            // 注意：不重置 loading 标志，因为新请求正在执行
            return;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log(`[Recall] 伏笔加载完成: ${data.length} 条，耗时 ${Date.now() - startTime}ms`);
        
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
        
        console.log(`[Recall] 伏笔加载完成，耗时 ${Date.now() - startTime}ms`);
        taskTracker.complete(taskId, true);
        _loadForeshadowingsLoading = false;
        _loadForeshadowingsController = null;
        _foreshadowingsLoaded = true;  // 标记已加载
    } catch (e) {
        // 检查是否是当前有效的请求
        if (_loadForeshadowingsRequestId !== currentRequestId) {
            console.log(`[Recall] 伏笔请求异常但已被新请求取代 (requestId=${currentRequestId})，忽略`);
            taskTracker.complete(taskId, true, '已被新请求取代');
            // 注意：不重置 loading 标志，因为新请求正在执行
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
            console.warn('[Recall] 加载伏笔失败:', errMsg);
        }
        
        taskTracker.complete(taskId, false, errMsg);
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
    
    const taskId = taskTracker.add('delete', '清空所有伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            taskTracker.complete(taskId, true);
            loadForeshadowings();
            console.log(`[Recall] 已清空 ${result.count} 个伏笔 (角色: ${currentCharacterId})`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 清空伏笔失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 清空伏笔失败:', e);
    }
}

/**
 * 加载持久条件列表
 * 添加防重入机制，避免多次并发请求
 * 当角色变化时，取消之前的请求
 */
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
    const currentRequestId = ++_loadPersistentContextsRequestId;
    
    const taskId = taskTracker.add('load', '加载持久条件');
    _loadPersistentContextsTaskId = taskId;
    const startTime = Date.now();
    
    try {
        // 添加超时控制（30秒）
        const controller = new AbortController();
        _loadPersistentContextsController = controller;
        
        const timeoutId = setTimeout(() => {
            console.log('[Recall] 持久条件请求超时，触发 abort');
            controller.abort();
        }, 30000);
        
        const url = `${pluginSettings.apiUrl}/v1/persistent-contexts?user_id=${userId}&character_id=${userId}`;
        
        const response = await fetch(url, {
            signal: controller.signal,
            mode: 'cors'
        });
        clearTimeout(timeoutId);
        
        // 检查是否是当前有效的请求
        if (_loadPersistentContextsRequestId !== currentRequestId) {
            console.log('[Recall] 持久条件请求完成但已被新请求取代，忽略结果');
            taskTracker.complete(taskId, true, '已被新请求取代');
            // 注意：不重置 loading 标志，因为新请求正在执行
            return;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log(`[Recall] 持久条件加载完成: ${data.length} 条，耗时 ${Date.now() - startTime}ms`);
        
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
        
        taskTracker.complete(taskId, true);
        _loadPersistentContextsLoading = false;
        _loadPersistentContextsController = null;
        _loadPersistentContextsTaskId = null;
        _persistentContextsLoaded = true;  // 标记已加载
    } catch (e) {
        // 检查是否是当前有效的请求
        if (_loadPersistentContextsRequestId !== currentRequestId) {
            console.log('[Recall] 持久条件请求异常但已被新请求取代，忽略');
            taskTracker.complete(taskId, true, '已被新请求取代');
            // 注意：不重置 loading 标志，因为新请求正在执行
            return;
        }
        
        const errMsg = e.name === 'AbortError' ? '请求超时（30s）' : (e.message || String(e));
        console.warn('[Recall] 加载持久条件失败:', errMsg);
        
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
    const taskId = taskTracker.add('add', '添加持久条件');
    
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
            taskTracker.complete(taskId, true);
            loadPersistentContexts();
            console.log(`[Recall] 持久条件已添加 (角色: ${currentCharacterId})`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 添加持久条件失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 添加持久条件失败:', e);
    }
}

/**
 * 移除持久条件
 */
async function removePersistentContext(contextId) {
    const taskId = taskTracker.add('delete', '移除持久条件');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadPersistentContexts();
            console.log(`[Recall] 持久条件已移除 (角色: ${currentCharacterId})`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 移除持久条件失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('delete', '清空所有条件');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            taskTracker.complete(taskId, true);
            loadPersistentContexts();
            console.log(`[Recall] 已清空 ${result.count} 个持久条件 (角色: ${currentCharacterId})`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 清空持久条件失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('load', '加载归档条件');
    
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
        
        taskTracker.complete(taskId, true);
    } catch (e) {
        console.warn('[Recall] 加载归档持久条件失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
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
    const taskId = taskTracker.add('save', '恢复归档条件');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}/restore?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadArchivedContexts();
            loadPersistentContexts();
            console.log(`[Recall] 已恢复归档条件: ${contextId}`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 恢复归档条件失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 恢复归档条件失败:', e);
    }
}

/**
 * 彻底删除归档的持久条件
 */
async function deleteArchivedContext(contextId) {
    const taskId = taskTracker.add('delete', '删除归档条件');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/archived/${contextId}?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadArchivedContexts();
            console.log(`[Recall] 已彻底删除归档条件: ${contextId}`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 删除归档条件失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('delete', '清空归档条件');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/archived?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            taskTracker.complete(taskId, true);
            loadArchivedContexts();
            console.log(`[Recall] 已清空 ${result.count} 个归档条件`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 清空归档条件失败:', e);
    }
}

/**
 * 手动归档活跃的持久条件
 */
async function archiveContext(contextId) {
    const taskId = taskTracker.add('save', '归档条件');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/${contextId}/archive?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadPersistentContexts();
            loadArchivedContexts();
            console.log(`[Recall] 已归档条件: ${contextId}`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('load', '加载归档伏笔');
    
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
        
        taskTracker.complete(taskId, true);
    } catch (e) {
        console.warn('[Recall] 加载归档伏笔失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
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
    const taskId = taskTracker.add('save', '恢复归档伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}/restore?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadArchivedForeshadowings();
            loadForeshadowings();
            console.log(`[Recall] 已恢复归档伏笔: ${foreshadowingId}`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 恢复归档伏笔失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 恢复归档伏笔失败:', e);
    }
}

/**
 * 彻底删除归档的伏笔
 */
async function deleteArchivedForeshadowing(foreshadowingId) {
    const taskId = taskTracker.add('delete', '删除归档伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/archived/${foreshadowingId}?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadArchivedForeshadowings();
            console.log(`[Recall] 已彻底删除归档伏笔: ${foreshadowingId}`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 删除归档伏笔失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('delete', '清空归档伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/archived?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            taskTracker.complete(taskId, true);
            loadArchivedForeshadowings();
            console.log(`[Recall] 已清空 ${result.count} 个归档伏笔`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 清空归档伏笔失败:', e);
    }
}

/**
 * 手动归档活跃的伏笔
 */
async function archiveForeshadowing(foreshadowingId) {
    const taskId = taskTracker.add('save', '归档伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}/archive?user_id=${userId}&character_id=${userId}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadForeshadowings();
            loadArchivedForeshadowings();
            console.log(`[Recall] 已归档伏笔: ${foreshadowingId}`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    const taskId = taskTracker.add('save', '更新持久条件');
    
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
            taskTracker.complete(taskId, true);
            safeToastr.success('持久条件已更新', 'Recall');
            loadPersistentContexts();
        } else {
            const errorText = await response.text();
            console.error('[Recall] 更新条件失败:', response.status, errorText);
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            safeToastr.error(`更新失败: ${response.status} ${errorText}`, 'Recall');
        }
    } catch (e) {
        console.error('[Recall] 更新条件失败:', e);
        taskTracker.complete(taskId, false, e.message);
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
    const taskId = taskTracker.add('save', '更新伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}?user_id=${userId}&character_id=${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadForeshadowings();
            console.log(`[Recall] 已更新伏笔: ${foreshadowingId}`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 更新伏笔失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('process', '压缩持久条件');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/persistent-contexts/consolidate?user_id=${userId}&character_id=${userId}&force=true`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            taskTracker.complete(taskId, true);
            loadPersistentContexts();
            if (result.reduced > 0) {
                console.log(`[Recall] 持久条件已压缩，减少了 ${result.reduced} 个`);
            } else {
                console.log('[Recall] 无需压缩');
            }
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('process', '重建向量索引');
    
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
            taskTracker.complete(taskId, true);
            alert(`✅ 向量索引重建完成！\n\n成功索引: ${result.indexed_count}/${result.total_memories} 条记忆`);
            console.log('[Recall] 向量索引重建完成:', result);
        } else {
            taskTracker.complete(taskId, false, result.message);
            alert(`❌ 重建失败: ${result.message}`);
            console.error('[Recall] 向量索引重建失败:', result);
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    const taskId = taskTracker.add('save', '解决伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}/resolve?user_id=${userId}&character_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resolution: '用户手动标记为已解决' })
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadForeshadowings();
            console.log(`[Recall] 伏笔已解决 (角色: ${currentCharacterId})`);
        } else {
            taskTracker.complete(taskId, false, `HTTP ${response.status}`);
            console.error('[Recall] 解决伏笔失败');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
        console.error('[Recall] 解决伏笔失败:', e);
    }
}

/**
 * 放弃/删除伏笔
 */
async function abandonForeshadowing(foreshadowingId) {
    const taskId = taskTracker.add('delete', '放弃伏笔');
    
    try {
        const userId = encodeURIComponent(currentCharacterId || 'default');
        const response = await fetch(`${pluginSettings.apiUrl}/v1/foreshadowing/${foreshadowingId}?user_id=${userId}&character_id=${userId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            taskTracker.complete(taskId, true);
            loadForeshadowings();
            console.log(`[Recall] 伏笔已放弃 (角色: ${currentCharacterId})`);
        } else {
            const error = await response.json().catch(() => ({}));
            taskTracker.complete(taskId, false, error.detail || '未知错误');
            console.error('[Recall] 放弃伏笔失败:', error.detail || '未知错误');
        }
    } catch (e) {
        taskTracker.complete(taskId, false, e.message);
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
    if (_loadEntitiesLoading) return;
    _loadEntitiesLoading = true;
    
    const userId = currentCharacterId || 'default';
    const searchInput = document.getElementById('recall-entity-search-input');
    const typeFilter = document.getElementById('recall-entity-type-filter');
    const search = searchInput?.value?.trim() || '';
    const entityType = typeFilter?.value || '';
    
    const taskId = taskTracker.add('load', '加载实体列表');
    
    try {
        // 使用配置的显示上限
        const displayLimit = pluginSettings.maxDisplayEntities || 100;
        let url = `${pluginSettings.apiUrl}/v1/entities?user_id=${encodeURIComponent(userId)}&limit=${displayLimit}`;
        if (entityType) url += `&entity_type=${encodeURIComponent(entityType)}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        // 兼容新旧两种返回格式：
        // 新格式: { entities: [...], total: N }
        // 旧格式: [...] 或 { entities: [...] }
        let entities = [];
        let total = 0;
        if (Array.isArray(data)) {
            // 旧格式：直接返回数组
            entities = data;
            total = data.length;
        } else if (data.entities) {
            // 新格式：包含 entities 和 total
            entities = data.entities || [];
            total = data.total ?? entities.length;
        } else {
            entities = [];
            total = 0;
        }
        
        // 保存服务端返回的总数（用于显示截断信息）
        // 注意：如果有类型过滤，serverTotal 是该类型的总数
        const serverTotal = data.total ?? entities.length;
        
        // 客户端搜索过滤（类型过滤已在服务端完成）
        if (search) {
            entities = entities.filter(e => 
                (e.name || '').toLowerCase().includes(search.toLowerCase())
            );
        }
        
        // 更新计数：显示真实总数
        const entityCountEl = document.getElementById('recall-entity-count');
        if (entityCountEl) {
            // 如果有搜索，显示过滤后的数量
            // 如果有截断（服务端总数 > 返回数量），显示 "X/Y" 格式
            if (search) {
                entityCountEl.textContent = entities.length;
            } else if (serverTotal > entities.length) {
                entityCountEl.textContent = `${entities.length}/${serverTotal}`;
            } else {
                entityCountEl.textContent = entities.length;
            }
        }
        
        // 渲染列表
        const listEl = document.getElementById('recall-entity-list');
        if (!listEl) {
            taskTracker.complete(taskId, true);
            _entitiesLoaded = true;  // 即使 DOM 元素不存在也标记已加载
            return;
        }
        
        if (entities.length === 0) {
            listEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">🏷️</div>
                    <p>暂无实体</p>
                    <small>对话时会自动提取实体</small>
                </div>
            `;
            taskTracker.complete(taskId, true);
            _entitiesLoaded = true;  // 空列表也标记已加载
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
        
        taskTracker.complete(taskId, true);
        _entitiesLoaded = true;  // 标记已加载
        
    } catch (e) {
        console.warn('[Recall] 加载实体失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
    } finally {
        _loadEntitiesLoading = false;
    }
}

/**
 * 创建单个实体项 HTML
 */
function createEntityItemHtml(entity) {
    const name = entity.name || entity.entity_name || '-';
    const type = entity.entity_type || entity.type || 'UNKNOWN';
    // 兼容多种字段名：occurrence_count (服务端返回) / mention_count / count
    const count = entity.occurrence_count || entity.mention_count || entity.count || 0;
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
        'ORG': '🏢',           // 服务端实际使用的组织类型
        'ORGANIZATION': '🏢', // 兼容旧数据
        'ITEM': '📦',          // 服务端实际使用的物品类型
        'OBJECT': '📦',       // 兼容旧数据
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
    
    const taskId = taskTracker.add('load', '加载实体详情', entityName);
    
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
        
        // 填充详情面板（添加空检查）
        const nameEl = document.getElementById('recall-entity-detail-name');
        const typeEl = document.getElementById('recall-entity-detail-type');
        const summaryEl = document.getElementById('recall-entity-detail-summary');
        const countEl = document.getElementById('recall-entity-detail-count');
        const relationsEl = document.getElementById('recall-entity-detail-relations');
        const panelEl = document.getElementById('recall-entity-detail-panel');
        
        if (nameEl) nameEl.textContent = entityName;
        if (typeEl) typeEl.textContent = entity.entity_type || entity.type || '-';
        if (summaryEl) summaryEl.textContent = entity.summary || '暂无摘要';
        // 兼容多种字段名：occurrence_count (服务端返回) / mention_count / count
        if (countEl) countEl.textContent = entity.occurrence_count || entity.mention_count || entity.count || '-';
        
        // 显示相关实体
        if (relationsEl) {
            if (relatedEntities.length > 0) {
                const relatedHtml = relatedEntities.slice(0, 10).map(r => {
                    const name = r.name || r.entity_name || r;
                    const relation = r.relation || r.relation_type || '';
                    return `<span class="recall-related-entity" data-name="${escapeHtml(name)}">${escapeHtml(name)}${relation ? ` (${relation})` : ''}</span>`;
                }).join(' ');
                relationsEl.innerHTML = relatedHtml;
                
                // 绑定相关实体点击事件
                document.querySelectorAll('.recall-related-entity').forEach(el => {
                    el.addEventListener('click', () => {
                        showEntityDetail(el.dataset.name);
                    });
                });
            } else {
                relationsEl.textContent = '暂无关系';
            }
        }
        
        // 显示面板
        if (panelEl) panelEl.style.display = 'block';
        
        taskTracker.complete(taskId, true);
        
    } catch (e) {
        console.warn('[Recall] 获取实体详情失败:', e);
        safeToastr.error('获取实体详情失败: ' + e.message);
        taskTracker.complete(taskId, false, e.message);
    }
}

/**
 * 生成实体摘要
 */
async function generateEntitySummary() {
    if (!currentSelectedEntity) return;
    
    const userId = currentCharacterId || 'default';
    const btn = document.getElementById('recall-generate-entity-summary');
    if (!btn) return;
    
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 生成中...';
    btn.disabled = true;
    
    const taskId = taskTracker.add('process', '生成实体摘要', currentSelectedEntity);
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/entities/${encodeURIComponent(currentSelectedEntity)}/generate-summary?user_id=${encodeURIComponent(userId)}`,
            { method: 'POST' }
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();
        
        const summaryEl = document.getElementById('recall-entity-detail-summary');
        if (summaryEl) summaryEl.textContent = result.summary || '生成失败';
        safeToastr.success('摘要已生成');
        
        taskTracker.complete(taskId, true);
        
    } catch (e) {
        console.warn('[Recall] 生成摘要失败:', e);
        safeToastr.error('生成摘要失败: ' + e.message);
        taskTracker.complete(taskId, false, e.message);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

/**
 * 加载矛盾列表
 */
async function loadContradictions() {
    if (_loadContradictionsLoading) return;
    _loadContradictionsLoading = true;
    
    const userId = currentCharacterId || 'default';
    const statusFilter = document.getElementById('recall-contradiction-status-filter');
    const status = statusFilter?.value || '';
    
    const taskId = taskTracker.add('load', '加载矛盾列表');
    
    try {
        let url = `${pluginSettings.apiUrl}/v1/contradictions?user_id=${encodeURIComponent(userId)}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        const contradictions = data.contradictions || data || [];
        
        // 更新计数
        const contradictionCountEl = document.getElementById('recall-contradiction-count');
        if (contradictionCountEl) contradictionCountEl.textContent = contradictions.length;
        
        // 渲染列表
        const listEl = document.getElementById('recall-contradiction-list');
        if (!listEl) {
            taskTracker.complete(taskId, true);
            _contradictionsLoaded = true;  // 即使 DOM 元素不存在也标记已加载
            return;
        }
        
        if (contradictions.length === 0) {
            listEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">⚔️</div>
                    <p>暂无矛盾</p>
                    <small>系统会自动检测事实冲突</small>
                </div>
            `;
            taskTracker.complete(taskId, true);
            _contradictionsLoaded = true;  // 空列表也标记已加载
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
        
        taskTracker.complete(taskId, true);
        _contradictionsLoaded = true;  // 标记已加载
        
    } catch (e) {
        console.warn('[Recall] 加载矛盾失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
    } finally {
        _loadContradictionsLoading = false;
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
    
    const taskId = taskTracker.add('process', '解决矛盾', `ID: ${contradictionId}`);
    
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
        const panelEl = document.getElementById('recall-contradiction-detail-panel');
        if (panelEl) panelEl.style.display = 'none';
        currentSelectedContradiction = null;
        taskTracker.complete(taskId, true);
        loadContradictions();
        
    } catch (e) {
        console.warn('[Recall] 解决矛盾失败:', e);
        safeToastr.error('解决矛盾失败: ' + e.message);
        taskTracker.complete(taskId, false, e.message);
    }
}

/**
 * 加载时态统计
 */
async function loadTemporalStats() {
    const userId = currentCharacterId || 'default';
    
    const taskId = taskTracker.add('load', '加载时态统计');
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/temporal/stats?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const stats = await response.json();
        
        const recordCountEl = document.getElementById('recall-temporal-record-count');
        const spanEl = document.getElementById('recall-temporal-span');
        if (recordCountEl) recordCountEl.textContent = stats.total_records || stats.record_count || 0;
        if (spanEl) spanEl.textContent = stats.time_span || stats.span || '-';
        
        taskTracker.complete(taskId, true);
        _temporalStatsLoaded = true;  // 标记已加载
        
    } catch (e) {
        console.warn('[Recall] 加载时态统计失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('query', '查询时间线', entityName);
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/temporal/timeline/${encodeURIComponent(entityName)}?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const timeline = data.timeline || data.events || data || [];
        
        taskTracker.complete(taskId, true);
        
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
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('query', '时间范围查询');
    
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
        
        taskTracker.complete(taskId, true);
        
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
        taskTracker.complete(taskId, false, e.message);
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
    
    const taskId = taskTracker.add('query', '图遍历', entityName);
    
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
        
        taskTracker.complete(taskId, true);
        
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
        taskTracker.complete(taskId, false, e.message);
    }
}

/**
 * 加载社区检测结果
 */
async function loadCommunities() {
    const userId = currentCharacterId || 'default';
    
    const taskId = taskTracker.add('load', '加载社区结构');
    
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
        taskTracker.complete(taskId, true);
        
    } catch (e) {
        console.warn('[Recall] 加载社区失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
    }
}

/**
 * 加载高级功能配置 (v4.0/v4.1)
 */
async function loadAdvancedConfig() {
    const taskId = taskTracker.add('load', '加载高级配置');
    
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
        
        taskTracker.complete(taskId, true);
        
    } catch (e) {
        console.warn('[Recall] 加载高级配置失败:', e);
        taskTracker.complete(taskId, false, e.message);
    }
}

/**
 * 保存高级功能配置到服务器
 */
async function saveAdvancedConfig() {
    const taskId = taskTracker.add('save', '保存高级配置');
    
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
            taskTracker.complete(taskId, true);
            safeToastr.success('高级配置已保存到服务器');
        } else {
            throw new Error(result.message || '保存失败');
        }
        
    } catch (e) {
        console.warn('[Recall] 保存高级配置失败:', e);
        taskTracker.complete(taskId, false, e.message);
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
    if (_loadEpisodesLoading) return;
    _loadEpisodesLoading = true;
    
    const userId = currentCharacterId || 'default';
    
    const taskId = taskTracker.add('load', '加载片段列表');
    
    try {
        const response = await fetch(
            `${pluginSettings.apiUrl}/v1/episodes?user_id=${encodeURIComponent(userId)}`
        );
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        const episodes = data.episodes || data || [];
        
        // 更新计数
        const episodeCountEl = document.getElementById('recall-episode-count');
        if (episodeCountEl) episodeCountEl.textContent = episodes.length;
        
        // 渲染列表
        const listEl = document.getElementById('recall-episode-list');
        if (!listEl) {
            taskTracker.complete(taskId, true);
            _episodesLoaded = true;  // 即使 DOM 元素不存在也标记已加载
            return;
        }
        
        if (episodes.length === 0) {
            listEl.innerHTML = `
                <div class="recall-empty-state">
                    <div class="recall-empty-icon">📖</div>
                    <p>暂无对话片段</p>
                    <small>对话时会自动组织成片段</small>
                </div>
            `;
            taskTracker.complete(taskId, true);
            _episodesLoaded = true;  // 空列表也标记已加载
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
        
        taskTracker.complete(taskId, true);
        _episodesLoaded = true;  // 标记已加载
        
    } catch (e) {
        console.warn('[Recall] 加载片段失败:', e.message);
        taskTracker.complete(taskId, false, e.message);
    } finally {
        _loadEpisodesLoading = false;
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
    
    const idEl = document.getElementById('recall-episode-detail-id');
    const startEl = document.getElementById('recall-episode-detail-start');
    const endEl = document.getElementById('recall-episode-detail-end');
    const memCountEl = document.getElementById('recall-episode-detail-memory-count');
    
    if (idEl) idEl.textContent = episodeId;
    if (startEl) startEl.textContent = formatTimelineDate(episode.start_time || episode.created_at);
    if (endEl) endEl.textContent = formatTimelineDate(episode.end_time || episode.updated_at);
    if (memCountEl) memCountEl.textContent = episode.memory_count || episode.memories?.length || 0;
    
    const taskId = taskTracker.add('load', '加载片段详情', episodeId.substring(0, 8));
    
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
        
        taskTracker.complete(taskId, true);
    } catch (e) {
        console.warn('[Recall] 加载 Episode 详情失败:', e);
        taskTracker.complete(taskId, false, e.message);
    }
    
    const panelEl = document.getElementById('recall-episode-detail-panel');
    if (panelEl) panelEl.style.display = 'block';
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
    
    const taskId = taskTracker.add('query', '高级搜索', `${searchType}: ${query.substring(0, 20)}`);
    
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
        
        taskTracker.complete(taskId, true);
        
        // 更新结果计数
        const countEl = document.getElementById('recall-search-result-count');
        if (countEl) countEl.textContent = `(${results.length})`;
        
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
        taskTracker.complete(taskId, false, e.message);
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
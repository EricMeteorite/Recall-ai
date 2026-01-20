# Recall v3 全面修复计划

> 创建日期：2026年1月20日  
> 目标：100% 满足 Recall-ai-plan.md 和 CHECKLIST-REPORT.md 的所有要求

---

## 📋 一、计划总览

### 1.1 核心承诺确认

| 承诺 | 当前状态 | 机制 |
|------|:--------:|------|
| **100%不遗忘对话原文** | ✅ 已满足 | L3 VolumeManager + VectorIndex + N-gram |
| **语义检索任意内容** | ✅ 已满足 | 8层检索系统 |
| **伏笔追踪** | ✅ 已满足 | ForeshadowingTracker + ForeshadowingAnalyzer |
| **规范遵守** | 🔧 部分满足 | L0注入✅ 规则编译器v3.1 |

### 1.2 需要修复/增强的问题

| 问题 | 优先级 | 复杂度 | 影响 |
|------|:------:|:------:|------|
| 伏笔/条件配置硬编码 | 🔴 高 | 低 | 用户无法自定义上限 |
| 配置文件内容不一致 | 🔴 高 | 低 | 脚本间配置模板不同步 |
| **伏笔归档机制缺失** | 🔴 高 | 中 | **几万轮后文件无限增长** |
| **条件归档机制缺失** | 🔴 高 | 中 | **几万轮后达到上限** |
| **伏笔/条件未索引到 VectorIndex** | 🔴 高 | 中 | **归档后无法语义检索** |
| 前端配置界面不完整 | 🟢 低 | 中 | 用户体验 |

### 1.3 关键问题解答

#### ❓ 问题1：几万轮对话后伏笔/条件达到上限怎么办？

**答案**：单纯调大上限只是缓解，**归档机制是必须实现的**。

```
┌─────────────────────────────────────────────────────────────┐
│                    伏笔/条件生命周期                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  活跃状态 ──────────────────────────► 归档状态               │
│                                                             │
│  伏笔: PLANTED/DEVELOPING    触发条件    伏笔: RESOLVED/ABANDONED │
│  条件: 高置信度              ──────►    条件: 低置信度(<0.1)    │
│                                                             │
│  存储: foreshadowing.json              存储: archive/         │
│       contexts.json                         *_archive.jsonl  │
│                                                             │
│  ⭐ 关键：创建时就索引到 VectorIndex                           │
│     这样即使归档后仍可通过语义搜索找到                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### ❓ 问题2：八层检索不够可靠，怎么保证100%不遗忘？

**答案**：100%不遗忘靠的是**原始对话的永久存储**，不是伏笔/条件系统。

```
┌─────────────────────────────────────────────────────────────┐
│                   100%不遗忘的三重保障                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1️⃣ VectorIndex（核心保障）                                  │
│     └─ 每条对话都建立语义索引，永不删除                       │
│     └─ 用户问"XX说过什么" → 语义搜索直接找到                  │
│                                                             │
│  2️⃣ L3 VolumeManager（原文存档）                             │
│     └─ 所有对话原文分卷存储，永久保留                         │
│     └─ 可按轮次号 O(1) 精确定位                              │
│                                                             │
│  3️⃣ N-gram Index（字符串兜底）                               │
│     └─ 原文全文索引，支持关键词搜索                          │
│     └─ 语义搜索失败时的最后防线                              │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  ⚠️ 伏笔/条件系统的定位：                                     │
│     └─ 这是"智能摘要"功能，不是"存储"功能                     │
│     └─ 即使伏笔被删除/归档，原始对话仍在 VectorIndex 中        │
│     └─ 用户问"那个神秘预言" → VectorIndex 找到原始对话        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**验证路径**：
- 用户问："我之前说过喜欢什么？"
- 系统：VectorIndex 语义搜索 → 找到原始对话 → 返回

即使八层检索的某些层"鸡肋"，**VectorIndex + N-gram 兜底保证了任何说过的话都能找到**。

---

## 📁 二、配置系统统一

### 2.1 当前配置现状

**配置文件位置**：`recall_data/config/api_keys.env`

**当前支持的配置项** (SUPPORTED_CONFIG_KEYS)：
```python
# server.py 第21-43行
SUPPORTED_CONFIG_KEYS = {
    # Embedding 配置
    'EMBEDDING_API_KEY',
    'EMBEDDING_API_BASE',
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMENSION',
    'RECALL_EMBEDDING_MODE',
    # LLM 配置
    'LLM_API_KEY',
    'LLM_API_BASE',
    'LLM_MODEL',
    # 伏笔配置
    'FORESHADOWING_LLM_ENABLED',
    'FORESHADOWING_TRIGGER_INTERVAL',
    'FORESHADOWING_AUTO_PLANT',
    'FORESHADOWING_AUTO_RESOLVE',
    # 去重配置
    'DEDUP_EMBEDDING_ENABLED',
    'DEDUP_HIGH_THRESHOLD',
    'DEDUP_LOW_THRESHOLD',
}
```

### 2.2 需要新增的配置项

#### 持久条件系统配置

| 配置项 | 当前硬编码位置 | 硬编码值 | 建议默认值 | 说明 |
|--------|---------------|---------|-----------|------|
| `CONTEXT_MAX_PER_TYPE` | context_tracker.py:133 | 5 | 10 | 每类型条件上限 |
| `CONTEXT_MAX_TOTAL` | context_tracker.py:134 | 30 | 100 | 条件总数上限 |
| `CONTEXT_DECAY_DAYS` | context_tracker.py:135 | 7 | 14 | 衰减开始天数 |
| `CONTEXT_DECAY_RATE` | context_tracker.py:136 | 0.1 | 0.05 | 每次衰减比例 |
| `CONTEXT_MIN_CONFIDENCE` | context_tracker.py:137 | 0.2 | 0.1 | 最低置信度 |

#### 伏笔系统配置

| 配置项 | 当前硬编码位置 | 硬编码值 | 建议默认值 | 说明 |
|--------|---------------|---------|-----------|------|
| `FORESHADOWING_MAX_RETURN` | foreshadowing.py:460 | 5 | 10 | 伏笔召回数量 |
| `FORESHADOWING_MAX_ACTIVE` | 新增 | 无 | 50 | **活跃伏笔数量上限**（超出自动归档最旧的） |

#### 检索系统配置（可选，高级用户）

| 配置项 | 当前硬编码位置 | 硬编码值 | 建议默认值 | 说明 |
|--------|---------------|---------|-----------|------|
| `RETRIEVAL_L5_TOP_K` | eight_layer.py:102 | 100 | 100 | 粗筛返回数量 |
| `RETRIEVAL_L6_TOP_K` | eight_layer.py:103 | 20 | 20 | 精排返回数量 |
| `RETRIEVAL_L7_TOP_K` | eight_layer.py:104 | 10 | 10 | 重排序返回数量 |
| `RETRIEVAL_L8_TOP_K` | eight_layer.py:105 | 5 | 5 | LLM过滤返回数量 |
| `RETRIEVAL_L8_ENABLED` | eight_layer.py:100 | False | false | 是否启用LLM过滤 |

> 💡 检索系统配置为高级选项，普通用户一般无需修改

### 2.3 配置文件需要同步的位置

**必须保持一致的位置**：

| # | 文件 | 位置 | 当前状态 | 缺少配置项 |
|---|------|------|:--------:|------------|
| 1 | `recall/server.py` | `SUPPORTED_CONFIG_KEYS` 字典 | ❌ | FORESHADOWING_MAX_RETURN, FORESHADOWING_MAX_ACTIVE, CONTEXT_* |
| 2 | `recall/server.py` | `get_default_config_content()` | ❌ | 同上 |
| 3 | `start.ps1` | `$supportedKeys` 数组 (L128-135) | ❌ | CONTEXT_*, FORESHADOWING_MAX_* |
| 4 | `start.ps1` | `$defaultConfig` 模板 (L169-221) | ❌ | DEDUP_*, CONTEXT_*, FORESHADOWING_MAX_* |
| 5 | `start.sh` | `supported_keys` 字符串 (L231) | ❌ | CONTEXT_*, FORESHADOWING_MAX_* |
| 6 | `start.sh` | EOF配置模板 (L268-320) | ❌ | DEDUP_*, CONTEXT_*, FORESHADOWING_MAX_* |
| 7 | `manage.ps1` | `$defaultConfig` 模板 (L285-337) | ❌ | DEDUP_*, CONTEXT_*, FORESHADOWING_MAX_* |
| 8 | **`manage.sh`** | EOF配置模板 (L295-345) | ❌ | DEDUP_*, CONTEXT_*, FORESHADOWING_MAX_* |

**需要检查的位置**（可能有配置模板）：

| # | 文件 | 说明 | 状态 |
|---|------|------|:----:|
| 9 | `install.ps1` | Windows 安装脚本 | ✅ 无配置模板 |
| 10 | `install.sh` | Linux/Mac 安装脚本 | ✅ 无配置模板 |

> ⚠️ **重要发现**：
> - `start.ps1` 和 `manage.ps1` 的配置模板缺少 `DEDUP_*` 配置项（只有 `supported_keys` 包含）
> - `start.sh` 和 `manage.sh` 的配置模板同样缺少 `DEDUP_*` 配置项
> - 所有脚本都缺少 `CONTEXT_*` 和 `FORESHADOWING_MAX_*` 配置项

### 2.4 完整配置模板（需要统一到以上所有位置）
```env
# ============================================================================
# Recall-AI 配置文件 / Configuration File
# ============================================================================

# ----------------------------------------------------------------------------
# Embedding 配置 (OpenAI 兼容接口)
# Embedding Configuration (OpenAI Compatible API)
# ----------------------------------------------------------------------------
EMBEDDING_API_KEY=
EMBEDDING_API_BASE=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=1024
RECALL_EMBEDDING_MODE=auto

# ----------------------------------------------------------------------------
# LLM 配置 (OpenAI 兼容接口)
# LLM Configuration (OpenAI Compatible API)
# ----------------------------------------------------------------------------
LLM_API_KEY=
LLM_API_BASE=
LLM_MODEL=

# ----------------------------------------------------------------------------
# 伏笔分析器配置
# Foreshadowing Analyzer Configuration
# ----------------------------------------------------------------------------
FORESHADOWING_LLM_ENABLED=false
FORESHADOWING_TRIGGER_INTERVAL=10
FORESHADOWING_AUTO_PLANT=true
FORESHADOWING_AUTO_RESOLVE=false
FORESHADOWING_MAX_RETURN=10

# 活跃伏笔数量上限（超出自动归档最旧的）/ Max active foreshadowings
FORESHADOWING_MAX_ACTIVE=50

# ----------------------------------------------------------------------------
# 持久条件系统配置
# Persistent Context Configuration
# ----------------------------------------------------------------------------
# 每类型最大条件数 / Max conditions per type
CONTEXT_MAX_PER_TYPE=10

# 条件总数上限 / Max total conditions
CONTEXT_MAX_TOTAL=100

# 置信度衰减开始天数 / Days before decay starts
CONTEXT_DECAY_DAYS=14

# 每次衰减比例 (0.0-1.0) / Decay rate per check
CONTEXT_DECAY_RATE=0.05

# 最低置信度（低于此值自动归档）/ Min confidence before archive
CONTEXT_MIN_CONFIDENCE=0.1

# ----------------------------------------------------------------------------
# 智能去重配置
# Smart Deduplication Configuration
# ----------------------------------------------------------------------------
DEDUP_EMBEDDING_ENABLED=true
DEDUP_HIGH_THRESHOLD=0.85
DEDUP_LOW_THRESHOLD=0.70
```

---

## �️ 三、前端配置界面分析

### 3.1 当前前端设置项

当前 ST 插件 (`plugins/sillytavern/index.js`) 的前端设置：

```javascript
const defaultSettings = {
    enabled: true,
    apiUrl: '',           // API地址（自动检测）
    autoInject: true,     // 自动注入上下文
    maxContextTokens: 8000,
    showIndicator: true,
    language: 'zh',
};
```

### 3.2 可以暴露到前端的配置项

| 配置项 | 是否适合前端 | 原因 |
|--------|:------------:|------|
| `CONTEXT_MAX_PER_TYPE` | ✅ 适合 | 用户可能想调整 |
| `CONTEXT_MAX_TOTAL` | ✅ 适合 | 用户可能想调整 |
| `FORESHADOWING_MAX_RETURN` | ✅ 适合 | 影响提示词长度 |
| `DEDUP_HIGH_THRESHOLD` | 🟡 可选 | 高级用户 |
| `DEDUP_LOW_THRESHOLD` | 🟡 可选 | 高级用户 |
| `FORESHADOWING_TRIGGER_INTERVAL` | ✅ 适合 | LLM消耗控制 |
| `RETRIEVAL_*` | ❌ 不适合 | 太技术性 |
| `*_API_KEY` | ❌ 不适合 | 应在配置文件中 |

### 3.3 前端配置实现方案

需要添加的 API：
```python
# recall/server.py
@app.get("/v1/config/limits")
async def get_limits_config():
    """获取当前限制配置"""
    return {
        "context_max_per_type": int(os.environ.get('CONTEXT_MAX_PER_TYPE', '10')),
        "context_max_total": int(os.environ.get('CONTEXT_MAX_TOTAL', '100')),
        "foreshadowing_max_return": int(os.environ.get('FORESHADOWING_MAX_RETURN', '10')),
        # ...
    }

@app.put("/v1/config/limits")
async def update_limits_config(updates: Dict[str, Any]):
    """更新限制配置（同时保存到文件）"""
    # 更新环境变量
    # 保存到 api_keys.env
    pass
```

需要添加的前端 UI：
```html
<!-- 在设置面板添加 -->
<div class="recall-setting-group">
    <h4>📊 容量限制</h4>
    <div class="recall-setting">
        <label>每类型条件上限</label>
        <input type="number" id="recall-context-max-per-type" min="1" max="50" value="10">
    </div>
    <div class="recall-setting">
        <label>条件总数上限</label>
        <input type="number" id="recall-context-max-total" min="10" max="500" value="100">
    </div>
    <div class="recall-setting">
        <label>伏笔召回数量</label>
        <input type="number" id="recall-foreshadowing-max" min="1" max="20" value="10">
    </div>
</div>
```

---

## 📝 四、需要修改的文件清单

### 第一阶段：配置系统统一（必须做）

| 文件 | 修改内容 | 复杂度 |
|------|----------|:------:|
| `recall/server.py` | 1. SUPPORTED_CONFIG_KEYS 添加新配置项<br>2. get_default_config_content() 更新模板 | 低 |
| `recall/processor/context_tracker.py` | 将 MAX_* 常量改为从环境变量读取 | 低 |
| `recall/processor/foreshadowing.py` | `max_count` 参数改为从环境变量读取 | 低 |
| `start.ps1` | 1. supportedKeys 数组添加新配置项<br>2. defaultConfig 更新模板（补全 DEDUP_*） | 低 |
| `start.sh` | 1. supported_keys 添加新配置项<br>2. EOF模板更新（补全 DEDUP_*） | 低 |
| `manage.ps1` | defaultConfig 更新模板（补全 DEDUP_*） | 低 |
| **`manage.sh`** | **EOF配置模板更新（补全 DEDUP_*）** | 低 |

### 第二阶段：归档机制实现（⚠️ 必须做，解决几万轮问题）

| 文件 | 修改内容 | 复杂度 |
|------|----------|:------:|
| `recall/processor/foreshadowing.py` | 添加 `_archive_foreshadowing()` 方法，resolved/abandoned 自动归档 | 中 |
| `recall/processor/context_tracker.py` | 添加 `_archive_context()` 方法，低置信度自动归档 | 中 |
| `recall/engine.py` | 伏笔/条件**创建时**索引到 VectorIndex（确保归档后可检索） | 中 |

#### 2.1 归档详细设计

##### 归档触发条件

| 类型 | 触发条件 | 说明 |
|------|---------|------|
| 伏笔 | `resolve()` 或 `abandon()` 被调用 | 状态变为 RESOLVED/ABANDONED |
| 伏笔 | **活跃数量 > MAX_ACTIVE** | 自动归档优先级最低的（见下方策略） |
| 条件 | `_apply_decay()` 后置信度 < MIN_CONFIDENCE | 在衰减检查时同时判断 |

##### MAX_ACTIVE 超限归档策略

当活跃伏笔数量超过 `FORESHADOWING_MAX_ACTIVE` 时：

```python
def _archive_overflow_foreshadowings(self):
    """当超过上限时，归档优先级最低的伏笔"""
    max_active = int(os.environ.get('FORESHADOWING_MAX_ACTIVE', '50'))
    
    if len(self.foreshadowings) <= max_active:
        return
    
    # 排序策略：优先归档 importance 最低的，其次是最旧的
    # 注意：DEVELOPING 状态也参与排序，可能被归档
    sorted_fsh = sorted(
        self.foreshadowings,
        key=lambda f: (f.importance, -f.created_turn)  # importance 升序，turn 降序
    )
    
    # 归档超出部分
    to_archive = sorted_fsh[:len(self.foreshadowings) - max_active]
    for fsh in to_archive:
        self._archive_foreshadowing(fsh)
        self.foreshadowings.remove(fsh)
```

> ⚠️ **DEVELOPING 状态说明**：DEVELOPING 属于活跃状态，当超过 MAX_ACTIVE 时也可能被归档（如果 importance 较低）。这是合理的——如果用户同时追踪太多伏笔，低优先级的需要让位。

##### 归档文件存储结构

```
recall_data/data/{user_id}/{character_id}/
├── foreshadowing.json          # 活跃伏笔（数量受限）
├── contexts.json               # 活跃条件（数量受限）
└── archive/                    # 归档目录
    ├── foreshadowing_archive.jsonl   # 已归档伏笔（JSONL格式）
    └── contexts_archive.jsonl        # 已归档条件（JSONL格式）
```

##### 归档文件大小管理

当单个归档文件过大时自动分卷：

```python
MAX_ARCHIVE_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def _get_archive_file_path(self, base_name: str) -> str:
    """获取归档文件路径，超过大小限制时自动创建新文件"""
    archive_dir = os.path.join(self.data_path, 'archive')
    os.makedirs(archive_dir, exist_ok=True)
    
    # 检查当前文件大小
    current_file = os.path.join(archive_dir, f'{base_name}.jsonl')
    if os.path.exists(current_file) and os.path.getsize(current_file) > MAX_ARCHIVE_FILE_SIZE:
        # 重命名为带编号的文件
        index = 1
        while os.path.exists(os.path.join(archive_dir, f'{base_name}_{index:03d}.jsonl')):
            index += 1
        os.rename(current_file, os.path.join(archive_dir, f'{base_name}_{index:03d}.jsonl'))
    
    return current_file
```

> 💡 归档文件格式：
> - 默认：`foreshadowing_archive.jsonl`
> - 分卷后：`foreshadowing_archive_001.jsonl`, `_002.jsonl`...

##### VectorIndex 文档ID格式

```python
# 文档ID前缀规范（区分不同类型的内容）
"mem_{user_id}_{memory_id}"      # 普通对话（现有）
"fsh_{user_id}_{foreshadowing_id}"  # 伏笔内容
"ctx_{user_id}_{context_id}"     # 条件内容
```

> ⚠️ **重要**：归档后 VectorIndex 条目**不删除**，这样才能保证"100%不遗忘"。
> 用户搜索时，VectorIndex 命中归档内容 → 从 archive/*.jsonl 读取详情。

##### 归档文件读取逻辑

```python
# 在 ForeshadowingTracker 中添加
def get_by_id(self, foreshadowing_id: str) -> Optional[Foreshadowing]:
    """获取伏笔（包括已归档的）"""
    # 1. 先查活跃伏笔
    for fsh in self.foreshadowings:
        if fsh.id == foreshadowing_id:
            return fsh
    
    # 2. 查归档文件
    archive_path = os.path.join(self.data_path, 'archive', 'foreshadowing_archive.jsonl')
    if os.path.exists(archive_path):
        with open(archive_path, 'r', encoding='utf-8') as f:
            for line in f:
                fsh_data = json.loads(line)
                if fsh_data['id'] == foreshadowing_id:
                    return Foreshadowing(**fsh_data)
    
    return None

# 在 ContextTracker 中添加类似方法
def get_context_by_id(self, context_id: str) -> Optional[PersistentContext]:
    """获取条件（包括已归档的）"""
    # 同上逻辑...
```

##### 条件归档触发时机

**衰减检查何时触发**：
```python
# 方案：在 get_context_for_prompt() 开头调用衰减检查
def get_context_for_prompt(self, user_id: str = "default") -> str:
    # 1. 先执行衰减检查（每次获取上下文时）
    self._apply_decay()
    
    # 2. 然后返回活跃条件
    # ...
```

**_apply_decay() 方法实现**：
```python
def _apply_decay(self):
    """应用置信度衰减，归档低置信度条件"""
    now = datetime.now()
    to_archive = []
    
    for ctx in self.contexts:
        # 检查是否超过衰减天数
        days_since_used = (now - ctx.last_used).days
        if days_since_used > self.DECAY_DAYS:
            ctx.confidence *= (1 - self.DECAY_RATE)
        
        # 低于阈值，加入归档列表
        if ctx.confidence < self.MIN_CONFIDENCE:
            to_archive.append(ctx)
    
    # 执行归档
    for ctx in to_archive:
        self._archive_context(ctx)
        self.contexts.remove(ctx)
```

#### 2.2 现有数据迁移

| 场景 | 处理方案 |
|------|----------|
| 已有伏笔未索引 | 首次启动时扫描，补建 VectorIndex 索引 |
| 已有条件未索引 | 首次启动时扫描，补建 VectorIndex 索引 |
| API触发 | 提供 `POST /v1/maintenance/rebuild-index` 手动重建 |

##### 索引重建触发条件（标记文件方式）

```python
# 在 engine.py 启动时调用
def _check_and_rebuild_index(self):
    """检查并重建索引（如果需要）"""
    # 使用标记文件判断是否需要重建
    marker_file = os.path.join(self.data_path, '.index_rebuilt_v1')
    
    if not os.path.exists(marker_file):
        print("[Recall] 正在为已有数据重建索引...")
        self._rebuild_foreshadowing_index()
        self._rebuild_context_index()
        
        # 写入标记文件（包含版本号，便于未来升级）
        with open(marker_file, 'w') as f:
            f.write(json.dumps({
                'version': 'v1',
                'rebuilt_at': datetime.now().isoformat(),
                'foreshadowing_count': len(self.foreshadowing_tracker.foreshadowings),
                'context_count': len(self.context_tracker.contexts),
            }))
        print("[Recall] 索引重建完成")

def _rebuild_foreshadowing_index(self):
    """为所有伏笔重建 VectorIndex"""
    # 遍历所有用户的伏笔数据（ForeshadowingTracker._user_data 是 Dict[user_id, {'foreshadowings': Dict[id, Foreshadowing]}]）
    for user_id, user_data in self.foreshadowing_tracker._user_data.items():
        fsh_dict = user_data.get('foreshadowings', {})
        for fsh_id, fsh in fsh_dict.items():
            if fsh.content:
                doc_id = f"fsh_{user_id}_{fsh_id}"
                self._vector_index.add_text(doc_id, fsh.content)

def _rebuild_context_index(self):
    """为所有条件重建 VectorIndex"""
    # 遍历所有用户的条件数据（ContextTracker.contexts 是 Dict[user_id, List[PersistentContext]]）
    for user_id, contexts_list in self.context_tracker.contexts.items():
        for ctx in contexts_list:
            if ctx.id and ctx.content:
                doc_id = f"ctx_{user_id}_{ctx.id}"
                self._vector_index.add_text(doc_id, ctx.content)
```

> 💡 **版本升级**：如果未来需要强制重建，只需将标记文件版本改为 `.index_rebuilt_v2`

### 第三阶段：前端配置界面（可选）

| 文件 | 修改内容 | 复杂度 |
|------|----------|:------:|
| `plugins/sillytavern/index.js` | 添加条件/伏笔上限配置 UI | 中 |
| `recall/server.py` | 添加 `/v1/config/context-limits` API | 低 |

---

## 🔧 四、具体实施步骤

### 步骤 1：更新 SUPPORTED_CONFIG_KEYS

**文件**：`recall/server.py`

```python
SUPPORTED_CONFIG_KEYS = {
    # Embedding 配置
    'EMBEDDING_API_KEY',
    'EMBEDDING_API_BASE',
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMENSION',
    'RECALL_EMBEDDING_MODE',
    # LLM 配置
    'LLM_API_KEY',
    'LLM_API_BASE',
    'LLM_MODEL',
    # 伏笔配置
    'FORESHADOWING_LLM_ENABLED',
    'FORESHADOWING_TRIGGER_INTERVAL',
    'FORESHADOWING_AUTO_PLANT',
    'FORESHADOWING_AUTO_RESOLVE',
    'FORESHADOWING_MAX_RETURN',          # 新增
    # 持久条件配置                        # 新增
    'CONTEXT_MAX_PER_TYPE',
    'CONTEXT_MAX_TOTAL',
    'CONTEXT_DECAY_DAYS',
    'CONTEXT_DECAY_RATE',
    'CONTEXT_MIN_CONFIDENCE',
    # 去重配置
    'DEDUP_EMBEDDING_ENABLED',
    'DEDUP_HIGH_THRESHOLD',
    'DEDUP_LOW_THRESHOLD',
}
```

### 步骤 2：修改 context_tracker.py

**文件**：`recall/processor/context_tracker.py`

将：
```python
class ContextTracker:
    # 配置常量
    MAX_PER_TYPE = 5
    MAX_TOTAL = 30
    DECAY_DAYS = 7
    DECAY_RATE = 0.1
    MIN_CONFIDENCE = 0.2
```

改为：
```python
class ContextTracker:
    @staticmethod
    def _get_limits_config() -> Dict[str, Any]:
        """获取限制配置（从环境变量，支持热更新）"""
        return {
            'max_per_type': int(os.environ.get('CONTEXT_MAX_PER_TYPE', '10')),
            'max_total': int(os.environ.get('CONTEXT_MAX_TOTAL', '100')),
            'decay_days': int(os.environ.get('CONTEXT_DECAY_DAYS', '14')),
            'decay_rate': float(os.environ.get('CONTEXT_DECAY_RATE', '0.05')),
            'min_confidence': float(os.environ.get('CONTEXT_MIN_CONFIDENCE', '0.1')),
        }
    
    # 兼容旧代码的属性访问
    @property
    def MAX_PER_TYPE(self) -> int:
        return self._get_limits_config()['max_per_type']
    
    @property
    def MAX_TOTAL(self) -> int:
        return self._get_limits_config()['max_total']
    
    # ... 其他属性
```

### 步骤 3：修改 foreshadowing.py

**文件**：`recall/processor/foreshadowing.py`

将 `get_context_for_prompt` 方法的 `max_count` 默认值改为从环境变量读取：
```python
def get_context_for_prompt(
    self, 
    user_id: str = "default", 
    current_turn: Optional[int] = None,
    max_count: int = None,  # 改为可选
) -> str:
    if max_count is None:
        max_count = int(os.environ.get('FORESHADOWING_MAX_RETURN', '10'))
    # ...
```

### 步骤 4：同步更新脚本配置

需要更新的脚本及位置：

| 脚本 | 位置 | 需更新内容 |
|------|------|-----------|
| start.ps1 | L128-135 `$supportedKeys` | 添加新配置项 |
| start.ps1 | L169-221 `$defaultConfig` | 更新模板（补 DEDUP_*、CONTEXT_*、FORESHADOWING_MAX_*） |
| start.sh | L231 `supported_keys` | 添加新配置项 |
| start.sh | L268-320 EOF模板 | 更新模板（同上） |
| manage.ps1 | L285-337 `$defaultConfig` | 更新模板（同上） |
| **manage.sh** | **L295-345 EOF模板** | **更新模板（同上）** |

---

## ✅ 五、CHECKLIST-REPORT 对照自查

### 5.1 十二点五最终自查项

| 需求 | 状态 | 说明 |
|------|:----:|------|
| 上万轮 RP | ✅ | VolumeManager 分卷存储 |
| 伏笔不遗忘 | ✅ | ForeshadowingTracker + LLM分析 |
| 几百万字规模 | ✅ | 分卷架构 + 懒加载 |
| 上千文件代码 | ❌ | v3.1 功能，可选 |
| 规范100%遵守 | 🔧 | L0注入✅ 规则编译器v3.1 |
| 零配置即插即用 | ✅ | pip install + API key |
| **100%不遗忘** | ✅ | Archive原文 + 8层检索 + N-gram |
| 面向大众友好 | ✅ | ST插件 + 全中文 |
| 配置key就能用 | ✅ | 环境变量或配置文件 |
| pip install即插即用 | ✅ | 自动下载NLP模型 |
| 普通人无门槛 | ✅ | 纯本地 + 用户自己API key |
| 3-5秒响应 | ✅ | 并行检索 + 缓存 |
| 知识图谱 | ✅ | 轻量本地图 |
| 多用户/多角色 | ✅ | MemoryScope 隔离 |
| 低配电脑支持 | ✅ | 轻量模式 ~80MB |

### 5.2 即插即用/环境隔离检查

| 需求 | 状态 | 说明 |
|------|:----:|------|
| 单一数据目录 | ✅ | ./recall_data/ |
| 模型隔离存储 | ✅ | ./recall_data/models/ |
| 无系统级修改 | ✅ | 不修改注册表/PATH |
| 环境变量隔离 | ✅ | 运行时临时设置 |
| 完整卸载支持 | ✅ | 删除目录即可 |
| 虚拟环境兼容 | ✅ | recall-env |
| 不修改其他应用 | ✅ | ST插件独立 |
| 离线运行支持 | ✅ | 模型下载后离线 |
| 跨平台支持 | ✅ | Win/Mac/Linux |
| 配置文件隔离 | ✅ | 项目目录内 |

### 5.3 本次需要确保的额外检查

| 检查项 | 状态 | 修复方案 |
|--------|:----:|---------|
| 配置文件模板一致性 | ❌ | 统一7个位置的配置模板 |
| 条件上限可配置 | ❌ | 暴露到 api_keys.env |
| 伏笔召回数量可配置 | ❌ | 暴露到 api_keys.env |
| **伏笔活跃数量上限** | ❌ | 新增 FORESHADOWING_MAX_ACTIVE=50 |
| **归档文件存储结构** | ❌ | archive/*.jsonl |
| **VectorIndex文档ID规范** | ❌ | fsh_, ctx_, mem_ 前缀 |
| **现有数据迁移** | ❌ | 启动时补建索引 |
| 前端可配置上限 | ❌ | 可选，添加设置UI |

---

## 🚀 六、实施优先级（修正版）

> ⚠️ **重要修正**：归档机制从"建议做"提升为"必须做"，否则几万轮后会出问题。

### 🔴 第一优先级（必须完成）

| # | 任务 | 说明 | 状态 |
|---|------|------|:----:|
| 1 | **配置项暴露** | 将硬编码常量改为环境变量 | ⏳ |
| 2 | **配置模板统一** | 同步所有脚本的配置模板 | ⏳ |
| 3 | **伏笔归档机制** | resolved/abandoned + 超出MAX_ACTIVE 自动归档 | ⏳ |
| 4 | **条件归档机制** | 低置信度自动归档，释放活跃配额 | ⏳ |
| 5 | **VectorIndex 索引** | 伏笔/条件创建时索引，确保归档后可检索 | ⏳ |
| 6 | **现有数据迁移** | 首次启动时为已有伏笔/条件补建索引 | ⏳ |
| 7 | 前端错误处理 | 超时控制、错误提示 | ✅ 已完成 |

### 🟢 第二优先级（可选）

| # | 任务 | 说明 | 状态 |
|---|------|------|:----:|
| 7 | **前端配置界面** | 在ST插件中配置上限 | ⏳ |
| 8 | **检索返回伏笔对象** | 增强检索结果 | ⏳ |

---

## 📊 七、预计工作量（修正版）

| 阶段 | 预计时间 | 文件数 | 必要性 |
|------|:--------:|:------:|:------:|
| 配置系统统一 | 1-2小时 | **7个** | 🔴 必须 |
| 归档机制实现 | 3-4小时 | 3个 | 🔴 必须 |
| VectorIndex 索引 | 2-3小时 | 2个 | 🔴 必须 |
| 现有数据迁移 | 1小时 | 1个 | 🔴 必须 |
| 前端配置界面 | 2-3小时 | 2个 | 🟢 可选 |
| **必须完成总计** | **7-10小时** | **13个** | - |
| **全部完成总计** | **9-13小时** | **15个** | - |

---

## ✅ 八、完成确认清单

执行前请确认：
- [ ] 已理解所有修改内容
- [ ] 已确认配置默认值（特别是上限值）
- [ ] 已确认脚本同步范围

执行后请验证：

**配置系统：**
- [ ] `recall/server.py` SUPPORTED_CONFIG_KEYS 已更新（含 FORESHADOWING_MAX_ACTIVE）
- [ ] `context_tracker.py` 常量改为环境变量读取
- [ ] `foreshadowing.py` max_count 和 max_active 可配置
- [ ] `start.ps1` 配置模板已更新（含 DEDUP_*、CONTEXT_*、FORESHADOWING_MAX_*）
- [ ] `start.sh` 配置模板已更新
- [ ] `manage.ps1` 配置模板已更新
- [ ] **`manage.sh` 配置模板已更新**
- [ ] 热更新后配置生效

**归档机制：**
- [ ] 伏笔 resolved/abandoned 时自动归档
- [ ] **伏笔数量超过 MAX_ACTIVE 时自动归档最旧的**
- [ ] 条件置信度低于阈值时自动归档（在衰减检查时触发）
- [ ] 归档文件正确写入 `archive/*.jsonl`
- [ ] 归档后主文件大小不再无限增长

**VectorIndex 索引：**
- [ ] 伏笔创建时内容被索引（文档ID: `fsh_{user_id}_{id}`）
- [ ] 条件创建时内容被索引（文档ID: `ctx_{user_id}_{id}`）
- [ ] 归档后仍可通过语义搜索找到

**现有数据迁移：**
- [ ] 首次启动时扫描已有伏笔，补建索引
- [ ] 首次启动时扫描已有条件，补建索引
- [ ] 提供 `/v1/maintenance/rebuild-index` API 手动触发

**验收测试：**
- [ ] 模拟1000轮对话，验证归档正常工作
- [ ] 创建超过50个伏笔，验证按 importance 优先级归档（非简单的"最旧"）
- [ ] 搜索已归档的伏笔内容，确认可检索到
- [ ] **调用 `get_by_id()` 获取已归档伏笔，确认能读取**
- [ ] **条件衰减测试：设置短衰减周期，验证低置信度自动归档**
- [ ] **版本升级测试：删除 `.index_rebuilt_v1` 后重启，验证索引重建**
- [ ] **归档文件分卷测试：生成超过10MB归档数据，验证自动分卷**
- [ ] **DEVELOPING 状态伏笔：验证低 importance 时可被归档**

---

## 📌 结论

| 用户问题 | 是否解决 | 解决方案 |
|----------|:--------:|----------|
| 几万轮后伏笔/条件达到上限 | ✅ | 归档机制 + 活跃数量上限 + 配置可调 |
| 100%不遗忘对话内容 | ✅ | VectorIndex + VolumeManager + N-gram（已实现） |
| 归档后能找到伏笔/条件 | ✅ | 创建时索引到 VectorIndex |
| 只创建不resolve的伏笔会堆积 | ✅ | MAX_ACTIVE 上限，超出自动归档 |

---

**是否开始执行第一优先级任务？**

# Recall AI v3.0.0

> 🧠 AI永久记忆系统 - 让AI永远不会忘记你说过的每一句话

## ⚡ 快速开始

### 方式一：本地安装（Windows/Mac/Linux）

```bash
# 克隆仓库
git clone https://github.com/your-repo/recall-ai.git
cd recall-ai

# Windows
.\install.ps1
.\start.ps1

# Linux / Mac  
chmod +x install.sh && ./install.sh
./start.sh
```

### 方式二：服务器部署（Ubuntu/Debian）

```bash
# 部署到服务器
git clone https://github.com/your-repo/recall-ai.git
cd recall-ai
chmod +x install.sh start.sh
./install.sh            # 安装（自动修复权限）
./start.sh --daemon     # 后台运行
./start.sh --stop       # 停止服务
```

服务启动后访问: http://YOUR_IP:18888/docs

---

## 🍺 SillyTavern 集成

### 架构说明

```
┌─────────────────┐        HTTP        ┌──────────────────┐
│  SillyTavern    │ ←───────────────→  │  Recall 服务器    │
│  (UI 扩展)      │   localhost:18888  │  (Python后端)    │
└─────────────────┘                    └──────────────────┘
```

**Recall 分两部分：**
1. **Python 后端** - 处理记忆存储、搜索、NLP（必须先启动）
2. **SillyTavern 插件** - 前端 UI，调用后端 API

### 安装 SillyTavern 插件

**方法 1：使用安装脚本（推荐）**
```bash
cd plugins/sillytavern
./install.sh  # 自动检测 ST 版本，按提示输入路径
```

**方法 2：手动复制**
```bash
# 新版 SillyTavern (1.12+) - 直接放在 extensions 下
cp -r plugins/sillytavern /path/to/SillyTavern/data/default-user/extensions/recall-memory

# 旧版 SillyTavern - 放在 third-party 下
cp -r plugins/sillytavern /path/to/SillyTavern/public/scripts/extensions/third-party/recall-memory

# 重启 SillyTavern
```

### 配置插件

1. 启动 Recall 服务：`./start.sh --daemon`
2. 重启 SillyTavern
3. 打开 SillyTavern → 扩展 → 找到 **Recall Memory**
4. 设置 API 地址（默认 `http://127.0.0.1:18888`）
5. 开启记忆功能

---

## 🖥️ API 使用

```python
from recall.engine import RecallEngine

engine = RecallEngine()

# 添加记忆
engine.add("Alice住在北京，是一名程序员")
engine.add("Bob是Alice的朋友")

# 搜索
results = engine.search("Alice的朋友")

# 构建上下文（给 LLM 用）
context = engine.build_context("告诉我关于Alice的信息")
```

---

## ✨ 特性

- ✅ **100% 不遗忘** - 8层检索防御 + 原文永久存档
- ✅ **伏笔追踪** - 自动检测叙事伏笔，主动提醒
- ✅ **知识图谱** - 轻量级本地图结构，无需Neo4j
- ✅ **多用户/多角色** - RP场景专门优化
- ✅ **规范遵守** - 确保设定不会自相矛盾
- ✅ **零配置** - pip install + API key 即可使用
- ✅ **纯本地** - 所有数据存储在项目目录

## 🗑️ 完整卸载

删除项目文件夹即可完全卸载，不会在系统留下任何痕迹。

---

## ⚙️ 配置说明

### 配置文件

启动后自动生成配置文件: `recall_data/config/api_keys.env`

```bash
# 方式一：硅基流动（推荐国内用户）
SILICONFLOW_API_KEY=sf-xxxxxx
SILICONFLOW_MODEL=BAAI/bge-large-zh-v1.5

# 方式二：OpenAI（支持中转站）
OPENAI_API_KEY=sk-xxxxxx
OPENAI_API_BASE=              # 留空用官方，或填中转站地址
OPENAI_MODEL=text-embedding-3-small

# 方式三：自定义 API（Azure/Ollama/其他）
EMBEDDING_API_KEY=your-key
EMBEDDING_API_BASE=https://your-api.com/v1
EMBEDDING_MODEL=your-model
EMBEDDING_DIMENSION=1536
```

### 热更新配置

修改配置文件后，无需重启服务：

```bash
# 热更新
curl -X POST http://localhost:18888/v1/config/reload

# 测试连接
curl http://localhost:18888/v1/config/test

# 查看当前配置
curl http://localhost:18888/v1/config
```

### 三种运行模式

| 模式 | 内存占用 | 特点 |
|------|---------|------|
| Lite 模式 | ~100MB | 仅关键词搜索，无需配置 |
| Cloud 模式 | ~150MB | 语义搜索，需要 API Key |
| Local 模式 | ~1.5GB | 本地模型，完全离线 |

---

## 📄 许可证

MIT License

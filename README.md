# Recall AI v3.0.0

> 🧠 AI永久记忆系统 - 让AI永远不会忘记你说过的每一句话

## ⚡ 一键安装

### Windows

```powershell
# 1. 克隆仓库
git clone https://github.com/your-repo/recall-ai.git
cd recall-ai

# 2. 双击 install.ps1 或运行:
.\install.ps1

# 3. 启动服务
.\start.ps1
```

### Linux / Mac

```bash
# 1. 克隆仓库
git clone https://github.com/your-repo/recall-ai.git
cd recall-ai

# 2. 安装
chmod +x install.sh && ./install.sh

# 3. 启动服务
./start.sh
```

服务启动后访问: http://127.0.0.1:18888

---

## 🍺 SillyTavern 插件

**需要先完成上面的主程序安装并启动服务！**

### Windows
```powershell
cd plugins\sillytavern
.\install.ps1
# 按提示输入你的 SillyTavern 路径
```

### Linux / Mac
```bash
cd plugins/sillytavern
chmod +x install.sh && ./install.sh
```

安装后重启 SillyTavern，在扩展面板启用 **Recall Memory**。

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

## 📄 许可证

MIT License

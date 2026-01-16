# Recall v3 - AI永久记忆系统

> 让AI永远不会忘记你说过的每一句话

## 🚀 快速开始

### 安装

```bash
# 推荐：使用虚拟环境
python -m venv recall-env
# Windows:
recall-env\Scripts\activate
# Linux/Mac:
source recall-env/bin/activate

pip install -e .
recall init          # 输入你的 API key
recall chat          # 开始使用
```

### 轻量模式（低配电脑）

```bash
recall init --lightweight   # 内存占用仅 ~80MB
```

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

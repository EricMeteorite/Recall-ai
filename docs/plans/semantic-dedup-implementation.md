# 语义去重实现总结

## 概述

为 Recall-ai 项目实现了基于 Embedding 的智能语义去重机制，用于处理持久条件（ContextTracker）和伏笔（ForeshadowingTracker）系统在上万轮对话中的重复问题。

## 三级去重策略

### 第一级：Embedding 向量余弦相似度（快速筛选）
- 使用现有的 `embedding_backend` 获取文本向量
- 计算余弦相似度判断语义相似度
- 高于 `DEDUP_HIGH_THRESHOLD`（默认 0.85）：自动合并
- 低于 `DEDUP_LOW_THRESHOLD`（默认 0.70）：视为不同

### 第二级：精确匹配检测
- 字符串完全相同时直接合并
- 避免不必要的 Embedding 计算

### 第三级：词重叠后备方案
- 当 Embedding 不可用时使用
- 兼容旧数据和轻量模式
- 使用 Jaccard 相似度，阈值 0.6

## 修改的文件

### 1. `recall/server.py`
- 添加配置键：`DEDUP_EMBEDDING_ENABLED`, `DEDUP_HIGH_THRESHOLD`, `DEDUP_LOW_THRESHOLD`

### 2. `start.ps1` / `start.sh`
- 添加新配置键支持

### 3. `recall/processor/context_tracker.py`
- `PersistentContext` 数据类添加 `_embedding` 字段
- 添加 `_get_dedup_config()` 静态方法
- 添加 `_get_embedding()` 方法
- 添加 `_compute_embedding_similarity()` 方法
- 重写 `_compute_similarity()` 支持 Embedding
- 重写 `_find_similar()` 返回相似度详情
- 修改 `add()` 方法使用新的去重逻辑

### 4. `recall/processor/foreshadowing.py`
- `Foreshadowing` 数据类添加 `_embedding` 字段
- 添加 `_get_dedup_config()` 静态方法
- 添加 `_get_embedding()` 方法
- 添加 `_compute_embedding_similarity()` 方法
- 添加 `_compute_word_similarity()` 方法
- 添加 `_find_similar()` 方法
- 重写 `plant()` 方法使用去重逻辑

### 5. `recall/engine.py`
- 获取 `embedding_backend` 并传递给追踪器
- 统一使用同一个 `embedding_backend_for_trackers` 变量

### 6. `tests/test_semantic_dedup.py`（新增）
- 完整的单元测试覆盖

## 配置项

通过环境变量配置（支持热更新）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEDUP_EMBEDDING_ENABLED` | `true` | 是否启用 Embedding 去重 |
| `DEDUP_HIGH_THRESHOLD` | `0.85` | 高相似度阈值（自动合并） |
| `DEDUP_LOW_THRESHOLD` | `0.70` | 低相似度阈值（视为不同） |

## 向后兼容性

- ✅ 旧数据无 `_embedding` 字段时自动设为 `None`
- ✅ 无 Embedding 后端时自动降级为词重叠方案
- ✅ 轻量模式完全兼容
- ✅ 所有原有 API 接口不变

## 性能考虑

- Embedding 计算仅在添加新条件时进行
- 已有条件的 Embedding 会持久化存储
- 余弦相似度计算使用 NumPy 向量化操作（~50ms）
- 精确匹配优先，避免不必要的计算

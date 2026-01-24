"""Recall API Server - FastAPI HTTP 接口"""

import os
import time
import asyncio
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .version import __version__
from .engine import RecallEngine


# ==================== 配置文件管理 ====================

# 支持的配置项（统一使用 OpenAI 兼容格式）
SUPPORTED_CONFIG_KEYS = {
    # Embedding 配置
    'EMBEDDING_API_KEY',
    'EMBEDDING_API_BASE',
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMENSION',
    # Embedding 速率限制
    'EMBEDDING_RATE_LIMIT',       # 每时间窗口最大请求数
    'EMBEDDING_RATE_WINDOW',      # 速率限制时间窗口（秒）
    # Embedding 模式
    'RECALL_EMBEDDING_MODE',
    # LLM 配置（用于伏笔分析器等功能）
    'LLM_API_KEY',
    'LLM_API_BASE',
    'LLM_MODEL',
    # 伏笔分析器配置
    'FORESHADOWING_LLM_ENABLED',
    'FORESHADOWING_TRIGGER_INTERVAL',
    'FORESHADOWING_AUTO_PLANT',
    'FORESHADOWING_AUTO_RESOLVE',
    'FORESHADOWING_MAX_RETURN',       # 伏笔召回数量
    'FORESHADOWING_MAX_ACTIVE',       # 活跃伏笔数量上限
    # 持久条件系统配置
    'CONTEXT_TRIGGER_INTERVAL',       # 条件提取触发间隔（每N轮）
    'CONTEXT_MAX_CONTEXT_TURNS',      # 对话获取范围（用于分析时获取的轮数）
    'CONTEXT_MAX_PER_TYPE',           # 每类型条件上限
    'CONTEXT_MAX_TOTAL',              # 条件总数上限
    'CONTEXT_DECAY_DAYS',             # 衰减开始天数
    'CONTEXT_DECAY_RATE',             # 每次衰减比例
    'CONTEXT_MIN_CONFIDENCE',         # 最低置信度（低于此自动归档）
    # 上下文构建配置（build_context）
    'BUILD_CONTEXT_INCLUDE_RECENT',   # 构建上下文时包含的最近对话数
    'PROACTIVE_REMINDER_ENABLED',     # 是否启用主动提醒（重要信息长期未提及时提醒）
    'PROACTIVE_REMINDER_TURNS',       # 主动提醒阈值（超过多少轮未提及则提醒）
    # 智能去重配置（持久条件和伏笔系统）
    'DEDUP_EMBEDDING_ENABLED',
    'DEDUP_HIGH_THRESHOLD',
    'DEDUP_LOW_THRESHOLD',
    
    # ====== v4.0 Phase 1/2 新增配置项 ======
    # 时态知识图谱配置
    'TEMPORAL_GRAPH_ENABLED',         # 是否启用时态知识图谱
    'TEMPORAL_GRAPH_BACKEND',         # 图谱后端: file/neo4j/falkordb
    'TEMPORAL_DECAY_RATE',            # 时态信息衰减率 (0.0-1.0)
    'TEMPORAL_MAX_HISTORY',           # 保留的最大时态历史记录数
    # 矛盾检测与管理配置
    'CONTRADICTION_DETECTION_ENABLED',  # 是否启用矛盾检测
    'CONTRADICTION_AUTO_RESOLVE',     # 是否自动解决矛盾（推荐 false）
    'CONTRADICTION_DETECTION_STRATEGY',  # 检测策略: RULE/LLM/MIXED/AUTO
    'CONTRADICTION_SIMILARITY_THRESHOLD',  # 相似度阈值（用于检测潜在矛盾）
    # 全文检索配置 (BM25)
    'FULLTEXT_ENABLED',               # 是否启用全文检索
    'FULLTEXT_K1',                    # BM25 k1 参数（词频饱和度）
    'FULLTEXT_B',                     # BM25 b 参数（文档长度归一化）
    'FULLTEXT_WEIGHT',                # 全文检索在混合搜索中的权重
    # 智能抽取器配置 (SmartExtractor)
    'SMART_EXTRACTOR_MODE',           # 模式: RULES/ADAPTIVE/LLM
    'SMART_EXTRACTOR_COMPLEXITY_THRESHOLD',  # 复杂度阈值（超过此值使用 LLM）
    'SMART_EXTRACTOR_ENABLE_TEMPORAL',  # 是否启用时态检测
    # 预算管理配置 (BudgetManager)
    'BUDGET_DAILY_LIMIT',             # 每日预算上限 (USD)
    'BUDGET_HOURLY_LIMIT',            # 每小时预算上限 (USD)
    'BUDGET_RESERVE',                 # 保留预算比例 (0.0-1.0)
    'BUDGET_ALERT_THRESHOLD',         # 预算警告阈值 (0.0-1.0)
    # 三阶段去重配置 (ThreeStageDeduplicator)
    'DEDUP_JACCARD_THRESHOLD',        # Jaccard 相似度阈值（阶段1）
    'DEDUP_SEMANTIC_THRESHOLD',       # 语义相似度阈值（阶段2 高）
    'DEDUP_SEMANTIC_LOW_THRESHOLD',   # 语义相似度低阈值（阶段2 低）
    'DEDUP_LLM_ENABLED',              # 是否启用 LLM 确认（阶段3）
    
    # ====== v4.0 Phase 3 十一层检索器配置项 ======
    'ELEVEN_LAYER_RETRIEVER_ENABLED', # 是否启用十一层检索器
    # 层开关配置
    'RETRIEVAL_L1_BLOOM_ENABLED',
    'RETRIEVAL_L2_TEMPORAL_ENABLED',
    'RETRIEVAL_L3_INVERTED_ENABLED',
    'RETRIEVAL_L4_ENTITY_ENABLED',
    'RETRIEVAL_L5_GRAPH_ENABLED',
    'RETRIEVAL_L6_NGRAM_ENABLED',
    'RETRIEVAL_L7_VECTOR_COARSE_ENABLED',
    'RETRIEVAL_L8_VECTOR_FINE_ENABLED',
    'RETRIEVAL_L9_RERANK_ENABLED',
    'RETRIEVAL_L10_CROSS_ENCODER_ENABLED',
    'RETRIEVAL_L11_LLM_ENABLED',
    # Top-K 配置
    'RETRIEVAL_L2_TEMPORAL_TOP_K',
    'RETRIEVAL_L3_INVERTED_TOP_K',
    'RETRIEVAL_L4_ENTITY_TOP_K',
    'RETRIEVAL_L5_GRAPH_TOP_K',
    'RETRIEVAL_L6_NGRAM_TOP_K',
    'RETRIEVAL_L7_VECTOR_TOP_K',
    'RETRIEVAL_L10_CROSS_ENCODER_TOP_K',
    'RETRIEVAL_L11_LLM_TOP_K',
    # 阈值与最终输出配置
    'RETRIEVAL_FINE_RANK_THRESHOLD',
    'RETRIEVAL_FINAL_TOP_K',
    # L5 图遍历配置
    'RETRIEVAL_L5_GRAPH_MAX_DEPTH',
    'RETRIEVAL_L5_GRAPH_MAX_ENTITIES',
    'RETRIEVAL_L5_GRAPH_DIRECTION',
    # L10 CrossEncoder 配置
    'RETRIEVAL_L10_CROSS_ENCODER_MODEL',
    # L11 LLM 配置
    'RETRIEVAL_L11_LLM_TIMEOUT',
    # 权重配置
    'RETRIEVAL_WEIGHT_INVERTED',
    'RETRIEVAL_WEIGHT_ENTITY',
    'RETRIEVAL_WEIGHT_GRAPH',
    'RETRIEVAL_WEIGHT_NGRAM',
    'RETRIEVAL_WEIGHT_VECTOR',
    'RETRIEVAL_WEIGHT_TEMPORAL',
}


def get_config_file_path() -> Path:
    """获取配置文件路径"""
    # 优先使用环境变量指定的数据目录
    data_root = os.environ.get('RECALL_DATA_ROOT', './recall_data')
    return Path(data_root) / 'config' / 'api_keys.env'


def get_default_config_content() -> str:
    """获取默认配置文件内容"""
    return '''# ============================================================================
# Recall-AI 配置文件
# Recall-AI Configuration File
# ============================================================================
#
# ⚡ 快速开始 (90%的用户只需要配置这里)
# ⚡ Quick Start (90% users only need to configure this section)
#
# 1. 填写 EMBEDDING_API_KEY 和 EMBEDDING_API_BASE (必须)
# 2. 填写 LLM_API_KEY 和 LLM_API_BASE (可选，用于伏笔/矛盾等高级功能)
# 3. 启动服务: ./start.ps1 或 ./start.sh
#
# 其他所有配置项都有合理的默认值，无需修改！
# All other settings have sensible defaults, no changes needed!
#
# ============================================================================

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  ⭐ 必填配置 - REQUIRED CONFIGURATION                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ----------------------------------------------------------------------------
# Embedding 配置 (OpenAI 兼容接口) - 必填!
# Embedding Configuration (OpenAI Compatible API) - REQUIRED!
# ----------------------------------------------------------------------------
# 示例 (Examples):
#   OpenAI:      https://api.openai.com/v1
#   SiliconFlow: https://api.siliconflow.cn/v1  (推荐国内用户)
#   Ollama:      http://localhost:11434/v1
# ----------------------------------------------------------------------------
EMBEDDING_API_KEY=
EMBEDDING_API_BASE=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=1024

# Embedding 模式: auto(自动检测), local(本地), api(远程API)
# Embedding Mode: auto(auto detect), local(local model), api(remote API)
RECALL_EMBEDDING_MODE=auto

# ----------------------------------------------------------------------------
# LLM 配置 (OpenAI 兼容接口) - 用于伏笔分析、矛盾检测等高级功能
# LLM Configuration (OpenAI Compatible API) - For foreshadowing, contradiction, etc.
# ----------------------------------------------------------------------------
LLM_API_KEY=
LLM_API_BASE=
LLM_MODEL=

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  ⚙️ 可选配置 - OPTIONAL CONFIGURATION (以下内容可保持默认值)              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ----------------------------------------------------------------------------
# Embedding API 速率限制
# Embedding API Rate Limiting
# ----------------------------------------------------------------------------
# 每时间窗口最大请求数（默认10，设为0禁用）
# Max requests per time window (default 10, set 0 to disable)
EMBEDDING_RATE_LIMIT=10

# 速率限制时间窗口（秒，默认60）
# Rate limit time window in seconds (default 60)
EMBEDDING_RATE_WINDOW=60

# ----------------------------------------------------------------------------
# 伏笔分析器配置
# Foreshadowing Analyzer Configuration
# ----------------------------------------------------------------------------
# 是否启用 LLM 伏笔分析 (true/false)
# Enable LLM-based foreshadowing analysis
FORESHADOWING_LLM_ENABLED=false

# 分析触发间隔（每N轮对话触发一次分析，最小1）
# Analysis trigger interval (trigger analysis every N turns, minimum 1)
FORESHADOWING_TRIGGER_INTERVAL=10

# 自动埋下伏笔 (true/false)
# Automatically plant detected foreshadowing
FORESHADOWING_AUTO_PLANT=true

# 自动解决伏笔 (true/false) - 建议保持 false，让用户手动确认
# Automatically resolve detected foreshadowing (recommend false)
FORESHADOWING_AUTO_RESOLVE=false

# 伏笔召回数量（构建上下文时返回的伏笔数量）
# Number of foreshadowings to return when building context
FORESHADOWING_MAX_RETURN=10

# 活跃伏笔数量上限（超出时自动归档低优先级的伏笔）
# Max active foreshadowings (auto-archive low-priority ones when exceeded)
FORESHADOWING_MAX_ACTIVE=50

# ----------------------------------------------------------------------------
# 持久条件系统配置
# Persistent Context Configuration
# ----------------------------------------------------------------------------
# 条件提取触发间隔（每N轮对话触发一次LLM提取，最小1）
# Context extraction trigger interval (trigger every N turns, minimum 1)
CONTEXT_TRIGGER_INTERVAL=5

# 对话获取范围（分析时获取的历史轮数，确保有足够上下文）
# Max context turns for analysis (history turns to fetch for analysis)
CONTEXT_MAX_CONTEXT_TURNS=20

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
# 上下文构建配置（100%不遗忘保证）
# Context Building Configuration (100% Memory Guarantee)
# ----------------------------------------------------------------------------
# 构建上下文时包含的最近对话数（确保对话连贯性）
# Recent turns to include when building context
BUILD_CONTEXT_INCLUDE_RECENT=10

# 是否启用主动提醒（重要信息长期未提及时主动提醒AI）
# Enable proactive reminders for important info not mentioned for a while
PROACTIVE_REMINDER_ENABLED=true

# 主动提醒阈值（超过多少轮未提及则触发提醒）
# Turns threshold to trigger proactive reminder
PROACTIVE_REMINDER_TURNS=50

# ----------------------------------------------------------------------------
# 智能去重配置（持久条件和伏笔系统）
# Smart Deduplication Configuration (Persistent Context & Foreshadowing)
# ----------------------------------------------------------------------------
# 是否启用 Embedding 语义去重 (true/false)
# 启用后使用向量相似度判断重复，更智能；禁用则使用简单词重叠
# Enable Embedding-based semantic deduplication
DEDUP_EMBEDDING_ENABLED=true

# 高相似度阈值：超过此值直接合并（0.0-1.0，推荐0.85）
# High similarity threshold: auto-merge when exceeded (recommend 0.85)
DEDUP_HIGH_THRESHOLD=0.85

# 低相似度阈值：低于此值视为不相似（0.0-1.0，推荐0.70）
# Low similarity threshold: considered different when below (recommend 0.70)
DEDUP_LOW_THRESHOLD=0.70

# ============================================================================
# v4.0 Phase 1/2 新增配置
# v4.0 Phase 1/2 New Configurations
# ============================================================================

# ----------------------------------------------------------------------------
# 时态知识图谱配置
# Temporal Knowledge Graph Configuration
# ----------------------------------------------------------------------------
# 是否启用时态知识图谱（追踪事实随时间的变化）
# Enable temporal knowledge graph (track facts over time)
TEMPORAL_GRAPH_ENABLED=true

# 图谱存储后端: file(本地JSON), neo4j, falkordb
# Graph storage backend: file(local JSON), neo4j, falkordb
TEMPORAL_GRAPH_BACKEND=file

# 时态信息衰减率（0.0-1.0，值越大衰减越快）
# Temporal decay rate (0.0-1.0, higher = faster decay)
TEMPORAL_DECAY_RATE=0.1

# 保留的最大时态历史记录数
# Max temporal history records to keep
TEMPORAL_MAX_HISTORY=1000

# ----------------------------------------------------------------------------
# 矛盾检测与管理配置
# Contradiction Detection & Management Configuration
# ----------------------------------------------------------------------------
# 是否启用矛盾检测
# Enable contradiction detection
CONTRADICTION_DETECTION_ENABLED=true

# 是否自动解决矛盾（推荐 false，让用户确认）
# Auto-resolve contradictions (recommend false, let user confirm)
CONTRADICTION_AUTO_RESOLVE=false

# 检测策略: RULE(规则), LLM(大模型判断), MIXED(混合), AUTO(自动选择)
# Detection strategy: RULE/LLM/MIXED/AUTO (HYBRID is deprecated alias for MIXED)
CONTRADICTION_DETECTION_STRATEGY=MIXED

# 相似度阈值（用于检测潜在矛盾，0.0-1.0）
# Similarity threshold for detecting potential contradictions
CONTRADICTION_SIMILARITY_THRESHOLD=0.8

# ----------------------------------------------------------------------------
# 全文检索配置 (BM25)
# Full-text Search Configuration (BM25)
# ----------------------------------------------------------------------------
# 是否启用 BM25 全文检索
# Enable BM25 full-text search
FULLTEXT_ENABLED=true

# BM25 k1 参数（词频饱和度，推荐 1.2-2.0）
# BM25 k1 parameter (term frequency saturation)
FULLTEXT_K1=1.5

# BM25 b 参数（文档长度归一化，0.0-1.0）
# BM25 b parameter (document length normalization)
FULLTEXT_B=0.75

# 全文检索在混合搜索中的权重（0.0-1.0）
# Full-text search weight in hybrid search
FULLTEXT_WEIGHT=0.3

# ----------------------------------------------------------------------------
# 智能抽取器配置 (SmartExtractor)
# Smart Extractor Configuration
# ----------------------------------------------------------------------------
# 抽取模式: RULES(规则), ADAPTIVE(自适应), LLM(全LLM)
# Extraction mode: RULES/ADAPTIVE/LLM (LOCAL/HYBRID/LLM_FULL are deprecated aliases)
SMART_EXTRACTOR_MODE=ADAPTIVE

# 复杂度阈值（超过此值使用 LLM 辅助抽取，0.0-1.0）
# Complexity threshold (use LLM when exceeded)
SMART_EXTRACTOR_COMPLEXITY_THRESHOLD=0.6

# 是否启用时态检测（识别时间相关信息）
# Enable temporal detection
SMART_EXTRACTOR_ENABLE_TEMPORAL=true

# ----------------------------------------------------------------------------
# 预算管理配置 (BudgetManager)
# Budget Management Configuration
# ----------------------------------------------------------------------------
# 每日预算上限（美元，0=无限制）
# Daily budget limit in USD (0 = unlimited)
BUDGET_DAILY_LIMIT=0

# 每小时预算上限（美元，0=无限制）
# Hourly budget limit in USD (0 = unlimited)
BUDGET_HOURLY_LIMIT=0

# 保留预算比例（为重要操作预留的预算比例，0.0-1.0）
# Reserve budget ratio for critical operations
BUDGET_RESERVE=0.1

# 预算警告阈值（使用量超过此比例时发出警告，0.0-1.0）
# Budget alert threshold (warn when usage exceeds this ratio)
BUDGET_ALERT_THRESHOLD=0.8

# ----------------------------------------------------------------------------
# 三阶段去重配置 (ThreeStageDeduplicator)
# Three-Stage Deduplication Configuration
# ----------------------------------------------------------------------------
# Jaccard 相似度阈值（阶段1 MinHash+LSH，0.0-1.0）
# Jaccard similarity threshold (Stage 1)
DEDUP_JACCARD_THRESHOLD=0.7

# 语义相似度高阈值（阶段2，超过此值直接合并）
# Semantic similarity high threshold (Stage 2, auto-merge when exceeded)
DEDUP_SEMANTIC_THRESHOLD=0.85

# 语义相似度低阈值（阶段2，低于此值视为不同）
# Semantic similarity low threshold (Stage 2, considered different when below)
DEDUP_SEMANTIC_LOW_THRESHOLD=0.70

# 是否启用 LLM 确认（阶段3，用于边界情况）
# Enable LLM confirmation (Stage 3, for borderline cases)
DEDUP_LLM_ENABLED=false

# ============================================================================
# v4.0 Phase 3 十一层检索器配置
# v4.0 Phase 3 Eleven-Layer Retriever Configuration
# ============================================================================

# ----------------------------------------------------------------------------
# 主开关
# Master Switch
# ----------------------------------------------------------------------------
# 是否启用十一层检索器（替代默认的八层检索器）
# Enable eleven-layer retriever (replaces default eight-layer)
ELEVEN_LAYER_RETRIEVER_ENABLED=false

# ----------------------------------------------------------------------------
# 层开关配置
# Layer Enable/Disable Configuration
# ----------------------------------------------------------------------------
# L1: Bloom Filter 快速否定（极低成本排除不相关记忆）
RETRIEVAL_L1_BLOOM_ENABLED=true

# L2: 时态过滤（根据时间范围筛选，需要 TEMPORAL_GRAPH_ENABLED=true）
RETRIEVAL_L2_TEMPORAL_ENABLED=true

# L3: 倒排索引（关键词匹配）
RETRIEVAL_L3_INVERTED_ENABLED=true

# L4: 实体索引（命名实体匹配）
RETRIEVAL_L4_ENTITY_ENABLED=true

# L5: 知识图谱遍历（实体关系扩展，需要 TEMPORAL_GRAPH_ENABLED=true）
RETRIEVAL_L5_GRAPH_ENABLED=true

# L6: N-gram 匹配（模糊文本匹配）
RETRIEVAL_L6_NGRAM_ENABLED=true

# L7: 向量粗排（ANN 近似最近邻）
RETRIEVAL_L7_VECTOR_COARSE_ENABLED=true

# L8: 向量精排（精确相似度计算）
RETRIEVAL_L8_VECTOR_FINE_ENABLED=true

# L9: 重排序（综合评分）
RETRIEVAL_L9_RERANK_ENABLED=true

# L10: CrossEncoder 精排（深度语义匹配，需要 sentence-transformers）
RETRIEVAL_L10_CROSS_ENCODER_ENABLED=false

# L11: LLM 过滤（大模型最终确认，消耗 API）
RETRIEVAL_L11_LLM_ENABLED=false

# ----------------------------------------------------------------------------
# Top-K 配置（每层返回的候选数量）
# Top-K Configuration (candidates returned per layer)
# ----------------------------------------------------------------------------
RETRIEVAL_L2_TEMPORAL_TOP_K=500
RETRIEVAL_L3_INVERTED_TOP_K=100
RETRIEVAL_L4_ENTITY_TOP_K=50
RETRIEVAL_L5_GRAPH_TOP_K=100
RETRIEVAL_L6_NGRAM_TOP_K=30
RETRIEVAL_L7_VECTOR_TOP_K=200
RETRIEVAL_L10_CROSS_ENCODER_TOP_K=50
RETRIEVAL_L11_LLM_TOP_K=20

# ----------------------------------------------------------------------------
# 阈值与最终输出配置
# Thresholds and Final Output Configuration
# ----------------------------------------------------------------------------
# 精排阈值（进入精排阶段的候选数）
RETRIEVAL_FINE_RANK_THRESHOLD=100

# 最终返回的记忆数量
RETRIEVAL_FINAL_TOP_K=20

# ----------------------------------------------------------------------------
# L5 知识图谱遍历配置
# L5 Knowledge Graph Traversal Configuration
# ----------------------------------------------------------------------------
# 图遍历最大深度
RETRIEVAL_L5_GRAPH_MAX_DEPTH=2

# 图遍历起始实体数量
RETRIEVAL_L5_GRAPH_MAX_ENTITIES=3

# 遍历方向: both(双向), outgoing(出边), incoming(入边)
RETRIEVAL_L5_GRAPH_DIRECTION=both

# ----------------------------------------------------------------------------
# L10 CrossEncoder 配置
# L10 CrossEncoder Configuration
# ----------------------------------------------------------------------------
# CrossEncoder 模型名称（需要安装 sentence-transformers）
RETRIEVAL_L10_CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# ----------------------------------------------------------------------------
# L11 LLM 配置
# L11 LLM Configuration
# ----------------------------------------------------------------------------
# LLM 判断超时时间（秒）
RETRIEVAL_L11_LLM_TIMEOUT=10.0

# ----------------------------------------------------------------------------
# 权重配置（调整各检索层的相对权重）
# Weight Configuration (adjust relative weight of each layer)
# ----------------------------------------------------------------------------
RETRIEVAL_WEIGHT_INVERTED=1.0
RETRIEVAL_WEIGHT_ENTITY=1.2
RETRIEVAL_WEIGHT_GRAPH=1.0
RETRIEVAL_WEIGHT_NGRAM=0.8
RETRIEVAL_WEIGHT_VECTOR=1.0
RETRIEVAL_WEIGHT_TEMPORAL=0.5
'''


def load_api_keys_from_file():
    """从配置文件加载配置到环境变量
    
    配置文件位置: recall_data/config/api_keys.env
    用户可以直接编辑这个文件，然后调用热更新接口
    """
    config_file = get_config_file_path()
    
    if not config_file.exists():
        # 创建默认配置文件
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(get_default_config_content(), encoding='utf-8')
        print(f"[Config] 已创建配置文件: {config_file}")
        return
    
    # 先清除所有支持的配置项（热更新时确保旧配置被清除）
    for key in SUPPORTED_CONFIG_KEYS:
        if key in os.environ:
            del os.environ[key]
    
    # 读取配置文件
    loaded_configs = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                # 解析 KEY=VALUE 格式
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # 只设置支持的配置项，且值非空
                    if value and key in SUPPORTED_CONFIG_KEYS:
                        os.environ[key] = value
                        # 敏感信息脱敏显示
                        if 'KEY' in key:
                            display_value = value[:8] + '...' if len(value) > 8 else '***'
                        else:
                            display_value = value
                        loaded_configs.append(f"{key}={display_value}")
        
        if loaded_configs:
            print(f"[Config] 已加载配置: {', '.join(loaded_configs)}")
        else:
            print(f"[Config] 配置文件为空或无有效配置")
    except Exception as e:
        print(f"[Config] 读取配置文件失败: {e}")


def save_config_to_file(updates: Dict[str, str]):
    """将配置更新保存到配置文件
    
    Args:
        updates: 要更新的配置项 {KEY: VALUE}
    """
    config_file = get_config_file_path()
    
    # 确保配置文件存在
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(get_default_config_content(), encoding='utf-8')
    
    # 读取现有配置
    lines = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[Config] 读取配置文件失败: {e}")
        return
    
    # 更新配置
    updated_keys = set()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        # 保留注释和空行
        if not stripped or stripped.startswith('#'):
            new_lines.append(line)
            continue
        
        # 解析 KEY=VALUE
        if '=' in stripped:
            key = stripped.split('=', 1)[0].strip()
            if key in updates:
                # 更新这一行
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                # 同时更新环境变量
                os.environ[key] = updates[key]
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # 添加新配置项（不存在于文件中的）
    for key, value in updates.items():
        if key not in updated_keys and key in SUPPORTED_CONFIG_KEYS:
            new_lines.append(f"{key}={value}\n")
            os.environ[key] = value
    
    # 写入文件
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"[Config] 已保存配置: {list(updates.keys())}")
    except Exception as e:
        print(f"[Config] 保存配置文件失败: {e}")


# ==================== 请求/响应模型 ====================

class AddMemoryRequest(BaseModel):
    """添加记忆请求"""
    content: str = Field(..., description="记忆内容")
    user_id: str = Field(default="default", description="用户ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")


class AddMemoryResponse(BaseModel):
    """添加记忆响应"""
    id: str
    success: bool
    entities: List[str] = []
    message: str = ""
    consistency_warnings: List[str] = []  # 一致性检查警告


class TemporalFilterRequest(BaseModel):
    """时态过滤请求 - Phase 3"""
    start: Optional[str] = Field(default=None, description="时间范围起点 (ISO 格式)")
    end: Optional[str] = Field(default=None, description="时间范围终点 (ISO 格式)")


class GraphExpandRequest(BaseModel):
    """图遍历扩展请求 - Phase 3"""
    center_entities: List[str] = Field(default=[], description="中心实体列表")
    max_depth: int = Field(default=2, ge=1, le=5, description="BFS 最大深度")
    direction: str = Field(default="both", description="遍历方向: out|in|both")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="搜索查询")
    user_id: str = Field(default="default", description="用户ID")
    top_k: int = Field(default=10, ge=1, le=100, description="返回数量")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="过滤条件")
    # Phase 3 新增参数
    temporal_filter: Optional[TemporalFilterRequest] = Field(default=None, description="时态过滤（Phase 3）")
    graph_expand: Optional[GraphExpandRequest] = Field(default=None, description="图遍历扩展（Phase 3）")
    config_preset: Optional[str] = Field(default=None, description="配置预设: default|fast|accurate（Phase 3）")


class SearchResultItem(BaseModel):
    """搜索结果项"""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = {}
    entities: List[str] = []


class RetrievalConfigRequest(BaseModel):
    """检索配置请求 - Phase 3"""
    # 层开关
    l1_enabled: Optional[bool] = Field(default=None, description="L1 Bloom Filter")
    l2_enabled: Optional[bool] = Field(default=None, description="L2 Temporal Filter")
    l3_enabled: Optional[bool] = Field(default=None, description="L3 Inverted Index")
    l4_enabled: Optional[bool] = Field(default=None, description="L4 Entity Index")
    l5_enabled: Optional[bool] = Field(default=None, description="L5 Graph Traversal")
    l6_enabled: Optional[bool] = Field(default=None, description="L6 N-gram Index")
    l7_enabled: Optional[bool] = Field(default=None, description="L7 Vector Coarse")
    l8_enabled: Optional[bool] = Field(default=None, description="L8 Vector Fine")
    l9_enabled: Optional[bool] = Field(default=None, description="L9 Rerank")
    l10_enabled: Optional[bool] = Field(default=None, description="L10 CrossEncoder")
    l11_enabled: Optional[bool] = Field(default=None, description="L11 LLM Filter")
    # Top-K 配置
    l7_vector_top_k: Optional[int] = Field(default=None, ge=10, le=1000, description="向量粗筛数量")
    final_top_k: Optional[int] = Field(default=None, ge=1, le=100, description="最终返回数量")
    # 预设
    preset: Optional[str] = Field(default=None, description="应用预设: default|fast|accurate")


class RetrievalConfigResponse(BaseModel):
    """检索配置响应 - Phase 3"""
    retriever_type: str = Field(description="检索器类型: ElevenLayer|EightLayer")
    l1_enabled: bool
    l2_enabled: bool
    l3_enabled: bool
    l4_enabled: bool
    l5_enabled: bool
    l6_enabled: bool
    l7_enabled: bool
    l8_enabled: bool
    l9_enabled: bool
    l10_enabled: bool
    l11_enabled: bool
    l7_vector_top_k: int
    final_top_k: int
    weights: Dict[str, float] = {}


class ContextRequest(BaseModel):
    """构建上下文请求"""
    query: str = Field(..., description="当前查询")
    user_id: str = Field(default="default", description="用户ID")
    character_id: str = Field(default="default", description="角色ID")
    max_tokens: int = Field(default=2000, description="最大token数")
    include_recent: int = Field(default=5, description="包含的最近对话数")
    include_core_facts: bool = Field(default=True, description="是否包含核心事实摘要")
    auto_extract_context: bool = Field(default=False, description="是否自动从查询提取持久条件（默认关闭，避免重复提取）")


# ==================== L0 核心设定模型 ====================

class CoreSettingsRequest(BaseModel):
    """L0核心设定请求"""
    character_card: Optional[str] = Field(default=None, description="角色卡（≤2000字）")
    world_setting: Optional[str] = Field(default=None, description="世界观（≤1000字）")
    writing_style: Optional[str] = Field(default=None, description="写作风格要求")
    code_standards: Optional[str] = Field(default=None, description="代码规范")
    project_structure: Optional[str] = Field(default=None, description="项目结构说明")
    naming_conventions: Optional[str] = Field(default=None, description="命名规范")
    absolute_rules: Optional[List[str]] = Field(default=None, description="绝对不能违反的规则")


class CoreSettingsResponse(BaseModel):
    """L0核心设定响应"""
    character_card: str = ""
    world_setting: str = ""
    writing_style: str = ""
    code_standards: str = ""
    project_structure: str = ""
    naming_conventions: str = ""
    user_preferences: Dict[str, Any] = {}
    absolute_rules: List[str] = []
    # 规则检测模式: "llm" = LLM语义检测, "fallback" = 关键词回退检测
    rule_detection_mode: str = "fallback"


class ForeshadowingRequest(BaseModel):
    """伏笔请求"""
    content: str = Field(..., description="伏笔内容")
    user_id: str = Field(default="default", description="用户ID（角色名）")
    character_id: str = Field(default="default", description="角色ID")
    related_entities: Optional[List[str]] = Field(default=None, description="相关实体")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性")


# ==================== 持久条件模型 ====================

class PersistentContextRequest(BaseModel):
    """添加持久条件请求"""
    content: str = Field(..., description="条件内容")
    context_type: str = Field(default="custom", description="条件类型：user_identity, user_goal, user_preference, environment, project, character_trait, world_setting, relationship, assumption, constraint, custom")
    user_id: str = Field(default="default", description="用户ID")
    character_id: str = Field(default="default", description="角色ID")
    keywords: Optional[List[str]] = Field(default=None, description="关键词")


class PersistentContextUpdateRequest(BaseModel):
    """更新持久条件请求"""
    content: Optional[str] = Field(default=None, description="新内容")
    context_type: Optional[str] = Field(default=None, description="新类型")
    confidence: Optional[float] = Field(default=None, ge=0, le=1, description="新置信度")
    keywords: Optional[List[str]] = Field(default=None, description="新关键词")


class PersistentContextItem(BaseModel):
    """持久条件项"""
    id: str
    content: str
    context_type: str
    confidence: float
    is_active: bool
    use_count: int
    created_at: float
    keywords: List[str] = []


class PersistentContextStats(BaseModel):
    """持久条件统计"""
    total: int
    active: int
    by_type: Dict[str, int]
    avg_confidence: float
    oldest_days: float
    limits: Dict[str, int]


class ForeshadowingItem(BaseModel):
    """伏笔项"""
    id: str
    content: str
    status: str
    importance: float
    hints: List[str] = []
    resolution: Optional[str] = None


class ForeshadowingAnalysisRequest(BaseModel):
    """伏笔分析请求"""
    content: str = Field(..., description="对话内容")
    role: str = Field(default="user", description="角色（user/assistant）")
    user_id: str = Field(default="default", description="用户ID（角色名）")
    character_id: str = Field(default="default", description="角色ID")


class ForeshadowingAnalysisResult(BaseModel):
    """伏笔分析结果"""
    triggered: bool = Field(default=False, description="是否触发了分析")
    new_foreshadowings: List[dict] = Field(default=[], description="新检测到的伏笔")
    potentially_resolved: List[dict] = Field(default=[], description="可能已解决的伏笔")
    error: Optional[str] = Field(default=None, description="错误信息")


class ForeshadowingConfigUpdate(BaseModel):
    """伏笔分析器配置更新"""
    llm_enabled: Optional[bool] = Field(default=None, description="启用 LLM 分析")
    trigger_interval: Optional[int] = Field(default=None, ge=1, description="触发间隔（轮次）")
    auto_plant: Optional[bool] = Field(default=None, description="自动埋下伏笔")
    auto_resolve: Optional[bool] = Field(default=None, description="自动解决伏笔")


# ==================== 全局引擎 ====================

_engine: Optional[RecallEngine] = None


def _build_foreshadowing_config():
    """构建伏笔分析器配置（内部辅助函数）
    
    Returns:
        ForeshadowingAnalyzerConfig 或 None
    """
    llm_api_key = os.environ.get('LLM_API_KEY')
    llm_enabled_str = os.environ.get('FORESHADOWING_LLM_ENABLED', 'false').lower()
    llm_enabled = llm_enabled_str in ('true', '1', 'yes')
    
    if llm_api_key and llm_enabled:
        # LLM 已配置且已启用
        from .processor.foreshadowing_analyzer import ForeshadowingAnalyzerConfig
        
        trigger_interval = int(os.environ.get('FORESHADOWING_TRIGGER_INTERVAL', '10'))
        auto_plant_str = os.environ.get('FORESHADOWING_AUTO_PLANT', 'true').lower()
        auto_resolve_str = os.environ.get('FORESHADOWING_AUTO_RESOLVE', 'false').lower()
        
        config = ForeshadowingAnalyzerConfig.llm_based(
            api_key=llm_api_key,
            model=os.environ.get('LLM_MODEL', 'gpt-4o-mini'),
            base_url=os.environ.get('LLM_API_BASE'),
            trigger_interval=trigger_interval,
            auto_plant=auto_plant_str in ('true', '1', 'yes'),
            auto_resolve=auto_resolve_str in ('true', '1', 'yes')
        )
        print(f"[Recall] 伏笔分析器: LLM 模式已启用")
        return config
    else:
        if llm_api_key and not llm_enabled:
            print("[Recall] 伏笔分析器: 手动模式 (LLM 已配置但未启用)")
        else:
            print("[Recall] 伏笔分析器: 手动模式 (未配置 LLM API)")
        return None


def _create_engine():
    """创建引擎实例（内部辅助函数）
    
    Returns:
        RecallEngine 实例
    """
    embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', '').lower()
    foreshadowing_config = _build_foreshadowing_config()
    
    lightweight = (embedding_mode == 'none')
    return RecallEngine(lightweight=lightweight, foreshadowing_config=foreshadowing_config)


def get_engine() -> RecallEngine:
    """获取全局引擎实例
    
    根据环境变量 RECALL_EMBEDDING_MODE 自动选择模式：
    - none: Lite 模式（轻量）
    - local: Local 模式（本地模型）
    - openai: Cloud 模式-OpenAI
    - siliconflow: Cloud 模式-硅基流动
    """
    global _engine
    if _engine is None:
        # 首次启动时加载配置文件
        load_api_keys_from_file()
        _engine = _create_engine()
    return _engine


def reload_engine():
    """重新加载引擎（热更新）
    
    用于在修改配置文件后重新初始化引擎
    """
    global _engine
    
    # 关闭旧引擎
    if _engine is not None:
        try:
            _engine.close()
        except:
            pass
        _engine = None
    
    # 重新加载配置并创建引擎
    load_api_keys_from_file()
    _engine = _create_engine()
    
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print(f"[Recall API] 服务启动 v{__version__}")
    get_engine()  # 预初始化
    
    yield
    
    # 关闭时
    if _engine:
        _engine.close()
    print("[Recall API] 服务关闭")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="Recall API",
    description="Recall - 智能记忆管理系统 API",
    version=__version__,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 健康检查 ====================

@app.get("/", tags=["Health"])
async def root():
    """根路径 - 服务信息"""
    return {
        "service": "Recall API",
        "version": __version__,
        "status": "running"
    }


@app.get("/health", tags=["Health"])
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": time.time()
    }


# ==================== 记忆管理 API ====================

@app.post("/v1/memories", response_model=AddMemoryResponse, tags=["Memories"])
async def add_memory(request: AddMemoryRequest):
    """添加记忆
    
    当保存用户消息时（metadata.role='user'），会自动从内容中提取持久条件。
    这是条件自动提取的正确时机，避免在每次生成时重复提取。
    """
    engine = get_engine()
    
    # 提取 user_id 和 character_id
    user_id = request.user_id
    character_id = request.metadata.get('character_id', 'default') if request.metadata else 'default'
    role = request.metadata.get('role', 'unknown') if request.metadata else 'unknown'
    
    content_preview = request.content[:80].replace('\n', ' ') if len(request.content) > 80 else request.content.replace('\n', ' ')
    print(f"[Recall][Memory] 📥 添加请求: user={user_id}, char={character_id}, role={role}")
    print(f"[Recall][Memory]    内容({len(request.content)}字): {content_preview}{'...' if len(request.content) > 80 else ''}")
    
    result = engine.add(
        content=request.content,
        user_id=request.user_id,
        metadata=request.metadata
    )
    
    # 记录结果（包括去重跳过的情况）
    if result.success:
        print(f"[Recall][Memory] ✅ 保存成功: id={result.id}, entities={result.entities}")
    else:
        print(f"[Recall][Memory] ⏭️ 跳过: {result.message}")
    
    # 【注意】条件提取已移至 /v1/foreshadowing/analyze/turn 端点
    # 与伏笔分析使用相同的触发间隔机制（默认每5轮），避免重复分析相同对话历史
    # 这样确保条件提取能获取完整的对话上下文，而不是只看单条消息
    
    return AddMemoryResponse(
        id=result.id,
        success=result.success,
        entities=result.entities,
        message=result.message,
        consistency_warnings=result.consistency_warnings
    )


@app.post("/v1/memories/search", response_model=List[SearchResultItem], tags=["Memories"])
async def search_memories(request: SearchRequest):
    """搜索记忆
    
    Phase 3 新增参数：
    - temporal_filter: 时态过滤（时间范围）
    - graph_expand: 图遍历扩展（关联实体发现）
    - config_preset: 配置预设（default/fast/accurate）
    """
    query_preview = request.query[:50].replace('\n', ' ') if len(request.query) > 50 else request.query.replace('\n', ' ')
    print(f"[Recall][Memory] 🔍 搜索请求: user={request.user_id}, top_k={request.top_k}")
    print(f"[Recall][Memory]    查询: {query_preview}{'...' if len(request.query) > 50 else ''}")
    
    # Phase 3: 处理新参数
    temporal_context = None
    if request.temporal_filter:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(request.temporal_filter.start) if request.temporal_filter.start else None
            end = datetime.fromisoformat(request.temporal_filter.end) if request.temporal_filter.end else None
            from recall.retrieval.config import TemporalContext
            temporal_context = TemporalContext(start=start, end=end)
            print(f"[Recall][Memory]    时态过滤: {start} ~ {end}")
        except Exception as e:
            print(f"[Recall][Memory]    时态过滤解析失败: {e}")
    
    # Phase 3: 处理图遍历扩展参数（添加到 filters）
    filters = request.filters or {}
    if request.graph_expand and request.graph_expand.center_entities:
        filters['graph_expand'] = {
            'center_entities': request.graph_expand.center_entities,
            'max_depth': request.graph_expand.max_depth,
            'direction': request.graph_expand.direction
        }
        print(f"[Recall][Memory]    图遍历: 实体={request.graph_expand.center_entities}, 深度={request.graph_expand.max_depth}")
    
    # Phase 3: 处理配置预设
    config_preset = None
    if request.config_preset:
        config_preset = request.config_preset
        filters['config_preset'] = request.config_preset
        print(f"[Recall][Memory]    配置预设: {request.config_preset}")
    
    engine = get_engine()
    results = engine.search(
        query=request.query,
        user_id=request.user_id,
        top_k=request.top_k,
        filters=filters,
        temporal_context=temporal_context,
        config_preset=config_preset
    )
    
    print(f"[Recall][Memory] 📊 搜索结果: 找到 {len(results)} 条记忆")
    for i, r in enumerate(results[:3]):  # 只打印前3条
        content_preview = r.content[:40].replace('\n', ' ')
        print(f"[Recall][Memory]    [{i+1}] score={r.score:.3f}: {content_preview}...")
    
    return [
        SearchResultItem(
            id=r.id,
            content=r.content,
            score=r.score,
            metadata=r.metadata,
            entities=r.entities
        )
        for r in results
    ]


@app.get("/v1/memories", tags=["Memories"])
async def list_memories(
    user_id: str = Query(default="default", description="用户ID"),
    limit: int = Query(default=100, ge=1, le=1000, description="限制数量"),
    offset: int = Query(default=0, ge=0, description="偏移量，用于分页")
):
    """获取所有记忆
    
    支持分页：
    - limit: 每页数量
    - offset: 跳过的记录数
    
    示例：
    - 第一页: ?limit=20&offset=0
    - 第二页: ?limit=20&offset=20
    """
    engine = get_engine()
    
    # 使用高效的分页方法，避免加载全部数据
    memories, total_count = engine.get_paginated(
        user_id=user_id,
        offset=offset,
        limit=limit
    )
    
    print(f"[Recall][Memory] 📋 获取列表: user={user_id}, offset={offset}, limit={limit}")
    print(f"[Recall][Memory]    返回 {len(memories)}/{total_count} 条记忆")
    
    return {
        "memories": memories, 
        "count": len(memories),
        "total": total_count,
        "offset": offset,
        "limit": limit
    }


@app.get("/v1/memories/{memory_id}", tags=["Memories"])
async def get_memory(memory_id: str, user_id: str = Query(default="default")):
    """获取单条记忆"""
    engine = get_engine()
    memory = engine.get(memory_id, user_id=user_id)
    
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    
    return memory


@app.delete("/v1/memories/{memory_id}", tags=["Memories"])
async def delete_memory(memory_id: str, user_id: str = Query(default="default")):
    """删除记忆"""
    engine = get_engine()
    success = engine.delete(memory_id, user_id=user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="记忆不存在或删除失败")
    
    return {"success": True, "message": "删除成功"}


@app.delete("/v1/memories", tags=["Memories"])
async def clear_memories(
    user_id: str = Query(..., description="用户ID（角色名），必填"),
    confirm: bool = Query(default=False, description="确认删除，必须为 true")
):
    """清空指定角色的所有记忆
    
    ⚠️ 危险操作！这将删除该角色的全部记忆数据，无法恢复。
    
    使用场景：
    - 删除角色卡后清理对应的记忆数据
    - 重置某个角色的所有记忆
    
    示例:
        DELETE /v1/memories?user_id=角色名&confirm=true
    """
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="请添加 confirm=true 参数确认删除操作"
        )
    
    if user_id == "default":
        raise HTTPException(
            status_code=400,
            detail="不能删除 default 用户的记忆，请指定具体的角色名"
        )
    
    engine = get_engine()
    
    # 使用高效的计数方法获取数量
    count = engine.count_memories(user_id=user_id)
    print(f"[Recall][Memory] 🗑️ 清空请求: user={user_id}, 后端计数={count}")
    
    if count == 0:
        return {"success": True, "message": "该角色没有记忆数据", "deleted_count": 0}
    
    # 清空
    success = engine.clear(user_id=user_id)
    print(f"[Recall][Memory] {'✅' if success else '❌'} 清空完成: user={user_id}, success={success}")
    
    if success:
        return {
            "success": True, 
            "message": f"已清空角色 '{user_id}' 的所有记忆",
            "deleted_count": count
        }
    else:
        raise HTTPException(status_code=500, detail="清空失败")


@app.put("/v1/memories/{memory_id}", tags=["Memories"])
async def update_memory(
    memory_id: str,
    content: str = Body(...),
    user_id: str = Query(default="default"),
    metadata: Optional[Dict[str, Any]] = Body(default=None)
):
    """更新记忆"""
    engine = get_engine()
    success = engine.update(memory_id, content, user_id=user_id, metadata=metadata)
    
    if not success:
        raise HTTPException(status_code=404, detail="记忆不存在或更新失败")
    
    return {"success": True, "message": "更新成功"}


# ==================== L0 核心设定 API ====================

@app.get("/v1/core-settings", response_model=CoreSettingsResponse, tags=["Core Settings"])
async def get_core_settings():
    """获取L0核心设定
    
    返回值中包含 rule_detection_mode 字段:
    - "llm": LLM 语义检测已启用（需配置 LLM_API_KEY）
    - "fallback": 使用关键词回退检测（未配置 LLM 或 LLM 不可用）
    """
    engine = get_engine()
    settings = engine.core_settings
    
    # 判断规则检测模式
    rule_mode = "llm" if (engine.consistency_checker._llm_client is not None) else "fallback"
    
    return CoreSettingsResponse(
        character_card=settings.character_card,
        world_setting=settings.world_setting,
        writing_style=settings.writing_style,
        code_standards=settings.code_standards,
        project_structure=settings.project_structure,
        naming_conventions=settings.naming_conventions,
        user_preferences=settings.user_preferences,
        absolute_rules=settings.absolute_rules,
        rule_detection_mode=rule_mode
    )


@app.put("/v1/core-settings", response_model=CoreSettingsResponse, tags=["Core Settings"])
async def update_core_settings(request: CoreSettingsRequest):
    """更新L0核心设定（部分更新）"""
    engine = get_engine()
    settings = engine.core_settings
    
    # 只更新提供的字段
    if request.character_card is not None:
        settings.character_card = request.character_card
    if request.world_setting is not None:
        settings.world_setting = request.world_setting
    if request.writing_style is not None:
        settings.writing_style = request.writing_style
    if request.code_standards is not None:
        settings.code_standards = request.code_standards
    if request.project_structure is not None:
        settings.project_structure = request.project_structure
    if request.naming_conventions is not None:
        settings.naming_conventions = request.naming_conventions
    if request.absolute_rules is not None:
        settings.absolute_rules = request.absolute_rules
        # 同步更新 ConsistencyChecker 的规则
        engine.consistency_checker.update_rules(request.absolute_rules)
    
    # 保存更新
    settings.save()
    
    # 获取检测模式
    rule_mode = "llm" if engine.consistency_checker._llm_client else "fallback"
    
    return CoreSettingsResponse(
        character_card=settings.character_card,
        world_setting=settings.world_setting,
        writing_style=settings.writing_style,
        code_standards=settings.code_standards,
        project_structure=settings.project_structure,
        naming_conventions=settings.naming_conventions,
        user_preferences=settings.user_preferences,
        absolute_rules=settings.absolute_rules,
        rule_detection_mode=rule_mode
    )


# ==================== 上下文构建 API ====================

@app.post("/v1/context", tags=["Context"])
async def build_context(request: ContextRequest):
    """构建上下文
    
    注意：auto_extract_context 默认为 False，条件提取已改为在保存用户消息时进行。
    如果需要强制提取条件，请显式传入 auto_extract_context=True。
    """
    query_preview = request.query[:60].replace('\n', ' ') if len(request.query) > 60 else request.query.replace('\n', ' ')
    print(f"[Recall][Context] 📦 构建上下文: user={request.user_id}, auto_extract={request.auto_extract_context}")
    print(f"[Recall][Context]    查询: {query_preview}{'...' if len(request.query) > 60 else ''}")
    
    engine = get_engine()
    context = engine.build_context(
        query=request.query,
        user_id=request.user_id,
        character_id=request.character_id,
        max_tokens=request.max_tokens,
        include_recent=request.include_recent,
        include_core_facts=request.include_core_facts,
        auto_extract_context=request.auto_extract_context
    )
    
    print(f"[Recall][Context] ✅ 上下文构建完成: 总长度={len(context)}字符")
    return {"context": context}


# ==================== 持久条件 API ====================

@app.post("/v1/persistent-contexts", response_model=PersistentContextItem, tags=["Persistent Contexts"])
async def add_persistent_context(request: PersistentContextRequest):
    """添加持久条件
    
    持久条件是已确立的背景设定，会在所有后续对话中自动包含。
    例如：用户身份、技术环境、角色设定等。
    """
    from .processor.context_tracker import ContextType
    
    engine = get_engine()
    
    # 转换类型
    try:
        ctx_type = ContextType(request.context_type)
    except ValueError:
        ctx_type = ContextType.CUSTOM
    
    ctx = engine.add_persistent_context(
        content=request.content,
        context_type=ctx_type,
        user_id=request.user_id,
        character_id=request.character_id,
        keywords=request.keywords
    )
    
    # add_persistent_context 返回 PersistentContext 对象
    return PersistentContextItem(
        id=ctx.id,
        content=ctx.content,
        context_type=ctx.context_type.value,
        confidence=ctx.confidence,
        is_active=ctx.is_active,
        use_count=ctx.use_count,
        created_at=ctx.created_at,
        keywords=ctx.keywords
    )


@app.get("/v1/persistent-contexts", response_model=List[PersistentContextItem], tags=["Persistent Contexts"])
async def list_persistent_contexts(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID"),
    context_type: Optional[str] = Query(default=None, description="按类型过滤")
):
    """获取所有活跃的持久条件"""
    engine = get_engine()
    contexts = engine.get_persistent_contexts(user_id, character_id)
    
    # 按类型过滤
    if context_type:
        contexts = [c for c in contexts if c['context_type'] == context_type]
    
    print(f"[Recall][Context] 📋 获取条件列表: user={user_id}, char={character_id}")
    print(f"[Recall][Context]    活跃条件: {len(contexts)} 条")
    if contexts:
        types_summary = {}
        for c in contexts:
            t = c.get('context_type', 'unknown')
            types_summary[t] = types_summary.get(t, 0) + 1
        print(f"[Recall][Context]    类型分布: {types_summary}")
    
    return [
        PersistentContextItem(
            id=c['id'],
            content=c['content'],
            context_type=c['context_type'],
            confidence=c['confidence'],
            is_active=c['is_active'],
            use_count=c['use_count'],
            created_at=c['created_at'],
            keywords=c.get('keywords', [])
        )
        for c in contexts
    ]


# 注意：固定路径必须在参数路径之前定义，否则 /stats 会被当作 {context_id}

@app.get("/v1/persistent-contexts/stats", response_model=PersistentContextStats, tags=["Persistent Contexts"])
async def get_persistent_context_stats(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """获取持久条件统计信息"""
    engine = get_engine()
    stats = engine.context_tracker.get_stats(user_id, character_id)
    return PersistentContextStats(**stats)


@app.post("/v1/persistent-contexts/consolidate", tags=["Persistent Contexts"])
async def consolidate_contexts(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID"),
    force: bool = Query(default=False, description="是否强制执行（不管数量是否超过阈值）")
):
    """压缩合并持久条件
    
    当持久条件数量过多时，智能合并相似的条件。
    如果配置了LLM，会使用LLM进行智能压缩。
    """
    engine = get_engine()
    result = engine.consolidate_persistent_contexts(user_id, character_id, force)
    return result


@app.post("/v1/persistent-contexts/extract", tags=["Persistent Contexts"])
async def extract_contexts_from_text(
    text: str = Body(..., embed=True, description="要分析的文本"),
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """从文本中自动提取持久条件
    
    使用 LLM（如果可用）或规则从文本中提取应该持久化的条件。
    """
    engine = get_engine()
    contexts = engine.extract_contexts_from_text(text, user_id, character_id)
    return {
        "extracted": len(contexts),
        "contexts": contexts
    }


@app.delete("/v1/persistent-contexts/{context_id}", tags=["Persistent Contexts"])
async def remove_persistent_context(
    context_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """停用持久条件"""
    engine = get_engine()
    success = engine.remove_persistent_context(context_id, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="持久条件不存在")
    
    return {"success": True, "message": "持久条件已停用"}


@app.delete("/v1/persistent-contexts", tags=["Persistent Contexts"])
async def clear_all_persistent_contexts(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """清空当前角色的所有持久条件"""
    engine = get_engine()
    
    # 获取所有活跃条件
    contexts = engine.get_persistent_contexts(user_id, character_id)
    count = len(contexts)
    
    # 逐个删除
    for ctx in contexts:
        engine.remove_persistent_context(ctx['id'], user_id, character_id)
    
    print(f"[Recall][Context] 🗑️ 清空条件: user={user_id}, char={character_id}, 删除={count}条")
    return {"success": True, "message": f"已清空 {count} 个持久条件", "count": count}


@app.post("/v1/persistent-contexts/{context_id}/used", tags=["Persistent Contexts"])
async def mark_context_used(
    context_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """标记持久条件已使用
    
    调用此接口可以更新条件的使用时间和使用次数，
    这对于置信度衰减机制很重要。
    """
    engine = get_engine()
    engine.context_tracker.mark_used(context_id, user_id, character_id)
    return {"success": True, "message": "已标记使用"}


@app.get("/v1/persistent-contexts/archived", tags=["Persistent Contexts"])
async def list_archived_contexts(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
    context_type: Optional[str] = Query(default=None, description="类型筛选")
):
    """获取归档的持久条件列表（分页、搜索、筛选）"""
    engine = get_engine()
    result = engine.context_tracker.get_archived_contexts(
        user_id=user_id,
        character_id=character_id,
        page=page,
        page_size=page_size,
        search=search,
        context_type=context_type
    )
    return result


@app.post("/v1/persistent-contexts/{context_id}/restore", tags=["Persistent Contexts"])
async def restore_context_from_archive(
    context_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """从归档恢复持久条件到活跃列表"""
    engine = get_engine()
    ctx = engine.context_tracker.restore_from_archive(context_id, user_id, character_id)
    
    if not ctx:
        raise HTTPException(status_code=404, detail="归档条件不存在")
    
    return {
        "success": True,
        "message": "已恢复条件",
        "context": {
            "id": ctx.id,
            "content": ctx.content,
            "context_type": ctx.context_type.value,
            "confidence": ctx.confidence
        }
    }


@app.delete("/v1/persistent-contexts/archived/{context_id}", tags=["Persistent Contexts"])
async def delete_archived_context(
    context_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """彻底删除归档中的持久条件"""
    engine = get_engine()
    success = engine.context_tracker.delete_archived(context_id, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="归档条件不存在")
    
    return {"success": True, "message": "已彻底删除归档条件"}


@app.delete("/v1/persistent-contexts/archived", tags=["Persistent Contexts"])
async def clear_all_archived_contexts(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """清空所有归档的持久条件"""
    engine = get_engine()
    count = engine.context_tracker.clear_archived(user_id, character_id)
    return {"success": True, "message": f"已清空 {count} 个归档条件", "count": count}


@app.post("/v1/persistent-contexts/{context_id}/archive", tags=["Persistent Contexts"])
async def archive_context(
    context_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """手动将活跃条件归档"""
    engine = get_engine()
    success = engine.context_tracker.archive_context(context_id, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="条件不存在")
    
    return {"success": True, "message": "已归档条件"}


@app.put("/v1/persistent-contexts/{context_id}", tags=["Persistent Contexts"])
async def update_persistent_context(
    context_id: str,
    request: PersistentContextUpdateRequest,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """编辑持久条件的字段"""
    engine = get_engine()
    ctx = engine.context_tracker.update_context(
        context_id=context_id,
        user_id=user_id,
        character_id=character_id,
        content=request.content,
        context_type=request.context_type,
        confidence=request.confidence,
        keywords=request.keywords
    )
    
    if not ctx:
        raise HTTPException(status_code=404, detail="条件不存在")
    
    return {
        "success": True,
        "message": "已更新条件",
        "context": {
            "id": ctx.id,
            "content": ctx.content,
            "context_type": ctx.context_type.value,
            "confidence": ctx.confidence,
            "keywords": ctx.keywords
        }
    }


# ==================== 伏笔 API ====================

@app.post("/v1/foreshadowing", response_model=ForeshadowingItem, tags=["Foreshadowing"])
async def plant_foreshadowing(request: ForeshadowingRequest):
    """埋下伏笔"""
    engine = get_engine()
    fsh = engine.plant_foreshadowing(
        content=request.content,
        user_id=request.user_id,
        character_id=request.character_id,
        related_entities=request.related_entities,
        importance=request.importance
    )
    return ForeshadowingItem(
        id=fsh.id,
        content=fsh.content,
        status=fsh.status.value,
        importance=fsh.importance,
        hints=fsh.hints,
        resolution=fsh.resolution
    )


@app.get("/v1/foreshadowing", response_model=List[ForeshadowingItem], tags=["Foreshadowing"])
async def list_foreshadowing(
    user_id: str = Query(default="default", description="用户ID（角色名）"),
    character_id: str = Query(default="default", description="角色ID")
):
    """获取活跃伏笔"""
    engine = get_engine()
    active = engine.get_active_foreshadowings(user_id, character_id)
    print(f"[Recall][Foreshadow] 📋 获取伏笔列表: user={user_id}, char={character_id}")
    print(f"[Recall][Foreshadow]    活跃伏笔: {len(active)} 条")
    if active:
        status_summary = {}
        for f in active:
            s = f.status.value
            status_summary[s] = status_summary.get(s, 0) + 1
        print(f"[Recall][Foreshadow]    状态分布: {status_summary}")
        for i, f in enumerate(active[:3]):
            preview = f.content[:40].replace('\n', ' ')
            print(f"[Recall][Foreshadow]    [{i+1}] {f.status.value}: {preview}...")
    return [
        ForeshadowingItem(
            id=f.id,
            content=f.content,
            status=f.status.value,
            importance=f.importance,
            hints=f.hints,
            resolution=f.resolution
        )
        for f in active
    ]


@app.post("/v1/foreshadowing/{foreshadowing_id}/resolve", tags=["Foreshadowing"])
async def resolve_foreshadowing(
    foreshadowing_id: str,
    resolution: str = Body(..., embed=True),
    user_id: str = Query(default="default", description="用户ID（角色名）"),
    character_id: str = Query(default="default", description="角色ID")
):
    """解决伏笔"""
    engine = get_engine()
    success = engine.resolve_foreshadowing(foreshadowing_id, resolution, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    
    return {"success": True, "message": "伏笔已解决"}


@app.post("/v1/foreshadowing/{foreshadowing_id}/hint", tags=["Foreshadowing"])
async def add_foreshadowing_hint(
    foreshadowing_id: str,
    hint: str = Body(..., embed=True, description="提示内容"),
    user_id: str = Query(default="default", description="用户ID（角色名）"),
    character_id: str = Query(default="default", description="角色ID")
):
    """添加伏笔提示
    
    为伏笔添加进展提示，会将状态从 PLANTED 更新为 DEVELOPING
    """
    engine = get_engine()
    success = engine.add_foreshadowing_hint(foreshadowing_id, hint, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    
    return {"success": True, "message": "提示已添加"}


@app.delete("/v1/foreshadowing/{foreshadowing_id}", tags=["Foreshadowing"])
async def abandon_foreshadowing(
    foreshadowing_id: str,
    user_id: str = Query(default="default", description="用户ID（角色名）"),
    character_id: str = Query(default="default", description="角色ID")
):
    """放弃/删除伏笔
    
    将伏笔标记为已放弃状态（不会物理删除，保留历史记录）
    """
    engine = get_engine()
    success = engine.abandon_foreshadowing(foreshadowing_id, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    
    return {"success": True, "message": "伏笔已放弃"}


@app.delete("/v1/foreshadowing", tags=["Foreshadowing"])
async def clear_all_foreshadowings(
    user_id: str = Query(default="default", description="用户ID（角色名）"),
    character_id: str = Query(default="default", description="角色ID")
):
    """清空当前角色的所有伏笔"""
    engine = get_engine()
    
    # 获取所有活跃伏笔
    foreshadowings = engine.get_foreshadowings(user_id, character_id)
    count = len(foreshadowings)
    
    # 逐个放弃
    for f in foreshadowings:
        engine.abandon_foreshadowing(f['id'], user_id, character_id)
    
    print(f"[Recall][Foreshadow] 🗑️ 清空伏笔: user={user_id}, char={character_id}, 删除={count}条")
    return {"success": True, "message": f"已清空 {count} 个伏笔", "count": count}


@app.get("/v1/foreshadowing/archived", tags=["Foreshadowing"])
async def list_archived_foreshadowings(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
    status: Optional[str] = Query(default=None, description="状态筛选（resolved/abandoned）")
):
    """获取归档的伏笔列表（分页、搜索、筛选）"""
    engine = get_engine()
    result = engine.foreshadowing_tracker.get_archived_foreshadowings(
        user_id=user_id,
        character_id=character_id,
        page=page,
        page_size=page_size,
        search=search,
        status=status
    )
    return result


@app.post("/v1/foreshadowing/{foreshadowing_id}/restore", tags=["Foreshadowing"])
async def restore_foreshadowing_from_archive(
    foreshadowing_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """从归档恢复伏笔到活跃列表"""
    engine = get_engine()
    fsh = engine.foreshadowing_tracker.restore_from_archive(foreshadowing_id, user_id, character_id)
    
    if not fsh:
        raise HTTPException(status_code=404, detail="归档伏笔不存在")
    
    return {
        "success": True,
        "message": "已恢复伏笔",
        "foreshadowing": {
            "id": fsh.id,
            "content": fsh.content,
            "status": fsh.status.value,
            "importance": fsh.importance
        }
    }


@app.delete("/v1/foreshadowing/archived/{foreshadowing_id}", tags=["Foreshadowing"])
async def delete_archived_foreshadowing(
    foreshadowing_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """彻底删除归档中的伏笔"""
    engine = get_engine()
    success = engine.foreshadowing_tracker.delete_archived(foreshadowing_id, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="归档伏笔不存在")
    
    return {"success": True, "message": "已彻底删除归档伏笔"}


@app.delete("/v1/foreshadowing/archived", tags=["Foreshadowing"])
async def clear_all_archived_foreshadowings(
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """清空所有归档的伏笔"""
    engine = get_engine()
    count = engine.foreshadowing_tracker.clear_archived(user_id, character_id)
    return {"success": True, "message": f"已清空 {count} 个归档伏笔", "count": count}


@app.post("/v1/foreshadowing/{foreshadowing_id}/archive", tags=["Foreshadowing"])
async def archive_foreshadowing_manually(
    foreshadowing_id: str,
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """手动将活跃伏笔归档"""
    engine = get_engine()
    success = engine.foreshadowing_tracker.archive_foreshadowing(foreshadowing_id, user_id, character_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    
    return {"success": True, "message": "已归档伏笔"}


@app.put("/v1/foreshadowing/{foreshadowing_id}", tags=["Foreshadowing"])
async def update_foreshadowing(
    foreshadowing_id: str,
    content: Optional[str] = Body(default=None, description="新内容"),
    status: Optional[str] = Body(default=None, description="新状态"),
    importance: Optional[float] = Body(default=None, ge=0, le=1, description="新重要性"),
    hints: Optional[List[str]] = Body(default=None, description="新提示列表"),
    resolution: Optional[str] = Body(default=None, description="解决方案"),
    user_id: str = Query(default="default", description="用户ID"),
    character_id: str = Query(default="default", description="角色ID")
):
    """编辑伏笔的字段"""
    engine = get_engine()
    fsh = engine.foreshadowing_tracker.update_foreshadowing(
        foreshadowing_id=foreshadowing_id,
        user_id=user_id,
        character_id=character_id,
        content=content,
        status=status,
        importance=importance,
        hints=hints,
        resolution=resolution
    )
    
    if not fsh:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    
    return {
        "success": True,
        "message": "已更新伏笔",
        "foreshadowing": {
            "id": fsh.id,
            "content": fsh.content,
            "status": fsh.status.value,
            "importance": fsh.importance,
            "hints": fsh.hints,
            "resolution": fsh.resolution
        }
    }


# ==================== 伏笔分析 API ====================

# 后台分析任务集合（防止被垃圾回收）
_background_analysis_tasks: set = set()


async def _background_foreshadowing_analysis(engine: RecallEngine, content: str, role: str, user_id: str, character_id: str):
    """后台异步执行伏笔分析和条件提取
    
    这个函数在后台运行，不阻塞 API 响应。
    使用引擎的异步分析方法来避免阻塞事件循环。
    设置 60 秒超时，防止 LLM 调用卡住导致线程池耗尽。
    
    同时触发：
    1. 伏笔分析（ForeshadowingAnalyzer.on_turn）
    2. 条件提取（ContextTracker.on_turn）
    
    两者使用相同的触发间隔机制，避免重复分析相同对话历史。
    """
    try:
        content_preview = content[:60].replace('\n', ' ') if len(content) > 60 else content.replace('\n', ' ')
        print(f"[Recall][Analysis] 🔄 后台分析: user={user_id}, role={role}")
        print(f"[Recall][Analysis]    内容({len(content)}字): {content_preview}{'...' if len(content) > 60 else ''}")
        
        loop = asyncio.get_event_loop()
        
        # 1. 伏笔分析
        foreshadow_result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: engine.on_foreshadowing_turn(
                    content=content,
                    role=role,
                    user_id=user_id,
                    character_id=character_id
                )
            ),
            timeout=60.0
        )
        if foreshadow_result.triggered:
            print(f"[Recall][Foreshadow] ✅ 分析完成: 新伏笔={len(foreshadow_result.new_foreshadowings)}, 可能解决={len(foreshadow_result.potentially_resolved)}")
            for f in foreshadow_result.new_foreshadowings[:2]:
                print(f"[Recall][Foreshadow]    🌱 新伏笔: {f[:50]}..." if len(f) > 50 else f"[Recall][Foreshadow]    🌱 新伏笔: {f}")
        else:
            print(f"[Recall][Foreshadow] ⏭️ 未达触发条件")
        if foreshadow_result.error:
            print(f"[Recall][Foreshadow] ⚠️ 警告: {foreshadow_result.error}")
        
        # 2. 条件提取（使用同样的触发间隔机制）
        try:
            context_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: engine.context_tracker.on_turn(user_id, character_id)
                ),
                timeout=60.0
            )
            if context_result.get('triggered'):
                print(f"[Recall][Context] ✅ 提取完成: 新条件={context_result.get('extracted_count', 0)}")
                for ctx in context_result.get('extracted', [])[:3]:
                    print(f"[Recall][Context]    🌱 [{ctx['type']}] {ctx['content'][:40]}..." if len(ctx['content']) > 40 else f"[Recall][Context]    🌱 [{ctx['type']}] {ctx['content']}")
            else:
                turns_left = context_result.get('turns_until_next', '?')
                print(f"[Recall][Context] ⏭️ 未达触发条件 (还需 {turns_left} 轮)")
        except Exception as e:
            print(f"[Recall][Context] ⚠️ 条件提取失败: {e}")
            
    except asyncio.TimeoutError:
        print(f"[Recall][Analysis] ⏱️ 分析超时 (>60s)")
    except Exception as e:
        print(f"[Recall][Analysis] ❌ 分析失败: {e}")


@app.post("/v1/foreshadowing/analyze/turn", response_model=ForeshadowingAnalysisResult, tags=["Foreshadowing Analysis"])
async def analyze_foreshadowing_turn(request: ForeshadowingAnalysisRequest):
    """处理新的一轮对话（用于伏笔分析）
    
    【非阻塞】: 立即返回响应，分析在后台异步执行。
    客户端不需要等待 LLM 分析完成。
    
    在每轮对话后调用此端点，分析器会根据配置决定是否触发分析：
    - 手动模式：不做任何操作，返回空结果
    - LLM模式：累积对话，达到触发条件时在后台自动分析
    """
    engine = get_engine()
    
    # 创建后台任务执行分析（不等待结果）
    task = asyncio.create_task(
        _background_foreshadowing_analysis(
            engine=engine,
            content=request.content,
            role=request.role,
            user_id=request.user_id,
            character_id=request.character_id
        )
    )
    
    # 保存任务引用防止被垃圾回收
    _background_analysis_tasks.add(task)
    task.add_done_callback(_background_analysis_tasks.discard)
    
    # 立即返回，不等待分析完成
    return ForeshadowingAnalysisResult(
        triggered=False,  # 实际触发状态在后台处理
        new_foreshadowings=[],
        potentially_resolved=[],
        error=None
    )


@app.post("/v1/foreshadowing/analyze/trigger", response_model=ForeshadowingAnalysisResult, tags=["Foreshadowing Analysis"])
async def trigger_foreshadowing_analysis(
    user_id: str = Query(default="default", description="用户ID（角色名）"),
    character_id: str = Query(default="default", description="角色ID")
):
    """手动触发伏笔分析
    
    强制触发 LLM 分析（如果已配置）。可以在任何时候调用。
    """
    engine = get_engine()
    result = engine.trigger_foreshadowing_analysis(user_id, character_id)
    return ForeshadowingAnalysisResult(
        triggered=result.triggered,
        new_foreshadowings=result.new_foreshadowings,
        potentially_resolved=result.potentially_resolved,
        error=result.error
    )


@app.get("/v1/foreshadowing/analyzer/config", tags=["Foreshadowing Analysis"])
async def get_foreshadowing_analyzer_config():
    """获取伏笔分析器配置
    
    配置项：
    - llm_enabled: 是否启用 LLM 分析
    - trigger_interval: 触发间隔
    - auto_plant: 自动埋伏笔
    - auto_resolve: 自动解决伏笔
    - llm_configured: LLM API 是否已配置（只读）
    """
    engine = get_engine()
    analyzer_config = engine.get_foreshadowing_analyzer_config()
    
    # 检查实际的分析器状态（backend == 'llm' 表示 LLM 模式已启用）
    actual_backend = analyzer_config.get('backend', 'manual')
    llm_enabled = (actual_backend == 'llm')
    
    # 检查 LLM API 是否已配置
    llm_api_key = os.environ.get('LLM_API_KEY', '')
    llm_configured = bool(llm_api_key)
    
    return {
        "success": True,
        "config": {
            "llm_enabled": llm_enabled,
            "llm_configured": llm_configured,
            "trigger_interval": analyzer_config.get('trigger_interval', 10),
            "auto_plant": analyzer_config.get('auto_plant', True),
            "auto_resolve": analyzer_config.get('auto_resolve', True),
            "backend": actual_backend,
            "llm_model": analyzer_config.get('llm_model', '')
        }
    }


@app.put("/v1/foreshadowing/analyzer/config", tags=["Foreshadowing Analysis"])
async def update_foreshadowing_analyzer_config(config: ForeshadowingConfigUpdate):
    """更新伏笔分析器配置
    
    配置会同时保存到：
    1. 内存中的分析器实例
    2. api_keys.env 配置文件（持久化）
    
    无需重启服务，配置立即生效。
    """
    engine = get_engine()
    
    # 准备要更新到配置文件的内容
    config_updates = {}
    llm_enable_error = None  # 记录 LLM 启用失败的错误
    
    # 处理 LLM 启用开关
    if config.llm_enabled is not None:
        config_updates['FORESHADOWING_LLM_ENABLED'] = 'true' if config.llm_enabled else 'false'
        
        # 动态切换分析器模式
        if config.llm_enabled:
            # 启用 LLM 模式
            llm_api_key = os.environ.get('LLM_API_KEY')
            if llm_api_key:
                engine.enable_foreshadowing_llm_mode(
                    api_key=llm_api_key,
                    model=os.environ.get('LLM_MODEL', 'gpt-4o-mini'),
                    base_url=os.environ.get('LLM_API_BASE')
                )
            else:
                # 记录错误但继续处理其他配置
                llm_enable_error = "无法启用 LLM 模式：未配置 LLM API Key"
                del config_updates['FORESHADOWING_LLM_ENABLED']  # 不保存失败的配置
        else:
            # 禁用 LLM 模式，切换到手动模式
            engine.disable_foreshadowing_llm_mode()
    
    # 处理其他配置（即使 LLM 启用失败也继续处理）
    if config.trigger_interval is not None:
        config_updates['FORESHADOWING_TRIGGER_INTERVAL'] = str(config.trigger_interval)
    if config.auto_plant is not None:
        config_updates['FORESHADOWING_AUTO_PLANT'] = 'true' if config.auto_plant else 'false'
    if config.auto_resolve is not None:
        config_updates['FORESHADOWING_AUTO_RESOLVE'] = 'true' if config.auto_resolve else 'false'
    
    # 更新内存中的分析器配置
    engine.update_foreshadowing_analyzer_config(
        trigger_interval=config.trigger_interval,
        auto_plant=config.auto_plant,
        auto_resolve=config.auto_resolve
    )
    
    # 保存到配置文件
    if config_updates:
        save_config_to_file(config_updates)
    
    # 如果 LLM 启用失败，返回部分成功的响应
    if llm_enable_error:
        return {
            "success": False, 
            "message": llm_enable_error,
            "partial_success": True,  # 表示其他配置已保存
            "config": (await get_foreshadowing_analyzer_config())["config"]
        }
    
    return {"success": True, "config": (await get_foreshadowing_analyzer_config())["config"]}


# ==================== v4.0 时态知识图谱 API ====================

class TemporalQueryRequest(BaseModel):
    """时态查询请求"""
    entity_name: str = Field(..., description="实体名称")
    timestamp: Optional[str] = Field(None, description="查询时间点 (ISO 格式)")
    user_id: str = Field(default="default", description="用户ID")


class TemporalRangeRequest(BaseModel):
    """时态范围查询请求"""
    entity_name: str = Field(..., description="实体名称")
    start_time: Optional[str] = Field(None, description="开始时间 (ISO 格式)")
    end_time: Optional[str] = Field(None, description="结束时间 (ISO 格式)")
    user_id: str = Field(default="default", description="用户ID")


@app.post("/v1/temporal/at", tags=["Temporal"])
async def get_facts_at_time(request: TemporalQueryRequest):
    """获取实体在特定时间点的事实
    
    查询某个实体在指定时间点的状态/属性值。
    如果不指定时间，返回最新状态。
    """
    engine = get_engine()
    
    # 检查是否启用了时态图谱
    if not hasattr(engine, 'temporal_graph') or engine.temporal_graph is None:
        return {
            "success": False,
            "error": "时态知识图谱未启用",
            "facts": []
        }
    
    try:
        from datetime import datetime
        timestamp = None
        if request.timestamp:
            timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
        
        facts = engine.temporal_graph.get_facts_at_time(
            entity_name=request.entity_name,
            timestamp=timestamp
        )
        
        return {
            "success": True,
            "entity": request.entity_name,
            "timestamp": request.timestamp,
            "facts": [
                {
                    "attribute": f.attribute,
                    "value": f.value,
                    "valid_from": f.valid_from.isoformat() if f.valid_from else None,
                    "valid_to": f.valid_to.isoformat() if f.valid_to else None,
                    "source_turn": f.source_turn,
                    "confidence": f.confidence
                }
                for f in facts
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "facts": []
        }


@app.post("/v1/temporal/range", tags=["Temporal"])
async def get_facts_in_range(request: TemporalRangeRequest):
    """获取实体在时间范围内的所有事实变化
    
    查询某个实体在指定时间范围内的所有状态变化历史。
    """
    engine = get_engine()
    
    if not hasattr(engine, 'temporal_graph') or engine.temporal_graph is None:
        return {
            "success": False,
            "error": "时态知识图谱未启用",
            "timeline": []
        }
    
    try:
        from datetime import datetime
        start = None
        end = None
        
        if request.start_time:
            start = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
        if request.end_time:
            end = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))
        
        timeline = engine.temporal_graph.get_entity_timeline(
            entity_name=request.entity_name,
            start_time=start,
            end_time=end
        )
        
        return {
            "success": True,
            "entity": request.entity_name,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "timeline": timeline
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timeline": []
        }


@app.get("/v1/temporal/timeline/{entity_name}", tags=["Temporal"])
async def get_entity_timeline(
    entity_name: str,
    user_id: str = Query(default="default", description="用户ID"),
    limit: int = Query(default=50, ge=1, le=200, description="返回数量")
):
    """获取实体的完整时间线
    
    返回实体的所有属性变化历史，按时间排序。
    """
    engine = get_engine()
    
    if not hasattr(engine, 'temporal_graph') or engine.temporal_graph is None:
        return {
            "success": False,
            "error": "时态知识图谱未启用",
            "timeline": []
        }
    
    try:
        timeline = engine.temporal_graph.get_entity_timeline(
            entity_name=entity_name,
            limit=limit
        )
        
        return {
            "success": True,
            "entity": entity_name,
            "timeline": timeline,
            "count": len(timeline)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timeline": []
        }


@app.get("/v1/temporal/stats", tags=["Temporal"])
async def get_temporal_stats(user_id: str = Query(default="default", description="用户ID")):
    """获取时态图谱统计信息"""
    engine = get_engine()
    
    if not hasattr(engine, 'temporal_graph') or engine.temporal_graph is None:
        return {
            "success": False,
            "error": "时态知识图谱未启用",
            "stats": {}
        }
    
    try:
        stats = engine.temporal_graph.get_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stats": {}
        }


class SnapshotResponse(BaseModel):
    """快照响应"""
    success: bool
    snapshot_id: Optional[str] = None
    timestamp: Optional[str] = None
    entities: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


@app.post("/v1/temporal/snapshot", tags=["Temporal"])
async def create_snapshot(
    user_id: str = Query(default="default", description="用户ID"),
    description: str = Query(default="", description="快照描述")
):
    """创建知识图谱快照
    
    保存当前时刻的知识图谱状态，用于后续比较或恢复。
    """
    engine = get_engine()
    
    if not hasattr(engine, 'temporal_graph') or engine.temporal_graph is None:
        return {
            "success": False,
            "error": "时态知识图谱未启用"
        }
    
    try:
        # 创建快照
        import time
        snapshot_id = f"snap_{int(time.time() * 1000)}"
        timestamp = datetime.now().isoformat()
        
        # 获取当前所有实体状态
        if hasattr(engine.temporal_graph, 'create_snapshot'):
            snapshot = engine.temporal_graph.create_snapshot(
                snapshot_id=snapshot_id,
                description=description
            )
            return {
                "success": True,
                "snapshot_id": snapshot.get('id', snapshot_id),
                "timestamp": snapshot.get('timestamp', timestamp),
                "entity_count": snapshot.get('entity_count', 0),
                "description": description
            }
        else:
            # 回退方案：记录当前状态
            return {
                "success": True,
                "snapshot_id": snapshot_id,
                "timestamp": timestamp,
                "description": description,
                "note": "快照功能需要 TemporalKnowledgeGraph 支持"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/v1/temporal/snapshot/compare", tags=["Temporal"])
async def compare_snapshots(
    snapshot_id_1: str = Query(..., description="第一个快照ID"),
    snapshot_id_2: str = Query(..., description="第二个快照ID（可选，默认与当前状态比较）"),
    user_id: str = Query(default="default", description="用户ID")
):
    """比较两个快照之间的差异
    
    返回两个时间点之间知识图谱的变化：新增、修改、删除的实体和属性。
    """
    engine = get_engine()
    
    if not hasattr(engine, 'temporal_graph') or engine.temporal_graph is None:
        return {
            "success": False,
            "error": "时态知识图谱未启用"
        }
    
    try:
        if hasattr(engine.temporal_graph, 'compare_snapshots'):
            diff = engine.temporal_graph.compare_snapshots(
                snapshot_id_1=snapshot_id_1,
                snapshot_id_2=snapshot_id_2
            )
            return {
                "success": True,
                "snapshot_1": snapshot_id_1,
                "snapshot_2": snapshot_id_2,
                "diff": diff
            }
        else:
            return {
                "success": False,
                "error": "快照比较功能需要 TemporalKnowledgeGraph 支持",
                "snapshot_1": snapshot_id_1,
                "snapshot_2": snapshot_id_2
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ==================== v4.0 矛盾检测与管理 API ====================

class ContradictionItem(BaseModel):
    """矛盾项"""
    id: str
    fact1: Dict[str, Any]
    fact2: Dict[str, Any]
    contradiction_type: str
    detected_at: str
    status: str
    resolution: Optional[str] = None


class ResolveContradictionRequest(BaseModel):
    """解决矛盾请求"""
    strategy: str = Field(..., description="解决策略: KEEP_NEWER/KEEP_OLDER/KEEP_BOTH/MANUAL")
    manual_resolution: Optional[str] = Field(None, description="手动解决说明（strategy=MANUAL 时使用）")


@app.get("/v1/contradictions", tags=["Contradictions"])
async def list_contradictions(
    user_id: str = Query(default="default", description="用户ID"),
    status: str = Query(default="pending", description="状态: pending/resolved/all"),
    limit: int = Query(default=50, ge=1, le=200, description="返回数量")
):
    """获取矛盾列表
    
    返回检测到的所有矛盾，可按状态过滤。
    """
    engine = get_engine()
    
    if not hasattr(engine, 'contradiction_manager') or engine.contradiction_manager is None:
        return {
            "success": False,
            "error": "矛盾管理器未启用",
            "contradictions": []
        }
    
    try:
        contradictions = engine.contradiction_manager.get_contradictions(
            status=status if status != "all" else None,
            limit=limit
        )
        
        return {
            "success": True,
            "contradictions": [
                {
                    "id": c.id,
                    "fact1": c.fact1,
                    "fact2": c.fact2,
                    "contradiction_type": c.contradiction_type.value if hasattr(c.contradiction_type, 'value') else str(c.contradiction_type),
                    "detected_at": c.detected_at.isoformat() if hasattr(c.detected_at, 'isoformat') else str(c.detected_at),
                    "status": c.status,
                    "resolution": c.resolution
                }
                for c in contradictions
            ],
            "count": len(contradictions)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "contradictions": []
        }


@app.get("/v1/contradictions/{contradiction_id}", tags=["Contradictions"])
async def get_contradiction(contradiction_id: str):
    """获取单个矛盾详情"""
    engine = get_engine()
    
    if not hasattr(engine, 'contradiction_manager') or engine.contradiction_manager is None:
        raise HTTPException(status_code=503, detail="矛盾管理器未启用")
    
    try:
        contradiction = engine.contradiction_manager.get_contradiction(contradiction_id)
        if not contradiction:
            raise HTTPException(status_code=404, detail="矛盾不存在")
        
        return {
            "success": True,
            "contradiction": {
                "id": contradiction.id,
                "fact1": contradiction.fact1,
                "fact2": contradiction.fact2,
                "contradiction_type": contradiction.contradiction_type.value if hasattr(contradiction.contradiction_type, 'value') else str(contradiction.contradiction_type),
                "detected_at": contradiction.detected_at.isoformat() if hasattr(contradiction.detected_at, 'isoformat') else str(contradiction.detected_at),
                "status": contradiction.status,
                "resolution": contradiction.resolution
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/contradictions/{contradiction_id}/resolve", tags=["Contradictions"])
async def resolve_contradiction(
    contradiction_id: str,
    request: ResolveContradictionRequest
):
    """解决矛盾
    
    策略:
    - KEEP_NEWER: 保留较新的事实
    - KEEP_OLDER: 保留较旧的事实
    - KEEP_BOTH: 保留两者（标记为已处理但不删除）
    - MANUAL: 手动提供解决方案
    """
    engine = get_engine()
    
    if not hasattr(engine, 'contradiction_manager') or engine.contradiction_manager is None:
        raise HTTPException(status_code=503, detail="矛盾管理器未启用")
    
    try:
        result = engine.contradiction_manager.resolve_contradiction(
            contradiction_id=contradiction_id,
            strategy=request.strategy,
            manual_resolution=request.manual_resolution
        )
        
        return {
            "success": result.success if hasattr(result, 'success') else True,
            "message": result.message if hasattr(result, 'message') else "矛盾已解决",
            "resolution": result.resolution if hasattr(result, 'resolution') else request.strategy
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/contradictions/stats", tags=["Contradictions"])
async def get_contradiction_stats(user_id: str = Query(default="default", description="用户ID")):
    """获取矛盾统计信息"""
    engine = get_engine()
    
    if not hasattr(engine, 'contradiction_manager') or engine.contradiction_manager is None:
        return {
            "success": False,
            "error": "矛盾管理器未启用",
            "stats": {}
        }
    
    try:
        stats = engine.contradiction_manager.get_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "stats": {}
        }


# ==================== v4.0 全文检索 API ====================

class FulltextSearchRequest(BaseModel):
    """全文检索请求"""
    query: str = Field(..., description="搜索查询")
    user_id: str = Field(default="default", description="用户ID")
    top_k: int = Field(default=10, ge=1, le=100, description="返回数量")


@app.post("/v1/search/fulltext", tags=["Search"])
async def fulltext_search(request: FulltextSearchRequest):
    """BM25 全文检索
    
    使用 BM25 算法进行全文检索，适合关键词精确匹配场景。
    与向量搜索互补，可用于混合搜索。
    """
    engine = get_engine()
    
    if not hasattr(engine, 'fulltext_index') or engine.fulltext_index is None:
        return {
            "success": False,
            "error": "全文索引未启用",
            "results": []
        }
    
    try:
        results = engine.fulltext_index.search(
            query=request.query,
            top_k=request.top_k
        )
        
        return {
            "success": True,
            "query": request.query,
            "results": [
                {
                    "id": r.get("id"),
                    "content": r.get("content"),
                    "score": r.get("score"),
                    "metadata": r.get("metadata", {})
                }
                for r in results
            ],
            "count": len(results)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": []
        }


@app.post("/v1/search/hybrid", tags=["Search"])
async def hybrid_search(request: SearchRequest):
    """混合搜索
    
    结合向量搜索和 BM25 全文检索的混合搜索。
    同时利用语义相似度和关键词匹配。
    """
    engine = get_engine()
    
    try:
        # 尝试使用引擎的混合搜索
        if hasattr(engine, 'hybrid_search'):
            results = engine.hybrid_search(
                query=request.query,
                user_id=request.user_id,
                top_k=request.top_k,
                filters=request.filters
            )
        else:
            # 回退到普通搜索
            results = engine.search(
                query=request.query,
                user_id=request.user_id,
                top_k=request.top_k,
                filters=request.filters
            )
        
        return {
            "success": True,
            "query": request.query,
            "results": [
                {
                    "id": r.id,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata,
                    "entities": r.entities if hasattr(r, 'entities') else []
                }
                for r in results
            ],
            "count": len(results)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": []
        }


# ==================== Phase 3: 检索配置 API ====================

@app.get("/v1/search/config", response_model=RetrievalConfigResponse, tags=["Search"])
async def get_search_config():
    """获取当前检索配置（Phase 3）
    
    返回当前检索器的配置状态，包括：
    - 检索器类型（ElevenLayer/EightLayer）
    - 各层开关状态
    - Top-K 参数
    - 权重配置
    """
    engine = get_engine()
    retriever = engine.retriever
    
    # 判断检索器类型
    from recall.retrieval.eleven_layer import ElevenLayerRetriever
    is_eleven_layer = isinstance(retriever, ElevenLayerRetriever)
    
    if is_eleven_layer and hasattr(retriever, 'config'):
        config = retriever.config
        return RetrievalConfigResponse(
            retriever_type="ElevenLayer",
            l1_enabled=config.l1_enabled,
            l2_enabled=config.l2_enabled,
            l3_enabled=config.l3_enabled,
            l4_enabled=config.l4_enabled,
            l5_enabled=config.l5_enabled,
            l6_enabled=config.l6_enabled,
            l7_enabled=config.l7_enabled,
            l8_enabled=config.l8_enabled,
            l9_enabled=config.l9_enabled,
            l10_enabled=config.l10_enabled,
            l11_enabled=config.l11_enabled,
            l7_vector_top_k=config.l7_vector_top_k,
            final_top_k=config.final_top_k,
            weights={
                "inverted": config.weights.inverted,
                "entity": config.weights.entity,
                "graph": config.weights.graph,
                "ngram": config.weights.ngram,
                "vector": config.weights.vector,
                "temporal": config.weights.temporal,
            }
        )
    else:
        # EightLayerRetriever 或兼容模式
        old_config = getattr(retriever, 'config', {})
        return RetrievalConfigResponse(
            retriever_type="EightLayer",
            l1_enabled=old_config.get('l1_enabled', True),
            l2_enabled=False,  # 旧版无 L2
            l3_enabled=old_config.get('l2_enabled', True),  # 旧 L2 = 新 L3
            l4_enabled=old_config.get('l3_enabled', True),  # 旧 L3 = 新 L4
            l5_enabled=False,  # 旧版无 L5
            l6_enabled=old_config.get('l4_enabled', True),  # 旧 L4 = 新 L6
            l7_enabled=old_config.get('l5_enabled', True),  # 旧 L5 = 新 L7
            l8_enabled=old_config.get('l6_enabled', True),  # 旧 L6 = 新 L8
            l9_enabled=old_config.get('l7_enabled', True),  # 旧 L7 = 新 L9
            l10_enabled=False,  # 旧版无 L10
            l11_enabled=old_config.get('l8_enabled', False),  # 旧 L8 = 新 L11
            l7_vector_top_k=200,
            final_top_k=20,
            weights={}
        )


@app.put("/v1/search/config", response_model=RetrievalConfigResponse, tags=["Search"])
async def update_search_config(request: RetrievalConfigRequest):
    """动态更新检索配置（Phase 3）
    
    允许在运行时调整检索策略，无需重启服务。
    
    使用方式：
    - 传入 preset="fast" 快速应用预设
    - 或单独设置各层开关和参数
    
    注意：此更改仅影响当前进程，重启后会恢复为环境变量配置。
    """
    engine = get_engine()
    retriever = engine.retriever
    
    from recall.retrieval.eleven_layer import ElevenLayerRetriever
    from recall.retrieval.config import RetrievalConfig
    
    if not isinstance(retriever, ElevenLayerRetriever):
        raise HTTPException(
            status_code=400,
            detail="当前使用 EightLayerRetriever，不支持动态配置。请设置 ELEVEN_LAYER_RETRIEVER_ENABLED=true 启用 ElevenLayerRetriever。"
        )
    
    config = retriever.config
    
    # 应用预设
    if request.preset:
        if request.preset == "fast":
            new_config = RetrievalConfig.fast()
        elif request.preset == "accurate":
            new_config = RetrievalConfig.accurate()
        elif request.preset == "default":
            new_config = RetrievalConfig.default()
        else:
            raise HTTPException(status_code=400, detail=f"未知预设: {request.preset}")
        retriever.config = new_config
        config = new_config
    else:
        # 单独更新各字段
        if request.l1_enabled is not None:
            config.l1_enabled = request.l1_enabled
        if request.l2_enabled is not None:
            config.l2_enabled = request.l2_enabled
        if request.l3_enabled is not None:
            config.l3_enabled = request.l3_enabled
        if request.l4_enabled is not None:
            config.l4_enabled = request.l4_enabled
        if request.l5_enabled is not None:
            config.l5_enabled = request.l5_enabled
        if request.l6_enabled is not None:
            config.l6_enabled = request.l6_enabled
        if request.l7_enabled is not None:
            config.l7_enabled = request.l7_enabled
        if request.l8_enabled is not None:
            config.l8_enabled = request.l8_enabled
        if request.l9_enabled is not None:
            config.l9_enabled = request.l9_enabled
        if request.l10_enabled is not None:
            config.l10_enabled = request.l10_enabled
        if request.l11_enabled is not None:
            config.l11_enabled = request.l11_enabled
        if request.l7_vector_top_k is not None:
            config.l7_vector_top_k = request.l7_vector_top_k
        if request.final_top_k is not None:
            config.final_top_k = request.final_top_k
    
    print(f"[Recall][Config] ⚙️ 检索配置已更新")
    
    # 返回更新后的配置
    return RetrievalConfigResponse(
        retriever_type="ElevenLayer",
        l1_enabled=config.l1_enabled,
        l2_enabled=config.l2_enabled,
        l3_enabled=config.l3_enabled,
        l4_enabled=config.l4_enabled,
        l5_enabled=config.l5_enabled,
        l6_enabled=config.l6_enabled,
        l7_enabled=config.l7_enabled,
        l8_enabled=config.l8_enabled,
        l9_enabled=config.l9_enabled,
        l10_enabled=config.l10_enabled,
        l11_enabled=config.l11_enabled,
        l7_vector_top_k=config.l7_vector_top_k,
        final_top_k=config.final_top_k,
        weights={
            "inverted": config.weights.inverted,
            "entity": config.weights.entity,
            "graph": config.weights.graph,
            "ngram": config.weights.ngram,
            "vector": config.weights.vector,
            "temporal": config.weights.temporal,
        }
    )


# ==================== v4.0 图谱遍历 API ====================

class GraphTraverseRequest(BaseModel):
    """图谱遍历请求"""
    start_entity: str = Field(..., description="起始实体")
    max_depth: int = Field(default=2, ge=1, le=5, description="最大深度")
    relation_types: Optional[List[str]] = Field(None, description="关系类型过滤")
    user_id: str = Field(default="default", description="用户ID")


@app.post("/v1/graph/traverse", tags=["Graph"])
async def traverse_graph(request: GraphTraverseRequest):
    """知识图谱遍历
    
    从指定实体开始，按关系遍历知识图谱。
    返回遍历路径上的所有实体和关系。
    """
    engine = get_engine()
    
    try:
        # 使用时态图谱或普通图谱
        if hasattr(engine, 'temporal_graph') and engine.temporal_graph is not None:
            result = engine.temporal_graph.traverse(
                start_entity=request.start_entity,
                max_depth=request.max_depth,
                relation_types=request.relation_types
            )
        elif hasattr(engine, 'knowledge_graph') and engine.knowledge_graph is not None:
            result = engine.knowledge_graph.traverse(
                start_entity=request.start_entity,
                max_depth=request.max_depth,
                relation_types=request.relation_types
            )
        else:
            return {
                "success": False,
                "error": "知识图谱未启用",
                "nodes": [],
                "edges": []
            }
        
        return {
            "success": True,
            "start_entity": request.start_entity,
            "nodes": result.get("nodes", []),
            "edges": result.get("edges", []),
            "depth_reached": result.get("depth_reached", 0)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "nodes": [],
            "edges": []
        }


@app.get("/v1/graph/entity/{entity_name}/neighbors", tags=["Graph"])
async def get_entity_neighbors(
    entity_name: str,
    user_id: str = Query(default="default", description="用户ID"),
    include_relations: bool = Query(default=True, description="是否包含关系详情")
):
    """获取实体的邻居节点
    
    返回与指定实体直接相连的所有实体。
    """
    engine = get_engine()
    
    try:
        related = engine.get_related_entities(entity_name)
        
        return {
            "success": True,
            "entity": entity_name,
            "neighbors": related,
            "count": len(related)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "neighbors": []
        }


# ==================== 实体 API ====================

@app.get("/v1/entities/{name}", tags=["Entities"])
async def get_entity(name: str):
    """获取实体信息"""
    engine = get_engine()
    entity = engine.get_entity(name)
    
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")
    
    return entity


@app.get("/v1/entities/{name}/related", tags=["Entities"])
async def get_related_entities(name: str):
    """获取相关实体"""
    engine = get_engine()
    related = engine.get_related_entities(name)
    return {"entity": name, "related": related}


# ==================== 管理 API ====================

@app.get("/v1/stats", tags=["Admin"])
async def get_stats():
    """获取统计信息"""
    engine = get_engine()
    return engine.get_stats()


@app.post("/v1/indexes/rebuild-vector", tags=["Admin"])
async def rebuild_vector_index(user_id: Optional[str] = None):
    """重建向量索引
    
    从现有记忆数据重新生成向量索引。
    用于修复维度不匹配、索引损坏等问题。
    
    Args:
        user_id: 可选，指定只重建某个用户的索引。为空时重建所有用户。
        
    注意：重建过程会消耗较多时间和 API 调用（如果使用 API embedding）。
    """
    engine = get_engine()
    print(f"[Recall] 收到重建向量索引请求: user_id={user_id}")
    result = engine.rebuild_vector_index(user_id)
    return result


@app.get("/v1/users", tags=["Admin"])
async def list_users():
    """列出所有用户（角色）
    
    返回所有有记忆数据的角色列表，以及每个角色的记忆数量。
    用于管理和清理不再需要的角色数据。
    """
    engine = get_engine()
    users = engine.storage.list_users()
    
    result = []
    for user_id in users:
        memories = engine.get_all(user_id=user_id, limit=10000)
        result.append({
            "user_id": user_id,
            "memory_count": len(memories)
        })
    
    return {
        "users": result,
        "total": len(result)
    }


@app.post("/v1/config/reload", tags=["Admin"])
async def reload_config():
    """热更新配置
    
    重新加载 recall_data/config/api_keys.env 配置文件。
    修改 API Key 后调用此接口即可生效，无需重启服务。
    
    使用方法：
    1. 编辑 recall_data/config/api_keys.env 文件
    2. 调用此接口: curl -X POST http://localhost:18888/v1/config/reload
    """
    try:
        engine = reload_engine()
        stats = engine.get_stats()
        
        # 获取当前 embedding 模式
        embedding_info = "Lite 模式" if stats.get('lite') else "Local/Cloud 模式"
        
        return {
            "success": True,
            "message": "配置已重新加载",
            "embedding_mode": embedding_info,
            "config_file": str(get_config_file_path())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载失败: {str(e)}")


@app.post("/v1/maintenance/rebuild-index", tags=["Admin"])
async def rebuild_index():
    """手动重建 VectorIndex 索引
    
    为所有伏笔和条件重建语义索引。通常不需要手动调用，
    系统会在首次升级时自动重建。
    
    使用场景：
    - 索引数据损坏需要重建
    - 手动导入了数据文件
    - 从备份恢复后需要重建索引
    
    注意：此操作可能需要较长时间，取决于数据量大小。
    """
    try:
        engine = get_engine()
        
        if not engine._vector_index or not engine._vector_index.enabled:
            return {
                "success": False,
                "message": "VectorIndex 未启用（Lite 模式下不可用）",
                "indexed_count": 0
            }
        
        # 使用公开方法强制重建索引
        indexed_count = engine.rebuild_vector_index(force=True)
        
        return {
            "success": True,
            "message": "索引重建完成",
            "indexed_count": indexed_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引重建失败: {str(e)}")


@app.get("/v1/config", tags=["Admin"])
async def get_config():
    """获取当前配置信息
    
    显示配置文件路径和当前配置状态（敏感信息脱敏）
    """
    config_file = get_config_file_path()
    
    # 检查各种配置状态
    def mask_key(key: str) -> str:
        """脱敏显示 API Key"""
        if not key:
            return "未配置"
        if len(key) > 8:
            return key[:4] + '****' + key[-4:]
        return '****'
    
    def safe_int(val: str, default: int) -> int:
        """安全转换整数"""
        try:
            return int(val) if val else default
        except (ValueError, TypeError):
            return default
    
    def safe_float(val: str, default: float) -> float:
        """安全转换浮点数"""
        try:
            return float(val) if val else default
        except (ValueError, TypeError):
            return default
    
    def safe_bool(val: str, default: bool) -> bool:
        """安全转换布尔值"""
        if not val:
            return default
        return val.lower() in ('true', '1', 'yes', 'on')
    
    # Embedding 配置
    embedding_key = os.environ.get('EMBEDDING_API_KEY', '')
    embedding_base = os.environ.get('EMBEDDING_API_BASE', '')
    embedding_model = os.environ.get('EMBEDDING_MODEL', '')
    embedding_dimension = os.environ.get('EMBEDDING_DIMENSION', '')
    embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', 'auto')
    
    # LLM 配置
    llm_key = os.environ.get('LLM_API_KEY', '')
    llm_base = os.environ.get('LLM_API_BASE', '')
    llm_model = os.environ.get('LLM_MODEL', '')
    
    # 容量限制配置
    context_trigger_interval = safe_int(os.environ.get('CONTEXT_TRIGGER_INTERVAL', ''), 5)
    context_max_context_turns = safe_int(os.environ.get('CONTEXT_MAX_CONTEXT_TURNS', ''), 20)
    context_max_per_type = safe_int(os.environ.get('CONTEXT_MAX_PER_TYPE', ''), 30)
    context_max_total = safe_int(os.environ.get('CONTEXT_MAX_TOTAL', ''), 100)
    context_decay_days = safe_int(os.environ.get('CONTEXT_DECAY_DAYS', ''), 7)
    context_decay_rate = safe_float(os.environ.get('CONTEXT_DECAY_RATE', ''), 0.1)
    context_min_confidence = safe_float(os.environ.get('CONTEXT_MIN_CONFIDENCE', ''), 0.3)
    
    # 上下文构建配置
    build_context_include_recent = safe_int(os.environ.get('BUILD_CONTEXT_INCLUDE_RECENT', ''), 10)
    proactive_reminder_enabled = safe_bool(os.environ.get('PROACTIVE_REMINDER_ENABLED', ''), True)
    proactive_reminder_turns = safe_int(os.environ.get('PROACTIVE_REMINDER_TURNS', ''), 50)
    
    foreshadowing_max_return = safe_int(os.environ.get('FORESHADOWING_MAX_RETURN', ''), 5)
    foreshadowing_max_active = safe_int(os.environ.get('FORESHADOWING_MAX_ACTIVE', ''), 50)
    
    # 智能去重配置
    dedup_embedding_enabled = safe_bool(os.environ.get('DEDUP_EMBEDDING_ENABLED', ''), True)
    dedup_high_threshold = safe_float(os.environ.get('DEDUP_HIGH_THRESHOLD', ''), 0.92)
    dedup_low_threshold = safe_float(os.environ.get('DEDUP_LOW_THRESHOLD', ''), 0.75)
    
    return {
        "config_file": str(config_file),
        "config_file_exists": config_file.exists(),
        "embedding": {
            "api_key": mask_key(embedding_key),
            "api_base": embedding_base or "未配置",
            "model": embedding_model or "未配置",
            "dimension": embedding_dimension or "未配置",
            "mode": embedding_mode,
            "status": "已配置" if (embedding_key and embedding_base) else "未配置"
        },
        "llm": {
            "api_key": mask_key(llm_key),
            "api_base": llm_base or "未配置",
            "model": llm_model or "未配置",
            "status": "已配置" if llm_key else "未配置"
        },
        "capacity_limits": {
            "context": {
                "trigger_interval": context_trigger_interval,
                "max_per_type": context_max_per_type,
                "max_total": context_max_total,
                "decay_days": context_decay_days,
                "decay_rate": context_decay_rate,
                "min_confidence": context_min_confidence
            },
            "build_context": {
                "max_context_turns": context_max_context_turns,
                "include_recent": build_context_include_recent,
                "proactive_reminder_enabled": proactive_reminder_enabled,
                "proactive_reminder_turns": proactive_reminder_turns
            },
            "foreshadowing": {
                "max_return": foreshadowing_max_return,
                "max_active": foreshadowing_max_active
            },
            "dedup": {
                "embedding_enabled": dedup_embedding_enabled,
                "high_threshold": dedup_high_threshold,
                "low_threshold": dedup_low_threshold
            }
        },
        "hint": "编辑配置文件后调用 POST /v1/config/reload 热更新，测试连接 GET /v1/config/test"
    }


@app.get("/v1/config/test", tags=["Admin"])
async def test_connection():
    """测试 Embedding API 连接
    
    测试当前配置的 Embedding API 是否可以正常连接。
    会实际调用 API 生成一个测试向量来验证。
    
    使用方法：
    curl http://localhost:18888/v1/config/test
    
    返回：
    - success: true/false
    - message: 测试结果描述
    - backend: 当前使用的后端类型
    - model: 当前使用的模型
    - dimension: 向量维度
    - latency_ms: API 调用延迟（毫秒）
    """
    engine = get_engine()
    
    # 检查是否是 Lite 模式
    config = engine.embedding_config
    if engine.lightweight or not config or config.backend.value == "none":
        return {
            "success": True,
            "message": "Lite 模式无需测试 API 连接",
            "backend": "none",
            "model": None,
            "dimension": None,
            "latency_ms": 0
        }
    
    # 从引擎获取当前配置
    backend_type = config.backend.value if config.backend else "unknown"
    model = config.api_model or config.local_model or "unknown"
    dimension = config.dimension
    
    # 获取 embedding 后端并测试
    try:
        # 实际测试 embedding 调用
        start_time = time.time()
        test_text = "Hello, this is a test."
        
        # 尝试获取 embedding
        if engine._vector_index and engine._vector_index.embedding_backend:
            embedding_backend = engine._vector_index.embedding_backend
            embedding = embedding_backend.encode(test_text)
            actual_dimension = len(embedding)
            elapsed_ms = (time.time() - start_time) * 1000
            
            return {
                "success": True,
                "message": f"API 连接成功！模型 {model} 工作正常",
                "backend": backend_type,
                "model": model,
                "dimension": actual_dimension,
                "latency_ms": round(elapsed_ms, 2)
            }
        else:
            return {
                "success": False,
                "message": "Embedding 后端未初始化（可能是 Lite 模式或索引未加载）",
                "backend": backend_type,
                "model": model,
                "dimension": dimension,
                "latency_ms": 0
            }
            
    except Exception as e:
        error_msg = str(e)
        
        # 友好的错误提示
        if "API key" in error_msg.lower() or "unauthorized" in error_msg.lower() or "401" in error_msg:
            friendly_msg = "API Key 无效或未配置"
        elif "connection" in error_msg.lower() or "network" in error_msg.lower():
            friendly_msg = "网络连接失败，请检查网络或 API 地址"
        elif "model" in error_msg.lower() or "404" in error_msg:
            friendly_msg = "模型不存在或不可用"
        else:
            friendly_msg = f"连接失败: {error_msg}"
        
        # 尝试获取当前配置信息用于错误响应
        try:
            cfg = engine.embedding_config
            current_backend = cfg.backend.value if cfg and cfg.backend else 'unknown'
            current_model = (cfg.api_model or cfg.local_model) if cfg else None
        except:
            current_backend = os.environ.get('RECALL_EMBEDDING_MODE', 'auto')
            current_model = None
        
        return {
            "success": False,
            "message": friendly_msg,
            "error": error_msg,
            "backend": current_backend,
            "model": current_model,
            "dimension": None,
            "latency_ms": 0
        }


@app.get("/v1/config/test/llm", tags=["Admin"])
async def test_llm_connection():
    """测试 LLM API 连接
    
    测试当前配置的 LLM API 是否可以正常连接。
    会实际调用 API 生成一个简短回复来验证。
    
    使用方法：
    curl http://localhost:18888/v1/config/test/llm
    
    返回：
    - success: true/false
    - message: 测试结果描述
    - model: 当前配置的模型
    - latency_ms: API 调用延迟（毫秒）
    """
    # 获取 LLM 配置
    llm_api_key = os.environ.get('LLM_API_KEY', '')
    llm_api_base = os.environ.get('LLM_API_BASE', '')
    llm_model = os.environ.get('LLM_MODEL', 'gpt-3.5-turbo')
    
    # 如果没有 LLM_API_KEY，尝试使用 OPENAI_API_KEY
    if not llm_api_key:
        llm_api_key = os.environ.get('OPENAI_API_KEY', '')
    
    if not llm_api_key:
        return {
            "success": False,
            "message": "LLM API Key 未配置",
            "model": llm_model,
            "api_base": llm_api_base or "默认",
            "latency_ms": 0,
            "hint": "请在 api_keys.env 中设置 LLM_API_KEY 或 OPENAI_API_KEY"
        }
    
    try:
        from .utils.llm_client import LLMClient
        
        start_time = time.time()
        
        # 创建 LLM 客户端
        client = LLMClient(
            model=llm_model,
            api_key=llm_api_key,
            api_base=llm_api_base if llm_api_base else None,
            timeout=15.0,
            max_retries=1
        )
        
        # 发送简单的测试请求
        response = client.chat(
            messages=[{"role": "user", "content": "Say 'Hello' in one word."}],
            max_tokens=10,
            temperature=0
        )
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            "success": True,
            "message": f"LLM 连接成功！模型 {response.model} 工作正常",
            "model": response.model,
            "api_base": llm_api_base or "默认",
            "response": response.content[:50] if response.content else "",
            "latency_ms": round(elapsed_ms, 2),
            "usage": response.usage
        }
        
    except Exception as e:
        error_msg = str(e)
        
        # 友好的错误提示
        if "API key" in error_msg.lower() or "unauthorized" in error_msg.lower() or "401" in error_msg:
            friendly_msg = "API Key 无效或未授权"
        elif "connection" in error_msg.lower() or "network" in error_msg.lower():
            friendly_msg = "网络连接失败，请检查网络或 API 地址"
        elif "model" in error_msg.lower() or "404" in error_msg:
            friendly_msg = f"模型 {llm_model} 不存在或不可用"
        elif "timeout" in error_msg.lower():
            friendly_msg = "请求超时，请检查网络连接"
        else:
            friendly_msg = f"连接失败: {error_msg}"
        
        return {
            "success": False,
            "message": friendly_msg,
            "error": error_msg,
            "model": llm_model,
            "api_base": llm_api_base or "默认",
            "latency_ms": 0
        }


@app.get("/v1/config/detect-dimension", tags=["Admin"])
async def detect_embedding_dimension(api_key: Optional[str] = None, api_base: Optional[str] = None, model: Optional[str] = None):
    """自动检测 Embedding 模型的向量维度
    
    调用 Embedding API 生成一个测试向量，返回其实际维度。
    如果未提供参数，则使用当前配置的 API。
    
    Args:
        api_key: 可选，临时使用的 API Key
        api_base: 可选，临时使用的 API Base URL
        model: 可选，临时使用的模型名称
        
    Returns:
        dimension: 检测到的向量维度
        model: 使用的模型
    """
    # 优先使用参数，否则使用配置
    embedding_key = api_key or os.environ.get('EMBEDDING_API_KEY', '')
    embedding_base = api_base or os.environ.get('EMBEDDING_API_BASE', '')
    embedding_model = model or os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
    
    if not embedding_key:
        return {
            "success": False,
            "message": "请先配置 Embedding API Key",
            "dimension": None
        }
    
    try:
        from openai import OpenAI
        
        client_kwargs = {"api_key": embedding_key, "timeout": 30}
        if embedding_base:
            client_kwargs["base_url"] = embedding_base
        
        client = OpenAI(**client_kwargs)
        
        # 生成测试向量
        start_time = time.time()
        response = client.embeddings.create(
            model=embedding_model,
            input="Hello, this is a test for dimension detection."
        )
        elapsed_ms = (time.time() - start_time) * 1000
        
        # 获取实际维度
        if response.data and len(response.data) > 0:
            actual_dimension = len(response.data[0].embedding)
            return {
                "success": True,
                "message": f"检测到向量维度: {actual_dimension}",
                "dimension": actual_dimension,
                "model": embedding_model,
                "api_base": embedding_base or "默认",
                "latency_ms": round(elapsed_ms, 2)
            }
        else:
            return {
                "success": False,
                "message": "API 返回空结果",
                "dimension": None
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"检测失败: {str(e)}",
            "dimension": None
        }


@app.get("/v1/config/models/embedding", tags=["Admin"])
async def get_embedding_models(api_key: Optional[str] = None, api_base: Optional[str] = None):
    """获取可用的 Embedding 模型列表
    
    从指定的 API 获取可用的模型列表。
    如果未提供参数，则使用当前配置的 API。
    
    Args:
        api_key: 可选，临时使用的 API Key
        api_base: 可选，临时使用的 API Base URL
    """
    # 优先使用参数，否则使用配置
    embedding_key = api_key or os.environ.get('EMBEDDING_API_KEY', '')
    embedding_base = api_base or os.environ.get('EMBEDDING_API_BASE', '')
    
    if not embedding_key:
        return {
            "success": False,
            "message": "请先填写 Embedding API Key",
            "models": []
        }
    
    try:
        from openai import OpenAI
        import httpx
        
        client_kwargs = {"api_key": embedding_key, "timeout": 30}
        if embedding_base:
            client_kwargs["base_url"] = embedding_base
        
        client = OpenAI(**client_kwargs)
        
        try:
            models_response = client.models.list()
        except Exception as list_err:
            # 如果 /models 端点不支持，尝试直接请求
            base_url = embedding_base or "https://api.openai.com/v1"
            models_url = f"{base_url.rstrip('/')}/models"
            
            try:
                async with httpx.AsyncClient(timeout=30) as http_client:
                    resp = await http_client.get(
                        models_url,
                        headers={"Authorization": f"Bearer {embedding_key}"}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        models_data = data.get('data', [])
                        if models_data:
                            embedding_models = []
                            for model in models_data:
                                model_id = model.get('id', '').lower()
                                if any(kw in model_id for kw in ['embed', 'bge', 'bce', 'e5', 'minilm', 'nomic']):
                                    embedding_models.append({
                                        "id": model.get('id'),
                                        "owned_by": model.get('owned_by', 'unknown')
                                    })
                            if not embedding_models:
                                embedding_models = [
                                    {"id": m.get('id'), "owned_by": m.get('owned_by', 'unknown')}
                                    for m in models_data
                                ]
                            return {
                                "success": True,
                                "message": f"获取到 {len(embedding_models)} 个模型",
                                "models": embedding_models,
                                "api_base": embedding_base or "默认"
                            }
                    # 如果请求失败，返回详细错误
                    return {
                        "success": False,
                        "message": f"该 API 不支持获取模型列表 (HTTP {resp.status_code})，请手动输入模型名称",
                        "models": [],
                        "hint": "选择'自定义模型'并手动输入模型名称"
                    }
            except Exception as http_err:
                return {
                    "success": False,
                    "message": f"该 API 不支持 /models 端点，请手动输入模型名称",
                    "models": [],
                    "hint": "选择'自定义模型'并手动输入模型名称",
                    "error_detail": str(http_err)
                }
        
        # 过滤出 embedding 相关的模型
        embedding_models = []
        for model in models_response.data:
            model_id = model.id.lower()
            # 匹配 embedding 模型的常见命名
            if any(kw in model_id for kw in ['embed', 'bge', 'bce', 'e5', 'minilm', 'nomic']):
                embedding_models.append({
                    "id": model.id,
                    "owned_by": getattr(model, 'owned_by', 'unknown')
                })
        
        # 如果没有找到明确的 embedding 模型，返回所有模型让用户选择
        if not embedding_models:
            embedding_models = [
                {"id": model.id, "owned_by": getattr(model, 'owned_by', 'unknown')}
                for model in models_response.data
            ]
        
        return {
            "success": True,
            "message": f"获取到 {len(embedding_models)} 个模型",
            "models": embedding_models,
            "api_base": embedding_base or "默认"
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "message": f"获取模型列表失败: {str(e)}",
            "models": [],
            "error_detail": traceback.format_exc()
        }


@app.get("/v1/config/models/llm", tags=["Admin"])
async def get_llm_models(api_key: Optional[str] = None, api_base: Optional[str] = None):
    """获取可用的 LLM 模型列表
    
    从指定的 API 获取可用的模型列表。
    如果未提供参数，则使用当前配置的 API。
    
    Args:
        api_key: 可选，临时使用的 API Key
        api_base: 可选，临时使用的 API Base URL
    """
    # 优先使用参数，否则使用配置
    llm_key = api_key or os.environ.get('LLM_API_KEY', '')
    llm_base = api_base or os.environ.get('LLM_API_BASE', '')
    
    if not llm_key:
        return {
            "success": False,
            "message": "请先填写 LLM API Key",
            "models": []
        }
    
    try:
        from openai import OpenAI
        import httpx
        
        client_kwargs = {"api_key": llm_key, "timeout": 30}
        if llm_base:
            client_kwargs["base_url"] = llm_base
        
        client = OpenAI(**client_kwargs)
        
        try:
            models_response = client.models.list()
        except Exception as list_err:
            # 如果 /models 端点不支持，尝试直接请求
            base_url = llm_base or "https://api.openai.com/v1"
            models_url = f"{base_url.rstrip('/')}/models"
            
            try:
                async with httpx.AsyncClient(timeout=30) as http_client:
                    resp = await http_client.get(
                        models_url,
                        headers={"Authorization": f"Bearer {llm_key}"}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        models_data = data.get('data', [])
                        if models_data:
                            llm_models = []
                            for model in models_data:
                                model_id = model.get('id', '').lower()
                                # 排除 embedding 模型
                                if not any(kw in model_id for kw in ['embed', 'bge', 'bce', 'e5-', 'minilm']):
                                    llm_models.append({
                                        "id": model.get('id'),
                                        "owned_by": model.get('owned_by', 'unknown')
                                    })
                            return {
                                "success": True,
                                "message": f"获取到 {len(llm_models)} 个模型",
                                "models": llm_models,
                                "api_base": llm_base or "默认"
                            }
                    # 如果请求失败，返回详细错误
                    return {
                        "success": False,
                        "message": f"该 API 不支持获取模型列表 (HTTP {resp.status_code})，请手动输入模型名称",
                        "models": [],
                        "hint": "选择'自定义模型'并手动输入模型名称"
                    }
            except Exception as http_err:
                return {
                    "success": False,
                    "message": f"该 API 不支持 /models 端点，请手动输入模型名称",
                    "models": [],
                    "hint": "选择'自定义模型'并手动输入模型名称",
                    "error_detail": str(http_err)
                }
        
        # 过滤出 LLM/Chat 相关的模型（排除 embedding 模型）
        llm_models = []
        for model in models_response.data:
            model_id = model.id.lower()
            # 排除 embedding 模型
            if not any(kw in model_id for kw in ['embed', 'bge', 'bce', 'e5-', 'minilm']):
                llm_models.append({
                    "id": model.id,
                    "owned_by": getattr(model, 'owned_by', 'unknown')
                })
        
        return {
            "success": True,
            "message": f"获取到 {len(llm_models)} 个模型",
            "models": llm_models,
            "api_base": llm_base or "默认"
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "message": f"获取模型列表失败: {str(e)}",
            "models": [],
            "error_detail": traceback.format_exc()
        }


class ConfigUpdateRequest(BaseModel):
    """配置更新请求（统一使用 OpenAI 兼容格式）"""
    # Embedding 配置
    embedding_api_key: Optional[str] = Field(default=None, description="Embedding API Key")
    embedding_api_base: Optional[str] = Field(default=None, description="Embedding API 地址")
    embedding_model: Optional[str] = Field(default=None, description="Embedding 模型")
    embedding_dimension: Optional[int] = Field(default=None, description="向量维度")
    recall_embedding_mode: Optional[str] = Field(default=None, description="Embedding 模式")
    embedding_rate_limit: Optional[int] = Field(default=None, description="API 速率限制（每时间窗口最大请求数）")
    embedding_rate_window: Optional[int] = Field(default=None, description="速率限制时间窗口（秒）")
    # LLM 配置
    llm_api_key: Optional[str] = Field(default=None, description="LLM API Key")
    llm_api_base: Optional[str] = Field(default=None, description="LLM API 地址")
    llm_model: Optional[str] = Field(default=None, description="LLM 模型")
    # 持久条件容量配置
    context_trigger_interval: Optional[int] = Field(default=None, description="条件提取触发间隔（每N轮）")
    context_max_per_type: Optional[int] = Field(default=None, description="每类型条件上限")
    context_max_total: Optional[int] = Field(default=None, description="条件总数上限")
    context_decay_days: Optional[int] = Field(default=None, description="衰减开始天数")
    context_decay_rate: Optional[float] = Field(default=None, description="每次衰减比例 (0-1)")
    context_min_confidence: Optional[float] = Field(default=None, description="最低置信度 (0-1)")
    # 伏笔系统容量配置
    foreshadowing_max_return: Optional[int] = Field(default=None, description="伏笔召回数量")
    foreshadowing_max_active: Optional[int] = Field(default=None, description="活跃伏笔数量上限")
    # 智能去重配置
    dedup_embedding_enabled: Optional[bool] = Field(default=None, description="启用语义去重")
    dedup_high_threshold: Optional[float] = Field(default=None, description="高相似度阈值 (0-1)")
    dedup_low_threshold: Optional[float] = Field(default=None, description="低相似度阈值 (0-1)")
    # 上下文构建配置（100%不遗忘保证）
    context_max_context_turns: Optional[int] = Field(default=None, description="对话提取最大轮次")
    build_context_include_recent: Optional[int] = Field(default=None, description="build_context默认最近对话轮次")
    proactive_reminder_enabled: Optional[bool] = Field(default=None, description="启用主动提醒")
    proactive_reminder_turns: Optional[int] = Field(default=None, description="主动提醒触发轮次")


@app.put("/v1/config", tags=["Admin"])
async def update_config(request: ConfigUpdateRequest):
    """更新配置文件
    
    更新 api_keys.env 中的配置项。只会更新请求中包含的非空字段。
    更新后会自动重新加载配置。
    
    使用方法：
    curl -X PUT http://localhost:18888/v1/config \\
         -H "Content-Type: application/json" \\
         -d '{"embedding_api_key": "your-api-key", "llm_api_key": "your-llm-key"}'
    """
    config_file = get_config_file_path()
    
    # 读取当前配置
    current_config = {}
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    current_config[key.strip()] = value.strip()
    
    # 映射请求字段到配置键（统一使用 OpenAI 兼容格式）
    field_to_key = {
        'embedding_api_key': 'EMBEDDING_API_KEY',
        'embedding_api_base': 'EMBEDDING_API_BASE',
        'embedding_model': 'EMBEDDING_MODEL',
        'embedding_dimension': 'EMBEDDING_DIMENSION',
        'recall_embedding_mode': 'RECALL_EMBEDDING_MODE',
        'embedding_rate_limit': 'EMBEDDING_RATE_LIMIT',
        'embedding_rate_window': 'EMBEDDING_RATE_WINDOW',
        'llm_api_key': 'LLM_API_KEY',
        'llm_api_base': 'LLM_API_BASE',
        'llm_model': 'LLM_MODEL',
        # 持久条件容量配置
        'context_trigger_interval': 'CONTEXT_TRIGGER_INTERVAL',
        'context_max_per_type': 'CONTEXT_MAX_PER_TYPE',
        'context_max_total': 'CONTEXT_MAX_TOTAL',
        'context_decay_days': 'CONTEXT_DECAY_DAYS',
        'context_decay_rate': 'CONTEXT_DECAY_RATE',
        'context_min_confidence': 'CONTEXT_MIN_CONFIDENCE',
        # 伏笔系统容量配置
        'foreshadowing_max_return': 'FORESHADOWING_MAX_RETURN',
        'foreshadowing_max_active': 'FORESHADOWING_MAX_ACTIVE',
        # 智能去重配置
        'dedup_embedding_enabled': 'DEDUP_EMBEDDING_ENABLED',
        'dedup_high_threshold': 'DEDUP_HIGH_THRESHOLD',
        'dedup_low_threshold': 'DEDUP_LOW_THRESHOLD',
        # 上下文构建配置（100%不遗忘保证）
        'context_max_context_turns': 'CONTEXT_MAX_CONTEXT_TURNS',
        'build_context_include_recent': 'BUILD_CONTEXT_INCLUDE_RECENT',
        'proactive_reminder_enabled': 'PROACTIVE_REMINDER_ENABLED',
        'proactive_reminder_turns': 'PROACTIVE_REMINDER_TURNS',
    }
    
    # 更新配置
    updated_fields = []
    request_dict = request.model_dump(exclude_none=True)
    
    for field, config_key in field_to_key.items():
        if field in request_dict:
            value = request_dict[field]
            if value is not None:
                # 转换为字符串
                str_value = str(value) if not isinstance(value, str) else value
                current_config[config_key] = str_value
                # 同时更新环境变量
                os.environ[config_key] = str_value
                updated_fields.append(config_key)
    
    if not updated_fields:
        return {
            "success": False,
            "message": "没有提供需要更新的配置项"
        }
    
    # 写回配置文件（保留注释和格式）
    try:
        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果文件不存在，先创建包含完整模板的文件
        if not config_file.exists():
            config_file.write_text(get_default_config_content(), encoding='utf-8')
            print(f"[Config] 已创建配置文件: {config_file}")
        
        # 读取原文件保留注释
        lines = []
        existing_keys = set()
        
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                original_line = line.rstrip('\n\r')
                stripped = original_line.strip()
                
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=')[0].strip()
                    if key in current_config:
                        # 更新这行的值
                        lines.append(f"{key}={current_config[key]}")
                        existing_keys.add(key)
                    else:
                        lines.append(original_line)
                else:
                    lines.append(original_line)
        
        # 添加新的配置项
        for key, value in current_config.items():
            if key not in existing_keys and key in SUPPORTED_CONFIG_KEYS:
                lines.append(f"{key}={value}")
        
        # 写入文件
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            if not lines[-1].endswith('\n'):
                f.write('\n')
        
        # 重新加载引擎配置
        try:
            reload_engine()
        except Exception as reload_err:
            # 配置已保存，但重新加载失败
            return {
                "success": True,
                "message": f"配置已保存，但重新加载失败: {str(reload_err)}",
                "updated_fields": updated_fields,
                "hint": "请手动重启服务或调用 POST /v1/config/reload"
            }
        
        return {
            "success": True,
            "message": "配置已更新并重新加载",
            "updated_fields": updated_fields
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")


@app.get("/v1/config/full", tags=["Admin"])
async def get_full_config():
    """获取完整配置信息
    
    返回 Embedding 和 LLM 的完整配置状态，包括脱敏后的 API Key。
    供任何客户端（插件、Web UI、CLI 等）使用。
    """
    def mask_key(key: str) -> str:
        """脱敏显示 API Key"""
        if not key:
            return ""
        if len(key) > 12:
            return key[:4] + '*' * 8 + key[-4:]
        elif len(key) > 4:
            return key[:2] + '*' * (len(key) - 2)
        return '****'
    
    def get_key_status(key: str) -> str:
        """获取 API Key 状态"""
        if not key:
            return "未配置"
        return "已配置"
    
    # Embedding 配置（统一使用 OpenAI 兼容格式）
    embedding_key = os.environ.get('EMBEDDING_API_KEY', '')
    
    embedding_config = {
        "api_key": mask_key(embedding_key),
        "api_key_status": get_key_status(embedding_key),
        "api_base": os.environ.get('EMBEDDING_API_BASE', ''),
        "model": os.environ.get('EMBEDDING_MODEL', ''),
        "dimension": os.environ.get('EMBEDDING_DIMENSION', ''),
        "mode": os.environ.get('RECALL_EMBEDDING_MODE', ''),
        "rate_limit": os.environ.get('EMBEDDING_RATE_LIMIT', ''),
        "rate_window": os.environ.get('EMBEDDING_RATE_WINDOW', ''),
    }
    
    # LLM 配置
    llm_key = os.environ.get('LLM_API_KEY', '')
    llm_config = {
        "api_key": mask_key(llm_key),
        "api_key_status": get_key_status(llm_key),
        "api_base": os.environ.get('LLM_API_BASE', ''),
        "model": os.environ.get('LLM_MODEL', 'gpt-3.5-turbo'),
    }
    
    return {
        "embedding": embedding_config,
        "llm": llm_config,
        "config_file": str(get_config_file_path()),
    }


@app.post("/v1/consolidate", tags=["Admin"])
async def consolidate(user_id: str = Query(default="default")):
    """执行记忆整合"""
    engine = get_engine()
    engine.consolidate(user_id=user_id)
    return {"success": True, "message": "整合完成"}


@app.post("/v1/reset", tags=["Admin"])
async def reset(
    user_id: Optional[str] = Query(default=None),
    confirm: bool = Query(default=False)
):
    """重置记忆（危险操作）"""
    if not confirm:
        raise HTTPException(status_code=400, detail="需要 confirm=true 确认")
    
    engine = get_engine()
    engine.reset(user_id=user_id)
    return {"success": True, "message": "重置完成"}


# ==================== mem0 兼容 API ====================
# 提供与 mem0 API 格式兼容的接口

@app.post("/v1/memory/", tags=["mem0 Compatible"])
async def mem0_add(
    messages: List[Dict[str, str]] = Body(...),
    user_id: str = Body(default="default"),
    metadata: Optional[Dict[str, Any]] = Body(default=None)
):
    """mem0 兼容 - 添加记忆"""
    engine = get_engine()
    
    results = []
    for msg in messages:
        content = msg.get('content', '')
        if content:
            result = engine.add(content, user_id=user_id, metadata=metadata)
            results.append({"id": result.id, "success": result.success})
    
    return {"results": results}


@app.get("/v1/memory/", tags=["mem0 Compatible"])
async def mem0_get_all(
    user_id: str = Query(default="default"),
    limit: int = Query(default=100)
):
    """mem0 兼容 - 获取所有记忆"""
    engine = get_engine()
    memories = engine.get_all(user_id=user_id, limit=limit)
    
    # 转换为 mem0 格式
    return {
        "memories": [
            {
                "id": m.get('id'),
                "memory": m.get('content', m.get('memory', '')),
                "user_id": user_id,
                "metadata": m.get('metadata', {}),
                "created_at": m.get('created_at')
            }
            for m in memories
        ]
    }


@app.post("/v1/memory/search/", tags=["mem0 Compatible"])
async def mem0_search(
    query: str = Body(...),
    user_id: str = Body(default="default"),
    limit: int = Body(default=10)
):
    """mem0 兼容 - 搜索记忆"""
    engine = get_engine()
    results = engine.search(query, user_id=user_id, top_k=limit)
    
    return {
        "memories": [
            {
                "id": r.id,
                "memory": r.content,
                "score": r.score,
                "user_id": user_id,
                "metadata": r.metadata
            }
            for r in results
        ]
    }


@app.delete("/v1/memory/{memory_id}/", tags=["mem0 Compatible"])
async def mem0_delete(memory_id: str, user_id: str = Query(default="default")):
    """mem0 兼容 - 删除记忆"""
    engine = get_engine()
    success = engine.delete(memory_id, user_id=user_id)
    return {"success": success}

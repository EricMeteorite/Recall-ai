"""IVF → IVF-HNSW 索引迁移工具

Phase 3.6: 由于 quantizer 类型不同（IndexFlatIP vs IndexHNSWFlat），
需要重建索引。此工具支持：
1. 读取现有 IVF 索引的所有向量
2. 创建新的 IVF-HNSW 索引
3. 重新添加所有向量
4. 保留原有元数据映射

使用方式：
    python tools/migrate_ivf_to_hnsw.py --data-path ./recall_data/indexes
    
可选参数：
    --hnsw-m: HNSW M 参数（默认 32）
    --ef-construction: HNSW efConstruction 参数（默认 200）
    --backup: 是否备份旧索引（默认 True）
"""

import os
import sys
import json
import argparse
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _safe_print(msg: str) -> None:
    """安全打印函数，处理 Windows GBK 编码问题"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def migrate_index(
    data_path: str,
    hnsw_m: int = 32,
    ef_construction: int = 200,
    ef_search: int = 64,
    backup: bool = True
) -> bool:
    """迁移 IVF 索引到 IVF-HNSW 格式
    
    Args:
        data_path: 索引数据目录
        hnsw_m: HNSW 图连接数
        ef_construction: 构建精度
        ef_search: 搜索精度
        backup: 是否备份旧索引
        
    Returns:
        是否迁移成功
    """
    try:
        import faiss
    except ImportError:
        _safe_print("[FAIL] faiss not installed. Run: pip install faiss-cpu")
        return False
    
    old_index_file = os.path.join(data_path, "vector_index_ivf.faiss")
    new_index_file = os.path.join(data_path, "vector_index_ivf_hnsw.faiss")
    mapping_file = os.path.join(data_path, "vector_mapping_ivf.npy")
    metadata_file = os.path.join(data_path, "vector_metadata_ivf.json")
    
    if not os.path.exists(old_index_file):
        _safe_print(f"[WARN] Old index not found: {old_index_file}")
        _safe_print("[HINT] Nothing to migrate. New indexes will use IVF-HNSW automatically.")
        return True
    
    _safe_print(f"[START] Loading old IVF index from {old_index_file}")
    old_index = faiss.read_index(old_index_file)
    
    # 检查是否已经是 HNSW 索引
    quantizer = faiss.downcast_index(old_index.quantizer)
    if hasattr(quantizer, 'hnsw'):
        _safe_print("[OK] Index is already IVF-HNSW, no migration needed")
        return True
    
    # 提取所有向量
    ntotal = old_index.ntotal
    dimension = old_index.d
    _safe_print(f"[STATS] Found {ntotal} vectors, dimension={dimension}")
    
    if ntotal == 0:
        _safe_print("[WARN] Index is empty, nothing to migrate")
        return True
    
    # 重建向量（从 IVF 索引中提取）
    _safe_print("[SYNC] Reconstructing vectors from old index...")
    vectors = old_index.reconstruct_n(0, ntotal)
    _safe_print(f"[OK] Reconstructed {len(vectors)} vectors")
    
    # 获取旧索引参数
    nlist = old_index.nlist
    nprobe = old_index.nprobe
    
    # 创建新的 IVF-HNSW 索引
    _safe_print(f"[PKG] Creating new IVF-HNSW index (nlist={nlist}, hnsw_m={hnsw_m})")
    hnsw_quantizer = faiss.IndexHNSWFlat(dimension, hnsw_m)
    hnsw_quantizer.hnsw.efConstruction = ef_construction
    hnsw_quantizer.hnsw.efSearch = ef_search
    
    new_index = faiss.IndexIVFFlat(
        hnsw_quantizer,
        dimension,
        nlist,
        faiss.METRIC_INNER_PRODUCT
    )
    new_index.nprobe = nprobe
    
    # 训练新索引
    _safe_print(f"[SYNC] Training new index on {len(vectors)} vectors...")
    new_index.train(vectors)
    
    # 添加向量
    _safe_print(f"[SYNC] Adding {len(vectors)} vectors to new index...")
    new_index.add(vectors)
    
    # 保存新索引
    _safe_print(f"[SAVE] Saving new index to {new_index_file}")
    faiss.write_index(new_index, new_index_file)
    
    # 备份旧索引
    if backup:
        backup_file = old_index_file + ".backup"
        if os.path.exists(backup_file):
            os.remove(backup_file)
        os.rename(old_index_file, backup_file)
        _safe_print(f"[OK] Old index backed up to {backup_file}")
    else:
        os.remove(old_index_file)
        _safe_print("[WARN] Old index removed (no backup)")
    
    # 重命名新索引
    os.rename(new_index_file, old_index_file)
    _safe_print(f"[DONE] Migration complete! New IVF-HNSW index saved to {old_index_file}")
    
    # 显示迁移信息
    _safe_print("\n" + "=" * 60)
    _safe_print("Migration Summary:")
    _safe_print(f"  - Vectors migrated: {ntotal}")
    _safe_print(f"  - Dimension: {dimension}")
    _safe_print(f"  - nlist: {nlist}")
    _safe_print(f"  - nprobe: {nprobe}")
    _safe_print(f"  - HNSW M: {hnsw_m}")
    _safe_print(f"  - HNSW efConstruction: {ef_construction}")
    _safe_print(f"  - HNSW efSearch: {ef_search}")
    _safe_print("=" * 60)
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Migrate IVF to IVF-HNSW index for better recall rate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Migrate with default parameters
    python tools/migrate_ivf_to_hnsw.py --data-path ./recall_data/indexes
    
    # High recall mode
    python tools/migrate_ivf_to_hnsw.py --data-path ./recall_data/indexes --hnsw-m 48 --ef-construction 300
    
    # Fast mode
    python tools/migrate_ivf_to_hnsw.py --data-path ./recall_data/indexes --hnsw-m 16 --ef-construction 100
"""
    )
    parser.add_argument(
        "--data-path",
        required=True,
        help="Index data directory (contains vector_index_ivf.faiss)"
    )
    parser.add_argument(
        "--hnsw-m",
        type=int,
        default=32,
        help="HNSW M parameter (default: 32, higher = better recall)"
    )
    parser.add_argument(
        "--ef-construction",
        type=int,
        default=200,
        help="HNSW efConstruction (default: 200, higher = better index quality)"
    )
    parser.add_argument(
        "--ef-search",
        type=int,
        default=64,
        help="HNSW efSearch (default: 64, higher = better search recall)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't backup old index (not recommended)"
    )
    
    args = parser.parse_args()
    
    success = migrate_index(
        data_path=args.data_path,
        hnsw_m=args.hnsw_m,
        ef_construction=args.ef_construction,
        ef_search=args.ef_search,
        backup=not args.no_backup
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

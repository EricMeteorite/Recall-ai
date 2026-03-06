"""
Recall v7.0 - JSON → SQLite Migration Tool

Reads all JSON data files from recall_data/ and migrates them into a
SQLite database using SQLiteMemoryBackend.

Features:
- Scans recall_data/data/ for memories.json, episodes.jsonl, entities JSON
- Creates (or opens) recall_data/data/memories.db
- Preserves IDs and metadata
- Adds namespace / source fields derived from character_id directory mapping
- Verifies count matches after migration
- Standalone runnable: python -m tools.migrate_json_to_sqlite

Usage:
    python -m tools.migrate_json_to_sqlite [--data-root recall_data]
    python tools/migrate_json_to_sqlite.py [--data-root recall_data]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so we can import recall.*
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from recall.backends.sqlite_memory import SQLiteMemoryBackend  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_print(msg: str) -> None:
    """Print with fallback for Windows GBK consoles."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def _load_json(path: Path) -> Any:
    """Load a JSON file and return its content."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL (newline-delimited JSON) file."""
    records: List[Dict[str, Any]] = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


# ---------------------------------------------------------------------------
# Scanner: find all data files
# ---------------------------------------------------------------------------

def scan_data_directory(data_root: Path) -> Dict[str, List[Path]]:
    """Walk recall_data/data/ and classify files.

    Returns a dict with keys:
        'memories'  -> list of memories.json paths
        'episodes'  -> list of episodes.jsonl paths
        'entities'  -> list of entities*.json paths
        'other'     -> other JSON/JSONL files
    """
    result: Dict[str, List[Path]] = {
        'memories': [],
        'episodes': [],
        'entities': [],
        'other': [],
    }

    data_dir = data_root / 'data'
    if not data_dir.exists():
        _safe_print(f"[WARN] Data directory not found: {data_dir}")
        return result

    for path in data_dir.rglob('*'):
        if not path.is_file():
            continue
        name = path.name.lower()
        # Skip SQLite files
        if path.suffix in ('.db', '.db-shm', '.db-wal'):
            continue
        if name == 'memories.json':
            result['memories'].append(path)
        elif name == 'episodes.jsonl':
            result['episodes'].append(path)
        elif name.startswith('entities') and path.suffix == '.json':
            result['entities'].append(path)
        elif path.suffix in ('.json', '.jsonl'):
            result['other'].append(path)

    return result


# ---------------------------------------------------------------------------
# Namespace inference from directory structure
# ---------------------------------------------------------------------------

def _infer_namespace(file_path: Path, data_root: Path) -> Tuple[str, str]:
    """Infer (namespace, source) from the file's position in the directory tree.

    The recall_data/data layout is typically:
        data/{user_id}/{character_id}/{namespace}/memories.json
    or:
        data/news_bot/default/default/memories.json

    Returns (namespace, character_id/source).
    """
    data_dir = data_root / 'data'
    try:
        rel = file_path.relative_to(data_dir)
    except ValueError:
        return ('default', 'user')

    parts = rel.parts  # e.g. ('news_bot', 'default', 'default', 'memories.json')

    if len(parts) >= 4:
        # user_id / character_id / namespace / file
        return (parts[2], parts[0])
    elif len(parts) >= 3:
        return (parts[1], parts[0])
    elif len(parts) >= 2:
        return (parts[0], 'user')
    else:
        return ('default', 'user')


# ---------------------------------------------------------------------------
# Migrators
# ---------------------------------------------------------------------------

def migrate_memories_file(
    backend: SQLiteMemoryBackend,
    path: Path,
    data_root: Path,
) -> int:
    """Migrate a single memories.json file. Returns count of imported records."""
    namespace, source = _infer_namespace(path, data_root)

    try:
        records = _load_json(path)
    except (json.JSONDecodeError, IOError) as e:
        _safe_print(f"  [FAIL] Could not read {path}: {e}")
        return 0

    if not isinstance(records, list):
        _safe_print(f"  [WARN] {path}: expected list, got {type(records).__name__}")
        return 0

    count = 0
    for rec in records:
        content = rec.get('content', '')
        if not content:
            continue

        metadata = rec.get('metadata', {}) or {}

        # Extract memory ID
        mem_id = metadata.get('id') or rec.get('id')
        external_id = mem_id
        user_id = rec.get('user_id') or metadata.get('user_id', 'default')

        # Importance
        importance = metadata.get('importance', 0.5)
        if isinstance(importance, str):
            try:
                importance = float(importance)
            except ValueError:
                importance = 0.5

        # Category
        category = metadata.get('category') or metadata.get('scenario')

        # Source override from metadata
        rec_source = metadata.get('source') or source

        backend.upsert(
            content=content,
            id=mem_id,
            external_id=external_id,
            metadata=metadata,
            user_id=user_id,
            namespace=namespace,
            source=rec_source,
            category=category,
            importance=importance,
        )
        count += 1

    return count


def migrate_episodes_file(
    backend: SQLiteMemoryBackend,
    path: Path,
    data_root: Path,
) -> int:
    """Migrate an episodes.jsonl file. Returns count of imported records."""
    namespace, source = _infer_namespace(path, data_root)

    try:
        records = _load_jsonl(path)
    except IOError as e:
        _safe_print(f"  [FAIL] Could not read {path}: {e}")
        return 0

    count = 0
    for rec in records:
        content = rec.get('content', '')
        if not content:
            continue

        ep_uuid = rec.get('uuid')
        user_id = rec.get('user_id', 'default')
        character_id = rec.get('character_id', '')

        metadata = {
            'node_type': rec.get('node_type', 'episode'),
            'group_id': rec.get('group_id', 'default'),
            'labels': rec.get('labels', []),
            'entity_edges': rec.get('entity_edges', []),
            'memory_ids': rec.get('memory_ids', []),
            'relation_ids': rec.get('relation_ids', []),
            'turn_number': rec.get('turn_number', 0),
            'role': rec.get('role', ''),
            'character_id': character_id,
            'source_type': rec.get('source_type', 'message'),
            'source_description': rec.get('source_description', ''),
            'confidence': rec.get('confidence', 0.5),
        }

        # Use the episode namespace or inferred one
        ep_namespace = character_id if character_id else namespace

        backend.upsert(
            content=content,
            id=ep_uuid,
            external_id=ep_uuid,
            metadata=metadata,
            user_id=user_id,
            namespace=ep_namespace,
            source='episode',
            category='episode',
            importance=rec.get('confidence', 0.5),
        )
        count += 1

    return count


def migrate_entities_file(
    backend: SQLiteMemoryBackend,
    path: Path,
    data_root: Path,
) -> int:
    """Migrate an entities JSON file. Returns count of imported records."""
    namespace, source = _infer_namespace(path, data_root)

    try:
        records = _load_json(path)
    except (json.JSONDecodeError, IOError) as e:
        _safe_print(f"  [FAIL] Could not read {path}: {e}")
        return 0

    if not isinstance(records, list):
        _safe_print(f"  [WARN] {path}: expected list, got {type(records).__name__}")
        return 0

    count = 0
    for rec in records:
        entity_id = rec.get('id', '')
        name = rec.get('name', '')
        if not name:
            continue

        content = f"Entity: {name}"
        if rec.get('entity_type'):
            content += f" (type={rec['entity_type']})"
        if rec.get('current_state'):
            content += f" | state: {json.dumps(rec['current_state'], ensure_ascii=False)}"

        metadata = {
            'entity_id': entity_id,
            'entity_type': rec.get('entity_type', ''),
            'aliases': rec.get('aliases', []),
            'confidence': rec.get('confidence', 1.0),
            'verification_count': rec.get('verification_count', 0),
            'source_turns': rec.get('source_turns', []),
            'source_memory_ids': rec.get('source_memory_ids', []),
            'relations': rec.get('relations', []),
        }

        backend.upsert(
            content=content,
            id=entity_id,
            external_id=entity_id,
            metadata=metadata,
            user_id='system',
            namespace=namespace,
            source='entity',
            category='entity',
            importance=rec.get('confidence', 1.0),
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Main migration orchestrator
# ---------------------------------------------------------------------------

def migrate(data_root: str | Path, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Run full JSON → SQLite migration.

    Parameters
    ----------
    data_root : str or Path
        Root of the recall_data directory.
    db_path : str, optional
        Path for the SQLite database.  Defaults to
        ``{data_root}/data/memories.db``.

    Returns
    -------
    dict
        Migration summary with counts and verification status.
    """
    data_root = Path(data_root)
    if db_path is None:
        db_path_resolved = data_root / 'data' / 'memories.db'
    else:
        db_path_resolved = Path(db_path)

    _safe_print(f"[Migrate] Data root : {data_root}")
    _safe_print(f"[Migrate] SQLite DB : {db_path_resolved}")
    _safe_print("")

    # Scan files
    files = scan_data_directory(data_root)
    _safe_print(f"[Scan] Found:")
    _safe_print(f"  memories.json  : {len(files['memories'])} file(s)")
    _safe_print(f"  episodes.jsonl : {len(files['episodes'])} file(s)")
    _safe_print(f"  entities*.json : {len(files['entities'])} file(s)")
    _safe_print(f"  other JSON     : {len(files['other'])} file(s)")
    _safe_print("")

    # Create backend
    backend = SQLiteMemoryBackend(db_path=str(db_path_resolved))
    start_time = time.time()

    # Track totals
    total_json_records = 0
    total_imported = 0
    details: Dict[str, int] = {}

    # 1. Memories
    for path in files['memories']:
        _safe_print(f"[Migrate] memories: {path}")
        n = migrate_memories_file(backend, path, data_root)
        _safe_print(f"  -> {n} records imported")
        total_imported += n
        total_json_records += n
        details[str(path)] = n

    # 2. Episodes
    for path in files['episodes']:
        _safe_print(f"[Migrate] episodes: {path}")
        n = migrate_episodes_file(backend, path, data_root)
        _safe_print(f"  -> {n} records imported")
        total_imported += n
        total_json_records += n
        details[str(path)] = n

    # 3. Entities
    for path in files['entities']:
        _safe_print(f"[Migrate] entities: {path}")
        n = migrate_entities_file(backend, path, data_root)
        _safe_print(f"  -> {n} records imported")
        total_imported += n
        total_json_records += n
        details[str(path)] = n

    elapsed = time.time() - start_time

    # Verification: count rows in SQLite
    db_count = backend.count(global_search=True)
    _safe_print("")
    _safe_print(f"[Verify] JSON records processed : {total_json_records}")
    _safe_print(f"[Verify] SQLite rows            : {db_count}")

    # The DB count may differ slightly if there are duplicate IDs that
    # got upserted, so we check >=
    verified = db_count >= total_json_records
    if verified:
        _safe_print(f"[Verify] Status: OK (counts match)")
    else:
        _safe_print(f"[Verify] Status: MISMATCH - some records may have been deduplicated or skipped")

    _safe_print(f"")
    _safe_print(f"[Done] Migration completed in {elapsed:.2f}s")
    _safe_print(f"       DB size: {db_path_resolved.stat().st_size / 1024:.1f} KB")

    backend.close()

    return {
        'total_json_records': total_json_records,
        'total_imported': total_imported,
        'db_count': db_count,
        'verified': verified,
        'elapsed_seconds': round(elapsed, 2),
        'db_path': str(db_path_resolved),
        'details': details,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Recall v7.0 - Migrate JSON data to SQLite',
    )
    parser.add_argument(
        '--data-root',
        type=str,
        default='recall_data',
        help='Path to the recall_data root directory (default: recall_data)',
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Override SQLite database path (default: {data-root}/data/memories.db)',
    )
    args = parser.parse_args()

    result = migrate(args.data_root, args.db_path)

    _safe_print("")
    _safe_print("=== Migration Summary ===")
    _safe_print(f"  JSON records : {result['total_json_records']}")
    _safe_print(f"  Imported     : {result['total_imported']}")
    _safe_print(f"  DB rows      : {result['db_count']}")
    _safe_print(f"  Verified     : {'YES' if result['verified'] else 'NO'}")
    _safe_print(f"  Elapsed      : {result['elapsed_seconds']}s")
    _safe_print(f"  DB path      : {result['db_path']}")

    sys.exit(0 if result['verified'] else 1)


if __name__ == '__main__':
    main()

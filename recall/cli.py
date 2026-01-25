"""Recall CLI - 命令行接口"""

import os
import sys
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .version import __version__

# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))




console = Console()


@click.group()
@click.version_option(version=__version__, prog_name='Recall')
def main():
    """Recall - 智能记忆管理系统
    
    支持多场景的持久化记忆存储、检索和管理。
    """
    pass


@main.command()
@click.option('--data-root', '-d', default=None, help='数据存储目录')
@click.option('--lightweight', '-l', is_flag=True, help='使用轻量模式')
def init(data_root, lightweight):
    """初始化 Recall 环境"""
    from .init import RecallInit
    
    console.print(Panel.fit(
        f"[bold blue]Recall v{__version__}[/bold blue]\n初始化向导",
        title="🧠 Recall"
    ))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("创建目录结构...", total=None)
        
        # RecallInit 使用类方法，不需要实例化
        actual_root = RecallInit.ensure_directories(data_root)
        
        progress.update(task, description="设置环境变量...")
        RecallInit.setup_environment(data_root)
        
        progress.update(task, description="完成!")
    
    console.print("\n[green]✓[/green] 初始化完成!")
    console.print(f"  数据目录: {actual_root}")
    
    if not lightweight:
        console.print("\n[yellow]提示:[/yellow] 首次运行可能需要下载模型，请确保网络连接。")


@main.command()
@click.argument('content')
@click.option('--user', '-u', default='default', help='用户ID')
@click.option('--metadata', '-m', default=None, help='元数据 (JSON)')
def add(content, user, metadata):
    """添加记忆"""
    import json
    from .engine import RecallEngine
    
    meta = json.loads(metadata) if metadata else None
    
    with console.status("添加记忆..."):
        engine = RecallEngine(lightweight=True)
        result = engine.add(content, user_id=user, metadata=meta)
    
    if result.success:
        console.print(f"[green]✓[/green] 记忆添加成功")
        console.print(f"  ID: {result.id}")
        if result.entities:
            console.print(f"  实体: {', '.join(result.entities)}")
    else:
        console.print(f"[red]✗[/red] {result.message}")


@main.command()
@click.argument('query')
@click.option('--user', '-u', default='default', help='用户ID')
@click.option('--top-k', '-k', default=5, help='返回数量')
def search(query, user, top_k):
    """搜索记忆"""
    from .engine import RecallEngine
    
    with console.status("搜索中..."):
        engine = RecallEngine(lightweight=True)
        results = engine.search(query, user_id=user, top_k=top_k)
    
    if not results:
        console.print("[yellow]未找到相关记忆[/yellow]")
        return
    
    table = Table(title=f"搜索结果 ({len(results)})")
    table.add_column("ID", style="dim")
    table.add_column("内容", max_width=50)
    table.add_column("分数", justify="right")
    table.add_column("实体")
    
    for r in results:
        content = r.content[:50] + "..." if len(r.content) > 50 else r.content
        entities = ", ".join(r.entities[:3]) if r.entities else "-"
        table.add_row(r.id[:12], content, f"{r.score:.2f}", entities)
    
    console.print(table)


@main.command()
@click.option('--user', '-u', default='default', help='用户ID')
@click.option('--limit', '-l', default=10, help='显示数量')
def list(user, limit):
    """列出记忆"""
    from .engine import RecallEngine
    
    with console.status("获取记忆..."):
        engine = RecallEngine(lightweight=True)
        memories = engine.get_all(user_id=user, limit=limit)
    
    if not memories:
        console.print("[yellow]暂无记忆[/yellow]")
        return
    
    table = Table(title=f"记忆列表 (用户: {user})")
    table.add_column("ID", style="dim")
    table.add_column("内容", max_width=60)
    table.add_column("创建时间")
    
    import time
    for m in memories:
        content = m.get('content', m.get('memory', ''))[:60]
        created = m.get('created_at', 0)
        created_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(created)) if created else '-'
        table.add_row(m.get('id', '-')[:12], content, created_str)
    
    console.print(table)


@main.command()
@click.argument('memory_id')
@click.option('--user', '-u', default='default', help='用户ID')
def delete(memory_id, user):
    """删除记忆"""
    from .engine import RecallEngine
    
    engine = RecallEngine(lightweight=True)
    success = engine.delete(memory_id, user_id=user)
    
    if success:
        console.print(f"[green]✓[/green] 记忆 {memory_id} 已删除")
    else:
        console.print(f"[red]✗[/red] 删除失败")


@main.command()
def stats():
    """显示统计信息"""
    from .engine import RecallEngine
    
    with console.status("获取统计..."):
        engine = RecallEngine(lightweight=True)
        stats = engine.get_stats()
    
    console.print(Panel.fit(
        f"[bold]Recall v{stats['version']}[/bold]\n"
        f"数据目录: {stats['data_root']}\n"
        f"轻量模式: {'是' if stats['lightweight'] else '否'}\n"
        f"用户数: {stats['storage']['scopes']}\n"
        f"活跃伏笔: {stats['foreshadowings']['active']}",
        title="📊 统计信息"
    ))


@main.command()
@click.option('--host', '-h', default='127.0.0.1', help='监听地址')
@click.option('--port', '-p', default=18888, help='监听端口')
@click.option('--reload', '-r', is_flag=True, help='开发模式（自动重载）')
def serve(host, port, reload):
    """启动 API 服务器"""
    console.print(f"[bold blue]启动 Recall API 服务器[/bold blue]")
    console.print(f"地址: http://{host}:{port}")
    console.print(f"文档: http://{host}:{port}/docs")
    
    import uvicorn
    uvicorn.run(
        "recall.server:app",
        host=host,
        port=port,
        reload=reload
    )


@main.command()
@click.option('--user', '-u', default='default', help='用户ID')
def consolidate(user):
    """执行记忆整合"""
    from .engine import RecallEngine
    
    with console.status("整合中..."):
        engine = RecallEngine(lightweight=True)
        engine.consolidate(user_id=user)
    
    console.print("[green]✓[/green] 记忆整合完成")


@main.command()
@click.option('--user', '-u', default=None, help='用户ID（不指定则重置全部）')
@click.option('--confirm', is_flag=True, help='确认重置')
def reset(user, confirm):
    """重置记忆（谨慎使用）"""
    if not confirm:
        console.print("[yellow]警告：此操作将清除记忆数据！[/yellow]")
        console.print("添加 --confirm 参数确认操作")
        return
    
    from .engine import RecallEngine
    
    engine = RecallEngine(lightweight=True)
    engine.reset(user_id=user)
    
    if user:
        console.print(f"[green]✓[/green] 用户 {user} 的记忆已重置")
    else:
        console.print("[green]✓[/green] 所有记忆已重置")


@main.group()
def foreshadowing():
    """伏笔管理"""
    pass


@foreshadowing.command('plant')
@click.argument('content')
@click.option('--importance', '-i', default=0.5, help='重要性 (0-1)')
def plant_foreshadowing(content, importance):
    """埋下伏笔"""
    from .engine import RecallEngine
    
    engine = RecallEngine(lightweight=True)
    fsh = engine.plant_foreshadowing(content, importance=importance)
    
    console.print(f"[green]✓[/green] 伏笔已埋下")
    console.print(f"  ID: {fsh.id}")


@foreshadowing.command('list')
def list_foreshadowing():
    """列出活跃伏笔"""
    from .engine import RecallEngine
    
    engine = RecallEngine(lightweight=True)
    active = engine.get_active_foreshadowings()
    
    if not active:
        console.print("[yellow]暂无活跃伏笔[/yellow]")
        return
    
    table = Table(title="活跃伏笔")
    table.add_column("ID", style="dim")
    table.add_column("内容", max_width=50)
    table.add_column("状态")
    table.add_column("重要性", justify="right")
    
    for f in active:
        content = f.content[:50] + "..." if len(f.content) > 50 else f.content
        table.add_row(f.id[:12], content, f.status.value, f"{f.importance:.1f}")
    
    console.print(table)


@foreshadowing.command('resolve')
@click.argument('foreshadowing_id')
@click.argument('resolution')
def resolve_foreshadowing(foreshadowing_id, resolution):
    """解决伏笔"""
    from .engine import RecallEngine
    
    engine = RecallEngine(lightweight=True)
    success = engine.resolve_foreshadowing(foreshadowing_id, resolution)
    
    if success:
        console.print(f"[green]✓[/green] 伏笔已解决")
    else:
        console.print(f"[red]✗[/red] 解决失败（伏笔不存在？）")


if __name__ == '__main__':
    main()

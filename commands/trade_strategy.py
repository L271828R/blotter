# ═══════════════════════════════════════════════════════════════════
# commands/trade_strategy.py - Strategy management functionality
# ═══════════════════════════════════════════════════════════════════

import typer
from config import add_strategy, list_strategies
from commands import cfg

def add_strategy_command(
    name: str,
    strategy_type: str = typer.Option("single_leg", help="Strategy type: single_leg, bull_put_spread, bear_call_spread"),
    default_type: str = typer.Option(None, help="Default trade type: FUTURE, OPTION"),
    default_side: str = typer.Option(None, help="Default side: BUY, SELL")
):
    """Add a new strategy to configuration"""
    add_strategy(name, strategy_type, default_type, default_side)

def fix_strategy_command(
    name: str,
    strategy_type: str = typer.Option(help="New strategy type: single_leg, bull_put_spread, bear_call_spread")
):
    """Fix strategy type after migration"""
    # Since fix_strategy_type doesn't exist, we'll implement it here
    import rich
    from config import load_config, save_config
    
    cfg = load_config()
    
    if name not in cfg.get("strategies", {}):
        rich.print(f"[red]Strategy '{name}' not found in configuration[/]")
        return
    
    cfg["strategies"][name]["type"] = strategy_type
    save_config(cfg)
    
    rich.print(f"[green]✓ Updated strategy '{name}' to type '{strategy_type}'[/]")

def list_strategies_command(
    strategy_type: str = typer.Option(None, help="Filter by type: single_leg, bull_put_spread, bear_call_spread")
):
    """List configured strategies"""
    list_strategies(cfg, strategy_type)

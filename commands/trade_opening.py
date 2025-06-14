# ═══════════════════════════════════════════════════════════════════
# commands/trade_opening.py - Trade opening functionality
# ═══════════════════════════════════════════════════════════════════

import typer
import rich
import sys
import os

from commands import cfg, book, trade_ops, stopwatch_manager

from core.config import get_strategy_type

from .trade_utils import (
    get_historical_timestamp, 
    is_option_strategy, 
    is_option_trade, 
    check_historical_blocks, 
    check_current_blocks, 
    handle_stopwatch
)

# FZF helper import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fzf_helper import select_strategy, check_fzf_installed

def open_trade(
    strat: str = typer.Option(None, help="Strategy"),
    typ: str = typer.Option(None, help="FUTURE or OPTION"),
    side: str = typer.Option(None, help="BUY or SELL"),
    symbol: str = typer.Option(None, help="Ticker"),
    qty: int = typer.Option(None, help="Contracts"),
    price: str = typer.Option(None, help="Fill price"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Test mode: don't save trade"),
    stopwatch: int = typer.Option(None, "--stopwatch", help="Start stopwatch timer (1 or 2 hours)"),
    historical: bool = typer.Option(False, "--historical", help="Enter historical trade with custom time"),
):
    """Open a new trade with enhanced strategy handling"""
    # Check if globals are properly set
    if cfg is None or book is None or trade_ops is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    
    # Show dry run notice
    if dry_run:
        rich.print("[bold yellow]🧪 DRY RUN MODE - Trade will not be saved[/]")
        rich.print()

    # Show historical mode notice
    if historical:
        rich.print("[bold cyan]📅 HISTORICAL MODE - Enter trade with custom timestamp[/]")
        rich.print()

    # Strategy selection with FZF or fallback
    if not strat:
        # Try FZF first, then fallback to traditional prompt
        rich.print("[cyan]🔍 Opening strategy selection with FZF...[/]")
        strat = select_strategy(book, config_path="strategies.txt", allow_custom=True)
        
        if strat:
            rich.print(f"[green]✓ Selected strategy via FZF: '{strat}'[/]")
        else:
            rich.print("[yellow]No strategy selected via FZF, falling back to prompt[/]")
            # Fallback to listing available strategies
            strategies = cfg.get("strategies", {})
            if strategies:
                strategy_names = sorted(strategies.keys())
                rich.print(f"[green]Available strategies:[/] {', '.join(strategy_names)}")
                strat = typer.prompt("Strategy")
            else:
                rich.print("[red]No strategies configured[/]")
                return
    else:
        rich.print(f"[green]✓ Strategy provided via command line: '{strat}'[/]")
    
    # Get strategy metadata
    strategy_info = get_strategy_type(strat, cfg)
    strategy_type = strategy_info["type"]
    
    rich.print(f"\n[cyan]📋 Strategy Analysis:[/]")
    rich.print(f"[cyan]  Name: {strat}[/]")
    rich.print(f"[cyan]  Type: {strategy_type}[/]") 
    rich.print(f"[cyan]  Default Trade Type: {strategy_info['default_type']}[/]")
    rich.print(f"[cyan]  Default Side: {strategy_info['default_side']}[/]")

    # Validate strategy exists in config
    strategies = cfg.get("strategies", {})
    if strat not in strategies:
        rich.print(f"[red]❌ Unknown strategy: {strat!r}[/]")
        rich.print(f"[yellow]Available strategies: {', '.join(sorted(strategies.keys()))}[/]")
        return

    # Handle historical trade entry
    custom_entry_time = None
    custom_entry_date = None
    
    if historical:
        custom_entry_time, custom_entry_date = get_historical_timestamp()
        
        # Check if historical time would have been blocked (informational)
        if not dry_run and is_option_strategy(strategy_type, typ):
            check_historical_blocks(custom_entry_time, strat, cfg)
    
    else:
        # Normal (live) trade - check blocks as usual
        if not dry_run and is_option_strategy(strategy_type, typ):
            if check_current_blocks(strat, cfg):
                return  # Blocked

    # Route to appropriate trade opening method based on strategy type
    trade = None
    
    rich.print(f"\n[bold]🚀 Opening {strategy_type.replace('_', ' ').title()}...[/]")
    
    if strategy_type == "bull_put_spread":
        # Get quantity for spread
        qty = qty or int(typer.prompt("Number of spreads", default="1"))
        
        rich.print(f"[cyan]Routing to Bull Put Spread handler...[/]")
        trade = trade_ops.open_bull_put_spread_enhanced(
            qty=qty, 
            strat=strat, 
            dry_run=dry_run,
            custom_entry_time=custom_entry_time,
            custom_entry_date=custom_entry_date
        )
        
    elif strategy_type == "bear_call_spread":
        # Get quantity for spread
        qty = qty or int(typer.prompt("Number of spreads", default="1"))
        
        rich.print(f"[cyan]Routing to Bear Call Spread handler...[/]")
        trade = trade_ops.open_bear_call_spread_enhanced(
            qty=qty,
            strat=strat, 
            dry_run=dry_run,
            custom_entry_time=custom_entry_time,
            custom_entry_date=custom_entry_date
        )
        
    else:  # single_leg
        rich.print(f"[cyan]Routing to Single Leg handler...[/]")
        
        # Use strategy defaults to reduce prompting
        typ = typ or strategy_info["default_type"]
        side = side or strategy_info["default_side"]
        
        # Prompt for any missing required fields
        if not typ:
            typ = typer.prompt("Type (FUTURE/OPTION)", default="FUTURE")
        if not side:
            side = typer.prompt("Side (BUY/SELL)", default="BUY")
        
        symbol = symbol or typer.prompt("Symbol")
        qty = qty or int(typer.prompt("Quantity", default="1"))
        price = price or typer.prompt("Entry price")
        
        rich.print(f"[dim]Using defaults from strategy: {typ} {side}[/]")
        
        trade = trade_ops.open_single_leg_trade(
            strat=strat, 
            typ=typ, 
            side=side, 
            symbol=symbol, 
            qty=qty, 
            price=price,
            dry_run=dry_run,
            custom_entry_time=custom_entry_time,
            custom_entry_date=custom_entry_date
        )
    
    # Start stopwatch if requested and it's an option trade (only for live trades)
    if trade and not dry_run and not historical and is_option_trade(trade):
        handle_stopwatch(trade, stopwatch)
    elif historical and trade and is_option_trade(trade):
        rich.print("[dim]Note: No stopwatch started for historical trades[/]")

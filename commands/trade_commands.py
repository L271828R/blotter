# ═══════════════════════════════════════════════════════════════════
# commands/trade_commands.py - Main trade commands module (refactored)
# ═══════════════════════════════════════════════════════════════════

import typer
import rich

from commands import cfg, book, trade_ops, stopwatch_manager
from .trade_opening import open_trade
from .trade_closing import close_trade, expire_spread, expire_leg, close_single_leg
from .trade_management import fix_trade_prices, delete_trade, find_trade
from .trade_strategy import add_strategy_command, fix_strategy_command, list_strategies_command
from .trade_utils import (
    get_historical_timestamp, 
    is_option_strategy, 
    is_option_trade, 
    check_historical_blocks, 
    check_current_blocks, 
    handle_stopwatch,
    calculate_leg_pnl
)

trade_app = typer.Typer()

# Register all commands
trade_app.command("open")(open_trade)
trade_app.command("close")(close_trade)
trade_app.command("close-leg")(close_single_leg)
trade_app.command("expire-spread")(expire_spread)
trade_app.command("expire-leg")(expire_leg)
trade_app.command("fix")(fix_trade_prices)
trade_app.command("delete")(delete_trade)
trade_app.command("add-strategy")(add_strategy_command)
trade_app.command("fix-strategy")(fix_strategy_command)
trade_app.command("list-strategies")(list_strategies_command)

@trade_app.command("ls")
def ls_command():
    """List all trades"""
    if book is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    from ls import list_trades
    list_trades(book)

@trade_app.command("pnl2h")
def record_2h_pnl(trade_id: str = typer.Option(None, help="Trade ID to record 2H PnL for")):
    """Record 2-hour PnL for a trade (required for BULL-PUT-OVERNIGHT before closing)"""
    rich.print("2H PnL recording not yet implemented in modules")

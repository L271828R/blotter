# Updated blotter.py - Import and use the ls module
"""
Updated main blotter.py that imports the ls functionality
"""

from __future__ import annotations
import typer
import rich
import datetime as dt

# Import our separated modules
from models import Risk, Leg, Trade
from config import load_config
from persistence import load_book, save_book, import_inbox_files
from utils import blocked_for_options
from trade_operations import TradeOperations
from ls import list_trades  # Import the list_trades function

# ───────── Setup ──────────
app = typer.Typer()

# Load configuration and data
cfg = load_config()
book = load_book()
added = import_inbox_files(book)
if added > 0:
    save_book(book)

# Create trade operations handler
trade_ops = TradeOperations(book, cfg)

@app.command("ls")
def ls_command():
    """List all trades"""
    list_trades(book)  # Call the function from ls.py

@app.command("close")
def close_trade(
    trade_id: str,
    qty: int = typer.Option(None, help="Quantity to close (partial close)")
):
    """Close a trade completely or partially"""
    trade_ops.close_trade_partial(trade_id, qty)

@app.command("open")
def open_trade(
    strat: str | None = typer.Option(None, help="Strategy"),
    typ: str | None = typer.Option(None, help="FUTURE or OPTION"),
    side: str | None = typer.Option(None, help="BUY or SELL"),
    symbol: str | None = typer.Option(None, help="Ticker"),
    qty: int | None = typer.Option(None, help="Contracts"),
    price: str | None = typer.Option(None, help="Fill price"),
):
    """Open a new trade"""
    # Enforce configured strategies
    allowed = {s.upper() for s in cfg.get("strategies", [])}
    while True:
        if not strat:
            strat = typer.prompt(f"Strategy ({', '.join(sorted(allowed))})")
        u = strat.upper()
        if u in allowed:
            break
        rich.print(f"[red]Unknown strategy: {strat!r}[/]")
        rich.print(f"[green]Valid strategies are:[/] {', '.join(sorted(allowed))}")
        strat = None  # force re-prompt

    # Handle spread strategies
    if u == "BULL-PUT":
        trade_ops.open_bull_put_spread(qty, strat)
    elif u == "BULL-PUT-OVERNIGHT":
        trade_ops.open_bull_put_spread(qty, u)
    elif u == "BEAR-CALL":
        trade_ops.open_bear_call_spread(qty)
    else:
        # Handle single-leg trades
        typ = typ or typer.prompt("Type", default="FUTURE")
        side = side or typer.prompt("Side", default="BUY")
        symbol = symbol or typer.prompt("Symbol")
        qty = qty or int(typer.prompt("Quantity", default="1"))
        price = price or typer.prompt("Entry price")
        
        trade_ops.open_single_leg_trade(strat, typ, side, symbol, qty, price)

@app.command("blocks")
def show_option_blocks():
    """Show current option block configuration and status"""
    rich.print("[bold]Option Trading Blocks[/]")
    
    now = dt.datetime.now().time()
    is_blocked, active_block = blocked_for_options(cfg)
    
    if is_blocked:
        rich.print(f"[red]🚫 Currently BLOCKED: {active_block}[/]")
    else:
        rich.print("[green]✅ Options trading currently ALLOWED[/]")
    
    rich.print("\n[bold]Configured Blocks:[/]")
    
    # Handle legacy configuration
    if "option_block" in cfg:
        start = cfg["option_block"]["start"]
        end = cfg["option_block"]["end"]
        name = cfg["option_block"].get("name", "Legacy Block")
        rich.print(f"  • {name}: {start} - {end}")
    
    # Handle new configuration
    if "option_blocks" in cfg:
        for block in cfg["option_blocks"]:
            start = block["start"]
            end = block["end"]
            name = block.get("name", "Unnamed Block")
            
            # Check if this block is currently active
            start_time = dt.time.fromisoformat(start)
            end_time = dt.time.fromisoformat(end)
            
            is_active = False
            if start_time > end_time:  # Overnight block
                is_active = now >= start_time or now <= end_time
            else:
                is_active = start_time <= now <= end_time
            
            status = " [red](ACTIVE)[/]" if is_active else ""
            rich.print(f"  • {name}: {start} - {end}{status}")

if __name__ == "__main__":
    app()

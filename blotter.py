# ═══════════════════════════════════════════════════════════════════
# Complete blotter.py - Main application with all commands
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations
import typer
import rich
import datetime as dt

from models import Risk, Leg, Trade, CommissionFees
from config import load_config
from persistence import load_book, save_book, import_inbox_files
from utils import blocked_for_options, to_decimal, calculate_costs
from ls import list_trades
from recalc import recalc_trade_pnl, recalc_all_trades, fix_data_types
from audit import audit_trade, audit_all_positions

app = typer.Typer()

cfg = load_config()
book = load_book()

def fix_legacy_commission_format():
    """Fix legacy commission format"""
    needs_save = False
    
    for trade in book:
        for leg in trade.legs:
            if isinstance(leg.entry_costs, dict):
                leg.entry_costs = CommissionFees(
                    commission=to_decimal(leg.entry_costs.get("commission", "0")),
                    exchange_fees=to_decimal(leg.entry_costs.get("exchange_fees", "0")),
                    regulatory_fees=to_decimal(leg.entry_costs.get("regulatory_fees", "0"))
                )
                needs_save = True
            
            if isinstance(leg.exit_costs, dict):
                leg.exit_costs = CommissionFees(
                    commission=to_decimal(leg.exit_costs.get("commission", "0")),
                    exchange_fees=to_decimal(leg.exit_costs.get("exchange_fees", "0")),
                    regulatory_fees=to_decimal(leg.exit_costs.get("regulatory_fees", "0"))
                )
                needs_save = True
    
    if needs_save:
        save_book(book)

fix_legacy_commission_format()

added = import_inbox_files(book)
if added > 0:
    save_book(book)

# Create trade operations handler (you'll need to create this file too)
from trade_operations import TradeOperations
trade_ops = TradeOperations(book, cfg)

@app.command("open")
def open_trade(
    strat: str = typer.Option(None, help="Strategy"),
    typ: str = typer.Option(None, help="FUTURE or OPTION"),
    side: str = typer.Option(None, help="BUY or SELL"),
    symbol: str = typer.Option(None, help="Ticker"),
    qty: int = typer.Option(None, help="Contracts"),
    price: str = typer.Option(None, help="Fill price"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Test mode: override blocks and don't save trade"),
):
    """Open a new trade"""
    # Show dry run notice
    if dry_run:
        rich.print("[bold yellow]🧪 DRY RUN MODE - Trade will not be saved and blocks are ignored[/]")
        rich.print()

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
        trade_ops.open_bull_put_spread(qty, strat, dry_run=dry_run)
    elif u == "BULL-PUT-OVERNIGHT":
        trade_ops.open_bull_put_spread(qty, u, dry_run=dry_run)
    elif u == "BEAR-CALL":
        trade_ops.open_bear_call_spread(qty, dry_run=dry_run)
    else:
        # Handle single-leg trades
        typ = typ or typer.prompt("Type", default="FUTURE")
        side = side or typer.prompt("Side", default="BUY")
        symbol = symbol or typer.prompt("Symbol")
        qty = qty or int(typer.prompt("Quantity", default="1"))
        price = price or typer.prompt("Entry price")
        
        trade_ops.open_single_leg_trade(strat, typ, side, symbol, qty, price, dry_run=dry_run)

@app.command("close")
def close_trade(
    trade_id: str,
    qty: int = typer.Option(None, help="Quantity to close (partial close)")
):
    """Close a trade completely or partially"""
    trade_ops.close_trade_partial(trade_id, qty)

@app.command("pnl2h")
def record_2h_pnl(trade_id: str = typer.Option(None, help="Trade ID to record 2H PnL for")):
    """Record 2-hour PnL for a trade (required for BULL-PUT-OVERNIGHT before closing)"""
    # You'll need to implement this - similar to your original code
    rich.print("2H PnL recording not yet implemented in modules")

@app.command("fix")
def fix_trade_prices(trade_id: str):
    """Manually fix trade prices and recalculate PnL"""
    
    # Find the trade
    trade = None
    for t in book:
        if t.id == trade_id:
            trade = t
            break
    
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return
    
    rich.print(f"[cyan]Fixing prices for trade {trade_id}[/]")
    rich.print(f"Trade: {trade.strat} - {trade.typ}")
    
    # Show current leg details and allow editing
    for i, leg in enumerate(trade.legs):
        rich.print(f"\n[bold]Leg {i+1}: {leg.side} {leg.qty} {leg.symbol}[/]")
        rich.print(f"  Current entry: ${leg.entry}")
        
        # Ask if they want to update entry price
        if typer.confirm(f"Update entry price for {leg.symbol}?"):
            new_entry = to_decimal(typer.prompt("New entry price"))
            leg.entry = new_entry
            rich.print(f"  ✓ Updated entry to ${new_entry}")
        
        # If trade is closed, allow updating exit price
        if leg.exit is not None:
            rich.print(f"  Current exit: ${leg.exit}")
            if typer.confirm(f"Update exit price for {leg.symbol}?"):
                new_exit = to_decimal(typer.prompt("New exit price"))
                leg.exit = new_exit
                rich.print(f"  ✓ Updated exit to ${new_exit}")
    
    # Recalculate and show results
    rich.print(f"\n[cyan]Recalculating PnL...[/]")
    recalc_trade_pnl(trade_id, book, show_details=True)



@app.command("ls")
def ls_command():
    """List all trades"""
    list_trades(book)

@app.command("recalc")
def recalc_pnl(
    trade_id: str = typer.Option(None, help="Trade ID to recalculate (leave empty for all trades)"),
    details: bool = typer.Option(False, "--details", "-d", help="Show detailed breakdown")
):
    """Recalculate PnL for a trade or all trades"""
    fix_data_types(book)
    
    if trade_id:
        recalc_trade_pnl(trade_id, book, show_details=details)
    else:
        if typer.confirm("Recalculate PnL for ALL closed trades?"):
            recalc_all_trades(book)

@app.command("fixdata") 
def fix_data_types_command():
    """Fix data type issues (string PnL values, etc.)"""
    rich.print("[cyan]Checking for data type issues...[/]")
    
    if fix_data_types(book):
        rich.print("[green]✓ Data types fixed and saved[/]")
    else:
        rich.print("[dim]No data type issues found[/]")

@app.command("audit")
def audit_command(
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Specific trade ID to audit"),
    status: str = typer.Option("ALL", "--status", "-s", help="Filter by status: ALL, OPEN, CLOSED")
):
    """Audit trade PnL calculations and costs"""
    if trade_id:
        audit_trade(trade_id, book)
    else:
        audit_all_positions(book, status.upper())

@app.command("addcosts")
def add_missing_costs():
    """Add missing commission and fees to old trades"""
    rich.print("[cyan]Adding missing costs to trades with zero costs...[/]")
    
    updated_count = 0
    
    for trade in book:
        for leg in trade.legs:
            if leg.entry_costs.total() == 0:
                if trade.typ.startswith("OPTION"):
                    trade_type = "OPTION"
                else:
                    trade_type = "FUTURE"
                
                leg.entry_costs = calculate_costs(trade_type, leg.qty, cfg)
                updated_count += 1
                
                rich.print(f"  Added entry costs to {trade.id} leg {leg.symbol}: ${leg.entry_costs.total():.2f}")
            
            if leg.exit is not None and leg.exit_costs is None:
                if trade.typ.startswith("OPTION"):
                    trade_type = "OPTION"
                else:
                    trade_type = "FUTURE"
                
                leg.exit_costs = calculate_costs(trade_type, leg.qty, cfg)
                updated_count += 1
                
                rich.print(f"  Added exit costs to {trade.id} leg {leg.symbol}: ${leg.exit_costs.total():.2f}")
    
    if updated_count > 0:
        rich.print(f"\n[yellow]Updated {updated_count} legs with missing costs[/]")
        rich.print("[yellow]Now recalculating PnL with proper costs...[/]")
        
        for trade in book:
            if trade.status == "CLOSED":
                trade.pnl = trade.net_pnl()
        
        save_book(book)
        rich.print("[green]✓ All costs added and PnL recalculated![/]")
        
        rich.print("\n[bold]Updated trades:[/]")
        for trade in book:
            if trade.status == "CLOSED":
                gross = trade.gross_pnl()
                net = trade.net_pnl()
                costs = trade.total_costs()
                rich.print(f"  {trade.id}: Gross ${gross:.2f} - Costs ${costs:.2f} = Net ${net:.2f}")
    else:
        rich.print("[dim]No missing costs found[/]")

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
    
    def format_time_12h(time_str: str) -> str:
        """Convert 24-hour time string to 12-hour format"""
        time_obj = dt.time.fromisoformat(time_str)
        return dt.datetime.combine(dt.date.today(), time_obj).strftime("%-I:%M %p")
    
    if "option_block" in cfg:
        start = cfg["option_block"]["start"]
        end = cfg["option_block"]["end"]
        name = cfg["option_block"].get("name", "Legacy Block")
        start_12h = format_time_12h(start)
        end_12h = format_time_12h(end)
        rich.print(f"  • {name}: {start_12h} - {end_12h}")
    
    if "option_blocks" in cfg:
        for block in cfg["option_blocks"]:
            start = block["start"]
            end = block["end"]
            name = block.get("name", "Unnamed Block")
            
            start_time = dt.time.fromisoformat(start)
            end_time = dt.time.fromisoformat(end)
            
            is_active = False
            if start_time > end_time:
                is_active = now >= start_time or now <= end_time
            else:
                is_active = start_time <= now <= end_time
            
            start_12h = format_time_12h(start)
            end_12h = format_time_12h(end)
            
            status = " [red](ACTIVE)[/]" if is_active else ""
            rich.print(f"  • {name}: {start_12h} - {end_12h}{status}")

if __name__ == "__main__":
    app()

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
# trade_ops = TradeOperations(book, cfg)

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
    
    if "option_block" in cfg:
        start = cfg["option_block"]["start"]
        end = cfg["option_block"]["end"]
        name = cfg["option_block"].get("name", "Legacy Block")
        rich.print(f"  • {name}: {start} - {end}")
    
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
            
            status = " [red](ACTIVE)[/]" if is_active else ""
            rich.print(f"  • {name}: {start} - {end}{status}")

if __name__ == "__main__":
    app()


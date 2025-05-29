# ═══════════════════════════════════════════════════════════════════
# recalc.py - PnL recalculation functionality
# ═══════════════════════════════════════════════════════════════════

import rich
from rich.table import Table
import typer
import decimal as dec

from utils import calc_trade_pnl, to_decimal
from persistence import save_book, write_single_trade_file

def safe_to_decimal(value):
    """Safely convert any value to Decimal, handling strings and existing Decimals"""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return dec.Decimal(value)
        except (dec.InvalidOperation, ValueError):
            return None
    if isinstance(value, (int, float)):
        return dec.Decimal(str(value))
    if isinstance(value, dec.Decimal):
        return value
    return None

def recalc_trade_pnl(trade_id: str, book: list, show_details: bool = False):
    """Recalculate PnL for a specific trade"""
    
    trade = None
    for t in book:
        if t.id == trade_id:
            trade = t
            break
    
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return False
    
    old_pnl = safe_to_decimal(trade.pnl)
    old_gross = trade.gross_pnl()
    old_costs = trade.total_costs()
    
    if trade.status == "CLOSED":
        trade.pnl = calc_trade_pnl(trade)
        new_pnl = trade.pnl
        new_gross = trade.gross_pnl()
        new_costs = trade.total_costs()
        
        rich.print(f"[cyan]Recalculated PnL for trade {trade_id}[/]")
        
        if show_details:
            tbl = Table(title=f"PnL Recalculation Details - {trade_id}")
            tbl.add_column("Metric", justify="left")
            tbl.add_column("Old Value", justify="right") 
            tbl.add_column("New Value", justify="right")
            tbl.add_column("Change", justify="right")
            
            gross_change = None
            if old_gross is not None and new_gross is not None:
                gross_change = new_gross - old_gross
            gross_change_str = f"${gross_change:.2f}" if gross_change is not None else "N/A"
            
            tbl.add_row(
                "Gross PnL",
                f"${old_gross:.2f}" if old_gross is not None else "N/A",
                f"${new_gross:.2f}" if new_gross is not None else "N/A",
                gross_change_str
            )
            
            costs_change = new_costs - old_costs
            tbl.add_row(
                "Total Costs",
                f"${old_costs:.2f}",
                f"${new_costs:.2f}",
                f"${costs_change:.2f}"
            )
            
            net_change = None
            if old_pnl is not None and new_pnl is not None:
                net_change = new_pnl - old_pnl
            net_change_str = f"${net_change:.2f}" if net_change is not None else "N/A"
            
            tbl.add_row(
                "Net PnL",
                f"${old_pnl:.2f}" if old_pnl is not None else "N/A", 
                f"${new_pnl:.2f}" if new_pnl is not None else "N/A",
                net_change_str
            )
            
            rich.print(tbl)
        else:
            rich.print(f"  Old PnL: ${old_pnl:.2f}" if old_pnl is not None else "  Old PnL: N/A")
            rich.print(f"  New PnL: ${new_pnl:.2f}" if new_pnl is not None else "  New PnL: N/A")
            
            if old_pnl is not None and new_pnl is not None:
                change = new_pnl - old_pnl
                change_color = "green" if change >= 0 else "red"
                rich.print(f"  Change: [{change_color}]${change:.2f}[/]")
        
        save_book(book)
        write_single_trade_file(trade)
        rich.print(f"[green]✓ Trade {trade_id} updated and saved[/]")
        
    else:
        rich.print(f"[yellow]Trade {trade_id} is still OPEN - no PnL to recalculate[/]")
        rich.print("[dim]Note: PnL is calculated when trades are closed[/]")
    
    return True

def recalc_all_trades(book: list):
    """Recalculate PnL for all closed trades"""
    closed_trades = [t for t in book if t.status == "CLOSED"]
    
    if not closed_trades:
        rich.print("[yellow]No closed trades found to recalculate[/]")
        return
    
    rich.print(f"[cyan]Recalculating PnL for {len(closed_trades)} closed trades...[/]")
    
    updated_count = 0
    for trade in closed_trades:
        old_pnl = safe_to_decimal(trade.pnl)
        new_pnl = calc_trade_pnl(trade)
        trade.pnl = new_pnl
        
        if old_pnl != new_pnl:
            updated_count += 1
            old_display = f"${old_pnl:.2f}" if old_pnl is not None else "N/A"
            new_display = f"${new_pnl:.2f}" if new_pnl is not None else "N/A"
            rich.print(f"  {trade.id}: {old_display} → {new_display}")
    
    if updated_count > 0:
        save_book(book)
        rich.print(f"[green]✓ Updated {updated_count} trades and saved[/]")
    else:
        rich.print("[dim]All PnL calculations were already correct[/]")

def fix_data_types(book: list):
    """Fix any string PnL values to Decimal objects"""
    fixed_count = 0
    
    for trade in book:
        if isinstance(trade.pnl, str):
            trade.pnl = safe_to_decimal(trade.pnl)
            fixed_count += 1
        
        if isinstance(trade.pnl_2h, str):
            trade.pnl_2h = safe_to_decimal(trade.pnl_2h)
    
    if fixed_count > 0:
        rich.print(f"[cyan]Fixed {fixed_count} data type issues[/]")
        save_book(book)
        return True
    return False


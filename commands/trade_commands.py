# ═══════════════════════════════════════════════════════════════════
# Updated commands/trade_commands.py - Historical trade entry
# ═══════════════════════════════════════════════════════════════════

import typer
import rich
import datetime as dt
from typing import List

from commands import cfg, book, trade_ops, stopwatch_manager
from utils import blocked_for_options, to_decimal, check_time_against_blocks
from persistence import save_book
from ls import list_trades
from recalc import recalc_trade_pnl

trade_app = typer.Typer()

@trade_app.command("open")
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
    """Open a new trade"""
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

    # Handle historical trade entry
    custom_entry_time = None
    custom_entry_date = None
    
    if historical:
        rich.print("[bold cyan]⏰ Historical Trade Entry[/]")
        
        # Get the date
        while True:
            try:
                date_input = typer.prompt("What date was this trade entered? (YYYY-MM-DD or MM-DD for this year)", default="today")
                
                if date_input.lower() == "today":
                    custom_entry_date = dt.date.today()
                elif len(date_input.split('-')) == 2:
                    # MM-DD format, use current year
                    month, day = map(int, date_input.split('-'))
                    custom_entry_date = dt.date(dt.date.today().year, month, day)
                else:
                    # YYYY-MM-DD format
                    custom_entry_date = dt.date.fromisoformat(date_input)
                
                rich.print(f"[green]✓ Using date: {custom_entry_date.strftime('%A, %B %d, %Y')}[/]")
                break
                
            except ValueError:
                rich.print("[red]Invalid date format. Please use YYYY-MM-DD or MM-DD[/]")
        
        # Get the time
        while True:
            try:
                time_input = typer.prompt("What time was this trade entered? (HH:MM format, e.g., 14:30)")
                # Parse the time
                entry_hour, entry_minute = map(int, time_input.split(':'))
                custom_entry_time = dt.time(entry_hour, entry_minute)
                
                # Validate it's a reasonable time (market hours)
                if 6 <= entry_hour <= 23:  # Reasonable trading hours
                    rich.print(f"[green]✓ Using time: {custom_entry_time.strftime('%I:%M %p')}[/]")
                    break
                else:
                    rich.print("[red]Please enter a time between 06:00 and 23:00[/]")
                    
            except (ValueError, IndexError):
                rich.print("[red]Invalid time format. Please use HH:MM (e.g., 14:30)[/]")
        
        # Show final timestamp
        custom_datetime = dt.datetime.combine(custom_entry_date, custom_entry_time)
        rich.print(f"[cyan]Final timestamp: {custom_datetime.strftime('%A, %B %d, %Y at %I:%M %p')}[/]")
        
        # Optional: Check if that time would have been blocked (for informational purposes)
        if not dry_run and (typ == "OPTION" or (typ is None and u in ["BULL-PUT", "BULL-PUT-OVERNIGHT", "BEAR-CALL"])):
            was_blocked_at_entry = check_time_against_blocks(custom_entry_time, cfg)
            exempt_strategies = cfg.get("exemption", [])
            is_exempt = u in [s.upper() for s in exempt_strategies]
            
            if was_blocked_at_entry and not is_exempt:
                rich.print(f"[yellow]ℹ️  Note: {custom_entry_time.strftime('%I:%M %p')} would have been during a block period[/]")
                rich.print(f"[yellow]   But you're entering this as historical data, so it's allowed[/]")
            else:
                rich.print(f"[green]ℹ️  {custom_entry_time.strftime('%I:%M %p')} was outside block periods[/]")
    
    else:
        # Normal (live) trade - check blocks as usual
        if not dry_run and (typ == "OPTION" or (typ is None and u in ["BULL-PUT", "BULL-PUT-OVERNIGHT", "BEAR-CALL"])):
            is_blocked, active_block = blocked_for_options(cfg)
            
            # Check if strategy is exempt from blocks
            exempt_strategies = cfg.get("exemption", [])
            is_exempt = u in [s.upper() for s in exempt_strategies]
            
            if is_blocked and not is_exempt:
                rich.print(f"[red]🚫 Option trading is currently blocked: {active_block}[/]")
                rich.print("[yellow]Use --historical if you want to enter a trade from earlier[/]")
                return

    # Handle spread strategies and get the trade object back
    trade = None
    if u == "BULL-PUT":
        trade = trade_ops.open_bull_put_spread(qty, strat, dry_run=dry_run, 
                                             custom_entry_time=custom_entry_time, 
                                             custom_entry_date=custom_entry_date)
    elif u == "BULL-PUT-OVERNIGHT":
        trade = trade_ops.open_bull_put_spread(qty, u, dry_run=dry_run, 
                                             custom_entry_time=custom_entry_time, 
                                             custom_entry_date=custom_entry_date)
    elif u == "BEAR-CALL":
        trade = trade_ops.open_bear_call_spread(qty, dry_run=dry_run, 
                                              custom_entry_time=custom_entry_time, 
                                              custom_entry_date=custom_entry_date)
    else:
        # Handle single-leg trades
        typ = typ or typer.prompt("Type", default="FUTURE")
        side = side or typer.prompt("Side", default="BUY")
        symbol = symbol or typer.prompt("Symbol")
        qty = qty or int(typer.prompt("Quantity", default="1"))
        price = price or typer.prompt("Entry price")
        
        trade = trade_ops.open_single_leg_trade(strat, typ, side, symbol, qty, price, dry_run=dry_run, 
                                              custom_entry_time=custom_entry_time, 
                                              custom_entry_date=custom_entry_date)
    
    # Start stopwatch if requested and it's an option trade (only for live trades)
    if trade and not dry_run and not historical and trade.typ.startswith("OPTION"):
        # Ask for stopwatch if not provided and it's an option
        if stopwatch is None:
            if typer.confirm("Start risk management stopwatch for this option?"):
                stopwatch = typer.prompt("Hours (1 or 2)", type=int, default=1)
        
        if stopwatch:
            if stopwatch in [1, 2]:
                stopwatch_manager.start_stopwatch(trade.id, stopwatch)
            else:
                rich.print("[red]Stopwatch must be 1 or 2 hours[/]")
    elif historical and trade and trade.typ.startswith("OPTION"):
        rich.print("[dim]Note: No stopwatch started for historical trades[/]")

# Rest of the commands remain the same...
@trade_app.command("close")
def close_trade(
    trade_id: str,
    qty: int = typer.Option(None, help="Quantity to close (partial close)")
):
    """Close a trade completely or partially"""
    if trade_ops is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    trade_ops.close_trade_partial(trade_id, qty)

@trade_app.command("fix")
def fix_trade_prices(trade_id: str):
    """Manually fix trade prices and recalculate PnL"""
    if book is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    
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

@trade_app.command("ls")
def ls_command():
    """List all trades"""
    if book is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    list_trades(book)

@trade_app.command("pnl2h")
def record_2h_pnl(trade_id: str = typer.Option(None, help="Trade ID to record 2H PnL for")):
    """Record 2-hour PnL for a trade (required for BULL-PUT-OVERNIGHT before closing)"""
    rich.print("2H PnL recording not yet implemented in modules")

@trade_app.command("delete")
def delete_trade(
    trade_id: str,
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Delete a trade permanently"""
    if book is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    
    # Find the trade
    trade = None
    trade_index = None
    for i, t in enumerate(book):
        if t.id == trade_id:
            trade = t
            trade_index = i
            break
    
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return
    
    # Show trade details
    rich.print(f"\n[bold red]⚠️  DELETE TRADE {trade_id}[/]")
    rich.print(f"[yellow]Strategy: {trade.strat}[/]")
    rich.print(f"[yellow]Type: {trade.typ}[/]")
    rich.print(f"[yellow]Status: {trade.status}[/]")
    
    # Handle timestamp format (could be string or datetime)
    try:
        if isinstance(trade.ts, str):
            # Parse ISO format string
            from datetime import datetime
            ts_dt = datetime.fromisoformat(trade.ts.replace('Z', '+00:00'))
            date_str = ts_dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # Already a datetime object
            date_str = trade.ts.strftime('%Y-%m-%d %H:%M:%S')
        rich.print(f"[yellow]Date: {date_str}[/]")
    except Exception as e:
        rich.print(f"[yellow]Date: {trade.ts} (raw)[/]")
    
    # Show legs
    rich.print(f"[yellow]Legs:[/]")
    for i, leg in enumerate(trade.legs):
        exit_info = f" → ${leg.exit}" if leg.exit else " (OPEN)"
        rich.print(f"[yellow]  {i+1}. {leg.side} {leg.qty} {leg.symbol} @ ${leg.entry}{exit_info}[/]")
    
    # Show PnL if closed
    if trade.status == "CLOSED" and trade.pnl:
        rich.print(f"[yellow]P&L: ${trade.pnl:.2f}[/]")
    
    # Confirmation unless forced
    if not force:
        rich.print(f"\n[bold red]This action cannot be undone![/]")
        if not typer.confirm(f"Are you sure you want to delete trade {trade_id}?"):
            rich.print("[yellow]Delete cancelled[/]")
            return
    
    # Delete the trade
    del book[trade_index]
    save_book(book)
    
    rich.print(f"[green]✓ Trade {trade_id} deleted successfully[/]")



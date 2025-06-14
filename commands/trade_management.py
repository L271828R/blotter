# ═══════════════════════════════════════════════════════════════════
# commands/trade_management.py - Trade management functionality
# ═══════════════════════════════════════════════════════════════════

import typer
import rich

def find_trade(trade_id):
    """Find a trade by ID"""
    from commands import book  # Import here to avoid circular imports
    for trade in book:
        if trade.id == trade_id:
            return trade
    return None

def fix_trade_prices(trade_id: str):
    """Manually fix trade prices and recalculate PnL"""
    from commands import book  # Import here to get current book
    
    if book is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    
    # Find the trade
    trade = find_trade(trade_id)
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return
    
    from utils import to_decimal
    from recalc import recalc_trade_pnl
    from core.persistence import save_book
    import datetime as dt
    
    rich.print(f"[cyan]Fixing trade {trade_id}[/]")
    rich.print(f"Trade: {trade.strat} - {trade.typ}")
    
    # Show current timestamp
    try:
        if isinstance(trade.ts, str):
            ts_dt = dt.datetime.fromisoformat(trade.ts.replace('Z', '+00:00'))
        else:
            ts_dt = trade.ts
        
        # Convert to EST for display
        est_tz = dt.timezone(dt.timedelta(hours=-5))
        est_time = ts_dt.astimezone(est_tz)
        rich.print(f"\n[bold]Current timestamp: {est_time.strftime('%Y-%m-%d %I:%M %p EST')}[/]")
        
        # Ask if they want to update timestamp
        if typer.confirm("Update timestamp?"):
            rich.print("\n[yellow]Enter new time (leave date unchanged):[/]")
            new_time_str = typer.prompt("New time (HH:MM format, e.g., 08:05)")
            
            try:
                # Parse new time
                new_hour, new_minute = map(int, new_time_str.split(':'))
                
                # Create new datetime with same date but new time
                new_dt = est_time.replace(hour=new_hour, minute=new_minute, second=0, microsecond=0)
                
                # Convert back to UTC and store
                new_utc = new_dt.astimezone(dt.timezone.utc)
                trade.ts = new_utc.isoformat()
                
                rich.print(f"[green]✓ Updated timestamp to: {new_dt.strftime('%Y-%m-%d %I:%M %p EST')}[/]")
                save_book(book)
                
            except (ValueError, IndexError):
                rich.print("[red]Invalid time format. Please use HH:MM (e.g., 08:05)[/]")
    
    except Exception as e:
        rich.print(f"[red]Error handling timestamp: {e}[/]")
    
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

def delete_trade(
    trade_id: str,
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Delete a trade permanently"""
    from commands import book  # Import here to get current book
    from persistence import save_book
    
    if book is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    
    # Find the trade
    trade = find_trade(trade_id)
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return
    
    trade_index = None
    for i, t in enumerate(book):
        if t.id == trade_id:
            trade_index = i
            break
    
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

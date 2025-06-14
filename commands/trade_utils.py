# ═══════════════════════════════════════════════════════════════════
# commands/trade_utils.py - Trade utility functions
# ═══════════════════════════════════════════════════════════════════

import typer
import rich
import datetime as dt

from commands import cfg, stopwatch_manager
from utils import blocked_for_options, check_time_against_blocks

def get_historical_timestamp():
    """Get historical timestamp from user input"""
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
    
    return custom_entry_time, custom_entry_date

def is_option_strategy(strategy_type, typ=None):
    """Check if strategy involves options"""
    if strategy_type in ["bull_put_spread", "bear_call_spread"]:
        return True
    return typ == "OPTION"

def is_option_trade(trade):
    """Check if trade involves options"""
    return trade.typ.startswith("OPTION") if trade else False

def check_historical_blocks(custom_entry_time, strat, cfg):
    """Check if historical time would have been blocked (informational only)"""
    was_blocked_at_entry = check_time_against_blocks(custom_entry_time, cfg)
    exempt_strategies = cfg.get("exemption", [])
    is_exempt = strat in exempt_strategies
    
    if was_blocked_at_entry and not is_exempt:
        rich.print(f"[yellow]ℹ️  Note: {custom_entry_time.strftime('%I:%M %p')} would have been during a block period[/]")
        rich.print(f"[yellow]   But you're entering this as historical data, so it's allowed[/]")
    else:
        rich.print(f"[green]ℹ️  {custom_entry_time.strftime('%I:%M %p')} was outside block periods[/]")

def check_current_blocks(strat, cfg):
    """Check if current time is blocked for options. Returns True if blocked."""
    is_blocked, active_block = blocked_for_options(cfg)
    
    # Check if strategy is exempt from blocks
    exempt_strategies = cfg.get("exemption", [])
    is_exempt = strat in exempt_strategies
    
    if is_blocked and not is_exempt:
        rich.print(f"[red]🚫 Option trading is currently blocked: {active_block}[/]")
        rich.print("[yellow]Use --historical if you want to enter a trade from earlier[/]")
        return True
    
    return False

def handle_stopwatch(trade, stopwatch):
    """Handle stopwatch setup for option trades"""
    # Ask for stopwatch if not provided and it's an option
    if stopwatch is None:
        if typer.confirm("Start risk management stopwatch for this option?"):
            stopwatch = typer.prompt("Hours (1 or 2)", type=int, default=1)
    
    if stopwatch:
        if stopwatch in [1, 2]:
            stopwatch_manager.start_stopwatch(trade.id, stopwatch)
        else:
            rich.print("[red]Stopwatch must be 1 or 2 hours[/]")

def calculate_leg_pnl(leg):
    """Calculate P&L for a single leg"""
    if not leg.exit:
        return 0  # Still open
    
    gross_diff = leg.exit - leg.entry
    
    if leg.side == "BUY":
        # You bought first, sold later: profit when exit > entry
        pnl = gross_diff * leg.qty * leg.multiplier
    else:  # leg.side == "SELL" 
        # You sold first, bought back later: profit when entry > exit
        pnl = -gross_diff * leg.qty * leg.multiplier
    
    # Subtract costs
    entry_costs = leg.entry_costs.total() if leg.entry_costs else 0
    exit_costs = leg.exit_costs.total() if leg.exit_costs else 0
    
    return float(pnl) - float(entry_costs) - float(exit_costs)

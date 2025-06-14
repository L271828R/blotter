# ═══════════════════════════════════════════════════════════════════
# Enhanced commands/trade_commands.py - Complete Strategy metadata integration
# ═══════════════════════════════════════════════════════════════════

import typer
import rich
import datetime as dt
from typing import List
from decimal import Decimal

from commands import cfg, book, trade_ops, stopwatch_manager
from utils import blocked_for_options, to_decimal, check_time_against_blocks, calculate_costs
from persistence import save_book
from ls import list_trades
from recalc import recalc_trade_pnl
from config import get_strategy_type, is_bull_put_spread, is_bear_call_spread, is_spread_strategy

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fzf_helper import select_strategy, check_fzf_installed

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

# Add new commands for spread management
@trade_app.command("close-leg")
def close_single_leg(
    trade_id: str,
    leg_symbol: str,
    exit_price: float,
    reason: str = typer.Option("Leg management", help="Reason for closing single leg")
):
    """Close individual leg of a spread"""
    
    trade = find_trade(trade_id)
    if not trade:
        rich.print(f"[red]Trade {trade_id} not found[/]")
        return
    
    # Find the specific leg
    for leg in trade.legs:
        if leg.symbol == leg_symbol:
            if leg.exit is not None:
                rich.print(f"[red]Leg {leg_symbol} already closed[/]")
                return
            
            # Close this leg
            leg.exit = to_decimal(exit_price)
            leg.exit_costs = calculate_costs("OPTION", leg.qty, cfg)
            
            rich.print(f"[green]✓ Closed leg {leg_symbol} at ${exit_price}[/]")
            rich.print(f"[green]  Reason: {reason}[/]")
            
            # Calculate leg P&L
            leg_pnl = calculate_leg_pnl(leg)
            rich.print(f"[green]  Leg P&L: ${leg_pnl:+.2f}[/]")
            
            # Check if all legs are closed
            open_legs = [l for l in trade.legs if l.exit is None]
            if not open_legs:
                trade.status = "CLOSED"
                trade.pnl = trade.net_pnl()
                rich.print(f"[green]✓ All legs closed - spread complete[/]")
                rich.print(f"[green]  Total P&L: ${trade.pnl:+.2f}[/]")
            else:
                rich.print(f"[yellow]  {len(open_legs)} legs still open[/]")
            
            save_book(book)
            return
    
    rich.print(f"[red]Leg {leg_symbol} not found in trade {trade_id}[/]")

@trade_app.command("expire-leg")
def expire_leg(
    trade_id: str,
    leg_symbol: str
):
    """Mark option leg as expired (automatically sets exit price to 0)"""
    
    trade = find_trade(trade_id)
    if not trade:
        rich.print(f"[red]Trade {trade_id} not found[/]")
        return
    
    # Find the specific leg
    for leg in trade.legs:
        if leg.symbol == leg_symbol:
            if leg.exit is not None:
                rich.print(f"[red]Leg {leg_symbol} already closed[/]")
                return
            
            # Mark as expired
            leg.exit = to_decimal("0.00")
            leg.exit_costs = calculate_costs("OPTION", leg.qty, cfg)
            
            rich.print(f"[green]✓ Leg {leg_symbol} marked as expired (value: $0.00)[/]")
            
            # Calculate leg P&L
            leg_pnl = calculate_leg_pnl(leg)
            rich.print(f"[green]  Leg P&L: ${leg_pnl:+.2f}[/]")
            
            # Check if all legs are closed
            open_legs = [l for l in trade.legs if l.exit is None]
            if not open_legs:
                trade.status = "CLOSED"
                trade.pnl = trade.net_pnl()
                rich.print(f"[green]✓ All legs closed - spread complete[/]")
                rich.print(f"[green]  Total P&L: ${trade.pnl:+.2f}[/]")
            else:
                rich.print(f"[yellow]  {len(open_legs)} legs still open[/]")
            
            save_book(book)
            return
    
    rich.print(f"[red]Leg {leg_symbol} not found in trade {trade_id}[/]")

def find_trade(trade_id):
    """Find a trade by ID"""
    for trade in book:
        if trade.id == trade_id:
            return trade
    return None

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

# Existing commands with minimal changes
@trade_app.command("close")
def close_trade(
    trade_id: str,
    qty: int = typer.Option(None, help="Quantity to close (partial close)")
):
    """Close a trade completely or partially"""
    if trade_ops is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    
    trade = find_trade(trade_id)
    if not trade:
        rich.print(f"[red]Trade {trade_id} not found[/]")
        return
    
    # Check if it's a spread - offer different closing options
    if len(trade.legs) > 1 and is_spread_strategy(trade.strat, cfg):
        rich.print(f"[cyan]Closing {trade.strat} spread: {trade_id}[/]")
        rich.print("1. Close entire spread with net debit")
        rich.print("2. Close with individual leg prices")
        
        choice = input("Choose method (1 or 2): ").strip()
        
        if choice == "1":
            net_debit = float(input("Net debit to close spread: ").strip())
            close_spread_with_net_debit(trade, net_debit)
        else:
            # Use existing close logic for individual prices
            trade_ops.close_trade_partial(trade_id, qty)
    else:
        # Single leg trade - use existing logic
        trade_ops.close_trade_partial(trade_id, qty)

def close_spread_with_net_debit(trade, net_debit):
    """Close spread using net debit - calculates P&L based on net credit received vs net debit paid"""
    # Convert net_debit to Decimal to prevent type mismatch
    net_debit = Decimal(str(net_debit))
    
    rich.print(f"[yellow]Closing {trade.strat} spread with net debit of ${net_debit}[/]")
    
    # Calculate the original net credit received when the spread was opened
    original_net_credit = Decimal('0')
    
    for leg in trade.legs:
        if leg.side == "SELL":
            # Money received when we sold
            original_net_credit += leg.entry
        else:  # leg.side == "BUY"
            # Money paid when we bought
            original_net_credit -= leg.entry
    
    rich.print(f"[cyan]Original net credit received: ${original_net_credit:.2f}[/]")
    rich.print(f"[cyan]Net debit paid to close: ${net_debit:.2f}[/]")
    
    # Calculate profit per contract (before multiplier and quantity)
    profit_per_contract = original_net_credit - net_debit
    rich.print(f"[cyan]Profit per contract: ${profit_per_contract:.2f}[/]")
    
    # For P&L calculation, we need to set exit prices that will result in the correct total P&L
    # The simplest approach is to set the exit prices to match the actual net debit
    
    # For a bull put spread being closed:
    # - The SELL leg (higher strike) gets bought back
    # - The BUY leg (lower strike) gets sold
    
    for i, leg in enumerate(trade.legs):
        if leg.exit is None:
            if leg.side == "SELL":
                # Originally sold this leg, now buying it back
                # Set exit price to the debit portion allocated to this leg
                leg.exit = net_debit * Decimal('0.8')  # Assume 80% of debit for sold leg
            else:  # leg.side == "BUY"
                # Originally bought this leg, now selling it back  
                # Set exit price to the credit portion allocated to this leg
                leg.exit = net_debit * Decimal('0.2')  # Assume 20% of debit for bought leg
            
            # Calculate exit costs - for spreads, only apply costs to first leg
            if i == 0:
                # First leg gets the spread exit costs
                leg.exit_costs = calculate_costs("OPTION", leg.qty, cfg)
            else:
                # Additional legs get zero exit costs (it's one spread order)
                from utils import CommissionFees
                leg.exit_costs = CommissionFees(
                    commission=Decimal('0'),
                    exchange_fees=Decimal('0'), 
                    regulatory_fees=Decimal('0')
                )
            
            rich.print(f"[yellow]  {leg.symbol} ({leg.side}): Entry ${leg.entry} → Exit ${leg.exit:.2f}[/]")
    
    # Mark trade as closed and calculate P&L
    trade.status = "CLOSED"
    
    # Calculate total P&L manually for verification
    total_gross_pnl = profit_per_contract * trade.legs[0].qty * trade.legs[0].multiplier
    
    # Calculate total costs
    total_entry_costs = sum(leg.entry_costs.total() if leg.entry_costs else 0 for leg in trade.legs)
    total_exit_costs = sum(leg.exit_costs.total() if leg.exit_costs else 0 for leg in trade.legs)
    total_costs = total_entry_costs + total_exit_costs
    
    # Debug cost breakdown
    rich.print(f"[dim]Cost breakdown:[/]")
    rich.print(f"[dim]  Entry costs: ${total_entry_costs:.2f}[/]")
    rich.print(f"[dim]  Exit costs: ${total_exit_costs:.2f}[/]")
    
    # Set the P&L directly
    trade.pnl = float(total_gross_pnl) - float(total_costs)
    
    save_book(book)
    
    rich.print(f"\n[green]✓ Spread closed successfully[/]")
    rich.print(f"[green]  Gross P&L: ${total_gross_pnl:+.2f}[/]")
    rich.print(f"[green]  Total costs: ${total_costs:.2f}[/]")
    rich.print(f"[green]  Net P&L: ${trade.pnl:+.2f}[/]")

@trade_app.command("fix")
def fix_trade_prices(trade_id: str):
    """Manually fix trade prices and recalculate PnL"""
    if book is None:
        rich.print("[red]Error: Global configuration not properly initialized[/]")
        return
    
    # Find the trade
    trade = find_trade(trade_id)
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

# Add strategy management commands
@trade_app.command("add-strategy")
def add_strategy_command(
    name: str,
    strategy_type: str = typer.Option("single_leg", help="Strategy type: single_leg, bull_put_spread, bear_call_spread"),
    default_type: str = typer.Option(None, help="Default trade type: FUTURE, OPTION"),
    default_side: str = typer.Option(None, help="Default side: BUY, SELL")
):
    """Add a new strategy to configuration"""
    from config import add_strategy
    add_strategy(name, strategy_type, default_type, default_side)

@trade_app.command("fix-strategy")
def fix_strategy_command(
    name: str,
    strategy_type: str = typer.Option(help="New strategy type: single_leg, bull_put_spread, bear_call_spread")
):
    """Fix strategy type after migration"""
    from config import fix_strategy_type
    fix_strategy_type(name, strategy_type, cfg)

@trade_app.command("list-strategies")
def list_strategies_command(
    strategy_type: str = typer.Option(None, help="Filter by type: single_leg, bull_put_spread, bear_call_spread")
):
    """List configured strategies"""
    from config import list_strategies
    list_strategies(cfg, strategy_type)

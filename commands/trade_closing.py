# ═══════════════════════════════════════════════════════════════════
# commands/trade_closing.py - Trade closing functionality
# ═══════════════════════════════════════════════════════════════════

import typer
import rich
from decimal import Decimal

from commands import cfg, book, trade_ops
from utils import to_decimal, calculate_costs
from models import CommissionFees
from persistence import save_book
from config import is_spread_strategy
from .trade_utils import calculate_leg_pnl

def find_trade(trade_id):
    """Find a trade by ID"""
    for trade in book:
        if trade.id == trade_id:
            return trade
    return None

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
    
    # Set exit prices for legs
    for i, leg in enumerate(trade.legs):
        if leg.exit is None:
            if leg.side == "SELL":
                # Originally sold this leg, now buying it back
                leg.exit = net_debit * Decimal('0.8')  # Assume 80% of debit for sold leg
            else:  # leg.side == "BUY"
                # Originally bought this leg, now selling it back  
                leg.exit = net_debit * Decimal('0.2')  # Assume 20% of debit for bought leg
            
            # Calculate exit costs - for spreads, only apply costs to first leg
            if i == 0:
                # First leg gets the spread exit costs
                leg.exit_costs = calculate_costs("OPTION", leg.qty, cfg)
            else:
                # Additional legs get zero exit costs (it's one spread order)
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

def expire_spread(trade_id: str):
    """Mark entire spread as expired (automatically sets all legs' exit prices to 0)"""
    
    trade = find_trade(trade_id)
    if not trade:
        rich.print(f"[red]Trade {trade_id} not found[/]")
        return
    
    # Check if it's actually a spread
    if len(trade.legs) < 2:
        rich.print(f"[red]Trade {trade_id} is not a spread (only {len(trade.legs)} leg)[/]")
        rich.print("[yellow]Use 'expire-leg' for single-leg trades[/]")
        return
    
    # Check if any legs are already closed
    open_legs = [leg for leg in trade.legs if leg.exit is None]
    if not open_legs:
        rich.print(f"[red]All legs in spread {trade_id} are already closed[/]")
        return
    
    rich.print(f"[cyan]Expiring {trade.strat} spread: {trade_id}[/]")
    rich.print(f"[yellow]This will set exit price to $0.00 for all {len(open_legs)} open legs[/]")
    
    # Confirm the action
    if not typer.confirm("Are you sure you want to expire the entire spread?"):
        rich.print("[yellow]Expiration cancelled[/]")
        return
    
    expired_legs = []
    
    # Expire all open legs
    for leg in trade.legs:
        if leg.exit is None:
            # Mark as expired
            leg.exit = to_decimal("0.00")
            
            # For spread expirations, TOS typically shows $0 fees
            leg.exit_costs = CommissionFees(
                commission=Decimal('0'),
                exchange_fees=Decimal('0'), 
                regulatory_fees=Decimal('0')
            )
            
            # Calculate leg P&L
            leg_pnl = calculate_leg_pnl(leg)
            expired_legs.append((leg.symbol, leg_pnl))
            
            rich.print(f"[green]✓ Expired {leg.symbol} (was {leg.side} @ ${leg.entry}) → P&L: ${leg_pnl:+.2f}[/]")
    
    # Mark trade as closed
    trade.status = "CLOSED"
    trade.pnl = trade.net_pnl()
    
    save_book(book)
    
    # Show summary
    rich.print(f"\n[green]✓ Spread {trade_id} expired successfully[/]")
    rich.print(f"[green]  Expired {len(expired_legs)} legs[/]")
    rich.print(f"[green]  Total P&L: ${trade.pnl:+.2f}[/]")
    
    # Show breakdown by leg
    rich.print(f"\n[dim]Leg breakdown:[/]")
    for symbol, pnl in expired_legs:
        rich.print(f"[dim]  {symbol}: ${pnl:+.2f}[/]")

def expire_leg(trade_id: str, leg_symbol: str):
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

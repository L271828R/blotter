# ═══════════════════════════════════════════════════════════════════
# risk_manager.py - Complete risk management with balance adjustments
# ═══════════════════════════════════════════════════════════════════

import datetime as dt
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any
import rich
import json
import os
import uuid

def load_risk_state():
    """Load risk management state from file"""
    try:
        with open('risk_state.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "consecutive_wins": 0,
            "consecutive_losses": 0,
            "last_trade_date": None,
            "cooldown_until": None,
            "cooldown_reason": None
        }

def save_risk_state(state):
    """Save risk management state to file"""
    with open('risk_state.json', 'w') as f:
        json.dump(state, f, indent=2, default=str)

def load_balance_adjustments():
    """Load balance adjustments from file"""
    try:
        with open('balance_adjustments.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_balance_adjustments(adjustments):
    """Save balance adjustments to file"""
    with open('balance_adjustments.json', 'w') as f:
        json.dump(adjustments, f, indent=2, default=str)

def add_balance_adjustment(amount, reason, date=None):
    """Add manual balance adjustment for external trades, deposits, withdrawals"""
    adjustments = load_balance_adjustments()
    
    if date is None:
        date = dt.datetime.now(dt.timezone.utc)
    elif isinstance(date, str):
        try:
            date = dt.datetime.fromisoformat(date.replace('Z', '+00:00'))
        except:
            date = dt.datetime.now(dt.timezone.utc)
    
    adjustment = {
        'amount': float(amount),
        'reason': reason,
        'date': date.isoformat(),
        'id': str(uuid.uuid4())[:8],
        'type': 'manual_adjustment'
    }
    
    adjustments.append(adjustment)
    save_balance_adjustments(adjustments)
    
    rich.print(f"[green]✓ Balance adjustment added: ${amount:+.2f}[/]")
    rich.print(f"[green]  Reason: {reason}[/]")
    rich.print(f"[green]  Date: {date.strftime('%Y-%m-%d %H:%M:%S UTC')}[/]")
    rich.print(f"[green]  ID: {adjustment['id']}[/]")
    
    return adjustment

def remove_balance_adjustment(adjustment_id):
    """Remove a balance adjustment by ID"""
    adjustments = load_balance_adjustments()
    
    for i, adj in enumerate(adjustments):
        if adj['id'] == adjustment_id:
            removed = adjustments.pop(i)
            save_balance_adjustments(adjustments)
            
            rich.print(f"[yellow]✓ Removed adjustment: ${removed['amount']:+.2f}[/]")
            rich.print(f"[yellow]  Reason: {removed['reason']}[/]")
            return True
    
    rich.print(f"[red]❌ Adjustment ID {adjustment_id} not found[/]")
    return False

def list_balance_adjustments(days=30):
    """List recent balance adjustments"""
    adjustments = load_balance_adjustments()
    
    if not adjustments:
        rich.print("[dim]No balance adjustments found[/]")
        return
    
    # Filter by date if specified
    if days:
        cutoff_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        adjustments = [
            adj for adj in adjustments 
            if dt.datetime.fromisoformat(adj['date'].replace('Z', '+00:00')) >= cutoff_date
        ]
    
    # Sort by date (most recent first)
    adjustments.sort(key=lambda x: x['date'], reverse=True)
    
    rich.print(f"\n[bold]Balance Adjustments (last {days} days):[/]")
    total = 0
    
    for adj in adjustments:
        date_str = dt.datetime.fromisoformat(adj['date'].replace('Z', '+00:00')).strftime('%m/%d %H:%M')
        amount = adj['amount']
        total += amount
        
        color = "green" if amount > 0 else "red"
        rich.print(f"[{color}]{date_str} | ${amount:+8.2f} | {adj['reason']} | ID: {adj['id']}[/]")
    
    rich.print(f"\n[bold]Total adjustments: ${total:+.2f}[/]")

def get_current_balance(book=None, cfg=None):
    """Calculate current account balance from starting balance + blotter P&L + adjustments"""
    if cfg is None:
        from config import load_config
        cfg = load_config()
    
    if book is None:
        from persistence import load_book
        book = load_book()
    
    starting_balance = cfg.get("risk_limits", {}).get("starting_balance", 10000)
    
    # Calculate total P&L from closed trades in blotter
    closed_trades = [t for t in book if t.status == "CLOSED" and hasattr(t, 'pnl') and t.pnl]
    blotter_pnl = sum(trade.pnl for trade in closed_trades)
    
    # Add manual balance adjustments (external trades, deposits, withdrawals)
    adjustments = load_balance_adjustments()
    total_adjustments = sum(adj['amount'] for adj in adjustments)
    
    current_balance = Decimal(str(starting_balance)) + Decimal(str(blotter_pnl)) + Decimal(str(total_adjustments))
    
    return current_balance

def get_balance_breakdown(book=None, cfg=None):
    """Get detailed breakdown of balance calculation"""
    if cfg is None:
        from config import load_config
        cfg = load_config()
    
    if book is None:
        from persistence import load_book
        book = load_book()
    
    starting_balance = cfg.get("risk_limits", {}).get("starting_balance", 10000)
    
    # Calculate blotter P&L
    closed_trades = [t for t in book if t.status == "CLOSED" and hasattr(t, 'pnl') and t.pnl]
    blotter_pnl = sum(trade.pnl for trade in closed_trades)
    
    # Calculate adjustments
    adjustments = load_balance_adjustments()
    total_adjustments = sum(adj['amount'] for adj in adjustments)
    
    # Calculate current balance
    current_balance = float(Decimal(str(starting_balance)) + Decimal(str(blotter_pnl)) + Decimal(str(total_adjustments)))
    
    return {
        'starting_balance': starting_balance,
        'blotter_pnl': float(blotter_pnl),
        'adjustments': total_adjustments,
        'current_balance': current_balance,
        'total_trades': len(closed_trades),
        'adjustment_count': len(adjustments)
    }

def set_current_balance(target_balance, reason="Manual balance correction"):
    """Set current balance by calculating needed adjustment"""
    current = float(get_current_balance())
    adjustment_needed = target_balance - current
    
    if abs(adjustment_needed) < 0.01:  # Less than 1 cent difference
        rich.print(f"[green]Balance is already ${target_balance:.2f}[/]")
        return
    
    rich.print(f"[cyan]Current balance: ${current:.2f}[/]")
    rich.print(f"[cyan]Target balance:  ${target_balance:.2f}[/]")
    rich.print(f"[cyan]Adjustment needed: ${adjustment_needed:+.2f}[/]")
    
    # Add the adjustment
    return add_balance_adjustment(adjustment_needed, reason)

def get_recent_trade_results(book, lookback_days=30):
    """Get recent trade results for analysis"""
    if not book:
        return []
    
    cutoff_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
    recent_trades = []
    
    for trade in book:
        if trade.status == "CLOSED" and hasattr(trade, 'pnl') and trade.pnl is not None:
            # Handle both string and datetime timestamps
            trade_date = trade.ts
            if isinstance(trade_date, str):
                try:
                    trade_date = dt.datetime.fromisoformat(trade_date.replace('Z', '+00:00'))
                except:
                    continue
            
            if trade_date >= cutoff_date:
                recent_trades.append({
                    'date': trade_date,
                    'pnl': float(trade.pnl),
                    'id': trade.id,
                    'strategy': trade.strat
                })
    
    # Sort by date
    return sorted(recent_trades, key=lambda x: x['date'])

def analyze_consecutive_results(recent_trades):
    """Analyze consecutive wins/losses from recent trades"""
    if not recent_trades:
        return 0, 0, None
    
    consecutive_wins = 0
    consecutive_losses = 0
    last_result = None
    
    # Look at trades from most recent backwards
    for trade in reversed(recent_trades):
        pnl = trade['pnl']
        
        if pnl > 0:  # Win
            if last_result == 'win' or last_result is None:
                consecutive_wins += 1
                last_result = 'win'
            else:
                break
        elif pnl < 0:  # Loss
            if last_result == 'loss' or last_result is None:
                consecutive_losses += 1
                last_result = 'loss'
            else:
                break
        # Skip break-even trades (pnl == 0)
    
    return consecutive_wins, consecutive_losses, last_result

def check_hot_hand_cooloff(book=None, cfg=None):
    """
    Check if trader should be in hot-hand cooldown period
    Returns True if trading is allowed, False if in cooldown
    """
    if cfg is None:
        from config import load_config
        cfg = load_config()
    
    if book is None:
        from persistence import load_book
        book = load_book()
    
    # Get risk limits from config
    risk_limits = cfg.get("risk_limits", {})
    hot_hand_threshold = risk_limits.get("hot_hand_threshold", 4)  # Consecutive wins before cooldown
    cooldown_hours = risk_limits.get("hot_hand_cooldown_hours", 24)  # Hours of cooldown
    
    # Load current risk state
    risk_state = load_risk_state()
    
    # Check if currently in forced cooldown
    if risk_state.get("cooldown_until"):
        try:
            cooldown_until = dt.datetime.fromisoformat(risk_state["cooldown_until"])
            if dt.datetime.now(dt.timezone.utc) < cooldown_until:
                hours_left = (cooldown_until - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
                rich.print(f"[red]🔥 HOT-HAND COOLDOWN: {hours_left:.1f} hours remaining[/]")
                rich.print(f"[yellow]Reason: {risk_state.get('cooldown_reason', 'Consecutive wins')}[/]")
                return False
            else:
                # Cooldown expired, clear it
                risk_state["cooldown_until"] = None
                risk_state["cooldown_reason"] = None
                save_risk_state(risk_state)
        except:
            # Invalid date format, clear cooldown
            risk_state["cooldown_until"] = None
            risk_state["cooldown_reason"] = None
            save_risk_state(risk_state)
    
    # Analyze recent trades
    recent_trades = get_recent_trade_results(book, lookback_days=7)  # Look at past week
    consecutive_wins, consecutive_losses, last_result = analyze_consecutive_results(recent_trades)
    
    # Update risk state
    risk_state["consecutive_wins"] = consecutive_wins
    risk_state["consecutive_losses"] = consecutive_losses
    
    # Check if we need to trigger cooldown
    if consecutive_wins >= hot_hand_threshold:
        # Calculate total winnings from the streak
        streak_winnings = sum(trade['pnl'] for trade in recent_trades[-consecutive_wins:] if trade['pnl'] > 0)
        
        # Trigger cooldown
        cooldown_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=cooldown_hours)
        risk_state["cooldown_until"] = cooldown_until.isoformat()
        risk_state["cooldown_reason"] = f"{consecutive_wins} consecutive wins (${streak_winnings:.2f})"
        save_risk_state(risk_state)
        
        rich.print(f"[bold red]🔥 HOT-HAND COOLDOWN TRIGGERED![/]")
        rich.print(f"[yellow]Consecutive wins: {consecutive_wins}[/]")
        rich.print(f"[yellow]Streak winnings: ${streak_winnings:.2f}[/]")
        rich.print(f"[yellow]Cooldown period: {cooldown_hours} hours[/]")
        rich.print(f"[red]Trading blocked until: {cooldown_until.strftime('%Y-%m-%d %H:%M:%S UTC')}[/]")
        
        return False
    
    # Save updated state
    save_risk_state(risk_state)
    return True

def check_position_sizing(trade_value, current_balance=None, cfg=None):
    """
    Check if trade value is within position sizing limits
    Returns True if position size is acceptable
    """
    if cfg is None:
        from config import load_config
        cfg = load_config()
    
    if current_balance is None:
        current_balance = float(get_current_balance(cfg=cfg))
    
    risk_limits = cfg.get("risk_limits", {})
    max_position_pct = risk_limits.get("max_position_percent", 33)
    max_position_value = current_balance * (max_position_pct / 100)
    
    if trade_value > max_position_value:
        rich.print(f"[red]❌ Position size violation![/]")
        rich.print(f"[red]  Trade value: ${trade_value:.2f}[/]")
        rich.print(f"[red]  Max allowed: ${max_position_value:.2f} ({max_position_pct}% of ${current_balance:.2f})[/]")
        return False
    
    return True

def get_risk_metrics(book=None, cfg=None):
    """Get comprehensive risk metrics"""
    if cfg is None:
        from config import load_config
        cfg = load_config()
    
    if book is None:
        from persistence import load_book
        book = load_book()
    
    current_balance = float(get_current_balance(book, cfg))
    recent_trades = get_recent_trade_results(book, lookback_days=30)
    consecutive_wins, consecutive_losses, last_result = analyze_consecutive_results(recent_trades)
    
    # Calculate metrics
    closed_trades = [t for t in book if t.status == "CLOSED" and hasattr(t, 'pnl') and t.pnl]
    winning_trades = len([t for t in closed_trades if t.pnl > 0])
    losing_trades = len([t for t in closed_trades if t.pnl < 0])
    total_trades = len(closed_trades)
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    # Recent performance (last 7 days)
    recent_pnl = sum(trade['pnl'] for trade in recent_trades)
    recent_wins = len([t for t in recent_trades if t['pnl'] > 0])
    recent_total = len(recent_trades)
    recent_win_rate = (recent_wins / recent_total * 100) if recent_total > 0 else 0
    
    return {
        'current_balance': current_balance,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'recent_pnl': recent_pnl,
        'recent_win_rate': recent_win_rate,
        'consecutive_wins': consecutive_wins,
        'consecutive_losses': consecutive_losses,
        'last_result': last_result,
        'recent_trades_count': recent_total
    }

def force_cooldown(reason, hours=24):
    """Manually trigger a cooldown period"""
    risk_state = load_risk_state()
    cooldown_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)
    risk_state["cooldown_until"] = cooldown_until.isoformat()
    risk_state["cooldown_reason"] = f"Manual: {reason}"
    save_risk_state(risk_state)
    
    rich.print(f"[red]🔒 Manual cooldown activated![/]")
    rich.print(f"[yellow]Reason: {reason}[/]")
    rich.print(f"[yellow]Duration: {hours} hours[/]")
    rich.print(f"[red]Trading blocked until: {cooldown_until.strftime('%Y-%m-%d %H:%M:%S UTC')}[/]")

def clear_cooldown():
    """Manually clear cooldown period"""
    risk_state = load_risk_state()
    risk_state["cooldown_until"] = None
    risk_state["cooldown_reason"] = None
    save_risk_state(risk_state)
    
    rich.print(f"[green]✅ Cooldown period cleared![/]")

def should_reduce_position_size(book=None, cfg=None):
    """
    Check if position sizes should be reduced due to recent losses
    Returns reduction factor (0.5 = 50% of normal size, 1.0 = normal size)
    """
    if cfg is None:
        from config import load_config
        cfg = load_config()
    
    if book is None:
        from persistence import load_book
        book = load_book()
    
    risk_limits = cfg.get("risk_limits", {})
    loss_reduction_threshold = risk_limits.get("loss_reduction_threshold", 3)  # Consecutive losses
    
    recent_trades = get_recent_trade_results(book, lookback_days=7)
    consecutive_wins, consecutive_losses, last_result = analyze_consecutive_results(recent_trades)
    
    if consecutive_losses >= loss_reduction_threshold:
        # Reduce position size based on number of consecutive losses
        reduction_factor = max(0.25, 1.0 - (consecutive_losses * 0.25))
        rich.print(f"[yellow]⚠️  Position size reduction active: {consecutive_losses} consecutive losses[/]")
        rich.print(f"[yellow]   Recommended size: {reduction_factor*100:.0f}% of normal[/]")
        return reduction_factor
    
    return 1.0  # Normal position size

def add_external_trade(strategy, symbol, pnl, date=None, description=None):
    """Add external trade as balance adjustment with trade-like metadata"""
    if description is None:
        description = f"External {strategy} trade: {symbol}"
    
    reason = f"{description} (P&L: ${pnl:+.2f})"
    return add_balance_adjustment(pnl, reason, date)

def show_balance_summary(book=None, cfg=None):
    """Show comprehensive balance summary"""
    breakdown = get_balance_breakdown(book, cfg)
    
    rich.print(f"\n[bold]💰 Account Balance Summary[/]")
    rich.print(f"[green]Starting Balance: ${breakdown['starting_balance']:.2f}[/]")
    rich.print(f"[blue]Blotter P&L:     ${breakdown['blotter_pnl']:+.2f} ({breakdown['total_trades']} trades)[/]")
    rich.print(f"[cyan]Adjustments:     ${breakdown['adjustments']:+.2f} ({breakdown['adjustment_count']} items)[/]")
    rich.print(f"[bold yellow]Current Balance:  ${breakdown['current_balance']:.2f}[/]")
    
    # Show percentage change
    if breakdown['starting_balance'] != 0:
        pct_change = ((breakdown['current_balance'] - breakdown['starting_balance']) / breakdown['starting_balance']) * 100
        color = "green" if pct_change >= 0 else "red"
        rich.print(f"[{color}]Total Return:     {pct_change:+.2f}%[/]")

# CLI-style functions for easy integration
def cmd_add_adjustment(amount, reason, date=None):
    """Command-line interface for adding adjustments"""
    return add_balance_adjustment(amount, reason, date)

def cmd_remove_adjustment(adjustment_id):
    """Command-line interface for removing adjustments"""
    return remove_balance_adjustment(adjustment_id)

def cmd_list_adjustments(days=30):
    """Command-line interface for listing adjustments"""
    return list_balance_adjustments(days)

def cmd_set_balance(target_balance, reason="Manual balance correction"):
    """Command-line interface for setting balance"""
    return set_current_balance(target_balance, reason)

def cmd_show_balance():
    """Command-line interface for showing balance"""
    return show_balance_summary()

def cmd_external_trade(strategy, symbol, pnl, date=None):
    """Command-line interface for adding external trades"""
    return add_external_trade(strategy, symbol, pnl, date)

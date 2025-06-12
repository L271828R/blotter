##═══════════════════════════════════════════════════════════════════
# commands/risk_commands.py - Risk management and balance commands
# ═══════════════════════════════════════════════════════════════════

import typer
import rich

from commands import risk_manager, cfg, book

risk_app = typer.Typer()

@risk_app.command("balance")
def show_balance():
    """Show current account balance and risk metrics"""
    current_balance = risk_manager.get_current_balance()
    
    # Calculate total PnL
    closed_trades = [t for t in book if t.status == "CLOSED" and hasattr(t, 'pnl') and t.pnl]
    total_pnl = sum(trade.pnl for trade in closed_trades)
    starting_balance = cfg.get("risk_limits", {}).get("starting_balance", 10000)
    
    # Calculate win rate
    winning_trades = len([t for t in closed_trades if t.pnl > 0])
    total_trades = len(closed_trades)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    # Show balance info
    rich.print(f"\n[bold]Account Balance & Risk Metrics[/]")
    rich.print(f"Starting Balance: ${starting_balance:.2f}")
    rich.print(f"Total PnL: ${total_pnl:.2f}")
    rich.print(f"Current Balance: [bold]${current_balance:.2f}[/]")
    rich.print(f"Win Rate: {win_rate:.1f}% ({winning_trades}/{total_trades})")
    
    # Risk limits
    risk_limits = cfg.get("risk_limits", {})
    max_position_pct = risk_limits.get("max_position_percent", 33)
    max_position_value = current_balance * (max_position_pct / 100)
    
    rich.print(f"\n[bold]Risk Limits:[/]")
    rich.print(f"Max Position Size: ${max_position_value:.2f} ({max_position_pct}% of balance)")
    
    # Check hot hand status
    if not risk_manager.check_hot_hand_cooloff():
        rich.print(f"[yellow]🔥 Currently in hot-hand cool-off period[/]")
    else:
        rich.print(f"[green]✅ No trading restrictions active[/]")

@risk_app.command("check")
def risk_check(
    trade_value: float = typer.Option(None, "--value", help="Trade value to check"),
):
    """Check risk management status and limits"""
    
    if trade_value:
        current_balance = risk_manager.get_current_balance()
        if risk_manager.check_position_sizing(trade_value, current_balance):
            rich.print(f"[green]✅ Position size OK: ${trade_value:.2f}[/]")
        # Position size violation message is shown in check_position_sizing
    
    # Check hot hand status
    if risk_manager.check_hot_hand_cooloff():
        rich.print(f"[green]✅ No hot-hand restrictions[/]")
    # Hot hand message is shown in check_hot_hand_cooloff
    
    # Show current balance
    current_balance = risk_manager.get_current_balance()
    rich.print(f"\nCurrent Balance: ${current_balance:.2f}")
    
    max_position_pct = cfg.get("risk_limits", {}).get("max_position_percent", 33)
    max_position_value = current_balance * (max_position_pct / 100)
    rich.print(f"Max Position Size: ${max_position_value:.2f} ({max_position_pct}%)")

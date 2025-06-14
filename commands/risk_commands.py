# ═══════════════════════════════════════════════════════════════════
# commands/risk_commands.py - Risk management and balance commands
# ═══════════════════════════════════════════════════════════════════
import typer
import rich
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk_manager import (
    set_current_balance, 
    add_balance_adjustment, 
    add_external_trade,
    show_balance_summary,
    check_hot_hand_cooloff,
    get_current_balance,
    check_position_sizing,
    list_balance_adjustments,
    remove_balance_adjustment,
    get_balance_breakdown,
    get_risk_metrics,
    force_cooldown,
    clear_cooldown,
    should_reduce_position_size
)

from commands import cfg, book

risk_app = typer.Typer()

@risk_app.command("balance")
def show_balance():
    """Show current account balance and risk metrics"""
    # Use the enhanced balance summary from risk_manager
    show_balance_summary(book, cfg)
    
    # Check hot hand status
    if not check_hot_hand_cooloff(book, cfg):
        rich.print(f"[yellow]🔥 Currently in hot-hand cool-off period[/]")
    else:
        rich.print(f"[green]✅ No trading restrictions active[/]")

@risk_app.command("check")
def risk_check(
    trade_value: float = typer.Option(None, "--value", help="Trade value to check"),
):
    """Check risk management status and limits"""
    
    if trade_value:
        current_balance = float(get_current_balance(book, cfg))
        if check_position_sizing(trade_value, current_balance, cfg):
            rich.print(f"[green]✅ Position size OK: ${trade_value:.2f}[/]")
        # Position size violation message is shown in check_position_sizing
    
    # Check hot hand status
    if check_hot_hand_cooloff(book, cfg):
        rich.print(f"[green]✅ No hot-hand restrictions[/]")
    # Hot hand message is shown in check_hot_hand_cooloff
    
    # Show current balance
    current_balance = float(get_current_balance(book, cfg))
    rich.print(f"\nCurrent Balance: ${current_balance:.2f}")
    
    max_position_pct = cfg.get("risk_limits", {}).get("max_position_percent", 33)
    max_position_value = current_balance * (max_position_pct / 100)
    rich.print(f"Max Position Size: ${max_position_value:.2f} ({max_position_pct}%)")

@risk_app.command("adjust")
def adjust_balance(
    amount: float,
    reason: str,
    date: str = typer.Option(None, help="Date (YYYY-MM-DD HH:MM)")
):
    """Add balance adjustment for external trades or corrections"""
    add_balance_adjustment(amount, reason, date)

@risk_app.command("set")
def set_balance(
    target: float,
    reason: str = typer.Option("Balance correction", help="Reason for adjustment")
):
    """Set exact balance (calculates needed adjustment automatically)"""
    set_current_balance(target, reason)

@risk_app.command("external")
def external_trade(
    strategy: str,
    symbol: str, 
    pnl: float,
    date: str = typer.Option(None, help="Date (YYYY-MM-DD HH:MM)")
):
    """Record external trade P&L"""
    add_external_trade(strategy, symbol, pnl, date)

@risk_app.command("list")
def list_adjustments(
    days: int = typer.Option(30, help="Number of days to show")
):
    """List recent balance adjustments"""
    list_balance_adjustments(days)

@risk_app.command("remove")
def remove_adjustment(
    adjustment_id: str
):
    """Remove a balance adjustment by ID"""
    remove_balance_adjustment(adjustment_id)

@risk_app.command("breakdown")
def balance_breakdown():
    """Show detailed balance breakdown"""
    breakdown = get_balance_breakdown(book, cfg)
    
    rich.print(f"\n[bold cyan]📊 Detailed Balance Breakdown[/]")
    rich.print(f"[green]Starting Balance:    ${breakdown['starting_balance']:.2f}[/]")
    rich.print(f"[blue]Blotter P&L:         ${breakdown['blotter_pnl']:+.2f} ({breakdown['total_trades']} trades)[/]")
    rich.print(f"[cyan]Manual Adjustments:  ${breakdown['adjustments']:+.2f} ({breakdown['adjustment_count']} items)[/]")
    rich.print(f"[bold yellow]═══════════════════════════════════════[/]")
    rich.print(f"[bold yellow]Current Balance:     ${breakdown['current_balance']:.2f}[/]")
    
    # Show percentage change
    if breakdown['starting_balance'] != 0:
        pct_change = ((breakdown['current_balance'] - breakdown['starting_balance']) / breakdown['starting_balance']) * 100
        color = "green" if pct_change >= 0 else "red"
        rich.print(f"[{color}]Total Return:        {pct_change:+.2f}%[/]")

@risk_app.command("metrics")
def risk_metrics():
    """Show comprehensive risk metrics"""
    metrics = get_risk_metrics(book, cfg)
    
    rich.print(f"\n[bold]🎯 Risk Management Metrics[/]")
    rich.print(f"Current Balance: ${metrics['current_balance']:.2f}")
    rich.print(f"Total Trades: {metrics['total_trades']}")
    rich.print(f"Overall Win Rate: {metrics['win_rate']:.1f}%")
    rich.print(f"Recent P&L (30d): ${metrics['recent_pnl']:+.2f}")
    rich.print(f"Recent Win Rate: {metrics['recent_win_rate']:.1f}% ({metrics['recent_trades_count']} trades)")
    rich.print(f"Consecutive Wins: {metrics['consecutive_wins']}")
    rich.print(f"Consecutive Losses: {metrics['consecutive_losses']}")
    
    if metrics['last_result']:
        color = "green" if metrics['last_result'] == 'win' else "red"
        rich.print(f"Last Result: [{color}]{metrics['last_result'].upper()}[/]")

@risk_app.command("cooldown")
def manage_cooldown(
    action: str = typer.Argument(help="Action: status, force, clear"),
    reason: str = typer.Option(None, help="Reason for forced cooldown"),
    hours: int = typer.Option(24, help="Hours for forced cooldown")
):
    """Manage hot-hand cooldown periods"""
    
    if action == "status":
        # Show current cooldown status
        if check_hot_hand_cooloff(book, cfg):
            rich.print(f"[green]✅ No cooldown active - trading allowed[/]")
        else:
            rich.print(f"[red]🔥 Cooldown period active - trading blocked[/]")
    
    elif action == "force":
        if not reason:
            reason = typer.prompt("Reason for forced cooldown")
        force_cooldown(reason, hours)
    
    elif action == "clear":
        clear_cooldown()
    
    else:
        rich.print(f"[red]Invalid action: {action}[/]")
        rich.print(f"[yellow]Valid actions: status, force, clear[/]")

@risk_app.command("position")
def position_check(
    trade_value: float,
    show_reduction: bool = typer.Option(False, "--show-reduction", help="Show position size reductions")
):
    """Check position sizing for a specific trade value"""
    current_balance = float(get_current_balance(book, cfg))
    
    # Check basic position sizing
    if check_position_sizing(trade_value, current_balance, cfg):
        rich.print(f"[green]✅ Position size OK: ${trade_value:.2f}[/]")
    
    # Show position size reduction if requested
    if show_reduction:
        reduction_factor = should_reduce_position_size(book, cfg)
        if reduction_factor < 1.0:
            recommended_size = trade_value * reduction_factor
            rich.print(f"[yellow]⚠️  Recommended reduced size: ${recommended_size:.2f} ({reduction_factor*100:.0f}% of normal)[/]")
        else:
            rich.print(f"[green]✅ No position size reduction recommended[/]")
    
    # Show risk limits
    risk_limits = cfg.get("risk_limits", {})
    max_position_pct = risk_limits.get("max_position_percent", 33)
    max_position_value = current_balance * (max_position_pct / 100)
    
    rich.print(f"\n[dim]Current Balance: ${current_balance:.2f}[/]")
    rich.print(f"[dim]Max Position Size: ${max_position_value:.2f} ({max_position_pct}% of balance)[/]")
    rich.print(f"[dim]Utilization: {(trade_value/max_position_value)*100:.1f}%[/]")

# ═══════════════════════════════════════════════════════════════════
# commands/timer_commands.py - Timer and stopwatch commands
# ═══════════════════════════════════════════════════════════════════

import typer
import rich
import datetime as dt
import time
import os

from commands import stopwatch_manager

timer_app = typer.Typer()

@timer_app.command("stopwatch")
def stopwatch_command(
    action: str = typer.Argument(help="Action: start, stop, list"),
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Trade ID"),
    hours: int = typer.Option(None, "--hours", "-h", help="Hours (1 or 2)")
):
    """Manage stopwatch timers for trades"""
    
    if action.lower() == "start":
        if not trade_id:
            trade_id = typer.prompt("Trade ID")
        if not hours:
            hours = typer.prompt("Hours (1 or 2)", type=int, default=1)
        
        if hours not in [1, 2]:
            rich.print("[red]Hours must be 1 or 2[/]")
            return
        
        stopwatch_manager.start_stopwatch(trade_id, hours)
    
    elif action.lower() == "stop":
        if not trade_id:
            trade_id = typer.prompt("Trade ID")
        stopwatch_manager.stop_stopwatch(trade_id)
    
    elif action.lower() == "list":
        stopwatch_manager.list_active_stopwatches()
    
    else:
        rich.print("[red]Action must be: start, stop, or list[/]")

@timer_app.command("timer")
def timer_alias():
    """Alias for stopwatch command"""
    rich.print("Use: blotter.py timer stopwatch [start|stop|list]")

@timer_app.command("timers")
def show_timers_loud():
    """Show active timers in your face - prominently display all active stopwatches"""
    if not stopwatch_manager.active_timers:
        rich.print("\n[bold green]🎉 NO ACTIVE TIMERS - ALL CLEAR! 🎉[/]")
        rich.print("[dim]No positions are being watched by the stopwatch system[/]")
        return
    
    rich.print("\n" + "="*60)
    rich.print("[bold red]⚠️  ACTIVE STOPWATCH ALERTS ⚠️[/]")
    rich.print("="*60)
    
    now = dt.datetime.now()
    urgent_timers = []
    normal_timers = []
    
    for trade_id, timer_info in stopwatch_manager.active_timers.items():
        remaining = timer_info['end_time'] - now
        remaining_minutes = remaining.total_seconds() / 60
        
        if remaining_minutes <= 30:  # Less than 30 minutes
            urgent_timers.append((trade_id, timer_info, remaining))
        else:
            normal_timers.append((trade_id, timer_info, remaining))
    
    # Show urgent timers first (< 30 min)
    if urgent_timers:
        rich.print("\n[bold red]🚨 URGENT - EXPIRING SOON! 🚨[/]")
        for trade_id, timer_info, remaining in urgent_timers:
            minutes = int(remaining.total_seconds() / 60)
            seconds = int(remaining.total_seconds() % 60)
            
            rich.print(f"[bold red]💥 {trade_id}: {minutes}m {seconds}s remaining![/]")
            rich.print(f"[red]   Expires at: {timer_info['end_time'].strftime('%I:%M %p')}[/]")
            rich.print(f"[red]   Started: {timer_info['hours']}h ago[/]")
            
            # Find the trade and show basic info
            trade = stopwatch_manager._find_trade(trade_id)
            if trade:
                rich.print(f"[yellow]   Trade: {trade.strat} - {trade.typ}[/]")
            rich.print()
    
    # Show normal timers
    if normal_timers:
        rich.print("[bold yellow]⏰ ACTIVE TIMERS:[/]")
        for trade_id, timer_info, remaining in normal_timers:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            
            rich.print(f"[yellow]🕐 {trade_id}: {hours}h {minutes}m remaining[/]")
            rich.print(f"[dim]   Expires at: {timer_info['end_time'].strftime('%I:%M %p')}[/]")
            
            # Find the trade and show basic info
            trade = stopwatch_manager._find_trade(trade_id)
            if trade:
                rich.print(f"[dim]   Trade: {trade.strat} - {trade.typ}[/]")
            rich.print()
    
    rich.print("="*60)
    rich.print(f"[bold]Total Active Timers: {len(stopwatch_manager.active_timers)}[/]")
    rich.print("[dim]Run 'python blotter.py timer timers' again to refresh[/]")
    rich.print("="*60 + "\n")

@timer_app.command("watch")
def watch_timers():
    """Continuously watch timers (refreshes every 30 seconds)"""
    try:
        while True:
            # Clear screen
            os.system('clear' if os.name == 'posix' else 'cls')
            
            # Show current time
            rich.print(f"[bold]Current Time: {dt.datetime.now().strftime('%I:%M:%S %p')}[/]")
            
            # Show timers
            show_timers_loud()
            
            # Show refresh info
            rich.print("[dim]Refreshing every 30 seconds... Press Ctrl+C to stop[/]")
            
            # Wait 30 seconds
            time.sleep(30)
            
    except KeyboardInterrupt:
        rich.print("\n[yellow]Timer watching stopped[/]")

@timer_app.command("alert")
def timer_alert():
    """Quick timer status check - perfect for aliasing"""
    if not stopwatch_manager.active_timers:
        rich.print("[green]✅ No timers[/]")
        return
    
    now = dt.datetime.now()
    urgent_count = 0
    
    for trade_id, timer_info in stopwatch_manager.active_timers.items():
        remaining = timer_info['end_time'] - now
        remaining_minutes = remaining.total_seconds() / 60
        
        if remaining_minutes <= 30:
            urgent_count += 1
    
    total_timers = len(stopwatch_manager.active_timers)
    
    if urgent_count > 0:
        rich.print(f"[bold red]🚨 {urgent_count} URGENT TIMER(S)! ({total_timers} total)[/]")
    else:
        rich.print(f"[yellow]⏰ {total_timers} active timer(s)[/]")
    
    rich.print("[dim]Run 'blotter.py timer timers' for details[/]")



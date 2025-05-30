# stopwatch.py - Stopwatch system for options risk management with persistence
import threading
import time
import datetime as dt
import json
import os
from typing import Optional, Dict, Any
import typer
import rich

class StopwatchManager:
    """Manages stopwatch timers for trades to enforce PnL checks"""
    
    def __init__(self):
        self.active_timers = {}  # trade_id -> timer_info
        self.trade_ops = None  # Will be set from main
        self.book = None
        self.stopwatch_file = "stopwatches.json"
        self.load_persistent_timers()
    
    def set_trade_ops(self, trade_ops, book):
        """Set the trade operations handler and book reference"""
        self.trade_ops = trade_ops
        self.book = book
    
    def save_timers(self):
        """Save active timers to file"""
        timer_data = {}
        for trade_id, timer_info in self.active_timers.items():
            timer_data[trade_id] = {
                'trade_id': timer_info['trade_id'],
                'hours': timer_info['hours'],
                'start_time': timer_info['start_time'].isoformat(),
                'end_time': timer_info['end_time'].isoformat()
            }
        
        with open(self.stopwatch_file, 'w') as f:
            json.dump(timer_data, f, indent=2)
    
    def load_persistent_timers(self):
        """Load and restart timers from file"""
        if not os.path.exists(self.stopwatch_file):
            return
        
        try:
            with open(self.stopwatch_file, 'r') as f:
                timer_data = json.load(f)
            
            now = dt.datetime.now()
            
            for trade_id, data in timer_data.items():
                end_time = dt.datetime.fromisoformat(data['end_time'])
                
                if end_time > now:
                    # Timer hasn't expired yet, restart it
                    remaining_seconds = (end_time - now).total_seconds()
                    
                    timer_info = {
                        'trade_id': data['trade_id'],
                        'hours': data['hours'],
                        'start_time': dt.datetime.fromisoformat(data['start_time']),
                        'end_time': end_time,
                        'timer': None
                    }
                    
                    # Start the timer with remaining time
                    timer = threading.Timer(remaining_seconds, self._timer_expired, args=[trade_id])
                    timer.daemon = True
                    timer.start()
                    
                    timer_info['timer'] = timer
                    self.active_timers[trade_id] = timer_info
                    
                    remaining_hours = remaining_seconds / 3600
                    rich.print(f"[green]⏰ Restored stopwatch for {trade_id} ({remaining_hours:.1f}h remaining)[/]")
        
        except Exception as e:
            rich.print(f"[yellow]Warning: Could not load persistent timers: {e}[/]")
    
    def start_stopwatch(self, trade_id: str, hours: int):
        """Start a stopwatch for a trade"""
        if trade_id in self.active_timers:
            rich.print(f"[yellow]Stopwatch already running for trade {trade_id}[/]")
            return
        
        # Calculate end time
        end_time = dt.datetime.now() + dt.timedelta(hours=hours)
        
        # Create timer info
        timer_info = {
            'trade_id': trade_id,
            'hours': hours,
            'start_time': dt.datetime.now(),
            'end_time': end_time,
            'timer': None
        }
        
        # Start the timer thread
        timer = threading.Timer(hours * 3600, self._timer_expired, args=[trade_id])
        timer.daemon = True  # Dies when main program exits
        timer.start()
        
        timer_info['timer'] = timer
        self.active_timers[trade_id] = timer_info
        
        # Save to file
        self.save_timers()
        
        rich.print(f"[green]⏰ Stopwatch started for trade {trade_id}[/]")
        rich.print(f"[green]Will check PnL in {hours} hour{'s' if hours != 1 else ''} at {end_time.strftime('%I:%M %p')}[/]")
    
    def _timer_expired(self, trade_id: str):
        """Called when timer expires - check PnL and potentially close"""
        try:
            # Find the trade
            trade = self._find_trade(trade_id)
            if not trade:
                rich.print(f"[red]⏰ Timer expired but trade {trade_id} not found[/]")
                return
            
            if trade.status == "CLOSED":
                rich.print(f"[yellow]⏰ Timer expired but trade {trade_id} already closed[/]")
                self._cleanup_timer(trade_id)
                return
            
            rich.print(f"\n[bold red]⏰ STOPWATCH EXPIRED for trade {trade_id}![/]")
            rich.print(f"[bold yellow]Time to check PnL and decide on this trade![/]")
            
            # Show trade info
            self._show_trade_summary(trade)
            
            # Get current PnL from user
            current_pnl = self._get_current_pnl()
            
            if current_pnl < 0:
                rich.print(f"[red]💸 Negative PnL detected: ${current_pnl:.2f}[/]")
                rich.print(f"[red]🔥 Risk management rule: MUST CLOSE losing position![/]")
                
                # Force close the trade
                if typer.confirm("Proceed with automatic close of losing position?", default=True):
                    self._force_close_trade(trade_id, abs(current_pnl))
                else:
                    rich.print(f"[yellow]⚠️  Manual close required - position still losing![/]")
            else:
                rich.print(f"[green]✅ Positive PnL: ${current_pnl:.2f}[/]")
                
                # Ask if they want to extend or close
                action = typer.prompt(
                    "Action", 
                    type=typer.Choice(["close", "extend1h", "extend2h", "monitor"]),
                    default="monitor"
                )
                
                if action == "close":
                    self.trade_ops.close_trade_partial(trade_id, None)
                elif action == "extend1h":
                    self.start_stopwatch(trade_id, 1)
                elif action == "extend2h":
                    self.start_stopwatch(trade_id, 2)
                else:
                    rich.print(f"[yellow]Continuing to monitor {trade_id}[/]")
            
            # Clean up the timer
            self._cleanup_timer(trade_id)
            
        except Exception as e:
            rich.print(f"[red]Error in timer callback: {e}[/]")
    
    def _get_current_pnl(self) -> float:
        """Get current PnL from user input"""
        rich.print(f"\n[bold cyan]Enter Current PnL:[/]")
        rich.print(f"[dim]Check your broker platform and enter the current unrealized PnL[/]")
        
        while True:
            try:
                pnl_str = typer.prompt("Current PnL ($)")
                # Handle both positive and negative inputs
                if pnl_str.startswith('-'):
                    return -abs(float(pnl_str[1:]))
                elif pnl_str.startswith('+'):
                    return abs(float(pnl_str[1:]))
                else:
                    return float(pnl_str)
            except ValueError:
                rich.print("[red]Please enter a valid number (e.g., -50.25 or 75.50)[/]")
    
    def _force_close_trade(self, trade_id: str, loss_amount: float):
        """Force close a losing trade"""
        rich.print(f"\n[bold red]🚨 FORCE CLOSING LOSING POSITION {trade_id}[/]")
        rich.print(f"[red]Loss amount: ${loss_amount:.2f}[/]")
        
        # Use the existing close functionality
        success = self.trade_ops.close_trade_partial(trade_id, None)
        
        if success:
            rich.print(f"[green]✅ Successfully closed losing position {trade_id}[/]")
            rich.print(f"[green]Risk management rule enforced![/]")
        else:
            rich.print(f"[red]❌ Failed to close {trade_id} - manual intervention required![/]")
    
    def _show_trade_summary(self, trade):
        """Show a summary of the trade"""
        rich.print(f"\n[bold]Trade Summary: {trade.id}[/]")
        rich.print(f"Strategy: {trade.strat}")
        rich.print(f"Type: {trade.typ}")
        rich.print(f"Opened: {trade.ts}")
        
        for i, leg in enumerate(trade.legs):
            rich.print(f"Leg {i+1}: {leg.side} {leg.qty} {leg.symbol} @ ${leg.entry}")
    
    def _find_trade(self, trade_id: str):
        """Find a trade by ID"""
        if self.book:
            for trade in self.book:
                if trade.id == trade_id:
                    return trade
        return None
    
    def _cleanup_timer(self, trade_id: str):
        """Clean up expired timer"""
        if trade_id in self.active_timers:
            del self.active_timers[trade_id]
            self.save_timers()  # Update persistent storage
    
    def stop_stopwatch(self, trade_id: str):
        """Stop a running stopwatch"""
        if trade_id not in self.active_timers:
            rich.print(f"[yellow]No active stopwatch for trade {trade_id}[/]")
            return False
        
        timer_info = self.active_timers[trade_id]
        timer_info['timer'].cancel()
        del self.active_timers[trade_id]
        
        # Update persistent storage
        self.save_timers()
        
        rich.print(f"[green]⏰ Stopped stopwatch for trade {trade_id}[/]")
        return True
    
    def list_active_stopwatches(self):
        """List all active stopwatches"""
        if not self.active_timers:
            rich.print("[dim]No active stopwatches[/]")
            return
        
        rich.print("[bold]Active Stopwatches:[/]")
        now = dt.datetime.now()
        
        for trade_id, timer_info in self.active_timers.items():
            remaining = timer_info['end_time'] - now
            if remaining.total_seconds() > 0:
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                rich.print(f"  • {trade_id}: {hours}h {minutes}m remaining (expires at {timer_info['end_time'].strftime('%I:%M %p')})")
            else:
                rich.print(f"  • {trade_id}: [red]EXPIRED[/]")

# Risk Management Functions
class RiskManager:
    """Additional risk management controls"""
    
    def __init__(self, cfg: dict, book: list):
        self.cfg = cfg
        self.book = book
    
    def check_position_sizing(self, trade_value: float, account_balance: float) -> bool:
        """Check if position size violates risk limits"""
        max_position_pct = self.cfg.get("risk_limits", {}).get("max_position_percent", 33)  # Default 1/3
        max_position_value = account_balance * (max_position_pct / 100)
        
        if trade_value > max_position_value:
            rich.print(f"[red]❌ Position size violation![/]")
            rich.print(f"[red]Trade value: ${trade_value:.2f}[/]")
            rich.print(f"[red]Max allowed: ${max_position_value:.2f} ({max_position_pct}% of ${account_balance:.2f})[/]")
            return False
        
        return True
    
    def check_hot_hand_cooloff(self) -> bool:
        """Check if in cool-off period after winning streak"""
        cooloff_config = self.cfg.get("risk_limits", {}).get("hot_hand_cooloff", {})
        if not cooloff_config.get("enabled", False):
            return True
        
        wins_threshold = cooloff_config.get("consecutive_wins", 3)
        cooloff_hours = cooloff_config.get("cooloff_hours", 24)
        
        # Count recent consecutive wins
        recent_trades = sorted([t for t in self.book if t.status == "CLOSED"], 
                              key=lambda x: x.ts, reverse=True)
        
        consecutive_wins = 0
        for trade in recent_trades:
            if hasattr(trade, 'pnl') and trade.pnl and trade.pnl > 0:
                consecutive_wins += 1
            else:
                break
        
        if consecutive_wins >= wins_threshold:
            # Check if still in cooloff period
            last_trade_time = dt.datetime.fromisoformat(recent_trades[0].ts.replace('Z', '+00:00'))
            cooloff_end = last_trade_time + dt.timedelta(hours=cooloff_hours)
            
            if dt.datetime.now(dt.timezone.utc) < cooloff_end:
                remaining = cooloff_end - dt.datetime.now(dt.timezone.utc)
                rich.print(f"[yellow]🔥 Hot hand detected: {consecutive_wins} consecutive wins[/]")
                rich.print(f"[yellow]⏱️  Cool-off period: {remaining.total_seconds()/3600:.1f}h remaining[/]")
                return False
        
        return True
    
    def get_current_balance(self) -> float:
        """Calculate current account balance from trades"""
        balance_config = self.cfg.get("risk_limits", {})
        starting_balance = balance_config.get("starting_balance", 10000)
        
        # Calculate total PnL from all closed trades
        total_pnl = sum(trade.pnl for trade in self.book 
                       if trade.status == "CLOSED" and hasattr(trade, 'pnl') and trade.pnl)
        
        current_balance = starting_balance + total_pnl
        return current_balance

# Global instances
stopwatch_manager = StopwatchManager()
risk_manager = None  # Will be initialized with config

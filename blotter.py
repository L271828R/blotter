# ═══════════════════════════════════════════════════════════════════
# Complete blotter.py - Main application with all commands
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations
import typer
import rich
import datetime as dt

from models import Risk, Leg, Trade, CommissionFees
from config import load_config
from persistence import load_book, save_book, import_inbox_files
from utils import blocked_for_options, to_decimal, calculate_costs
from ls import list_trades
from recalc import recalc_trade_pnl, recalc_all_trades, fix_data_types
from audit import audit_trade, audit_all_positions

app = typer.Typer()

cfg = load_config()
book = load_book()

def fix_legacy_commission_format():
    """Fix legacy commission format"""
    needs_save = False
    
    for trade in book:
        for leg in trade.legs:
            if isinstance(leg.entry_costs, dict):
                leg.entry_costs = CommissionFees(
                    commission=to_decimal(leg.entry_costs.get("commission", "0")),
                    exchange_fees=to_decimal(leg.entry_costs.get("exchange_fees", "0")),
                    regulatory_fees=to_decimal(leg.entry_costs.get("regulatory_fees", "0"))
                )
                needs_save = True
            
            if isinstance(leg.exit_costs, dict):
                leg.exit_costs = CommissionFees(
                    commission=to_decimal(leg.exit_costs.get("commission", "0")),
                    exchange_fees=to_decimal(leg.exit_costs.get("exchange_fees", "0")),
                    regulatory_fees=to_decimal(leg.exit_costs.get("regulatory_fees", "0"))
                )
                needs_save = True
    
    if needs_save:
        save_book(book)

fix_legacy_commission_format()

added = import_inbox_files(book)
if added > 0:
    save_book(book)

# Create trade operations handler (you'll need to create this file too)
from trade_operations import TradeOperations
from stopwatch import stopwatch_manager, RiskManager
from images import image_manager

trade_ops = TradeOperations(book, cfg)

# Initialize stopwatch manager and risk manager
stopwatch_manager.set_trade_ops(trade_ops, book)
risk_manager = RiskManager(cfg, book)

@app.command("open")
def open_trade(
    strat: str = typer.Option(None, help="Strategy"),
    typ: str = typer.Option(None, help="FUTURE or OPTION"),
    side: str = typer.Option(None, help="BUY or SELL"),
    symbol: str = typer.Option(None, help="Ticker"),
    qty: int = typer.Option(None, help="Contracts"),
    price: str = typer.Option(None, help="Fill price"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Test mode: override blocks and don't save trade"),
    stopwatch: int = typer.Option(None, "--stopwatch", help="Start stopwatch timer (1 or 2 hours)"),
):
    """Open a new trade"""
    # Show dry run notice
    if dry_run:
        rich.print("[bold yellow]🧪 DRY RUN MODE - Trade will not be saved and blocks are ignored[/]")
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

    # Handle spread strategies and get the trade object back
    trade = None
    if u == "BULL-PUT":
        trade = trade_ops.open_bull_put_spread(qty, strat, dry_run=dry_run)
    elif u == "BULL-PUT-OVERNIGHT":
        trade = trade_ops.open_bull_put_spread(qty, u, dry_run=dry_run)
    elif u == "BEAR-CALL":
        trade = trade_ops.open_bear_call_spread(qty, dry_run=dry_run)
    else:
        # Handle single-leg trades
        typ = typ or typer.prompt("Type", default="FUTURE")
        side = side or typer.prompt("Side", default="BUY")
        symbol = symbol or typer.prompt("Symbol")
        qty = qty or int(typer.prompt("Quantity", default="1"))
        price = price or typer.prompt("Entry price")
        
        trade = trade_ops.open_single_leg_trade(strat, typ, side, symbol, qty, price, dry_run=dry_run)
    
    # Start stopwatch if requested and it's an option trade
    if trade and not dry_run and trade.typ.startswith("OPTION"):
        # Ask for stopwatch if not provided and it's an option
        if stopwatch is None:
            if typer.confirm("Start risk management stopwatch for this option?"):
                stopwatch = typer.prompt("Hours (1 or 2)", type=int, default=1)
        
        if stopwatch:
            if stopwatch in [1, 2]:
                stopwatch_manager.start_stopwatch(trade.id, stopwatch)
            else:
                rich.print("[red]Stopwatch must be 1 or 2 hours[/]")

@app.command("close")
def close_trade(
    trade_id: str,
    qty: int = typer.Option(None, help="Quantity to close (partial close)")
):
    """Close a trade completely or partially"""
    trade_ops.close_trade_partial(trade_id, qty)

@app.command("pnl2h")
def record_2h_pnl(trade_id: str = typer.Option(None, help="Trade ID to record 2H PnL for")):
    """Record 2-hour PnL for a trade (required for BULL-PUT-OVERNIGHT before closing)"""
    # You'll need to implement this - similar to your original code
    rich.print("2H PnL recording not yet implemented in modules")

@app.command("fix")
def fix_trade_prices(trade_id: str):
    """Manually fix trade prices and recalculate PnL"""
    
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



@app.command("ls")
def ls_command():
    """List all trades"""
    list_trades(book)

@app.command("recalc")
def recalc_pnl(
    trade_id: str = typer.Option(None, help="Trade ID to recalculate (leave empty for all trades)"),
    details: bool = typer.Option(False, "--details", "-d", help="Show detailed breakdown")
):
    """Recalculate PnL for a trade or all trades"""
    fix_data_types(book)
    
    if trade_id:
        recalc_trade_pnl(trade_id, book, show_details=details)
    else:
        if typer.confirm("Recalculate PnL for ALL closed trades?"):
            recalc_all_trades(book)

@app.command("fixdata") 
def fix_data_types_command():
    """Fix data type issues (string PnL values, etc.)"""
    rich.print("[cyan]Checking for data type issues...[/]")
    
    if fix_data_types(book):
        rich.print("[green]✓ Data types fixed and saved[/]")
    else:
        rich.print("[dim]No data type issues found[/]")

@app.command("audit")
def audit_command(
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Specific trade ID to audit"),
    status: str = typer.Option("ALL", "--status", "-s", help="Filter by status: ALL, OPEN, CLOSED")
):
    """Audit trade PnL calculations and costs"""
    if trade_id:
        audit_trade(trade_id, book)
    else:
        audit_all_positions(book, status.upper())

@app.command("addcosts")
def add_missing_costs():
    """Add missing commission and fees to old trades"""
    rich.print("[cyan]Adding missing costs to trades with zero costs...[/]")
    
    updated_count = 0
    
    for trade in book:
        for leg in trade.legs:
            if leg.entry_costs.total() == 0:
                if trade.typ.startswith("OPTION"):
                    trade_type = "OPTION"
                else:
                    trade_type = "FUTURE"
                
                leg.entry_costs = calculate_costs(trade_type, leg.qty, cfg)
                updated_count += 1
                
                rich.print(f"  Added entry costs to {trade.id} leg {leg.symbol}: ${leg.entry_costs.total():.2f}")
            
            if leg.exit is not None and leg.exit_costs is None:
                if trade.typ.startswith("OPTION"):
                    trade_type = "OPTION"
                else:
                    trade_type = "FUTURE"
                
                leg.exit_costs = calculate_costs(trade_type, leg.qty, cfg)
                updated_count += 1
                
                rich.print(f"  Added exit costs to {trade.id} leg {leg.symbol}: ${leg.exit_costs.total():.2f}")
    
    if updated_count > 0:
        rich.print(f"\n[yellow]Updated {updated_count} legs with missing costs[/]")
        rich.print("[yellow]Now recalculating PnL with proper costs...[/]")
        
        for trade in book:
            if trade.status == "CLOSED":
                trade.pnl = trade.net_pnl()
        
        save_book(book)
        rich.print("[green]✓ All costs added and PnL recalculated![/]")
        
        rich.print("\n[bold]Updated trades:[/]")
        for trade in book:
            if trade.status == "CLOSED":
                gross = trade.gross_pnl()
                net = trade.net_pnl()
                costs = trade.total_costs()
                rich.print(f"  {trade.id}: Gross ${gross:.2f} - Costs ${costs:.2f} = Net ${net:.2f}")
    else:
        rich.print("[dim]No missing costs found[/]")

@app.command("blocks")
def show_option_blocks():
    """Show current option block configuration and status"""
    rich.print("[bold]Option Trading Blocks[/]")
    
    now = dt.datetime.now().time()
    is_blocked, active_block = blocked_for_options(cfg)
    
    if is_blocked:
        rich.print(f"[red]🚫 Currently BLOCKED: {active_block}[/]")
    else:
        rich.print("[green]✅ Options trading currently ALLOWED[/]")
    
    rich.print("\n[bold]Configured Blocks:[/]")
    
    def format_time_12h(time_str: str) -> str:
        """Convert 24-hour time string to 12-hour format"""
        time_obj = dt.time.fromisoformat(time_str)
        return dt.datetime.combine(dt.date.today(), time_obj).strftime("%-I:%M %p")
    
    if "option_block" in cfg:
        start = cfg["option_block"]["start"]
        end = cfg["option_block"]["end"]
        name = cfg["option_block"].get("name", "Legacy Block")
        start_12h = format_time_12h(start)
        end_12h = format_time_12h(end)
        rich.print(f"  • {name}: {start_12h} - {end_12h}")
    
    if "option_blocks" in cfg:
        for block in cfg["option_blocks"]:
            start = block["start"]
            end = block["end"]
            name = block.get("name", "Unnamed Block")
            
            start_time = dt.time.fromisoformat(start)
            end_time = dt.time.fromisoformat(end)
            
            is_active = False
            if start_time > end_time:
                is_active = now >= start_time or now <= end_time
            else:
                is_active = start_time <= now <= end_time
            
            start_12h = format_time_12h(start)
            end_12h = format_time_12h(end)
            
            status = " [red](ACTIVE)[/]" if is_active else ""
            rich.print(f"  • {name}: {start_12h} - {end_12h}{status}")
    
    # Show block exemptions (using your "exemption" format)
    exempt_strategies = cfg.get("exemption", [])
    
    if exempt_strategies:
        rich.print("\n[bold]Block-Exempt Strategies:[/]")
        for strategy in exempt_strategies:
            rich.print(f"  • [green]{strategy}[/]: Allowed during blocks")
    else:
        rich.print("\n[dim]No strategies are exempt from blocks[/]")
    
    rich.print(f"\n[dim]Tip: Add strategies to 'exemption' list in config.yaml to allow trading during blocks[/]")

@app.command("stopwatch")
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

@app.command("timer")
def timer_alias():
    """Alias for stopwatch command"""
    rich.print("Use: blotter.py stopwatch [start|stop|list]")

@app.command("timers")
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
    rich.print("[dim]Run 'python blotter.py timers' again to refresh[/]")
    rich.print("="*60 + "\n")

@app.command("watch")
def watch_timers():
    """Continuously watch timers (refreshes every 30 seconds)"""
    import time
    import os
    
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

@app.command("alert")
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
    
    rich.print("[dim]Run 'blotter.py timers' for details[/]")

@app.command("balance")
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

@app.command("risk")
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

@app.command("attach")
def attach_image(
    trade_id: str,
    image_path: str,
    category: str = typer.Option("screenshots", help="Category: screenshots, charts, setup, exit"),
    description: str = typer.Option("", help="Description of the image"),
    copy: bool = typer.Option(True, "--copy/--no-copy", help="Copy file to trade_images folder")
):
    """Attach an image to a trade"""
    result = image_manager.attach_image(trade_id, image_path, category, description, copy, book)
    if result:
        # Save the updated book with image data
        save_book(book)
        rich.print(f"[green]📁 Trade data saved with image attachment[/]")

@app.command("images")
def show_images(
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Trade ID to show images for")
):
    """Show images attached to a trade"""
    if not trade_id:
        trade_id = typer.prompt("Trade ID")
    
    image_manager.show_trade_images(trade_id, book)

@app.command("report")
def generate_report(
    trade_id: str,
    export: bool = typer.Option(False, "--export", help="Export to markdown file"),
    images: bool = typer.Option(True, "--images/--no-images", help="Include images in report")
):
    """Generate a comprehensive trade report"""
    # Find the trade
    trade = None
    for t in book:
        if t.id == trade_id:
            trade = t
            break
    
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return
    
    if export:
        # Export to markdown file
        output_file = image_manager.export_trade_report(trade)
        if output_file:
            # Create clickable link to the report
            abs_path = os.path.abspath(output_file)
            file_url = f"file://{abs_path}"
            rich.print(f"[blue underline][link={file_url}]Click to open report[/link][/]")
    else:
        # Display report in terminal
        report_content = image_manager.generate_trade_report(trade, images)
        rich.print(report_content)

@app.command("screenshot")
def quick_screenshot(
    trade_id: str,
    description: str = typer.Option("", help="Description of screenshot")
):
    """Quick screenshot command - takes screenshot and attaches to trade"""
    rich.print(f"[yellow]📸 Taking screenshot for trade {trade_id}[/]")
    
    # Use macOS screenshot command
    import subprocess
    import tempfile
    import datetime as dt
    
    # Create temporary file
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file = f"/tmp/trade_screenshot_{trade_id}_{timestamp}.png"
    
    try:
        # Take screenshot with macOS screencapture
        result = subprocess.run([
            "screencapture", 
            "-i",  # Interactive selection
            temp_file
        ], check=True)
        
        if os.path.exists(temp_file):
            # Attach the screenshot
            final_path = image_manager.attach_image(
                trade_id, 
                temp_file, 
                "screenshots", 
                description or f"Screenshot taken at {dt.datetime.now().strftime('%I:%M %p')}",
                True,  # copy_file
                book   # pass book for JSON persistence
            )
            
            # Clean up temp file
            os.unlink(temp_file)
            
            if final_path:
                # Save the updated book
                save_book(book)
                rich.print(f"[green]✅ Screenshot attached to trade {trade_id} and saved[/]")
        else:
            rich.print("[yellow]Screenshot cancelled[/]")
            
    except subprocess.CalledProcessError:
        rich.print("[red]Error taking screenshot[/]")
    except Exception as e:
        rich.print(f"[red]Error: {e}[/]")

@app.command("gallery")
def show_gallery():
    """Show a gallery of all trade images"""
    all_images = []
    
    # Get all trades with images
    for trade in book:
        images = image_manager.get_trade_images(trade.id, book)
        for img in images:
            img['trade_id'] = trade.id
            img['trade_strategy'] = trade.strat
            img['trade_status'] = trade.status
            all_images.append(img)
    
    if not all_images:
        rich.print("[yellow]No images found in any trades[/]")
        return
    
    rich.print(f"\n[bold]Trade Image Gallery ({len(all_images)} images):[/]")
    
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Trade ID", style="cyan")
    table.add_column("Strategy", style="white")
    table.add_column("Category", style="yellow")
    table.add_column("Description", style="white")
    table.add_column("Image Link", style="blue underline")
    
    for img in sorted(all_images, key=lambda x: (x['trade_id'], x['category'])):
        file_url = f"file://{img['path']}"
        clickable_link = f"[link={file_url}]{img['filename']}[/link]"
        
        table.add_row(
            img['trade_id'],
            img['trade_strategy'],
            img['category'],
            img['description'] or "[dim]No description[/dim]",
            clickable_link
        )
    
    rich.print(table)
    rich.print(f"[dim]💡 Command+Click on links to open images on macOS[/dim]")

@app.command("migrate-images")
def migrate_images():
    """Migrate existing filesystem images to trade JSON data"""
    rich.print("[cyan]Migrating filesystem images to trade data...[/]")
    
    migrated = image_manager.migrate_filesystem_images_to_trades(book)
    
    if migrated > 0:
        save_book(book)
        rich.print(f"[green]✅ Migration complete! {migrated} images now stored in trade JSON[/]")
    else:
        rich.print("[dim]No images found to migrate[/]")

if __name__ == "__main__":
    app()

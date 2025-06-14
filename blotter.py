# ═══════════════════════════════════════════════════════════════════
# blotter.py - Main application with backward compatibility and historical support
# ═══════════════════════════════════════════════════════════════════
from __future__ import annotations  # Fix: double underscore, not **
import typer

# Updated imports from core
from core.config import load_config
from core.persistence import load_book, save_book, import_inbox_files
from core.models import CommissionFees
from utils import to_decimal

# Import command modules (these stay the same)
from commands.trade_commands import trade_app
from commands.management_commands import mgmt_app
from commands.timer_commands import timer_app
from commands.image_commands import image_app
from commands.risk_commands import risk_app
from commands.trade_commands import (
    open_trade, 
    close_trade, 
    fix_trade_prices, 
    ls_command, 
    record_2h_pnl, 
    expire_spread,
    delete_trade  # You can combine this with the other imports above
)
# Rest of your blotter.py code stays the same...

# Create main app and add sub-apps
app = typer.Typer()
app.add_typer(trade_app, name="trade", help="Trade operations")
app.add_typer(mgmt_app, name="mgmt", help="Management operations")
app.add_typer(timer_app, name="timer", help="Timer operations")
app.add_typer(image_app, name="image", help="Image operations")
app.add_typer(risk_app, name="risk", help="Risk management")

# Global initialization
cfg = load_config()
book = load_book()




# Add these aliases to the backward compatibility section:

@app.command("delete")
def delete_alias(
    trade_id: str,
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """Delete a trade (alias for 'trade delete')"""
    return delete_trade(trade_id, force)

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

# Initialize data
fix_legacy_commission_format()
added = import_inbox_files(book)
if added > 0:
    save_book(book)

# Set global references for command modules
from commands import set_globals
set_globals(cfg, book)

# ═══════════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY ALIASES - Keep your old commands working!
# ═══════════════════════════════════════════════════════════════════

# Import the actual command functions
from commands.trade_commands import open_trade, close_trade, fix_trade_prices, ls_command, record_2h_pnl
from commands.management_commands import recalc_pnl, fix_data_types_command, audit_command, add_missing_costs, show_option_blocks
from commands.timer_commands import stopwatch_command, show_timers_loud, watch_timers, timer_alert
from commands.image_commands import attach_image, show_images, generate_report, quick_screenshot, show_gallery, migrate_images
from commands.risk_commands import show_balance, risk_check

# Trade command aliases
@app.command("open")
def open_alias(
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
    """Open a new trade (alias for 'trade open')"""
    return open_trade(strat, typ, side, symbol, qty, price, dry_run, stopwatch, historical)

@app.command("close")
def close_alias(
    trade_id: str,
    qty: int = typer.Option(None, help="Quantity to close (partial close)")
):
    """Close a trade (alias for 'trade close')"""
    return close_trade(trade_id, qty)

@app.command("fix")
def fix_alias(trade_id: str):
    """Fix trade prices (alias for 'trade fix')"""
    return fix_trade_prices(trade_id)

@app.command("ls")
def ls_alias():
    """List all trades (alias for 'trade ls')"""
    return ls_command()

@app.command("pnl2h")
def pnl2h_alias(trade_id: str = typer.Option(None, help="Trade ID to record 2H PnL for")):
    """Record 2H PnL (alias for 'trade pnl2h')"""
    return record_2h_pnl(trade_id)

# Management command aliases
@app.command("recalc")
def recalc_alias(
    trade_id: str = typer.Option(None, help="Trade ID to recalculate (leave empty for all trades)"),
    details: bool = typer.Option(False, "--details", "-d", help="Show detailed breakdown")
):
    """Recalculate PnL (alias for 'mgmt recalc')"""
    return recalc_pnl(trade_id, details)

@app.command("fixdata")
def fixdata_alias():
    """Fix data types (alias for 'mgmt fixdata')"""
    return fix_data_types_command()

@app.command("audit")
def audit_alias(
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Specific trade ID to audit"),
    status: str = typer.Option("ALL", "--status", "-s", help="Filter by status: ALL, OPEN, CLOSED")
):
    """Audit trades (alias for 'mgmt audit')"""
    return audit_command(trade_id, status)

@app.command("addcosts")
def addcosts_alias():
    """Add missing costs (alias for 'mgmt addcosts')"""
    return add_missing_costs()

@app.command("blocks")
def blocks_alias():
    """Show option blocks (alias for 'mgmt blocks')"""
    return show_option_blocks()

# Timer command aliases
@app.command("stopwatch")
def stopwatch_alias(
    action: str = typer.Argument(help="Action: start, stop, list"),
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Trade ID"),
    hours: int = typer.Option(None, "--hours", "-h", help="Hours (1 or 2)")
):
    """Manage stopwatch (alias for 'timer stopwatch')"""
    return stopwatch_command(action, trade_id, hours)

@app.command("timers")
def timers_alias():
    """Show timers (alias for 'timer timers')"""
    return show_timers_loud()

@app.command("watch")
def watch_alias():
    """Watch timers (alias for 'timer watch')"""
    return watch_timers()

@app.command("alert")
def alert_alias():
    """Timer alert (alias for 'timer alert')"""
    return timer_alert()

# Image command aliases
@app.command("attach")
def attach_alias(
    trade_id: str,
    image_path: str,
    category: str = typer.Option("screenshots", help="Category: screenshots, charts, setup, exit"),
    description: str = typer.Option("", help="Description of the image"),
    copy: bool = typer.Option(True, "--copy/--no-copy", help="Copy file to trade_images folder")
):
    """Attach image (alias for 'image attach')"""
    return attach_image(trade_id, image_path, category, description, copy)

@app.command("images")
def images_alias(
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Trade ID to show images for")
):
    """Show images (alias for 'image images')"""
    return show_images(trade_id)

@app.command("report")
def report_alias(
    trade_id: str,
    export: bool = typer.Option(False, "--export", help="Export to markdown file"),
    images: bool = typer.Option(True, "--images/--no-images", help="Include images in report")
):
    """Generate report (alias for 'image report')"""
    return generate_report(trade_id, export, images)

@app.command("screenshot")
def screenshot_alias(
    trade_id: str,
    description: str = typer.Option("", help="Description of screenshot")
):
    """Take screenshot (alias for 'image screenshot')"""
    return quick_screenshot(trade_id, description)

@app.command("gallery")
def gallery_alias():
    """Show gallery (alias for 'image gallery')"""
    return show_gallery()

@app.command("migrate-images")
def migrate_images_alias():
    """Migrate images (alias for 'image migrate-images')"""
    return migrate_images()

# Risk command aliases
@app.command("balance")
def balance_alias():
    """Show balance (alias for 'risk balance')"""
    return show_balance()

@app.command("risk")
def risk_alias(
    trade_value: float = typer.Option(None, "--value", help="Trade value to check"),
):
    """Check risk (alias for 'risk check')"""
    return risk_check(trade_value)


@app.command("expire-spread")
def expire_spread_alias(trade_id: str):
    """Expire entire spread (alias for 'trade expire-spread')"""
    return expire_spread(trade_id)


if __name__ == "__main__":
    app()

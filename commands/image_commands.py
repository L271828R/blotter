# ═══════════════════════════════════════════════════════════════════
# commands/image_commands.py - Image and screenshot commands
# ═══════════════════════════════════════════════════════════════════

import typer
import rich
import datetime as dt
import subprocess
import os
from rich.table import Table

from commands import image_manager, book
from core.persistence import save_book

image_app = typer.Typer()

@image_app.command("attach")
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

@image_app.command("images")
def show_images(
    trade_id: str = typer.Option(None, "--trade-id", "-t", help="Trade ID to show images for")
):
    """Show images attached to a trade"""
    if not trade_id:
        trade_id = typer.prompt("Trade ID")
    
    image_manager.show_trade_images(trade_id, book)

@image_app.command("report")
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

@image_app.command("screenshot")
def quick_screenshot(
    trade_id: str,
    description: str = typer.Option("", help="Description of screenshot")
):
    """Quick screenshot command - takes screenshot and attaches to trade"""
    rich.print(f"[yellow]📸 Taking screenshot for trade {trade_id}[/]")
    
    # Use macOS screenshot command
    import tempfile
    
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

@image_app.command("gallery")
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

@image_app.command("migrate-images")
def migrate_images():
    """Migrate existing filesystem images to trade JSON data"""
    rich.print("[cyan]Migrating filesystem images to trade data...[/]")
    
    migrated = image_manager.migrate_filesystem_images_to_trades(book)
    
    if migrated > 0:
        save_book(book)
        rich.print(f"[green]✅ Migration complete! {migrated} images now stored in trade JSON[/]")
    else:
        rich.print("[dim]No images found to migrate[/]")


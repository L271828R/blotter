# images.py - Trade image attachment system
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional
import typer
import rich
from rich.table import Table

class ImageManager:
    """Manages image attachments for trades"""
    
    def __init__(self, images_dir: str = "trade_images"):
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(exist_ok=True)
        
        # Create subdirectories for organization
        (self.images_dir / "screenshots").mkdir(exist_ok=True)
        (self.images_dir / "charts").mkdir(exist_ok=True)
        (self.images_dir / "setup").mkdir(exist_ok=True)
        (self.images_dir / "exit").mkdir(exist_ok=True)
    
    def attach_image(self, trade_id: str, image_path: str, category: str = "screenshots", 
                    description: str = "", copy_file: bool = True, book: list = None) -> Optional[str]:
        """
        Attach an image to a trade
        
        Args:
            trade_id: Trade ID to attach image to
            image_path: Path to the source image
            category: Category (screenshots, charts, setup, exit)
            description: Optional description
            copy_file: Whether to copy file to trade_images folder
            book: Trade book to update (will update trade JSON)
            
        Returns:
            Path to the attached image or None if failed
        """
        source_path = Path(image_path)
        
        if not source_path.exists():
            rich.print(f"[red]Error: Image file not found: {image_path}[/]")
            return None
        
        # Validate category
        valid_categories = ["screenshots", "charts", "setup", "exit"]
        if category not in valid_categories:
            rich.print(f"[red]Invalid category. Use: {', '.join(valid_categories)}[/]")
            return None
        
        # Generate unique filename to avoid conflicts
        timestamp = uuid.uuid4().hex[:8]
        file_extension = source_path.suffix.lower()
        new_filename = f"{trade_id}_{timestamp}_{category}{file_extension}"
        
        # Determine destination path
        dest_path = self.images_dir / category / new_filename
        
        try:
            if copy_file:
                # Copy the file to our images directory
                shutil.copy2(source_path, dest_path)
                final_path = dest_path
            else:
                # Just reference the original file
                final_path = source_path.resolve()
            
            # Create metadata file
            metadata_file = dest_path.with_suffix('.txt')
            with open(metadata_file, 'w') as f:
                f.write(f"Trade ID: {trade_id}\n")
                f.write(f"Category: {category}\n")
                f.write(f"Description: {description}\n")
                f.write(f"Original Path: {source_path}\n")
                f.write(f"Attached Path: {final_path}\n")
            
            # Update trade JSON if book is provided
            if book:
                self._update_trade_images(trade_id, str(final_path), category, description, book)
            
            rich.print(f"[green]✅ Image attached to trade {trade_id}[/]")
            rich.print(f"[green]Category: {category}[/]")
            rich.print(f"[green]Path: {final_path}[/]")
            
            return str(final_path)
            
        except Exception as e:
            rich.print(f"[red]Error attaching image: {e}[/]")
            return None
    
    def _update_trade_images(self, trade_id: str, image_path: str, category: str, description: str, book: list):
        """Update the trade object with image information"""
        # Find the trade in the book
        trade = None
        for t in book:
            if t.id == trade_id:
                trade = t
                break
        
        if not trade:
            rich.print(f"[yellow]Warning: Trade {trade_id} not found in book[/]")
            return
        
        # Initialize images list if it doesn't exist
        if not hasattr(trade, 'images'):
            trade.images = []
        
        # Create image record
        image_record = {
            'path': image_path,
            'category': category,
            'description': description,
            'filename': Path(image_path).name,
            'attached_at': dt.datetime.now().isoformat()
        }
        
        trade.images.append(image_record)
        
        rich.print(f"[green]✅ Image record added to trade {trade_id} data[/]")
    
    def get_trade_images(self, trade_id: str, book: list = None) -> List[dict]:
        """Get all images for a specific trade - checks both trade data and file system"""
        images = []
        
        # First, try to get images from trade data (if book provided)
        if book:
            trade = None
            for t in book:
                if t.id == trade_id:
                    trade = t
                    break
            
            if trade and hasattr(trade, 'images'):
                for img_record in trade.images:
                    # Verify the file still exists
                    if Path(img_record['path']).exists():
                        images.append(img_record)
                    else:
                        rich.print(f"[yellow]Warning: Image file missing: {img_record['path']}[/]")
        
        # Fallback: search file system if no images found in trade data
        if not images:
            images = self._get_images_from_filesystem(trade_id)
        
        return sorted(images, key=lambda x: x['category'])
    
    def _get_images_from_filesystem(self, trade_id: str) -> List[dict]:
        """Fallback method: get images by searching file system"""
        images = []
        
        # Search through all category directories
        for category_dir in self.images_dir.iterdir():
            if not category_dir.is_dir():
                continue
                
            # Look for images and metadata files for this trade
            for file_path in category_dir.glob(f"{trade_id}_*"):
                if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']:
                    # Found an image file
                    metadata_file = file_path.with_suffix('.txt')
                    description = ""
                    
                    if metadata_file.exists():
                        try:
                            with open(metadata_file, 'r') as f:
                                metadata = f.read()
                                for line in metadata.split('\n'):
                                    if line.startswith('Description: '):
                                        description = line.replace('Description: ', '').strip()
                                        break
                        except Exception:
                            pass
                    
                    images.append({
                        'path': str(file_path.resolve()),
                        'category': category_dir.name,
                        'description': description,
                        'filename': file_path.name,
                        'attached_at': 'unknown'
                    })
        
        return images
    
    def show_trade_images(self, trade_id: str, book: list = None):
        """Display all images for a trade with clickable links"""
        images = self.get_trade_images(trade_id, book)
        
        if not images:
            rich.print(f"[yellow]No images found for trade {trade_id}[/]")
            return
        
        rich.print(f"\n[bold]Images for Trade {trade_id}:[/]")
        
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Category", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Date Added", style="dim")
        table.add_column("Clickable Link", style="blue underline")
        
        for img in images:
            # Create file:// URL for macOS
            file_url = f"file://{img['path']}"
            # Rich can create clickable links
            clickable_link = f"[link={file_url}]{img['filename']}[/link]"
            
            # Format date
            date_str = "unknown"
            if img.get('attached_at') and img['attached_at'] != 'unknown':
                try:
                    dt_obj = dt.datetime.fromisoformat(img['attached_at'].replace('Z', '+00:00'))
                    date_str = dt_obj.strftime('%m/%d %I:%M%p')
                except:
                    date_str = "unknown"
            
            table.add_row(
                img['category'],
                img['description'] or "[dim]No description[/dim]",
                date_str,
                clickable_link
            )
        
        rich.print(table)
        rich.print(f"[dim]💡 Command+Click on links to open images on macOS[/dim]")
        
        # Show data source
        if book:
            rich.print(f"[dim]📊 Image data stored in trade JSON[/dim]")
    
    def migrate_filesystem_images_to_trades(self, book: list) -> int:
        """Migrate existing filesystem images to trade data"""
        migrated_count = 0
        
        for trade in book:
            # Get images from filesystem for this trade
            fs_images = self._get_images_from_filesystem(trade.id)
            
            if fs_images:
                # Initialize images list if needed
                if not hasattr(trade, 'images'):
                    trade.images = []
                
                # Add filesystem images to trade data
                for img in fs_images:
                    # Check if image is already in trade data
                    existing = any(existing_img['path'] == img['path'] 
                                 for existing_img in trade.images)
                    
                    if not existing:
                        trade.images.append(img)
                        migrated_count += 1
        
        if migrated_count > 0:
            rich.print(f"[green]✅ Migrated {migrated_count} images from filesystem to trade data[/]")
        
        return migrated_count
    
    def delete_image(self, trade_id: str, filename: str) -> bool:
        """Delete a specific image from a trade"""
        # Search for the file
        for category_dir in self.images_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            image_file = category_dir / filename
            metadata_file = image_file.with_suffix('.txt')
            
            if image_file.exists():
                try:
                    # Delete both image and metadata
                    image_file.unlink()
                    if metadata_file.exists():
                        metadata_file.unlink()
                    
                    rich.print(f"[green]✅ Deleted {filename} from trade {trade_id}[/]")
                    return True
                except Exception as e:
                    rich.print(f"[red]Error deleting image: {e}[/]")
                    return False
        
        rich.print(f"[red]Image {filename} not found for trade {trade_id}[/]")
        return False
    
    def generate_trade_report(self, trade, include_images: bool = True) -> str:
        """Generate a comprehensive trade report with images"""
        report = []
        report.append(f"# Trade Report: {trade.id}")
        report.append(f"**Strategy:** {trade.strat}")
        report.append(f"**Type:** {trade.typ}")
        report.append(f"**Status:** {trade.status}")
        report.append(f"**Date:** {trade.ts}")
        
        # Trade details
        report.append("\n## Trade Details")
        for i, leg in enumerate(trade.legs):
            report.append(f"**Leg {i+1}:** {leg.side} {leg.qty} {leg.symbol} @ ${leg.entry}")
            if leg.exit:
                report.append(f"  Exit: ${leg.exit}")
        
        # PnL information
        if trade.status == "CLOSED" and hasattr(trade, 'pnl'):
            report.append(f"\n## P&L")
            if hasattr(trade, 'gross_pnl'):
                report.append(f"**Gross P&L:** ${trade.gross_pnl():.2f}")
            if hasattr(trade, 'total_costs'):
                report.append(f"**Total Costs:** ${trade.total_costs():.2f}")
            report.append(f"**Net P&L:** ${trade.pnl:.2f}")
        
        # Risk information
        if hasattr(trade, 'risk') and trade.risk:
            report.append(f"\n## Risk Assessment")
            if trade.risk.note:
                report.append(f"**Notes:** {trade.risk.note}")
        
        # Images section
        if include_images:
            images = self.get_trade_images(trade.id)
            if images:
                report.append(f"\n## Attached Images")
                
                for category in ["setup", "screenshots", "charts", "exit"]:
                    category_images = [img for img in images if img['category'] == category]
                    if category_images:
                        report.append(f"\n### {category.title()}")
                        for img in category_images:
                            file_url = f"file://{img['path']}"
                            desc = img['description'] or "No description"
                            report.append(f"- [{img['filename']}]({file_url}) - {desc}")
        
        return "\n".join(report)
    
    def export_trade_report(self, trade, output_file: str = None) -> str:
        """Export trade report to markdown file"""
        if not output_file:
            output_file = f"trade_report_{trade.id}.md"
        
        report_content = self.generate_trade_report(trade)
        
        try:
            with open(output_file, 'w') as f:
                f.write(report_content)
            
            rich.print(f"[green]✅ Trade report exported to {output_file}[/]")
            return output_file
        except Exception as e:
            rich.print(f"[red]Error exporting report: {e}[/]")
            return None

# Global image manager instance
image_manager = ImageManager()

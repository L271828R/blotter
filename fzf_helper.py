# ═══════════════════════════════════════════════════════════════════
# fzf_helpers.py - FZF integration for strategy selection
# ═══════════════════════════════════════════════════════════════════

import subprocess
import shutil
from typing import Optional, List
import rich

def check_fzf_installed() -> bool:
    """Check if fzf is installed on the system"""
    return shutil.which('fzf') is not None

def fzf_select(items: List[str], prompt: str = "Select: ") -> Optional[str]:
    """
    Use fzf to select from a list of items
    Returns the selected item or None if cancelled
    """
    if not check_fzf_installed():
        rich.print("[red]FZF is not installed. Install it with: brew install fzf[/]")
        return None
    
    if not items:
        rich.print("[red]No items to select from[/]")
        return None
    
    try:
        # Join items with newlines for fzf input
        input_text = '\n'.join(items)
        
        # Run fzf with the items
        result = subprocess.run(
            ['fzf', '--prompt', prompt, '--height', '40%', '--reverse'],
            input=input_text,
            text=True,
            capture_output=True
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # User cancelled (Ctrl+C or ESC)
            return None
            
    except Exception as e:
        rich.print(f"[red]Error running fzf: {e}[/]")
        return None

def get_strategies_from_book(book) -> List[str]:
    """Extract unique strategies from the trade book"""
    strategies = set()
    for trade in book:
        if trade.strat:
            strategies.add(trade.strat)
    return sorted(list(strategies))

def load_strategies_from_config(config_path: str = "strategies.txt") -> List[str]:
    """Load strategies from a config file"""
    try:
        with open(config_path, 'r') as f:
            strategies = []
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    strategies.append(line.upper())
            return strategies
    except FileNotFoundError:
        rich.print(f"[yellow]Config file {config_path} not found. Creating example file...[/]")
        create_example_strategies_file(config_path)
        return load_strategies_from_config(config_path)
    except Exception as e:
        rich.print(f"[red]Error reading strategies config: {e}[/]")
        return []

def create_example_strategies_file(config_path: str = "strategies.txt"):
    """Create an example strategies config file"""
    example_strategies = [
        "# Trading Strategies Configuration",
        "# One strategy per line",
        "# Lines starting with # are comments",
        "",
        "SCALP",
        "SWING", 
        "MOMENTUM",
        "BREAKOUT",
        "REVERSAL",
        "BULL-PUT-SPREAD",
        "BEAR-CALL-SPREAD",
        "IRON-CONDOR",
        "STRADDLE",
        "STRANGLE",
        "COVERED-CALL",
        "PROTECTIVE-PUT",
        "BUTTERFLY",
        "CALENDAR",
        "DIAGONAL"
    ]
    
    try:
        with open(config_path, 'w') as f:
            f.write('\n'.join(example_strategies))
        rich.print(f"[green]Created example strategies file: {config_path}[/]")
        rich.print(f"[green]Edit this file to customize your strategies[/]")
    except Exception as e:
        rich.print(f"[red]Error creating strategies file: {e}[/]")

def select_strategy(book, config_path: str = "strategies.txt", allow_custom: bool = True) -> Optional[str]:
    """
    Interactive strategy selection using FZF
    Reads strategies from config file and combines with book history
    """
    if not check_fzf_installed():
        rich.print("[yellow]FZF not found. Install with: brew install fzf[/]")
        # Fallback to manual input
        strategy = input("Strategy: ").strip().upper()
        return strategy if strategy else None
    
    # Load strategies from config file
    config_strategies = load_strategies_from_config(config_path)
    
    # Get strategies from book history
    book_strategies = get_strategies_from_book(book)
    
    # Combine strategies: config first, then book history (if not already in config)
    all_strategies = config_strategies.copy()
    for strat in book_strategies:
        if strat not in all_strategies:
            all_strategies.append(strat)
    
    # Add option to enter custom strategy
    if allow_custom:
        all_strategies.append(">>> ENTER CUSTOM STRATEGY <<<")
    
    if not all_strategies:
        rich.print("[red]No strategies found in config or book history[/]")
        return None
    
    rich.print(f"[cyan]Select strategy using FZF (loaded {len(config_strategies)} from config)[/]")
    rich.print("[dim]Type to filter, Enter to select, Esc to cancel[/]")
    
    selected = fzf_select(all_strategies, "Strategy: ")
    
    if selected is None:
        rich.print("[yellow]Strategy selection cancelled[/]")
        return None
    
    # Handle custom strategy entry
    if selected == ">>> ENTER CUSTOM STRATEGY <<<":
        custom = input("Enter custom strategy: ").strip().upper()
        if custom:
            # Optionally add to config file
            add_to_config = input(f"Add '{custom}' to strategies config? (y/N): ").strip().lower()
            if add_to_config == 'y':
                try:
                    with open(config_path, 'a') as f:
                        f.write(f"\n{custom}")
                    rich.print(f"[green]Added '{custom}' to {config_path}[/]")
                except Exception as e:
                    rich.print(f"[red]Error adding to config: {e}[/]")
        return custom if custom else None
    
    return selected



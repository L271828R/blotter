# ═══════════════════════════════════════════════════════════════════
# Enhanced config.py - Single source of truth for strategies
# ═══════════════════════════════════════════════════════════════════

import pathlib
from ruamel.yaml import YAML
import rich

yaml = YAML(typ="safe")
CONFIG_FILE = pathlib.Path("config.yaml")

DEFAULT_CFG = {
    "option_blocks": [
        {"start": "09:30", "end": "09:45", "name": "Market Open"},
        {"start": "12:00", "end": "16:00", "name": "Lunch Block"},
        {"start": "18:00", "end": "21:15", "name": "Asian Open"}
    ],
    "multipliers": {
        "/MES": 5,
        "MES": 5, 
        "MES_OPT": 5
    },
    "strategies": {
        # Single leg strategies
        "5AM-LONG-SLUG": {
            "type": "single_leg",
            "default_type": "OPTION",
            "default_side": "BUY"
        },
        "5AM-OTHER": {
            "type": "single_leg",
            "default_type": "OPTION"
        },
        "NORMAL": {
            "type": "single_leg",
            "default_type": "FUTURE"
        },
        # Spread strategies
        "BULL-PUT": {
            "type": "bull_put_spread"
        },
        "BULL-PUT-OVERNIGHT": {
            "type": "bull_put_spread"
        },
        "BULL-PUT-1:30-3:00": {
            "type": "bull_put_spread"
        },
        "BEAR-CALL": {
            "type": "bear_call_spread"
        }
    },
    "exemption": ["BULL-PUT-1:30-3:00"],
    "costs": {
        "FUTURE": {
            "commission_per_contract": "1.10",
            "exchange_fees_per_contract": "0.37",
            "regulatory_fees_per_contract": "0.00"
        },
        "OPTION": {
            "commission_per_contract": "1.25",
            "exchange_fees_per_contract": "0.50",
            "regulatory_fees_per_contract": "0.02"
        }
    },
    "prompt_triggers": {
        "on_entry": True,
        "on_exit": False
    },
    "prompts": {
        "1_Stop-watch": "Are you going to sell it in 1 hour if no profit?",
        "2_small_amount": "Is the potential loss acceptable?",
        "3_One_Shot": "Are you only doing one purchase? Buying more will anchor you",
        "4_45_degree_angles": "Any 45% angles? price, yellow? Have they been digested by 9EMA",
        "5_Red_50_SMVA": "Is the red-50 above below? With you against you:",
        "6_VWAP": "Was it abused recently? Is that good or bad:",
        "7_economic_events I": "Any major economic events today? (Fed, CPI, NFP, etc.)?",
        "8_economic_events II": "Any 8:30AM (savior) economic events? This might anchor you, make you wait more than needed:",
        "9_auction": "Treasury auction (1PM) schedule affecting rates today?",
        "10_earnings": "Major earnings releases this week that could impact market?",
        "11_fed_speakers": "Fed speakers scheduled today? (Check Fed calendar)?",
        "12_market_conditions": "Current market conditions/sentiment? (Bullish/Bearish/Neutral)",
        "13_volatility": "VIX level and volatility environment? (High/Normal/Low)",
        "14_invent_a_note_of_trade_going_wrong": "Write a note pretending trade went wrong:",
        "15_real_note": "Write a note:"
    },
    "risk_limits": {
        "starting_balance": 10000,
        "max_position_percent": 33,
        "hot_hand_threshold": 4,
        "hot_hand_cooldown_hours": 24,
        "loss_reduction_threshold": 3
    }
}

def generate_strategies_txt(cfg):
    """Generate strategies.txt from config at runtime"""
    strategies = cfg.get("strategies", {})
    
    strategy_lines = [
        "# Trading Strategies (Auto-generated from config.yaml)",
        "# DO NOT EDIT - This file is regenerated on startup",
        "# To add strategies, edit config.yaml",
        ""
    ]
    
    # Group by type for better organization
    single_leg = []
    bull_put_spreads = []
    bear_call_spreads = []
    other_spreads = []
    
    for name, meta in strategies.items():
        strategy_type = meta.get("type", "single_leg")
        
        if strategy_type == "bull_put_spread":
            bull_put_spreads.append(name)
        elif strategy_type == "bear_call_spread":
            bear_call_spreads.append(name)
        elif strategy_type in ["iron_condor", "straddle", "strangle"]:
            other_spreads.append(name)
        else:
            single_leg.append(name)
    
    # Add sections with headers
    if single_leg:
        strategy_lines.append("# Single Leg Strategies")
        strategy_lines.extend(sorted(single_leg))
        strategy_lines.append("")
    
    if bull_put_spreads:
        strategy_lines.append("# Bull Put Spreads")
        strategy_lines.extend(sorted(bull_put_spreads))
        strategy_lines.append("")
    
    if bear_call_spreads:
        strategy_lines.append("# Bear Call Spreads") 
        strategy_lines.extend(sorted(bear_call_spreads))
        strategy_lines.append("")
        
    if other_spreads:
        strategy_lines.append("# Other Spreads")
        strategy_lines.extend(sorted(other_spreads))
    
    # Write to file
    try:
        with open("strategies.txt", "w") as f:
            f.write("\n".join(strategy_lines))
        # rich.print("[dim]✓ Generated strategies.txt[/]")
    except Exception as e:
        rich.print(f"[red]Error generating strategies.txt: {e}[/]")

def migrate_old_strategies_list(cfg):
    """One-time migration from old list format to new dict format"""
    if isinstance(cfg.get("strategies"), list):
        rich.print("[yellow]Migrating strategies from old list format...[/]")
        
        old_strategies = cfg["strategies"]
        new_strategies = {}
        
        for strategy in old_strategies:
            strategy_upper = strategy.upper()
            
            # Auto-detect strategy types based on naming patterns
            if "BULL-PUT" in strategy_upper:
                new_strategies[strategy] = {"type": "bull_put_spread"}
            elif "BEAR-CALL" in strategy_upper:
                new_strategies[strategy] = {"type": "bear_call_spread"}
            elif "5AM" in strategy_upper:
                new_strategies[strategy] = {
                    "type": "single_leg", 
                    "default_type": "OPTION",
                    "default_side": "BUY"
                }
            elif strategy_upper in ["SCALP", "MOMENTUM", "BREAKOUT"]:
                new_strategies[strategy] = {
                    "type": "single_leg",
                    "default_type": "FUTURE",
                    "default_side": "BUY"
                }
            else:
                new_strategies[strategy] = {"type": "single_leg"}
        
        # Update config
        cfg["strategies"] = new_strategies
        save_config(cfg)
        
        rich.print(f"[green]✓ Migrated {len(old_strategies)} strategies to new format[/]")
        return True
    
    return False

def load_config():
    """Load configuration and generate strategies.txt"""
    if not CONFIG_FILE.exists():
        rich.print("[yellow]Creating default config.yaml...[/]")
        yaml.dump(DEFAULT_CFG, CONFIG_FILE)
    
    cfg = yaml.load(CONFIG_FILE)
    
    # Handle migration from old format
    migrated = migrate_old_strategies_list(cfg)
    if migrated:
        cfg = yaml.load(CONFIG_FILE)  # Reload after migration
    
    # Generate strategies.txt for FZF
    generate_strategies_txt(cfg)
    
    return cfg

def save_config(config):
    """Save configuration to file and regenerate strategies.txt"""
    yaml.dump(config, CONFIG_FILE)
    generate_strategies_txt(config)

def get_strategy_type(strategy_name, cfg):
    """Get strategy type and metadata"""
    strategies = cfg.get("strategies", {})
    strategy_meta = strategies.get(strategy_name, {})
    
    return {
        "type": strategy_meta.get("type", "single_leg"),
        "default_type": strategy_meta.get("default_type", "FUTURE"),
        "default_side": strategy_meta.get("default_side", "BUY"),
        "meta": strategy_meta
    }

def add_strategy(name, strategy_type="single_leg", default_type=None, default_side=None):
    """Add a new strategy to config"""
    cfg = load_config()
    
    strategy_meta = {"type": strategy_type}
    
    if default_type:
        strategy_meta["default_type"] = default_type
    if default_side:
        strategy_meta["default_side"] = default_side
    
    cfg["strategies"][name] = strategy_meta
    save_config(cfg)
    
    rich.print(f"[green]✓ Added strategy '{name}' (type: {strategy_type})[/]")

def list_strategies(cfg, strategy_type=None):
    """List strategies, optionally filtered by type"""
    strategies = cfg.get("strategies", {})
    
    if strategy_type:
        filtered = {k: v for k, v in strategies.items() if v.get("type") == strategy_type}
        strategies = filtered
    
    if not strategies:
        rich.print(f"[dim]No strategies found{f' of type {strategy_type}' if strategy_type else ''}[/]")
        return
    
    rich.print(f"\n[bold]Strategies{f' ({strategy_type})' if strategy_type else ''}:[/]")
    
    for name, meta in sorted(strategies.items()):
        strategy_type = meta.get("type", "single_leg")
        defaults = []
        
        if meta.get("default_type"):
            defaults.append(f"type={meta['default_type']}")
        if meta.get("default_side"):
            defaults.append(f"side={meta['default_side']}")
        
        default_str = f" ({', '.join(defaults)})" if defaults else ""
        rich.print(f"  [cyan]{name}[/] - {strategy_type}{default_str}")

def validate_strategies(cfg):
    """Validate strategy configuration"""
    strategies = cfg.get("strategies", {})
    valid_types = ["single_leg", "bull_put_spread", "bear_call_spread", "iron_condor", "straddle", "strangle"]
    valid_trade_types = ["FUTURE", "OPTION"]
    valid_sides = ["BUY", "SELL"]
    
    errors = []
    
    for name, meta in strategies.items():
        # Check required type field
        if "type" not in meta:
            errors.append(f"Strategy '{name}' missing 'type' field")
            continue
        
        # Check valid type
        if meta["type"] not in valid_types:
            errors.append(f"Strategy '{name}' has invalid type '{meta['type']}'")
        
        # Check defaults for single leg strategies
        if meta["type"] == "single_leg":
            if "default_type" in meta and meta["default_type"] not in valid_trade_types:
                errors.append(f"Strategy '{name}' has invalid default_type '{meta['default_type']}'")
            
            if "default_side" in meta and meta["default_side"] not in valid_sides:
                errors.append(f"Strategy '{name}' has invalid default_side '{meta['default_side']}'")
    
    if errors:
        rich.print("[red]Strategy configuration errors:[/]")
        for error in errors:
            rich.print(f"[red]  - {error}[/]")
        return False
    
    rich.print("[green]✓ Strategy configuration is valid[/]")
    return True

# Utility functions for strategy management
def is_spread_strategy(strategy_name, cfg):
    """Check if strategy is a spread strategy"""
    strategy_info = get_strategy_type(strategy_name, cfg)
    return strategy_info["type"] in ["bull_put_spread", "bear_call_spread", "iron_condor", "straddle", "strangle"]

def is_bull_put_spread(strategy_name, cfg):
    """Check if strategy is a bull put spread"""
    strategy_info = get_strategy_type(strategy_name, cfg)
    return strategy_info["type"] == "bull_put_spread"

def is_bear_call_spread(strategy_name, cfg):
    """Check if strategy is a bear call spread"""
    strategy_info = get_strategy_type(strategy_name, cfg)
    return strategy_info["type"] == "bear_call_spread"

# CLI functions for strategy management
def cmd_add_strategy():
    """Command line interface for adding strategies"""
    name = input("Strategy name: ").strip()
    if not name:
        rich.print("[red]Strategy name required[/]")
        return
    
    rich.print("Strategy type:")
    rich.print("1. Single leg")
    rich.print("2. Bull put spread") 
    rich.print("3. Bear call spread")
    
    choice = input("Choose (1-3): ").strip()
    
    type_map = {
        "1": "single_leg",
        "2": "bull_put_spread", 
        "3": "bear_call_spread"
    }
    
    strategy_type = type_map.get(choice)
    if not strategy_type:
        rich.print("[red]Invalid choice[/]")
        return
    
    default_type = None
    default_side = None
    
    if strategy_type == "single_leg":
        default_type = input("Default trade type (FUTURE/OPTION, or leave blank): ").strip().upper()
        if default_type and default_type not in ["FUTURE", "OPTION"]:
            default_type = None
        
        default_side = input("Default side (BUY/SELL, or leave blank): ").strip().upper()
        if default_side and default_side not in ["BUY", "SELL"]:
            default_side = None
    
    add_strategy(name, strategy_type, default_type, default_side)

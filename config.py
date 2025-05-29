# config.py - Updated with commission/fee rates
"""Configuration management for the trade blotter"""

import pathlib
from ruamel.yaml import YAML

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
    "strategies": ["5AM", "NORMAL", "BULL-PUT", "BEAR-CALL", "BULL-PUT-OVERNIGHT"],
    
    # Commission and fee structure
    "costs": {
        "FUTURE": {
            "commission_per_contract": "1.10",      # $1.10 per contract
            "exchange_fees_per_contract": "0.37",   # $0.37 per contract  
            "regulatory_fees_per_contract": "0.00"  # $0.00 (included in exchange)
        },
        "OPTION": {
            "commission_per_contract": "1.25",      # $1.25 per contract
            "exchange_fees_per_contract": "0.50",   # $0.50 per contract
            "regulatory_fees_per_contract": "0.02"  # $0.02 per contract
        }
    }
}

def load_config():
    """Load configuration, creating defaults if needed"""
    if not CONFIG_FILE.exists():
        yaml.dump(DEFAULT_CFG, CONFIG_FILE)
    return yaml.load(CONFIG_FILE)

def save_config(config):
    """Save configuration to file"""
    yaml.dump(config, CONFIG_FILE)

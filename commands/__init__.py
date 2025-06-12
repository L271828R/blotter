# ═══════════════════════════════════════════════════════════════════
# 2. commands/__init__.py - Complete globals management
# ═══════════════════════════════════════════════════════════════════

from typing import List, Any

# Global references that all command modules can access
cfg = None
book = None
trade_ops = None
stopwatch_manager = None
risk_manager = None
image_manager = None

def set_globals(config, trade_book):
    """Set global references for all command modules"""
    global cfg, book, trade_ops, stopwatch_manager, risk_manager, image_manager
    
    cfg = config
    book = trade_book
    
    # Initialize managers
    from trade_operations import TradeOperations
    from stopwatch import stopwatch_manager as sw_mgr, RiskManager
    from images import image_manager as img_mgr
    
    trade_ops = TradeOperations(book, cfg)
    stopwatch_manager = sw_mgr
    risk_manager = RiskManager(cfg, book)
    image_manager = img_mgr
    
    # Initialize stopwatch manager
    stopwatch_manager.set_trade_ops(trade_ops, book)
    
    # IMPORTANT: Set globals in each command module
    import commands.trade_commands
    import commands.management_commands
    import commands.timer_commands
    import commands.image_commands
    import commands.risk_commands
    
    # Set the globals in each module
    commands.trade_commands.cfg = cfg
    commands.trade_commands.book = book
    commands.trade_commands.trade_ops = trade_ops
    commands.trade_commands.stopwatch_manager = stopwatch_manager
    
    commands.management_commands.cfg = cfg
    commands.management_commands.book = book
    
    commands.timer_commands.stopwatch_manager = stopwatch_manager
    
    commands.image_commands.image_manager = image_manager
    commands.image_commands.book = book
    
    commands.risk_commands.risk_manager = risk_manager
    commands.risk_commands.cfg = cfg
    commands.risk_commands.book = book



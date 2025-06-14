# LLM Context: Ulysses Trading Blotter

> **Purpose**: This document provides context for AI assistants helping debug/enhance this trading blotter system.

## 🎯 System Overview

**Ulysses Blotter** is a Python-based trading journal that tracks futures and options trades, with accurate P&L calculations that match ThinkOrSwim (TOS) broker statements.

### Key Features
- **Spread Trading Support**: Bull put spreads, bear call spreads
- **Commission Accuracy**: Matches TOS commission structure exactly
- **Historical Trade Entry**: Backfill trades with custom timestamps
- **FZF Integration**: Fast strategy selection
- **Risk Management**: Option trading blocks, stopwatch timers

## 🏗️ Architecture

### Core Structure
```
ulysses-blotter/
├── blotter.py              # Main entry point with command aliases
├── commands/               # Modular command structure
│   ├── trade_commands.py   # Main trade command router
│   ├── trade_opening.py    # Trade opening logic
│   ├── trade_closing.py    # Trade closing & expiration
│   ├── trade_management.py # Fix/delete trades
│   ├── trade_utils.py      # Shared utilities
│   └── trade_strategy.py   # Strategy management
├── config.py               # Strategy configuration
├── trade_operations.py     # Core trading operations
├── models.py               # Data models (Trade, Leg, CommissionFees)
├── utils.py                # Utilities
├── persistence.py          # Data storage
└── ls.py                   # Trade listing
```

### Data Models
```python
Trade:
  - id: str (unique identifier)
  - ts: datetime (entry timestamp)
  - typ: str ("FUTURE", "OPTION", "OPTION-SPREAD")
  - strat: str (strategy name from config)
  - legs: List[Leg] (trade components)
  - status: str ("OPEN", "CLOSED")
  - pnl: float (net P&L after costs)

Leg:
  - symbol: str (e.g., "MES_P_5925")
  - side: str ("BUY", "SELL")
  - qty: int (contract quantity)
  - entry: Decimal (entry price)
  - exit: Decimal (exit price, None if open)
  - multiplier: int (contract multiplier, usually 5 for MES)
  - entry_costs: CommissionFees
  - exit_costs: CommissionFees
```

## 💰 Commission Structure (Critical!)

**The #1 issue solved**: TOS charges commission **per spread order**, not per leg.

### Correct Implementation:
```python
# For spreads: Only first leg gets costs, others get zero
if spread_trade:
    leg1.entry_costs = calculate_costs("OPTION", qty, cfg)
    leg2.entry_costs = CommissionFees(0, 0, 0)  # Zero costs
```

### TOS Commission Rates:
```yaml
OPTION:
  commission_per_contract: "2.20"  # $176 for 80 contracts
  exchange_fees_per_contract: "0.44"  # $35.20 for 80 contracts  
  regulatory_fees_per_contract: "0.00"
  # Total: $211.20 per spread order (not per leg!)
```

## 🔧 Common Commands

### Trade Operations
```bash
# Open trades
python blotter.py open                    # Interactive mode
python blotter.py open --historical       # Backfill historical trades

# Close trades  
python blotter.py close 14090300         # Interactive closing
python blotter.py expire-spread 14090300  # Mark options as expired

# Trade management
python blotter.py trade fix 14090300     # Fix prices/timestamps
python blotter.py ls                     # List all trades
python blotter.py audit --trade-id 14090300  # Detailed trade info
```

### Strategy Management
```bash
python blotter.py trade list-strategies  # Show configured strategies
python blotter.py trade add-strategy MyStrategy bull_put_spread
```

## 📊 Key Data Flows

### 1. Opening a Bull Put Spread
1. User selects "BULL-PUT" strategy (via FZF)
2. System routes to `bull_put_spread` handler
3. User enters net credit received (e.g., $4.00)
4. System estimates individual leg prices
5. **Critical**: Only first leg gets commission costs
6. Trade saved with correct net credit calculation

### 2. Closing with Net Debit
1. User chooses "Close entire spread with net debit"
2. Enters net debit (e.g., $1.75)
3. System calculates: Credit - Debit = Profit per contract
4. **Critical**: Only first leg gets exit costs
5. P&L = (Credit - Debit) × Qty × Multiplier - Total Costs

### 3. Expiring Options
1. User runs `expire-spread 14090300`
2. System sets all legs exit price to $0.00
3. Exit costs set to $0 (TOS shows no fees for expirations)
4. Final P&L = Full premium received - Entry costs

## ⚠️ Common Issues & Solutions

### Commission Double-Counting
**Problem**: P&L doesn't match TOS  
**Cause**: Calculating costs for each leg separately  
**Solution**: Only first leg gets costs for spreads

### Quantity Display
**Problem**: Spreads showing 160 instead of 80  
**Solution**: For `OPTION-SPREAD`, show `legs[0].qty` not `sum(leg.qty)`

### Timestamp Format
**Problem**: Times in UTC instead of EST  
**Solution**: Convert to EST with 12-hour format for display

### Import Errors After Refactoring
**Problem**: "Global configuration not properly initialized"  
**Solution**: Import `book`/`cfg` inside functions, not at module level

## 🔍 Debugging Tips

### 1. Check Trade Details
```bash
python blotter.py audit --trade-id XXXXX
```

### 2. Verify Commission Calculation
Look for cost breakdown in closing output:
```
Entry costs: $211.20  # Should be single spread cost
Exit costs: $211.20   # Should be single spread cost
Total costs: $422.40  # Entry + Exit
```

### 3. Check Configuration
```bash
python blotter.py trade list-strategies  # Show strategy types
```

### 4. Recalculate P&L
```bash
python blotter.py recalc --trade-id XXXXX --details
```

## 🎯 Success Metrics

**The system is working correctly when**:
- Bull put spread P&L matches TOS exactly
- Commission costs are ~$211 per spread (not ~$422)
- Expired options show correct profit (full premium - entry costs)
- Spreads display quantity as number of spreads (not total contracts)

## 📝 Configuration Files

### config.yaml
Contains strategy definitions, commission rates, trading blocks, and risk limits.

### strategies.txt  
Auto-generated from config.yaml for FZF integration.

---

**When helping debug**: Focus on commission calculations first - 90% of P&L issues stem from double-counting spread costs.

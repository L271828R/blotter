# Ulysses Trading Blotter - Examples & Capabilities

> **Complete guide** showing all features and commands with real examples

## 🎯 Overview

Ulysses Blotter is a professional trading journal that accurately tracks futures and options trades with precise P&L calculations that match your broker (ThinkOrSwim) exactly.

**Key Strengths:**
- ✅ **Accurate Commission Modeling** - Matches TOS exactly
- ✅ **Spread Trading Support** - Bull puts, bear calls with proper accounting
- ✅ **Historical Trade Entry** - Backfill trades with custom timestamps
- ✅ **Smart Strategy Management** - FZF integration for fast selection
- ✅ **Risk Management** - Trading blocks, stopwatch timers
- ✅ **Flexible Closing** - Net debit, individual legs, or expirations

---

## 📋 Table of Contents

1. [Trade Opening](#-trade-opening)
2. [Trade Closing](#-trade-closing)  
3. [Trade Management](#-trade-management)
4. [Strategy Management](#-strategy-management)
5. [Trade Analysis](#-trade-analysis)
6. [Risk Management](#-risk-management)
7. [Historical Features](#-historical-features)
8. [Advanced Features](#-advanced-features)

---

## 🚀 Trade Opening

### Single Leg Trades

#### Open a Simple Future Trade
```bash
python blotter.py open
```
```
🔍 Opening strategy selection with FZF...
✓ Selected strategy via FZF: 'NORMAL'

📋 Strategy Analysis:
  Name: NORMAL
  Type: single_leg
  Default Trade Type: FUTURE
  Default Side: BUY

🚀 Opening Single Leg...
Symbol: MESM25
Quantity [1]: 3
Entry price: 5992.25

✓ FUTURE BUY trade opened: 14085059
  Symbol: MESM25 | Qty: 3 | Price: $5992.25
  Costs: $4.41
```

#### Command Line Trade Opening
```bash
python blotter.py open --strat NORMAL --symbol MESM25 --qty 3 --price 5992.25
```

### Options Spreads

#### Bull Put Spread (Interactive)
```bash
python blotter.py open
```
```
✓ Selected strategy via FZF: 'BULL-PUT'

🚀 Opening Bull Put Spread...
Number of spreads [1]: 80

Entry Mode:
1. Net Credit (what you see on broker)
2. Individual Leg Prices
Choose mode (1 or 2): 1

Strike Information:
Short put strike (sell/higher): 5925
Long put strike (buy/lower): 5905

Net Credit Mode:
Net credit received: 4.00

✓ Bull Put Spread opened: 14084721
  Short: SELL 80 MES_P_5925 @ $4.10
  Long:  BUY 80 MES_P_5905 @ $0.10
  Net Credit: $1388.80 (after costs)
  Max Risk: $6611.20
  Total Costs: $211.20
```

#### Bear Call Spread
```bash
python blotter.py open --strat BEAR-CALL --qty 50
```
Similar interactive flow for bear call spreads.

---

## 🔒 Trade Closing

### Standard Closing
```bash
python blotter.py close 14085059
```
```
Closing NORMAL trade 14085059
Position: BUY 3 MESM25
Entry: $5992.25
Exit price for MESM25: 5992.25

✓ Trade 14085059 closed successfully
  Gross P&L: $0.00
  Total Costs: $8.82
  Net P&L: $-8.82
```

### Spread Closing with Net Debit
```bash
python blotter.py close 14084721
```
```
Closing BULL-PUT spread: 14084721
1. Close entire spread with net debit
2. Close with individual leg prices
Choose method (1 or 2): 1
Net debit to close spread: 1.75

Closing BULL-PUT spread with net debit of $1.75
Original net credit received: $4.00
Net debit paid to close: $1.75
Profit per contract: $2.25

✓ Spread closed successfully
  Gross P&L: $+900.00
  Total costs: $422.40
  Net P&L: $+477.60
```

### Individual Leg Closing
```bash
python blotter.py close-leg 14084721 MES_P_5925 6.50 --reason "Early exit"
```
```
✓ Closed leg MES_P_5925 at $6.50
  Reason: Early exit
  Leg P&L: $-600.00
  1 legs still open
```

### Option Expiration
```bash
python blotter.py expire-spread 14090300
```
```
Expiring BULL-PUT spread: 14090300
This will set exit price to $0.00 for all 2 open legs
Are you sure you want to expire the entire spread? [y/N]: y

✓ Expired MES_P_5990 (was SELL @ $2.70) → P&L: $+1069.20
✓ Expired MES_P_5970 (was BUY @ $0.10) → P&L: $-40.40

✓ Spread 14090300 expired successfully
  Expired 2 legs
  Total P&L: $+828.80
```

```bash
python blotter.py expire-leg 14084721 MES_P_5925
```
Single leg expiration.

---

## 🛠️ Trade Management

### List All Trades
```bash
python blotter.py ls
```
```
                                    Trades
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━┳━━━━━━━━┳━━━━━━━━━━━┓
┃ id          ┃ date/time           ┃ type          ┃ strat         ┃ legs           ┃ qty ┃ status ┃       PnL ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━╇━━━━━━━━━━━┩
┃ 14084721    ┃ 2025-06-14 8:47 AM  ┃ OPTION-SPREAD ┃ BULL-PUT      ┃ S 5925; B 5905 ┃  80 ┃ CLOSED ┃   $477.60 ┃
┃ 14085059    ┃ 2025-06-14 8:50 AM  ┃ FUTURE        ┃ NORMAL        ┃ B MESM25       ┃   3 ┃ CLOSED ┃    $-8.82 ┃
┃ 14090300    ┃ 2025-06-14 9:05 AM  ┃ OPTION-SPREAD ┃ BULL-PUT      ┃ S 5990; B 5970 ┃  80 ┃ CLOSED ┃   $828.80 ┃
└─────────────┴─────────────────────┴───────────────┴───────────────┴────────────────┴─────┴────────┴───────────┘
```

### Fix Trade Details
```bash
python blotter.py trade fix 14090300
```
```
Fixing trade 14090300
Trade: BULL-PUT - OPTION-SPREAD

Current timestamp: 2025-06-14 9:03 AM EST
Update timestamp? [y/N]: y

Enter new time (leave date unchanged):
New time (HH:MM format, e.g., 08:05): 09:05
✓ Updated timestamp to: 2025-06-14 9:05 AM EST

Leg 1: SELL 80 MES_P_5990
  Current entry: $2.70
Update entry price for MES_P_5990? [y/N]: n

Recalculating PnL...
✓ Trade 14090300 updated and saved
```

### Audit Trade Details
```bash
python blotter.py audit --trade-id 14084721
```
```
📊 Trade Audit Report - 14084721
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Basic Information:
  Strategy: BULL-PUT
  Type: OPTION-SPREAD  
  Status: CLOSED
  Entry: 2025-06-14 8:47 AM EST

Leg Details:
  Leg 1: SELL 80 MES_P_5925 @ $4.10 → $1.40
    Entry Costs: $211.20
    Exit Costs: $0.00
    
  Leg 2: BUY 80 MES_P_5905 @ $0.10 → $0.35  
    Entry Costs: $0.00
    Exit Costs: $211.20

P&L Breakdown:
  Gross P&L: $900.00
  Total Costs: $422.40
  Net P&L: $477.60
```

### Delete Trade
```bash
python blotter.py delete 14085059 --force
```
```
✓ Trade 14085059 deleted successfully
```

---

## 📈 Strategy Management

### List Strategies
```bash
python blotter.py trade list-strategies
```
```
Strategies:
  BEAR-CALL - bear_call_spread
  BULL-PUT - bull_put_spread  
  BULL-PUT-1:30-3:00 - bull_put_spread
  BULL-PUT-OVERNIGHT - bull_put_spread
  NORMAL - single_leg (type=FUTURE)
  5AM-LONG-SLUG - bull_put_spread (type=OPTION, side=BUY)
```

### Add New Strategy
```bash
python blotter.py trade add-strategy "SCALP-FUTURES" single_leg --default-type FUTURE --default-side BUY
```
```
✓ Added strategy 'SCALP-FUTURES' (type: single_leg)
```

### Modify Strategy
```bash
python blotter.py trade fix-strategy "OLD-STRATEGY" bull_put_spread
```
```
✓ Updated strategy 'OLD-STRATEGY' to type 'bull_put_spread'
```

---

## 📊 Trade Analysis

### Recalculate P&L
```bash
python blotter.py recalc --trade-id 14084721 --details
```
```
      PnL Recalculation Details - 14084721
┏━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric      ┃ Old Value ┃ New Value ┃ Change ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│ Gross PnL   │  $900.00  │  $900.00  │  $0.00 │
│ Total Costs │  $422.40  │  $422.40  │  $0.00 │
│ Net PnL     │  $477.60  │  $477.60  │  $0.00 │
└─────────────┴───────────┴───────────┴────────┘
✓ Trade 14084721 updated and saved
```

### Recalculate All Trades
```bash
python blotter.py recalc
```

### Data Validation
```bash
python blotter.py audit
```
Comprehensive audit of all trades for data integrity issues.

---

## ⏰ Risk Management

### View Trading Blocks
```bash
python blotter.py blocks
```
```
Option Trading Blocks:
  Market Open: 09:30 - 09:45
  Lunch Block: 12:00 - 16:00  
  Asian Open: 18:00 - 21:15

Exempt Strategies: BULL-PUT-1:30-3:00
```

### Stopwatch Management
```bash
python blotter.py stopwatch start --trade-id 14084721 --hours 2
```
```
✓ Started 2-hour stopwatch for trade 14084721
  Will alert at: 10:47 AM EST
```

```bash
python blotter.py timers
```
```
🔔 ACTIVE RISK TIMERS

Trade 14084721 (BULL-PUT):
  Started: 8:47 AM
  Duration: 2 hours  
  Alert Time: 10:47 AM
  Remaining: 23 minutes
  STATUS: ⚠️  ALERT SOON
```

### Risk Checks
```bash
python blotter.py risk --value 5000
```
```
💰 Risk Analysis for $5,000 trade:
  Account Balance: $10,226.89
  Position Size: 48.9% of account
  Risk Limit: 33% (EXCEEDED!)
  Recommendation: Reduce position size
```

---

## 📅 Historical Features

### Historical Trade Entry
```bash
python blotter.py open --historical
```
```
📅 HISTORICAL MODE - Enter trade with custom timestamp

⏰ Historical Trade Entry
What date was this trade entered? (YYYY-MM-DD or MM-DD): 06-12
✓ Using date: Wednesday, June 12, 2025

What time was this trade entered? (HH:MM format): 09:45
✓ Using time: 09:45 AM

Final timestamp: Wednesday, June 12, 2025 at 09:45 AM

ℹ️  Note: 09:45 AM would have been during a block period
   But you're entering this as historical data, so it's allowed
```

### Backfill Multiple Trades
```bash
python blotter.py open --historical --strat BULL-PUT --qty 50
```
Interactive historical entry with pre-filled strategy.

---

## 🔧 Advanced Features

### Dry Run Mode
```bash
python blotter.py open --dry-run --strat NORMAL
```
```
🧪 DRY RUN MODE - Trade will not be saved

DRY RUN: Would create FUTURE BUY trade 14085123
  Symbol: MESM25 | Qty: 3 | Price: $5995.00
```

### Command Line Shortcuts
```bash
# Quick future trade
python blotter.py open --strat NORMAL --symbol MESM25 --qty 1 --price 6000

# Quick options with stopwatch
python blotter.py open --strat BULL-PUT --qty 10 --stopwatch 1
```

### Data Management
```bash
# Fix data types after updates
python blotter.py fixdata

# Add missing commission costs to old trades
python blotter.py addcosts

# Balance tracking
python blotter.py balance
```

### Image Management
```bash
# Attach screenshots to trades
python blotter.py attach 14084721 screenshot.png --category setup

# View trade images
python blotter.py images --trade-id 14084721

# Generate trade report with images
python blotter.py report 14084721 --export
```

---

## 🎯 Real-World Workflows

### Morning Routine: Check Overnight Positions
```bash
# Check what's open
python blotter.py ls | grep OPEN

# Check any active risk timers
python blotter.py timers

# Quick account status
python blotter.py balance
```

### Opening a Bull Put Spread
```bash
# 1. Open the trade
python blotter.py open
# Select BULL-PUT, enter details

# 2. Set risk timer  
python blotter.py stopwatch start --trade-id [ID] --hours 1

# 3. Attach setup screenshot
python blotter.py screenshot [ID] "Entry setup"
```

### Closing at Expiration
```bash
# 1. Check what expires today
python blotter.py ls | grep "OPTION-SPREAD"

# 2. Expire worthless options
python blotter.py expire-spread 14090300

# 3. Generate final report
python blotter.py report 14090300 --export
```

### End of Week: Data Cleanup
```bash
# Audit all trades for issues
python blotter.py audit

# Recalculate everything
python blotter.py recalc

# Check account performance
python blotter.py ls | tail -20
```

---

## 🏆 Success Indicators

**Your blotter is working correctly when:**

✅ **P&L matches broker exactly**  
✅ **Commission costs are realistic** (~$211 per spread, not $422)  
✅ **Expired options show correct profit** (full premium - entry costs)  
✅ **Spreads display proper quantity** (80 spreads, not 160 contracts)  
✅ **Times show in EST with AM/PM format**  
✅ **All commands execute without errors**

---

*This covers the complete capabilities of Ulysses Blotter. Each feature is designed to provide professional-grade trade tracking with broker-accurate calculations.*

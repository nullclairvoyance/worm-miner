# 🐛 WORM Multi-Wallet Farmer

**by [Nullclairvoyant](https://github.com/nullclairvoyance)**

Automated farming script for [WORM Protocol](https://worm.cx/app/mine) on Sepolia testnet.

## What It Does

1. **Burns ETH → BETH** — Converts Sepolia ETH to BETH using ZK proofs (via remote prover)
2. **Participates in Epochs** — Commits BETH to mining epochs (1 epoch per cycle)
3. **Claims WORM** — Automatically claims WORM rewards every N participations
4. **Multi-Wallet** — Supports up to 5 wallets farming simultaneously

## Smart Features

| Feature | Description |
|---------|-------------|
| **1 epoch/cycle** | Participates one epoch at a time (avoids TX reverts) |
| **Smart burn** | Only burns when BETH < 1 epoch needed |
| **Skip burn** | Uses existing BETH balance if sufficient |
| **Auto claim** | Claims ALL available WORM every N participations |
| **Optimal gas** | 20% priority buffer for fast testnet TX |
| **Dynamic gas** | Estimates actual gas needed per TX |
| **Auto-failover** | Switches to backup prover if primary fails |
| **Gas protection** | Refuses TX above 100 Gwei |

## Quick Start

```bash
./setup.sh
```

Or manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
python main.py
```

## Configuration

Edit `.env`:

```env
# Network
RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
PK1=your_private_key

# Budget (auto-adapts to actual balance)
TOTAL_ETH_BUDGET=0.05    # Max ETH to burn
BETH_PER_EPOCH=0.001     # BETH per epoch
CLAIM_INTERVAL=5         # Claim every N participations

# Prover
PROVER_URL=https://worm-miner-3.darkube.app
```

## How It Works

```
┌─────────────────────────────────────────┐
│            Per-Cycle Flow               │
├─────────────────────────────────────────┤
│  1. Check BETH balance                  │
│  2. If BETH < 0.001 → Burn ETH          │
│  3. Participate in 1 epoch              │
│  4. Every 5 participations → Claim WORM │
│  5. Sleep 600s, repeat                  │
└─────────────────────────────────────────┘
```

## Commands

```bash
python main.py              # Start farming
python main.py --dry-run    # Validate config + show balances
python main.py --debug      # Debug logging
```

## Security

- Private keys redacted in logs (`[REDACTED]`)
- `.env` file secured with `chmod 600`
- Gas price limits prevent wallet drain
- Pinned dependency versions
- No Docker required

## License

MIT

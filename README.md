# 🪱 WORM Multi-Wallet Farmer

**by [Nullclairvoyant](https://github.com/nullclairvoyance)**

Automated farming script for [WORM Protocol](https://worm.cx/app/mine) on Sepolia testnet.

## What It Does

This script automates the WORM token farming process:

1. **Burns ETH → BETH** — Converts Sepolia ETH to BETH using ZK proofs (via remote prover)
2. **Participates in Epochs** — Commits BETH to mining epochs to earn WORM rewards
3. **Claims WORM** — Automatically claims earned WORM tokens every N epochs
4. **Multi-Wallet** — Supports up to 5 wallets farming simultaneously

### Smart Features

- **Skip burn if BETH exists** — Won't burn ETH if you already have sufficient BETH
- **Auto-failover provers** — Switches to backup prover if primary fails
- **Gas price protection** — Refuses transactions above 100 Gwei
- **Budget-based epochs** — Set total ETH, bot calculates optimal epochs

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

# Budget
TOTAL_ETH_BUDGET=0.05    # ETH to burn
BETH_PER_EPOCH=0.001     # BETH per epoch
CLAIM_INTERVAL=5         # Claim every N epochs

# Prover
PROVER_URL=https://worm-miner-3.darkube.app
```

## Commands

```bash
python main.py              # Start farming
python main.py --dry-run    # Validate config only
python main.py --debug      # Debug logging
```

## How It Works

```
┌─────────────────────────────────────────┐
│            WORM Multi-Wallet Farmer     │
├─────────────────────────────────────────┤
│  1. Check BETH balance                  │
│  2. If needed: Burn ETH → BETH          │
│  3. Participate in epochs               │
│  4. Claim WORM every N epochs           │
│  5. Repeat                              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│       Remote Prover (ZK Proofs)         │
│  • https://worm-miner-3.darkube.app     │
│  • https://worm-testnet.metatarz.xyz    │
└─────────────────────────────────────────┘
```

## Security

- Private keys never logged (redacted as `[REDACTED]`)
- `.env` file secured with `chmod 600`
- Gas price limits prevent wallet drain
- Pinned dependency versions

## License

MIT

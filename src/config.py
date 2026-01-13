"""
Configuration loading and validation.

Loads settings from .env file and provides type-safe configuration objects.
"""

import decimal
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from eth_account import Account

from .utils.logger import get_logger


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


@dataclass
class WalletConfig:
    """Configuration for a single wallet."""
    
    name: str           # Friendly name (e.g., "Wallet 1")
    private_key: str    # 0x-prefixed private key
    address: str        # Derived from private key
    
    @classmethod
    def from_private_key(cls, pk: str, index: int) -> "WalletConfig":
        """Create wallet config from private key."""
        # Strip whitespace
        pk = pk.strip()
        
        # Add 0x prefix if missing
        if not pk.startswith("0x"):
            pk = f"0x{pk}"
        
        # Validate format: 0x + 64 hex characters
        import re
        if not re.match(r'^0x[a-fA-F0-9]{64}$', pk):
            raise ConfigError(
                f"Invalid private key format for wallet {index + 1}. "
                "Expected 64 hex characters (with or without 0x prefix)."
            )
        
        try:
            account = Account.from_key(pk)
            return cls(
                name=f"Wallet {index + 1}",
                private_key=pk,
                address=account.address
            )
        except Exception as e:
            raise ConfigError(f"Invalid private key for wallet {index + 1}: {e}")
    
    @property
    def short_address(self) -> str:
        """Return shortened address for display."""
        return f"{self.address[:6]}...{self.address[-4:]}"
    
    def __repr__(self) -> str:
        """Safe repr that redacts private key."""
        return f"WalletConfig(name='{self.name}', address='{self.short_address}', private_key='[REDACTED]')"


@dataclass
class FarmingConfig:
    """Complete farming configuration."""
    
    # Network
    rpc_url: str
    network: str = "sepolia"
    
    # Wallets
    wallets: List[WalletConfig] = field(default_factory=list)
    
    # Budget & Mining Strategy
    total_eth_budget: Decimal = Decimal("0.05")  # Total ETH to burn
    beth_per_epoch: Decimal = Decimal("0.001")   # BETH per epoch
    claim_interval: int = 5                       # Claim every N epochs
    burn_fee: Decimal = Decimal("0.00001")        # Protocol burn fee
    
    # Orchestration
    loop_interval_seconds: int = 600
    max_retries: int = 3
    retry_delay_seconds: int = 30
    
    # Remote Prover
    prover_url: str = ""
    prover_backup_url: str = ""
    prover_timeout: int = 600
    
    # Logging
    log_level: str = "INFO"
    log_to_file: bool = True
    log_file: str = "logs/worm-farmer.log"
    
    @property
    def burn_spend(self) -> Decimal:
        """BETH received from burn = budget - fee."""
        return self.total_eth_budget - self.burn_fee
    
    @property
    def total_epochs(self) -> int:
        """Number of epochs from budget."""
        return int(self.burn_spend / self.beth_per_epoch)
    
    @property
    def use_remote_prover(self) -> bool:
        """Check if remote prover is configured."""
        return bool(self.prover_url)
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.rpc_url:
            raise ConfigError("RPC_URL is required")
        
        if not self.wallets:
            raise ConfigError("At least one wallet private key (PK1) is required")
        
        if self.total_eth_budget <= 0:
            raise ConfigError("TOTAL_ETH_BUDGET must be positive")
        
        if self.beth_per_epoch <= 0:
            raise ConfigError("BETH_PER_EPOCH must be positive")
        
        if self.burn_fee >= self.total_eth_budget:
            raise ConfigError("BURN_FEE must be less than TOTAL_ETH_BUDGET")
        
        if self.claim_interval < 1 or self.claim_interval > 100:
            raise ConfigError("CLAIM_INTERVAL must be between 1 and 100")
        
        if self.loop_interval_seconds < 60 or self.loop_interval_seconds > 3600:
            raise ConfigError("LOOP_INTERVAL_SECONDS must be between 60 and 3600")
        
        if self.max_retries < 1 or self.max_retries > 10:
            raise ConfigError("MAX_RETRIES must be between 1 and 10")


def load_config(env_path: Optional[str] = None) -> FarmingConfig:
    """
    Load configuration from .env file.
    
    Args:
        env_path: Optional path to .env file. Defaults to .env in current dir.
        
    Returns:
        Validated FarmingConfig instance
        
    Raises:
        ConfigError: If configuration is invalid
    """
    logger = get_logger()
    
    # Load .env file
    if env_path:
        env_file = Path(env_path)
    else:
        env_file = Path(".env")
    
    if not env_file.exists():
        raise ConfigError(
            f".env file not found at {env_file.absolute()}. "
            f"Copy .env.example to .env and configure it."
        )
    
    load_dotenv(env_file)
    logger.debug(f"Loaded environment from {env_file}")
    
    # Load wallet private keys (PK1 through PK5)
    wallets: List[WalletConfig] = []
    for i in range(1, 6):  # PK1 to PK5
        pk = os.getenv(f"PK{i}", "").strip()
        if pk:
            try:
                wallet = WalletConfig.from_private_key(pk, i - 1)
                wallets.append(wallet)
                logger.debug(f"Loaded wallet {i}: {wallet.short_address}")
            except ConfigError as e:
                logger.warning(f"Skipping PK{i}: {e}")
    
    if not wallets:
        raise ConfigError(
            "No valid wallet private keys found. "
            "Set at least PK1 in your .env file."
        )
    
    # Build config with error handling for invalid values
    try:
        config = FarmingConfig(
            # Network
            rpc_url=os.getenv("RPC_URL", ""),
            network=os.getenv("NETWORK", "sepolia"),
            
            # Wallets
            wallets=wallets,
            
            # Budget & Mining Strategy
            total_eth_budget=Decimal(os.getenv("TOTAL_ETH_BUDGET", "0.05")),
            beth_per_epoch=Decimal(os.getenv("BETH_PER_EPOCH", "0.001")),
            claim_interval=int(os.getenv("CLAIM_INTERVAL", "5")),
            burn_fee=Decimal(os.getenv("BURN_FEE", "0.00001")),
            
            # Orchestration
            loop_interval_seconds=int(os.getenv("LOOP_INTERVAL_SECONDS", "600")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            retry_delay_seconds=int(os.getenv("RETRY_DELAY_SECONDS", "30")),
            
            # Remote Prover
            prover_url=os.getenv("PROVER_URL", ""),
            prover_backup_url=os.getenv("PROVER_BACKUP_URL", ""),
            prover_timeout=int(os.getenv("PROVER_TIMEOUT", "600")),
            
            # Logging
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_to_file=os.getenv("LOG_TO_FILE", "true").lower() == "true",
            log_file=os.getenv("LOG_FILE", "logs/worm-farmer.log"),
        )
    except (ValueError, TypeError, decimal.InvalidOperation) as e:
        raise ConfigError(f"Invalid value in configuration: {e}. Check your .env file.")
    
    logger.info(f"✓ Configuration loaded: {len(wallets)} wallet(s)")
    return config


def print_config_summary(config: FarmingConfig):
    """Print a summary of the current configuration."""
    logger = get_logger()
    
    logger.info("")
    logger.info("=" * 50)
    logger.info("[bold]🪱 WORM MULTI-WALLET FARMER CONFIG[/bold]")
    logger.info("=" * 50)
    logger.info("")
    
    logger.info("[bold]Network:[/bold]")
    # Mask API key in RPC URL
    masked_rpc = _mask_rpc_url(config.rpc_url)
    logger.info(f"  • RPC: {masked_rpc}")
    logger.info(f"  • Network: {config.network}")
    logger.info("")
    
    logger.info("[bold]Wallets:[/bold]")
    for i, wallet in enumerate(config.wallets):
        logger.info(f"  • [{i+1}] {wallet.short_address}")
    logger.info("")
    
    logger.info("[bold]Budget:[/bold]")
    logger.info(f"  • Total ETH: {config.total_eth_budget} ETH")
    logger.info(f"  • → BETH: {config.burn_spend} (after fee)")
    logger.info(f"  • → Epochs: {config.total_epochs} @ {config.beth_per_epoch}/epoch")
    logger.info("")
    
    logger.info("[bold]Mining:[/bold]")
    logger.info(f"  • Claim every: {config.claim_interval} epochs")
    logger.info(f"  • Loop interval: {config.loop_interval_seconds}s")
    logger.info("")
    
    logger.info("[bold]Prover:[/bold]")
    if config.use_remote_prover:
        logger.info(f"  • Mode: [green]Remote[/green] ⚡")
        logger.info(f"  • URL: {config.prover_url}")
    else:
        logger.info(f"  • Mode: [yellow]Not configured[/yellow]")
    logger.info("")
    logger.info("=" * 50)
    logger.info("")


def _mask_rpc_url(url: str) -> str:
    """Mask API key in RPC URL for safe logging."""
    import re
    # Match common patterns: /v2/KEY, /v3/KEY, apikey=KEY, key=KEY
    patterns = [
        (r'(/v[23]/)([a-zA-Z0-9_-]{8,})', r'\1***MASKED***'),
        (r'(apikey=)([a-zA-Z0-9_-]{8,})', r'\1***MASKED***'),
        (r'(key=)([a-zA-Z0-9_-]{8,})', r'\1***MASKED***'),
    ]
    masked = url
    for pattern, replacement in patterns:
        masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)
    return masked[:60] + "..." if len(masked) > 60 else masked

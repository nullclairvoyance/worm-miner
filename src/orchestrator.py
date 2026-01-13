"""
Main orchestration engine for WORM farming.

Implements the core farming loop: check balances → burn if needed → mine → repeat.
"""

import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, Union

from .config import FarmingConfig, WalletConfig, print_config_summary
from .blockchain import BlockchainClient, create_blockchain_client, BlockchainError
from .remote_miner import RemoteMinerClient, create_remote_miner, RemoteMinerError
from .utils.logger import (
    get_logger, 
    setup_logger,
    log_cycle_start, 
    log_cycle_end,
    log_balance,
    log_operation_start,
    log_operation_end,
)


@dataclass
class WalletState:
    """Runtime state for a wallet."""
    
    address: str
    name: str
    
    # Balances (updated each cycle)
    eth_balance: Decimal = Decimal("0")
    beth_balance: Decimal = Decimal("0")
    worm_balance: Decimal = Decimal("0")
    
    # Tracking
    last_burn_time: Optional[datetime] = None
    last_mine_time: Optional[datetime] = None
    burns_count: int = 0
    mines_count: int = 0
    
    # Error tracking
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    
    @property
    def short_address(self) -> str:
        return f"{self.address[:6]}...{self.address[-4:]}"


@dataclass  
class OrchestratorState:
    """Global orchestrator state."""
    
    cycle_count: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    total_burns: int = 0
    total_mines: int = 0
    is_running: bool = True
    
    wallets: Dict[str, WalletState] = field(default_factory=dict)


class Orchestrator:
    """
    Main orchestration engine.
    
    Coordinates the farming loop across multiple wallets:
    1. Check balances for each wallet
    2. Burn ETH → BETH if balance below threshold
    3. Mine (participate in epochs)
    4. Sleep and repeat
    """
    
    def __init__(
        self,
        config: FarmingConfig,
        blockchain: BlockchainClient,
        miner: RemoteMinerClient
    ):
        """
        Initialize orchestrator.
        
        Args:
            config: Farming configuration
            blockchain: Blockchain client for balance queries
            miner: Remote miner client
        """
        self.config = config
        self.blockchain = blockchain
        self.miner = miner
        self.logger = get_logger()
        
        # Initialize state
        self.state = OrchestratorState()
        
        # Initialize wallet states
        for wallet in config.wallets:
            self.state.wallets[wallet.address] = WalletState(
                address=wallet.address,
                name=wallet.name
            )
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info("")
        self.logger.info("🛑 Shutdown signal received. Finishing current operation...")
        self.state.is_running = False
    
    def _update_balances(self, wallet: WalletConfig) -> WalletState:
        """
        Update balances for a wallet.
        
        Args:
            wallet: Wallet configuration
            
        Returns:
            Updated wallet state
        """
        state = self.state.wallets[wallet.address]
        
        try:
            eth, beth, worm = self.blockchain.get_all_balances(wallet.address)
            state.eth_balance = eth
            state.beth_balance = beth
            state.worm_balance = worm
            state.consecutive_failures = 0
            
            log_balance(self.logger, float(beth), float(eth))
            
        except BlockchainError as e:
            state.consecutive_failures += 1
            state.last_error = str(e)
            self.logger.error(f"Failed to get balances: {e}")
        
        return state
    
    def _should_burn(self, state: WalletState) -> bool:
        """
        Determine if wallet needs to burn ETH for more BETH.
        
        Args:
            state: Current wallet state
            
        Returns:
            True if burn is needed
        """
        # Only burn if we don't have enough for 1 epoch
        # (since we participate 1 epoch at a time)
        if state.beth_balance >= self.config.beth_per_epoch:
            self.logger.info(
                f"✓ Sufficient BETH ({state.beth_balance}) for mining. Skipping burn."
            )
            return False
        
        # Check if we have enough ETH to burn
        min_eth_needed = self.config.total_eth_budget + Decimal("0.01")  # Buffer for gas
        if state.eth_balance < min_eth_needed:
            self.logger.warning(
                f"[warning]⚠[/warning] Insufficient ETH for burn. "
                f"Need {min_eth_needed}, have {state.eth_balance}"
            )
            return False
        
        self.logger.info(
            f"🔥 Need to burn: BETH balance {state.beth_balance} < 1 epoch ({self.config.beth_per_epoch})"
        )
        return True
    
    def _process_wallet(self, wallet: WalletConfig) -> bool:
        """
        Process a single wallet: check, burn if needed, mine.
        
        Args:
            wallet: Wallet to process
            
        Returns:
            True if all operations succeeded
        """
        self.logger.info(f"")
        self.logger.info(f"🔷 Processing {wallet.name} ({wallet.short_address})")
        self.logger.info(f"{'─' * 40}")
        
        # Update balances
        state = self._update_balances(wallet)
        
        # Check for too many failures
        if state.consecutive_failures >= self.config.max_retries:
            self.logger.error(
                f"[error]⚠[/error] Skipping wallet due to {state.consecutive_failures} "
                f"consecutive failures. Last error: {state.last_error}"
            )
            return False
        
        # Burn if needed
        if self._should_burn(state):
            self.logger.info(
                f"📉 Need more BETH. Burning {self.config.total_eth_budget} ETH..."
            )
            
            result = self.miner.burn(
                wallet=wallet,
                amount=self.config.total_eth_budget,
                spend=self.config.burn_spend,
                fee=self.config.burn_fee
            )
            
            if result.success:
                state.last_burn_time = datetime.now()
                state.burns_count += 1
                self.state.total_burns += 1
                
                # Re-fetch balance after burn
                time.sleep(2)  # Wait for tx to propagate
                self._update_balances(wallet)
            else:
                state.consecutive_failures += 1
                state.last_error = result.error_message
                return False
        else:
            self.logger.info(
                f"✓ Skipping burn - using existing BETH ({state.beth_balance})"
            )
        
        # Mine (participate in epochs)
        # Check if we have enough BETH for 1 epoch
        state = self.state.wallets[wallet.address]
        
        if state.beth_balance < self.config.beth_per_epoch:
            self.logger.warning(
                f"⚠️ Insufficient BETH ({state.beth_balance}) for 1 epoch "
                f"(need {self.config.beth_per_epoch})"
            )
            return False
        
        # Participate in 1 epoch per cycle (not all at once!)
        self.logger.info(
            f"📊 BETH: {state.beth_balance} → participating in 1 epoch"
        )
        
        result = self.miner.mine(
            wallet=wallet,
            amount_per_epoch=self.config.beth_per_epoch,
            num_epochs=1,  # ONE epoch per cycle
        )
        
        if result.success:
            state.last_mine_time = datetime.now()
            state.mines_count += 1
            self.state.total_mines += 1
            state.consecutive_failures = 0
        else:
            state.consecutive_failures += 1
            state.last_error = result.error_message
            return False
        
        return True
    
    def run_cycle(self) -> bool:
        """
        Run one complete farming cycle across all wallets.
        
        Returns:
            True if cycle completed without critical errors
        """
        self.state.cycle_count += 1
        cycle_start = time.time()
        
        log_cycle_start(self.state.cycle_count, len(self.config.wallets))
        
        success_count = 0
        
        for wallet in self.config.wallets:
            if not self.state.is_running:
                self.logger.info("Shutdown requested, stopping cycle")
                break
            
            try:
                if self._process_wallet(wallet):
                    success_count += 1
            except Exception as e:
                self.logger.error(f"Unexpected error processing {wallet.name}: {e}")
        
        cycle_duration = time.time() - cycle_start
        
        log_cycle_end(
            self.state.cycle_count,
            cycle_duration,
            self.config.loop_interval_seconds
        )
        
        self.logger.info(
            f"📊 Stats: {success_count}/{len(self.config.wallets)} wallets OK | "
            f"Total burns: {self.state.total_burns} | Total mines: {self.state.total_mines}"
        )
        
        return success_count == len(self.config.wallets)
    
    def run(self):
        """
        Run the main farming loop indefinitely.
        
        Continues until shutdown signal received.
        """
        self.logger.info("")
        self.logger.info("🪱 [bold]WORM MULTI-WALLET FARMER by Nullclairvoyant[/bold]")
        self.logger.info("")
        
        # Print config summary
        print_config_summary(self.config)
        
        # Verify connections
        self.logger.info("Verifying connections...")
        
        if not self.blockchain.check_connection():
            self.logger.error("Failed to connect to blockchain. Exiting.")
            return
        self.logger.info("[success]✓[/success] Blockchain connection OK")
        
        if not self.miner.check_prover():
            self.logger.warning("⚠️ Prover health check failed - will retry on first use")
        else:
            self.logger.info("[success]✓[/success] Prover connection OK")
        
        self.logger.info("")
        self.logger.info("Starting farming loop. Press Ctrl+C to stop.")
        self.logger.info("")
        
        # Main loop
        while self.state.is_running:
            try:
                self.run_cycle()
                
                if not self.state.is_running:
                    break
                
                # Sleep between cycles
                self.logger.info(
                    f"💤 Sleeping for {self.config.loop_interval_seconds}s..."
                )
                
                # Interruptible sleep
                for _ in range(self.config.loop_interval_seconds):
                    if not self.state.is_running:
                        break
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                self.logger.info("")
                self.logger.info("Keyboard interrupt received")
                self.state.is_running = False
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                self.logger.info("Continuing after error...")
                time.sleep(30)  # Brief pause before retry
        
        # Shutdown
        self._print_summary()
    
    def _print_summary(self):
        """Print final summary on shutdown."""
        runtime = datetime.now() - self.state.start_time
        hours = runtime.total_seconds() / 3600
        
        self.logger.info("")
        self.logger.info("=" * 50)
        self.logger.info("[bold]🪱 WORM MULTI-WALLET FARMER SHUTDOWN SUMMARY[/bold]")
        self.logger.info("=" * 50)
        self.logger.info(f"  • Runtime: {runtime}")
        self.logger.info(f"  • Cycles completed: {self.state.cycle_count}")
        self.logger.info(f"  • Total burns: {self.state.total_burns}")
        self.logger.info(f"  • Total mines: {self.state.total_mines}")
        
        if hours > 0:
            self.logger.info(f"  • Burns/hour: {self.state.total_burns / hours:.2f}")
            self.logger.info(f"  • Mines/hour: {self.state.total_mines / hours:.2f}")
        
        self.logger.info("")
        self.logger.info("Wallet Summary:")
        for addr, state in self.state.wallets.items():
            self.logger.info(
                f"  • {state.short_address}: "
                f"Burns={state.burns_count}, Mines={state.mines_count}, "
                f"BETH={state.beth_balance:.6f}"
            )
        
        self.logger.info("")
        self.logger.info("👋 Goodbye!")
        self.logger.info("")


def create_orchestrator(config: FarmingConfig) -> Orchestrator:
    """
    Create orchestrator with all dependencies.
    
    Args:
        config: Farming configuration
        
    Returns:
        Ready Orchestrator instance
    """
    logger = get_logger()
    
    # Setup logging
    setup_logger(
        level=config.log_level,
        log_to_file=config.log_to_file,
        log_file=config.log_file
    )
    
    # Create clients
    blockchain = create_blockchain_client(config)
    miner = create_remote_miner(config)
    
    logger.info("⚡ Using remote prover")
    
    return Orchestrator(config, blockchain, miner)

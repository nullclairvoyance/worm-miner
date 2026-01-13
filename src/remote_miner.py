"""
Remote Miner Client for WORM Protocol.

Fully Docker-free implementation:
- Burn: Remote prover for ZK proofs
- Mine/Claim: Direct web3 contract calls (no prover needed!)
"""

from decimal import Decimal
from typing import Optional
from dataclasses import dataclass
import time

from .config import FarmingConfig, WalletConfig
from .prover import ProverClient, ProofInput, ProofOutput, ProverError, create_prover_client
from .contracts import (
    BethContract, ContractError, create_beth_contract,
    WormContract, create_worm_contract,
)
from .crypto import generate_burn_inputs
from .utils.logger import get_logger


class RemoteMinerError(Exception):
    """Raised when remote miner operation fails."""
    pass


@dataclass
class MinerResult:
    """Result from any miner operation."""
    success: bool
    tx_hash: Optional[str] = None
    error_message: Optional[str] = None
    duration: float = 0.0


class RemoteMinerClient:
    """
    Remote miner client - 100% Docker-free!
    
    - burn(): Uses remote prover for ZK proofs
    - mine(): Direct web3 call (no prover!)
    - claim(): Direct web3 call (no prover!)
    """
    
    def __init__(self, config: FarmingConfig):
        """
        Initialize remote miner client.
        
        Args:
            config: Farming configuration with prover_url
        """
        self.config = config
        self.logger = get_logger()
        
        # Initialize components
        self.prover = create_prover_client(
            prover_url=config.prover_url,
            timeout=config.prover_timeout,
        )
        self.beth_contract = create_beth_contract(config)
        self.worm_contract = create_worm_contract(config)
    
    def check_prover(self) -> bool:
        """Check if prover service is available."""
        return self.prover.check_health()
    
    def burn(
        self,
        wallet: WalletConfig,
        amount: Decimal,
        spend: Decimal,
        fee: Decimal,
    ) -> MinerResult:
        """
        Execute full burn flow: burn ETH → get proof → mint BETH.
        
        Args:
            wallet: Wallet to burn from
            amount: ETH amount to burn
            spend: BETH amount to mint
            fee: Protocol fee
            
        Returns:
            MinerResult with operation status
        """
        start_time = time.time()
        
        try:
            self.logger.info(
                f"🔥 Remote burn: {amount} ETH → {spend} BETH for {wallet.short_address}"
            )
            
            # Convert to wei
            from web3 import Web3
            amount_wei = Web3.to_wei(amount, 'ether')
            spend_wei = Web3.to_wei(spend, 'ether')
            fee_wei = Web3.to_wei(fee, 'ether')
            
            # Step 1: Generate burn_key (client-side PoW)
            self.logger.info("🔐 Generating burn key (PoW)...")
            burn_key, extra_commit = generate_burn_inputs(
                wallet_address=wallet.address,
                amount_wei=amount_wei,
                spend_wei=spend_wei,
                fee_wei=fee_wei,
            )
            self.logger.debug(f"burn_key: {burn_key}")
            
            # Step 2: Create proof input
            proof_input = ProofInput(
                network=self.config.network,
                amount=str(amount),
                broadcaster_fee="0",
                prover_fee="0",
                spend=str(spend),
                burn_key=str(burn_key),
                wallet_address=wallet.address,
                receiver_hook="0x",
            )
            
            # Step 3: Get proof from remote prover
            self.logger.info("📡 Requesting proof from remote prover...")
            proof_output = self.prover.generate_proof(proof_input)
            
            self.logger.info(f"✓ Proof generated! Burn address: {proof_output.burn_address[:16]}...")
            
            # Step 4: Send ETH to burn address
            self.beth_contract.send_burn_tx(
                wallet=wallet,
                burn_address=proof_output.burn_address,
                amount=amount,
            )
            
            # Step 5: Submit proof to mint BETH
            mint_tx = self.beth_contract.mint_from_proof(
                wallet=wallet,
                proof_output=proof_output,
                spend=spend,
            )
            
            duration = time.time() - start_time
            self.logger.info(
                f"[success]✓[/success] Burn complete! Minted {spend} BETH in {duration:.1f}s"
            )
            
            return MinerResult(success=True, tx_hash=mint_tx, duration=duration)
            
        except (ProverError, ContractError) as e:
            duration = time.time() - start_time
            self.logger.error(f"[error]✗[/error] Burn failed: {e}")
            return MinerResult(success=False, error_message=str(e), duration=duration)
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"[error]✗[/error] Burn failed: {e}")
            return MinerResult(success=False, error_message=str(e), duration=duration)
    
    def mine(
        self,
        wallet: WalletConfig,
        amount_per_epoch: Optional[Decimal] = None,
        num_epochs: Optional[int] = None,
    ) -> MinerResult:
        """
        Participate in mining epochs.
        
        NO PROVER NEEDED - direct web3 contract call!
        
        Args:
            wallet: Wallet to mine with
            amount_per_epoch: BETH per epoch (default from config)
            num_epochs: Number of epochs (default from config)
            
        Returns:
            MinerResult with operation status
        """
        start_time = time.time()
        
        # Use config defaults
        amount = amount_per_epoch or self.config.amount_per_epoch
        epochs = num_epochs or self.config.num_epochs
        
        try:
            tx_hash = self.worm_contract.participate(
                wallet=wallet,
                amount_per_epoch=amount,
                num_epochs=epochs,
            )
            
            duration = time.time() - start_time
            return MinerResult(success=True, tx_hash=tx_hash, duration=duration)
            
        except ContractError as e:
            duration = time.time() - start_time
            self.logger.error(f"[error]✗[/error] Mine failed: {e}")
            return MinerResult(success=False, error_message=str(e), duration=duration)
    
    def claim(
        self,
        wallet: WalletConfig,
        starting_epoch: int,
        num_epochs: int,
    ) -> MinerResult:
        """
        Claim WORM rewards from past epochs.
        
        NO PROVER NEEDED - direct web3 contract call!
        
        Args:
            wallet: Wallet to claim to
            starting_epoch: First epoch to claim from
            num_epochs: Number of epochs to claim
            
        Returns:
            MinerResult with operation status
        """
        start_time = time.time()
        
        try:
            tx_hash = self.worm_contract.claim(
                wallet=wallet,
                starting_epoch=starting_epoch,
                num_epochs=num_epochs,
            )
            
            duration = time.time() - start_time
            return MinerResult(success=True, tx_hash=tx_hash, duration=duration)
            
        except ContractError as e:
            duration = time.time() - start_time
            self.logger.error(f"[error]✗[/error] Claim failed: {e}")
            return MinerResult(success=False, error_message=str(e), duration=duration)


def create_remote_miner(config: FarmingConfig) -> RemoteMinerClient:
    """Factory function to create remote miner client."""
    return RemoteMinerClient(config)


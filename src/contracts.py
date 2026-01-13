"""
Smart contract interaction for WORM Protocol.

Handles direct on-chain transactions for burn and mint operations,
enabling Docker-free operation with remote provers.
"""

from decimal import Decimal
from typing import Optional, Tuple
from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount

from .config import FarmingConfig, WalletConfig
from .prover import ProofOutput
from .utils.logger import get_logger


# BETH Contract on Sepolia
BETH_CONTRACT_ADDRESS = "0x716bC7e331c9Da551e5Eb6A099c300db4c08E994"

# BETH Contract ABI for mintCoin
BETH_MINT_ABI = [
    {
        "name": "mintCoin",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_pA", "type": "uint256[2]"},
            {"name": "_pB", "type": "uint256[2][2]"},
            {"name": "_pC", "type": "uint256[2]"},
            {"name": "_blockNumber", "type": "uint256"},
            {"name": "_nullifier", "type": "uint256"},
            {"name": "_remainingCoin", "type": "uint256"},
            {"name": "_broadcasterFee", "type": "uint256"},
            {"name": "_revealedAmount", "type": "uint256"},
            {"name": "_revealedAmountReceiver", "type": "address"},
            {"name": "_proverFee", "type": "uint256"},
            {"name": "_prover", "type": "address"},
            {"name": "_receiverPostMintHook", "type": "bytes"},
            {"name": "_broadcasterFeePostMintHook", "type": "bytes"},
        ],
        "outputs": [],
    }
]


class ContractError(Exception):
    """Raised when contract interaction fails."""
    pass


# SECURITY: Maximum gas price in Gwei (prevents wallet drain on spikes)
MAX_GAS_GWEI = 100


class BethContract:
    """
    Client for BETH contract interactions.
    
    Handles sending burn transactions and minting BETH from proofs.
    """
    
    def __init__(self, config: FarmingConfig):
        """
        Initialize BETH contract client.
        
        Args:
            config: Farming configuration
        """
        self.config = config
        self.logger = get_logger()
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        
        self.beth_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(BETH_CONTRACT_ADDRESS),
            abi=BETH_MINT_ABI
        )
    
    def _check_gas_price(self) -> int:
        """Get gas price and verify it's within safe limits."""
        gas_price = self.w3.eth.gas_price
        max_gas_wei = self.w3.to_wei(MAX_GAS_GWEI, 'gwei')
        
        if gas_price > max_gas_wei:
            raise ContractError(
                f"Gas price too high: {gas_price / 1e9:.1f} Gwei "
                f"(max: {MAX_GAS_GWEI} Gwei). Try again later."
            )
        return gas_price
    
    def _get_optimal_gas(self) -> int:
        """Get optimal gas price for Sepolia with priority buffer.
        
        Adds 20% buffer to current gas price to ensure TX gets mined quickly.
        """
        base_gas = self._check_gas_price()
        # Add 20% priority buffer for testnets
        optimal_gas = int(base_gas * 1.2)
        self.logger.debug(f"Gas: base={base_gas/1e9:.2f} Gwei, optimal={optimal_gas/1e9:.2f} Gwei")
        return optimal_gas
    
    def send_burn_tx(
        self,
        wallet: WalletConfig,
        burn_address: str,
        amount: Decimal,
    ) -> str:
        """
        Send ETH to a burn address.
        
        Args:
            wallet: Wallet to burn from
            burn_address: Generated burn address
            amount: ETH amount to burn
            
        Returns:
            Transaction hash
            
        Raises:
            ContractError: If transaction fails
        """
        try:
            self.logger.info(
                f"🔥 Sending {amount} ETH to burn address {burn_address[:10]}..."
            )
            
            account: LocalAccount = Account.from_key(wallet.private_key)
            
            # Convert amount to wei
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # SECURITY: Check gas price limits
            gas_price = self._check_gas_price()
            
            # Build transaction
            tx = {
                'from': account.address,
                'to': Web3.to_checksum_address(burn_address),
                'value': amount_wei,
                'gas': 21000,  # Standard ETH transfer
                'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'chainId': self.w3.eth.chain_id,
            }
            
            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, wallet.private_key)
            raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            self.logger.info(f"📤 Burn TX sent: {tx_hash.hex()[:16]}...")
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                self.logger.info(f"✓ Burn TX confirmed in block {receipt['blockNumber']}")
                return tx_hash.hex()
            else:
                raise ContractError("Burn transaction reverted")
                
        except Exception as e:
            raise ContractError(f"Failed to send burn TX: {e}")
    
    def mint_from_proof(
        self,
        wallet: WalletConfig,
        proof_output: ProofOutput,
        spend: Decimal,
    ) -> str:
        """
        Mint BETH by submitting proof to contract.
        
        Args:
            wallet: Wallet to receive BETH (must sign TX)
            proof_output: Proof from remote prover
            spend: BETH amount being minted
            
        Returns:
            Transaction hash
            
        Raises:
            ContractError: If transaction fails
        """
        try:
            self.logger.info(f"📝 Submitting proof to mint BETH...")
            
            account: LocalAccount = Account.from_key(wallet.private_key)
            
            # Parse proof data from ProofOutput
            proof = proof_output.proof
            
            # Extract proof arrays (pi_a, pi_b, pi_c)
            pi_a = [int(proof['pi_a'][0]), int(proof['pi_a'][1])]
            pi_b = [
                [int(proof['pi_b'][0][1]), int(proof['pi_b'][0][0])],  # Flipped!
                [int(proof['pi_b'][1][1]), int(proof['pi_b'][1][0])],
            ]
            pi_c = [int(proof['pi_c'][0]), int(proof['pi_c'][1])]
            
            # Convert amounts to wei
            spend_wei = self.w3.to_wei(spend, 'ether')
            
            # Parse other values from proof output
            block_number = proof_output.block_number
            nullifier = int(proof_output.nullifier_u256)
            remaining_coin = int(proof_output.remaining_coin)
            broadcaster_fee = int(proof_output.broadcaster_fee)
            prover_fee = int(proof_output.prover_fee)
            prover_address = Web3.to_checksum_address(proof_output.prover)
            receiver_address = Web3.to_checksum_address(proof_output.wallet_address)
            reveal_amount = int(proof_output.reveal_amount)
            
            # Build contract call
            mint_tx = self.beth_contract.functions.mintCoin(
                pi_a,
                pi_b,
                pi_c,
                block_number,
                nullifier,
                remaining_coin,
                broadcaster_fee,
                reveal_amount,
                receiver_address,
                prover_fee,
                prover_address,
                b'',  # receiverPostMintHook
                b'',  # broadcasterFeePostMintHook
            ).build_transaction({
                'from': account.address,
                'gas': 500000,  # Estimated for proof verification
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'chainId': self.w3.eth.chain_id,
            })
            
            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(mint_tx, wallet.private_key)
            raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            self.logger.info(f"📤 Mint TX sent: {tx_hash.hex()[:16]}...")
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                self.logger.info(
                    f"[success]✓[/success] Minted BETH in block {receipt['blockNumber']}"
                )
                return tx_hash.hex()
            else:
                raise ContractError("Mint transaction reverted")
                
        except Exception as e:
            raise ContractError(f"Failed to mint BETH: {e}")


def create_beth_contract(config: FarmingConfig) -> BethContract:
    """Factory function to create BETH contract client."""
    return BethContract(config)


# WORM Contract on Sepolia
WORM_CONTRACT_ADDRESS = "0xcBdF9890B5935F01B2f21583d1885CdC8389eb5F"

# WORM Contract ABI for mining
WORM_MINE_ABI = [
    {
        "name": "participate",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_amountPerEpoch", "type": "uint256"},
            {"name": "_numEpochs", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "claim",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_startingEpoch", "type": "uint256"},
            {"name": "_numEpochs", "type": "uint256"},
        ],
        "outputs": [],
    }
]

# ERC20 Approve ABI
ERC20_APPROVE_ABI = [
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


class WormContract:
    """
    Client for WORM contract mining operations.
    
    Handles participate (commit BETH to epochs) and claim (get WORM rewards).
    NO prover needed - direct web3 calls!
    """
    
    def __init__(self, config: FarmingConfig):
        """
        Initialize WORM contract client.
        
        Args:
            config: Farming configuration
        """
        self.config = config
        self.logger = get_logger()
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        
        self.worm_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(WORM_CONTRACT_ADDRESS),
            abi=WORM_MINE_ABI
        )
        
        self.beth_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(BETH_CONTRACT_ADDRESS),
            abi=ERC20_APPROVE_ABI
        )
    def _get_optimal_gas(self) -> int:
        """Get optimal gas price for Sepolia with priority buffer.
        
        Adds 20% buffer to current gas price to ensure TX gets mined quickly.
        """
        base_gas = self.w3.eth.gas_price
        max_gas_wei = self.w3.to_wei(MAX_GAS_GWEI, 'gwei')
        
        if base_gas > max_gas_wei:
            raise ContractError(
                f"Gas price too high: {base_gas / 1e9:.1f} Gwei "
                f"(max: {MAX_GAS_GWEI} Gwei). Try again later."
            )
        
        # Add 20% priority buffer for testnets
        optimal_gas = int(base_gas * 1.2)
        return optimal_gas
    
    def check_allowance(self, wallet: WalletConfig) -> int:
        """Check BETH allowance for WORM contract."""
        return self.beth_contract.functions.allowance(
            wallet.address,
            WORM_CONTRACT_ADDRESS
        ).call()
    
    def approve_beth(self, wallet: WalletConfig, amount: Decimal) -> str:
        """
        Approve WORM contract to spend BETH.
        
        Args:
            wallet: Wallet to approve from
            amount: BETH amount to approve
            
        Returns:
            Transaction hash
        """
        try:
            account = Account.from_key(wallet.private_key)
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # Check current allowance
            current_allowance = self.check_allowance(wallet)
            if current_allowance >= amount_wei:
                self.logger.debug("BETH already approved")
                return "already_approved"
            
            self.logger.info(f"📝 Approving {amount} BETH for mining...")
            
            tx = self.beth_contract.functions.approve(
                WORM_CONTRACT_ADDRESS,
                amount_wei
            ).build_transaction({
                'from': account.address,
                'gas': 60000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'chainId': self.w3.eth.chain_id,
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, wallet.private_key)
            raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if receipt['status'] == 1:
                self.logger.info("✓ BETH approved")
                return tx_hash.hex()
            else:
                raise ContractError("Approval transaction reverted")
                
        except Exception as e:
            raise ContractError(f"Failed to approve BETH: {e}")
    
    def participate(
        self,
        wallet: WalletConfig,
        amount_per_epoch: Decimal,
        num_epochs: int,
    ) -> str:
        """
        Participate in mining epochs.
        
        Args:
            wallet: Wallet to participate with
            amount_per_epoch: BETH to commit per epoch
            num_epochs: Number of epochs to participate in
            
        Returns:
            Transaction hash
        """
        try:
            account = Account.from_key(wallet.private_key)
            amount_wei = self.w3.to_wei(amount_per_epoch, 'ether')
            total_beth = amount_per_epoch * num_epochs
            
            # Ensure BETH is approved
            self.approve_beth(wallet, total_beth)
            
            self.logger.info(
                f"⛏️ Participating: {amount_per_epoch} BETH × {num_epochs} epochs"
            )
            
            # Estimate gas for this specific call
            gas_estimate = self.worm_contract.functions.participate(
                amount_wei,
                num_epochs
            ).estimate_gas({'from': account.address})
            
            tx = self.worm_contract.functions.participate(
                amount_wei,
                num_epochs
            ).build_transaction({
                'from': account.address,
                'gas': int(gas_estimate * 1.2),  # 20% buffer
                'gasPrice': self._get_optimal_gas(),
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'chainId': self.w3.eth.chain_id,
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, wallet.private_key)
            raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            self.logger.info(f"📤 Participate TX sent: {tx_hash.hex()[:16]}...")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                self.logger.info(
                    f"[success]✓[/success] Participating in {num_epochs} epochs"
                )
                return tx_hash.hex()
            else:
                raise ContractError("Participate transaction reverted")
                
        except Exception as e:
            raise ContractError(f"Failed to participate: {e}")
    
    def claim(
        self,
        wallet: WalletConfig,
        starting_epoch: int,
        num_epochs: int,
    ) -> str:
        """
        Claim WORM rewards from past epochs.
        
        Args:
            wallet: Wallet to claim to
            starting_epoch: First epoch to claim from
            num_epochs: Number of epochs to claim
            
        Returns:
            Transaction hash
        """
        try:
            account = Account.from_key(wallet.private_key)
            
            self.logger.info(
                f"🎁 Claiming WORM for epochs {starting_epoch} to {starting_epoch + num_epochs - 1}"
            )
            
            tx = self.worm_contract.functions.claim(
                starting_epoch,
                num_epochs
            ).build_transaction({
                'from': account.address,
                'gas': 300000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'chainId': self.w3.eth.chain_id,
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, wallet.private_key)
            raw_tx = signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            
            self.logger.info(f"📤 Claim TX sent: {tx_hash.hex()[:16]}...")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                self.logger.info(
                    f"[success]✓[/success] Claimed WORM rewards!"
                )
                return tx_hash.hex()
            else:
                raise ContractError("Claim transaction reverted")
                
        except Exception as e:
            raise ContractError(f"Failed to claim: {e}")


def create_worm_contract(config: FarmingConfig) -> WormContract:
    """Factory function to create WORM contract client."""
    return WormContract(config)

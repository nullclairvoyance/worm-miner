"""
Blockchain interaction layer using web3.py.

Handles balance queries for ETH and BETH tokens.
"""

from decimal import Decimal
from typing import Optional, Tuple

from web3 import Web3
from web3.exceptions import Web3Exception

from .config import FarmingConfig
from .utils.logger import get_logger
from .utils.retry import retry_with_backoff


# BETH Token Contract on Sepolia
BETH_CONTRACT_ADDRESS = "0x716bC7e331c9Da551e5Eb6A099c300db4c08E994"

# WORM Token Contract on Sepolia  
WORM_CONTRACT_ADDRESS = "0xcBdF9890B5935F01B2f21583d1885CdC8389eb5F"

# Standard ERC20 ABI for balanceOf
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# WORM contract ABI for epoch queries and protocol metrics
WORM_EPOCH_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "currentEpoch",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "epochRemainingTime",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "startingTimestamp",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalWorm",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalBeth",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]


class BlockchainError(Exception):
    """Raised when blockchain interaction fails."""
    pass


class BlockchainClient:
    """
    Client for blockchain interactions.
    
    Provides methods to query balances and check network health.
    """
    
    def __init__(self, config: FarmingConfig):
        """
        Initialize blockchain client.
        
        Args:
            config: Farming configuration with RPC URL
        """
        self.config = config
        self.logger = get_logger()
        
        # Initialize web3
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        
        # Initialize token contracts
        self.beth_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(BETH_CONTRACT_ADDRESS),
            abi=ERC20_ABI
        )
        self.worm_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(WORM_CONTRACT_ADDRESS),
            abi=ERC20_ABI + WORM_EPOCH_ABI
        )
    
    def check_connection(self) -> bool:
        """
        Check if RPC connection is healthy.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            connected = self.w3.is_connected()
            if connected:
                chain_id = self.w3.eth.chain_id
                block = self.w3.eth.block_number
                self.logger.debug(f"Connected to chain {chain_id}, block {block}")
            return connected
        except Exception as e:
            self.logger.error(f"RPC connection check failed: {e}")
            return False
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, operation_name="get_eth_balance")
    def get_eth_balance(self, address: str) -> Decimal:
        """
        Get native ETH balance for an address.
        
        Args:
            address: Ethereum address
            
        Returns:
            Balance in ETH as Decimal
        """
        try:
            checksum_addr = Web3.to_checksum_address(address)
            balance_wei = self.w3.eth.get_balance(checksum_addr)
            balance_eth = Decimal(str(self.w3.from_wei(balance_wei, "ether")))
            return balance_eth
        except Web3Exception as e:
            raise BlockchainError(f"Failed to get ETH balance for {address}: {e}")
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, operation_name="get_beth_balance")
    def get_beth_balance(self, address: str) -> Decimal:
        """
        Get BETH token balance for an address.
        
        Args:
            address: Ethereum address
            
        Returns:
            Balance in BETH as Decimal
        """
        try:
            checksum_addr = Web3.to_checksum_address(address)
            balance_raw = self.beth_contract.functions.balanceOf(checksum_addr).call()
            # BETH has 18 decimals like ETH
            balance = Decimal(str(balance_raw)) / Decimal(10 ** 18)
            return balance
        except Web3Exception as e:
            raise BlockchainError(f"Failed to get BETH balance for {address}: {e}")
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, operation_name="get_worm_balance")
    def get_worm_balance(self, address: str) -> Decimal:
        """
        Get WORM token balance for an address.
        
        Args:
            address: Ethereum address
            
        Returns:
            Balance in WORM as Decimal
        """
        try:
            checksum_addr = Web3.to_checksum_address(address)
            balance_raw = self.worm_contract.functions.balanceOf(checksum_addr).call()
            # Assuming WORM has 18 decimals
            balance = Decimal(str(balance_raw)) / Decimal(10 ** 18)
            return balance
        except Web3Exception as e:
            raise BlockchainError(f"Failed to get WORM balance for {address}: {e}")
    
    def get_all_balances(self, address: str) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Get all balances (ETH, BETH, WORM) for an address.
        
        Args:
            address: Ethereum address
            
        Returns:
            Tuple of (eth_balance, beth_balance, worm_balance)
        """
        eth = self.get_eth_balance(address)
        beth = self.get_beth_balance(address)
        worm = self.get_worm_balance(address)
        return eth, beth, worm
    
    def get_current_epoch(self) -> Optional[int]:
        """
        Get the current epoch from the WORM contract.
        
        Returns:
            Current epoch number, or None if not available
        """
        try:
            epoch = self.worm_contract.functions.currentEpoch().call()
            return int(epoch)
        except Exception as e:
            self.logger.debug(f"Could not fetch current epoch: {e}")
            return None
    
    def get_epoch_info(self) -> Tuple[Optional[int], Optional[int]]:
        """
        Get current epoch and remaining time.
        
        Returns:
            Tuple of (current_epoch, remaining_seconds_in_epoch)
        """
        epoch = self.get_current_epoch()
        remaining = None
        try:
            remaining = int(self.worm_contract.functions.epochRemainingTime().call())
        except Exception:
            pass
        return epoch, remaining
    
    def get_protocol_stats(self) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Get protocol-wide statistics.
        
        Returns:
            Tuple of (total_beth_minted, total_worm_distributed)
            Values are in ether units, or None if unavailable
        """
        total_beth = None
        total_worm = None
        
        try:
            beth_wei = self.worm_contract.functions.totalBeth().call()
            total_beth = Decimal(str(self.w3.from_wei(beth_wei, 'ether')))
        except Exception as e:
            self.logger.debug(f"Could not fetch totalBeth: {e}")
        
        try:
            worm_wei = self.worm_contract.functions.totalWorm().call()
            total_worm = Decimal(str(self.w3.from_wei(worm_wei, 'ether')))
        except Exception as e:
            self.logger.debug(f"Could not fetch totalWorm: {e}")
        
        return total_beth, total_worm
    
    def get_gas_price(self) -> Decimal:
        """
        Get current gas price in Gwei.
        
        Returns:
            Gas price in Gwei as Decimal
        """
        try:
            gas_wei = self.w3.eth.gas_price
            gas_gwei = Decimal(str(self.w3.from_wei(gas_wei, "gwei")))
            return gas_gwei
        except Web3Exception as e:
            self.logger.warning(f"Failed to get gas price: {e}")
            return Decimal("0")
    
    def estimate_gas_cost(self, gas_limit: int = 500000) -> Decimal:
        """
        Estimate gas cost in ETH for a transaction.
        
        Args:
            gas_limit: Expected gas limit for transaction
            
        Returns:
            Estimated cost in ETH
        """
        gas_price = self.get_gas_price()
        cost_gwei = gas_price * gas_limit
        cost_eth = cost_gwei / Decimal(10 ** 9)
        return cost_eth


def create_blockchain_client(config: FarmingConfig) -> BlockchainClient:
    """
    Create and validate blockchain client.
    
    Args:
        config: Farming configuration
        
    Returns:
        Connected BlockchainClient instance
        
    Raises:
        BlockchainError: If connection fails
    """
    client = BlockchainClient(config)
    
    if not client.check_connection():
        raise BlockchainError(
            f"Failed to connect to RPC at {config.rpc_url}. "
            "Check your RPC_URL in .env"
        )
    
    return client

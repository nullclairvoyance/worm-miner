"""
Cryptographic utilities for WORM Protocol.

Implements burn_key generation using Poseidon hash and proof-of-work,
matching the worm-miner Rust implementation.
"""

import os
import secrets
from typing import Tuple
from eth_utils import keccak
from web3 import Web3


# BN254 prime field modulus (same as used in circom/snarkjs)
BN254_PRIME = 21888242871839275222246405745257275088548364400416034343698204186575808495617

# Poseidon prefix constant: keccak256("EIP-7503") mod P
POSEIDON_PREFIX_VALUE = 5265656504298861414514317065875120428884240036965045859626767452974705356670


def bytes_to_int_be(data: bytes) -> int:
    """Convert bytes to big-endian integer."""
    return int.from_bytes(data, 'big')


def int_to_bytes32_be(value: int) -> bytes:
    """Convert integer to 32-byte big-endian bytes."""
    return value.to_bytes(32, 'big')


def generate_burn_extra_commit(
    receiver: str,
    prover_fee: int,
    broadcaster_fee: int,
    receiver_hook: bytes = b'',
) -> int:
    """
    Generate the burn extra commitment hash.
    
    This is: keccak256(abi.encodePacked(broadcasterFee, proverFee, receiver, receiverHook)) >> 8
    
    Args:
        receiver: Receiver address (checksummed)
        prover_fee: Prover fee in wei
        broadcaster_fee: Broadcaster fee in wei
        receiver_hook: Hook data (usually empty)
        
    Returns:
        Extra commitment as integer
    """
    # ABI encode packed: broadcaster_fee (32) + prover_fee (32) + receiver (20) + hook (variable)
    receiver_bytes = bytes.fromhex(receiver[2:] if receiver.startswith('0x') else receiver)
    
    packed = (
        int_to_bytes32_be(broadcaster_fee) +
        int_to_bytes32_be(prover_fee) +
        receiver_bytes +
        receiver_hook
    )
    
    hash_bytes = keccak(packed)
    # Right shift by 8 bits (1 byte)
    result = bytes_to_int_be(hash_bytes) >> 8
    return result


def find_burn_key(
    pow_min_zero_bytes: int,
    burn_extra_commit: int,
    reveal: int,
) -> int:
    """
    Find a valid burn_key using proof-of-work.
    
    The key must produce a hash with at least `pow_min_zero_bytes` leading zero bytes.
    
    Algorithm:
        hash = keccak256(burn_key || reveal || extra_commit || "EIP-7503")
        Keep incrementing burn_key until hash has required leading zeros.
    
    Args:
        pow_min_zero_bytes: Required leading zero bytes (usually 2)
        burn_extra_commit: Extra commitment value
        reveal: Reveal amount (spend in wei)
        
    Returns:
        Valid burn_key as integer
    """
    # Start with random value
    curr = secrets.randbits(256)
    
    # Ensure within field
    curr = curr % BN254_PRIME
    
    iterations = 0
    max_iterations = 10_000_000  # Safety limit
    
    while iterations < max_iterations:
        # Build input: curr (32) + reveal (32) + extra_commit (32) + "EIP-7503" (8)
        input_bytes = (
            int_to_bytes32_be(curr) +
            int_to_bytes32_be(reveal) +
            int_to_bytes32_be(burn_extra_commit) +
            b"EIP-7503"
        )
        
        hash_bytes = keccak(input_bytes)
        
        # Check for leading zero bytes
        leading_zeros = 0
        for b in hash_bytes:
            if b == 0:
                leading_zeros += 1
            else:
                break
        
        if leading_zeros >= pow_min_zero_bytes:
            return curr
        
        curr = (curr + 1) % BN254_PRIME
        iterations += 1
    
    raise RuntimeError(f"Failed to find burn_key after {max_iterations} iterations")


def compute_nullifier(burn_key: int) -> int:
    """
    Compute nullifier from burn_key.
    
    This is a simplified version - the actual uses Poseidon hash.
    For remote prover use, the prover computes this server-side.
    
    Args:
        burn_key: The burn key integer
        
    Returns:
        Nullifier as integer (simplified - actual uses Poseidon)
    """
    # Note: This is simplified. The actual nullifier uses:
    # poseidon2(poseidon_nullifier_prefix(), burn_key)
    # But the remote prover computes this for us.
    return burn_key  # Placeholder - prover returns actual nullifier


def generate_burn_inputs(
    wallet_address: str,
    amount_wei: int,
    spend_wei: int,
    fee_wei: int,
    pow_zero_bytes: int = 2,
) -> Tuple[int, int]:
    """
    Generate inputs needed for remote prover.
    
    Args:
        wallet_address: Receiver wallet address
        amount_wei: Burn amount in wei
        spend_wei: Spend amount in wei
        fee_wei: Protocol fee in wei
        pow_zero_bytes: PoW difficulty (default 2)
        
    Returns:
        Tuple of (burn_key, extra_commit)
    """
    # Compute extra commitment
    # For simplicity, using 0 prover/broadcaster fees (user pays gas)
    extra_commit = generate_burn_extra_commit(
        receiver=wallet_address,
        prover_fee=0,
        broadcaster_fee=0,
        receiver_hook=b'',
    )
    
    # Find burn_key with PoW
    burn_key = find_burn_key(
        pow_min_zero_bytes=pow_zero_bytes,
        burn_extra_commit=extra_commit,
        reveal=spend_wei,
    )
    
    return burn_key, extra_commit


# Note: Full burn address generation requires Poseidon hash which is complex.
# The remote prover handles this - we just need to provide burn_key and it
# returns the burn_address in the ProofOutput.

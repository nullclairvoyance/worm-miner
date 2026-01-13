"""
Remote Prover Client for WORM Protocol.

Communicates with external proving services to generate ZK proofs
without requiring local Docker/computation.

Public prover endpoints:
- https://worm-miner-3.darkube.app/proof
- https://worm-testnet.metatarz.xyz/proof
"""

import time
from dataclasses import dataclass
from typing import Optional
import requests

from .utils.logger import get_logger


class ProverError(Exception):
    """Raised when prover interaction fails."""
    pass


@dataclass
class ProofInput:
    """Input for proof generation request."""
    network: str
    amount: str
    broadcaster_fee: str
    prover_fee: str
    spend: str
    burn_key: str
    wallet_address: str
    receiver_hook: str = "0x"
    proof: Optional[dict] = None  # EIP1186 account proof
    block_number: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert to API request format."""
        data = {
            "network": self.network,
            "amount": self.amount,
            "broadcaster_fee": self.broadcaster_fee,
            "prover_fee": self.prover_fee,
            "spend": self.spend,
            "burn_key": self.burn_key,
            "wallet_address": self.wallet_address,
            "receiver_hook": self.receiver_hook,
        }
        if self.proof is not None:
            data["proof"] = self.proof
        if self.block_number is not None:
            data["block_number"] = self.block_number
        return data


@dataclass
class ProofOutput:
    """Output from proof generation."""
    burn_address: str
    proof: dict
    block_number: int
    nullifier_u256: str
    remaining_coin: str
    broadcaster_fee: str
    prover_fee: str
    prover: str
    reveal_amount: str
    wallet_address: str
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProofOutput":
        """Create from API response."""
        return cls(
            burn_address=data["burn_address"],
            proof=data["proof"],
            block_number=data["block_number"],
            nullifier_u256=data["nullifier_u256"],
            remaining_coin=data["remaining_coin"],
            broadcaster_fee=data["broadcaster_fee"],
            prover_fee=data["prover_fee"],
            prover=data["prover"],
            reveal_amount=data["reveal_amount"],
            wallet_address=data["wallet_address"],
        )


# Default public prover endpoints
DEFAULT_PROVERS = [
    "https://worm-miner-3.darkube.app",
    "https://worm-testnet.metatarz.xyz",
]


class ProverClient:
    """
    Client for remote ZK proof generation.
    
    Submits proof jobs and polls for results without needing
    local Docker or zk-SNARK parameters.
    """
    
    def __init__(
        self,
        prover_url: str = None,
        timeout: int = 600,
        poll_interval: int = 5,
    ):
        """
        Initialize prover client.
        
        Args:
            prover_url: Base URL of prover service (without /proof)
            timeout: Maximum seconds to wait for proof
            poll_interval: Seconds between status polls
        """
        self.prover_url = (prover_url or DEFAULT_PROVERS[0]).rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.logger = get_logger()
        
        # HTTP session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
    
    def submit_proof(self, proof_input: ProofInput) -> str:
        """
        Submit a proof job to the prover.
        
        Args:
            proof_input: Proof generation parameters
            
        Returns:
            job_id for polling
            
        Raises:
            ProverError: If submission fails on all endpoints
        """
        # Try all available endpoints
        endpoints = [self.prover_url]
        for backup in DEFAULT_PROVERS:
            backup = backup.rstrip("/")
            if backup != self.prover_url:
                endpoints.append(backup)
        
        last_error = None
        for endpoint in endpoints:
            url = f"{endpoint}/proof"
            try:
                self.logger.debug(f"Submitting proof to {url}")
                response = self.session.post(
                    url,
                    json=proof_input.to_dict(),
                    timeout=30,
                )
                
                if response.status_code == 429:
                    self.logger.warning(f"Queue full at {endpoint}, trying next...")
                    continue
                
                if response.status_code == 503:
                    self.logger.warning(f"Service unavailable at {endpoint}, trying next...")
                    continue
                
                data = response.json()
                
                if data.get("status") == "error":
                    last_error = data.get('message')
                    self.logger.warning(f"Error from {endpoint}: {last_error}")
                    continue
                
                job_id = data.get("result", {}).get("job_id")
                if not job_id:
                    continue
                
                # Success! Update prover_url to working endpoint
                if endpoint != self.prover_url:
                    self.logger.info(f"⚡ Switched to prover: {endpoint}")
                    self.prover_url = endpoint
                
                self.logger.info(f"Proof job submitted: {job_id[:8]}...")
                return job_id
                
            except requests.RequestException as e:
                last_error = str(e)
                self.logger.warning(f"Failed to reach {endpoint}: {e}")
                continue
        
        raise ProverError(f"All prover endpoints failed. Last error: {last_error}")
    
    def poll_result(self, job_id: str) -> Optional[ProofOutput]:
        """
        Poll for proof result.
        
        Args:
            job_id: Job ID from submit_proof
            
        Returns:
            ProofOutput if complete, None if still pending
            
        Raises:
            ProverError: If proof generation failed
        """
        url = f"{self.prover_url}/proof/{job_id}"
        
        try:
            response = self.session.get(url, timeout=10)
            data = response.json()
            
            status = data.get("status")
            
            if status == "pending":
                self.logger.debug(f"Job {job_id[:8]}... pending")
                return None
            
            if status == "in_progress":
                self.logger.debug(f"Job {job_id[:8]}... in progress")
                return None
            
            if status == "error":
                raise ProverError(f"Proof failed: {data.get('message')}")
            
            if status == "completed":
                result = data.get("result")
                if not result:
                    raise ProverError("Completed but no result")
                return ProofOutput.from_dict(result)
            
            self.logger.warning(f"Unknown status: {status}")
            return None
            
        except requests.RequestException as e:
            raise ProverError(f"Failed to poll result: {e}")
    
    def generate_proof(self, proof_input: ProofInput) -> ProofOutput:
        """
        Generate a proof (submit + poll until complete).
        
        Args:
            proof_input: Proof generation parameters
            
        Returns:
            Completed proof output
            
        Raises:
            ProverError: If proof generation fails or times out
        """
        job_id = self.submit_proof(proof_input)
        
        start_time = time.time()
        last_log = 0
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > self.timeout:
                raise ProverError(
                    f"Proof generation timed out after {self.timeout}s"
                )
            
            # Log progress every 30 seconds
            if elapsed - last_log >= 30:
                self.logger.info(
                    f"⏳ Waiting for proof... ({int(elapsed)}s elapsed)"
                )
                last_log = elapsed
            
            result = self.poll_result(job_id)
            if result is not None:
                self.logger.info(
                    f"✓ Proof generated in {int(elapsed)}s"
                )
                return result
            
            time.sleep(self.poll_interval)
    
    def check_health(self) -> bool:
        """Check if prover is reachable."""
        try:
            # Try a minimal POST to see if it responds
            response = self.session.post(
                f"{self.prover_url}/proof",
                json={},
                timeout=5,
            )
            # 400 = bad request (expected with empty body) = healthy
            # 405 = method not allowed = healthy  
            # 200/etc = also healthy
            return response.status_code in (200, 400, 405, 422)
        except Exception:
            return False


def create_prover_client(
    prover_url: str = None,
    timeout: int = 600,
) -> ProverClient:
    """
    Factory function to create a prover client.
    
    Args:
        prover_url: Optional custom prover URL
        timeout: Max seconds to wait for proof
        
    Returns:
        Configured ProverClient
    """
    return ProverClient(
        prover_url=prover_url,
        timeout=timeout,
    )

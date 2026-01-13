#!/usr/bin/env python3
"""
WORM Multi-Wallet Farming Script by Nullclairvoyant

Automated farming for WORM testnet on Sepolia.
Monitors BETH balances, burns ETH when needed, and participates in epochs.

Usage:
    python main.py                  # Run with default .env
    python main.py --env .env.prod  # Run with custom env file
    python main.py --dry-run        # Check config without running
    python main.py --once           # Run single cycle then exit
"""

import argparse
import sys
import warnings
from pathlib import Path

# Suppress urllib3 OpenSSL warning (LibreSSL compatibility)
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config, print_config_summary, ConfigError
from src.orchestrator import create_orchestrator
from src.blockchain import create_blockchain_client, BlockchainError
from src.utils.logger import setup_logger, get_logger


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="WORM Multi-Wallet Farming Script by Nullclairvoyant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    Run farming loop
  python main.py --dry-run          Validate config only
  python main.py --once             Run single cycle
  python main.py --env .env.test    Use different config
        """
    )
    
    parser.add_argument(
        "--env",
        type=str,
        default=".env",
        help="Path to .env configuration file (default: .env)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and exit without running"
    )
    
    parser.add_argument(
        "--once",
        action="store_true", 
        help="Run a single farming cycle then exit"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup initial logger
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logger(level=log_level)
    logger = get_logger()
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config(args.env)
        
        # Override log level if debug flag set
        if args.debug:
            config.log_level = "DEBUG"
        
        # Dry run - validate and show balances
        if args.dry_run:
            print_config_summary(config)
            
            try:
                blockchain = create_blockchain_client(config)
                
                # Show current epoch
                epoch, remaining = blockchain.get_epoch_info()
                total_beth, total_worm = blockchain.get_protocol_stats()
                
                logger.info("[bold]Protocol Status:[/bold]")
                
                # Epoch info
                if epoch is not None:
                    epoch_info = f"  • Current Epoch: [green]{epoch}[/green]"
                    if remaining:
                        mins, secs = divmod(remaining, 60)
                        logger.info(f"{epoch_info} ({mins}m {secs}s remaining)")
                    else:
                        logger.info(epoch_info)
                
                # Protocol totals
                if total_beth is not None:
                    logger.info(f"  • Total ETH Burned: [yellow]{total_beth:.4f} ETH[/yellow]")
                if total_worm is not None:
                    logger.info(f"  • Total WORM Minted: [magenta]{total_worm:.4f} WORM[/magenta]")
                
                logger.info("")
                
                # Show wallet balances
                logger.info("[bold]Wallet Balances (Sepolia):[/bold]")
                for wallet in config.wallets:
                    eth, beth, worm = blockchain.get_all_balances(wallet.address)
                    logger.info(
                        f"  • {wallet.short_address}: "
                        f"[yellow]{eth:.4f} ETH[/yellow] | "
                        f"[cyan]{beth:.4f} BETH[/cyan] | "
                        f"[magenta]{worm:.4f} WORM[/magenta]"
                    )
            except BlockchainError as e:
                logger.warning(f"  Could not fetch data: {e}")
            
            logger.info("")
            logger.info("[success]✓[/success] Configuration valid! Ready to run.")
            logger.info("Use 'python main.py' to start farming.")
            return 0
        
        # Create orchestrator
        orchestrator = create_orchestrator(config)
        
        # Single cycle mode
        if args.once:
            logger.info("Running single cycle mode...")
            orchestrator.run_cycle()
            logger.info("Single cycle complete.")
            return 0
        
        # Full farming loop
        orchestrator.run()
        return 0
        
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        logger.info("")
        logger.info("Please check your .env file. Copy from .env.example if needed:")
        logger.info("  cp .env.example .env")
        return 1
        
    except KeyboardInterrupt:
        logger.info("")
        logger.info("Interrupted by user")
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""
Structured logging with colors and optional file output.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# Custom theme for wallet-specific colors
WALLET_COLORS = ["cyan", "magenta", "yellow", "green", "blue"]

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green bold",
    "wallet.0": "cyan",
    "wallet.1": "magenta", 
    "wallet.2": "yellow",
    "wallet.3": "green",
    "wallet.4": "blue",
})

console = Console(theme=custom_theme)

# Global logger registry
_loggers: dict[str, logging.Logger] = {}


def setup_logger(
    name: str = "worm-farmer",
    level: str = "INFO",
    log_to_file: bool = False,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Set up a structured logger with rich console output.
    
    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_to_file: Whether to also log to file
        log_file: Path to log file
        
    Returns:
        Configured logger instance
    """
    if name in _loggers:
        return _loggers[name]
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    
    # Rich console handler
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
    )
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.addHandler(console_handler)
    
    # File handler with rotation (prevents disk exhaustion)
    if log_to_file and log_file:
        from logging.handlers import RotatingFileHandler
        
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 10MB max per file, keep 5 backup files
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)  # Always DEBUG for file
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    _loggers[name] = logger
    return logger


def get_logger(name: str = "worm-farmer") -> logging.Logger:
    """Get an existing logger or create a default one."""
    if name in _loggers:
        return _loggers[name]
    return setup_logger(name)


def get_wallet_logger(wallet_index: int, address: str) -> logging.Logger:
    """
    Get a logger for a specific wallet with colored prefix.
    
    Args:
        wallet_index: 0-based wallet index
        address: Wallet address (will be truncated)
        
    Returns:
        Logger configured for this wallet
    """
    short_addr = f"{address[:6]}...{address[-4:]}"
    logger_name = f"wallet-{wallet_index}-{short_addr}"
    
    if logger_name in _loggers:
        return _loggers[logger_name]
    
    # Get color for this wallet
    color = WALLET_COLORS[wallet_index % len(WALLET_COLORS)]
    
    # Create child logger from main logger
    main_logger = get_logger("worm-farmer")
    wallet_logger = main_logger.getChild(f"[{color}]{short_addr}[/{color}]")
    
    _loggers[logger_name] = wallet_logger
    return wallet_logger


def log_operation_start(logger: logging.Logger, operation: str, details: str = ""):
    """Log the start of an operation with visual separator."""
    logger.info(f"▶ [bold]{operation}[/bold] {details}")


def log_operation_end(logger: logging.Logger, operation: str, success: bool, duration: float):
    """Log the end of an operation with result."""
    status = "[success]✓[/success]" if success else "[error]✗[/error]"
    logger.info(f"{status} {operation} completed in {duration:.2f}s")


def log_balance(logger: logging.Logger, beth: float, eth: float):
    """Log wallet balances in a formatted way."""
    logger.info(f"💰 BETH: [cyan]{beth:.6f}[/cyan] | ETH: [yellow]{eth:.6f}[/yellow]")


def log_cycle_start(cycle_num: int, wallet_count: int):
    """Log the start of a farming cycle."""
    logger = get_logger()
    logger.info("")
    logger.info(f"{'═' * 50}")
    logger.info(f"🔄 [bold]CYCLE {cycle_num}[/bold] | {wallet_count} wallet(s) | {datetime.now().strftime('%H:%M:%S')}")
    logger.info(f"{'═' * 50}")


def log_cycle_end(cycle_num: int, duration: float, next_cycle_in: int):
    """Log the end of a farming cycle."""
    logger = get_logger()
    logger.info(f"{'─' * 50}")
    logger.info(f"✅ Cycle {cycle_num} complete in {duration:.1f}s | Next cycle in {next_cycle_in}s")
    logger.info("")

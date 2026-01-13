#!/bin/bash
# WORM Multi-Wallet Farmer Setup Script by Nullclairvoyant
# Works on: macOS, Linux, Windows (Git Bash/WSL), VPS

set -e

echo "🪱 WORM Multi-Wallet Farmer Initializing..."
echo "===================="

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)  OS="macos" ;;
        Linux*)   OS="linux" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *)        OS="unknown" ;;
    esac
    echo "Detected OS: $OS"
}

# Check Python
check_python() {
    echo ""
    echo "🐍 Checking Python..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "❌ Python not found!"
        echo ""
        case "$OS" in
            macos)
                echo "Install with: brew install python3"
                ;;
            linux)
                echo "Install with: sudo apt install python3 python3-venv python3-pip"
                ;;
            windows)
                echo "Download from: https://www.python.org/downloads/"
                ;;
        esac
        exit 1
    fi
    
    # Check version
    PY_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    echo "✓ Python found: $PY_VERSION"
}

# Create virtual environment
setup_venv() {
    echo ""
    echo "📦 Setting up virtual environment..."
    
    if [ -d "venv" ]; then
        echo "✓ Virtual environment exists"
    else
        $PYTHON_CMD -m venv venv
        echo "✓ Created virtual environment"
    fi
    
    # Activate
    if [ "$OS" = "windows" ]; then
        source venv/Scripts/activate
    else
        source venv/bin/activate
    fi
    echo "✓ Activated virtual environment"
}

# Install requirements
install_requirements() {
    echo ""
    echo "📥 Installing dependencies..."
    
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    
    echo "✓ Dependencies installed"
}

# Setup .env
setup_env() {
    echo ""
    if [ ! -f ".env" ]; then
        echo "📝 Creating .env from template..."
        cp .env.example .env
        chmod 600 .env  # SECURITY: Protect private keys
        echo "✓ Created .env file (permissions: 600)"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env with your settings:"
        echo "   - RPC_URL (Alchemy/Infura Sepolia endpoint)"
        echo "   - PK1 (Your wallet private key)"
        echo ""
    else
        # Ensure existing .env has secure permissions
        chmod 600 .env
        echo "✓ .env file exists (permissions secured)"
    fi
}

# Verify installation
verify() {
    echo ""
    echo "🔍 Verifying installation..."
    
    if $PYTHON_CMD -c "import web3, requests, dotenv, rich" 2>/dev/null; then
        echo "✓ All dependencies OK"
    else
        echo "❌ Some dependencies missing, reinstalling..."
        pip install -r requirements.txt
    fi
}

# Run dry-run
test_config() {
    echo ""
    echo "🧪 Testing configuration..."
    echo ""
    $PYTHON_CMD main.py --dry-run
}

# Main
main() {
    detect_os
    check_python
    setup_venv
    install_requirements
    setup_env
    verify
    
    echo ""
    echo "✅ Setup complete!"
    echo ""
    
    # Check if config is ready
    echo "🧪 Checking configuration..."
    echo ""
    
    if $PYTHON_CMD main.py --dry-run 2>&1 | grep -q "Configuration valid"; then
        echo ""
        echo "🚀 Starting WORM Miner..."
        echo ""
        $PYTHON_CMD main.py
    else
        echo ""
        echo "⚠️  Configuration incomplete!"
        echo ""
        echo "Please edit your .env file:"
        echo "  nano .env"
        echo ""
        echo "Required settings:"
        echo "  RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY"
        echo "  PK1=your_private_key_here"
        echo "  PROVER_URL=https://worm-miner-3.darkube.app"
        echo ""
        echo "Then run:"
        echo "  source venv/bin/activate"
        echo "  python main.py"
        echo ""
    fi
}

main "$@"

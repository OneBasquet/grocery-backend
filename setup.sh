#!/bin/bash
# Setup script for Grocery Price Comparison Engine

echo "🛒 Grocery Price Comparison Engine - Setup"
echo "=========================================="
echo ""

# Check if conda is available
if command -v conda &> /dev/null; then
    echo "✓ Conda detected"
    echo ""
    echo "Creating conda environment..."
    conda env create -f environment.yml
    echo ""
    echo "To activate the environment, run:"
    echo "  conda activate grocery-backend"
else
    echo "ℹ Conda not found, using pip..."
    echo ""
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    echo "Activating virtual environment..."
    source venv/bin/activate
    
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

echo ""
echo "Installing Playwright browsers..."
playwright install chromium

echo ""
echo "=========================================="
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Create a .env file with your APIFY_API_TOKEN"
echo "2. Run: python main.py stats"
echo "3. Start scraping: python main.py scrape --query 'milk'"
echo ""
echo "For more information, see QUICKSTART.md"
echo "=========================================="

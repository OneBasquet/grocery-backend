"""
Configuration settings for the grocery backend application.
Loads environment variables from .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# Apify Configuration
APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN', '')

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', '')

# API Configuration
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 8000))

# Debug Mode
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

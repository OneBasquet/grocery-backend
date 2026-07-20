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


def _load_secret(secret_name: str, env_fallback: str) -> str:
    """Read a secret from AWS Secrets Manager, falling back to a local env var.

    Lets production (EC2 + IAM role) source secrets from Secrets Manager while
    local dev keeps using .env, without any code branching at the call site.
    """
    try:
        import boto3
        client = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        return client.get_secret_value(SecretId=secret_name)['SecretString']
    except Exception:
        return os.getenv(env_fallback, '')


# Pepesto Catalog API Configuration
PEPESTO_API_KEY = _load_secret('onebasqet/pepesto-api-key', 'PEPESTO_API_KEY')

# API Configuration
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 8000))

# Debug Mode
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

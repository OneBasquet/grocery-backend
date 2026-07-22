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


def _load_ssm_param(name: str, env_fallback: str) -> str:
    """Read a secret from SSM Parameter Store, falling back to a local env var.

    Lets production (EC2 + IAM role) source secrets from Parameter Store while
    local dev keeps using .env, without any code branching at the call site.
    SSM Parameter Store (unlike Secrets Manager) has no per-parameter charge,
    matching the pattern already used for admin_api_key/db_password.
    """
    try:
        import boto3
        client = boto3.client('ssm', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        return client.get_parameter(Name=name, WithDecryption=True)['Parameter']['Value']
    except Exception:
        return os.getenv(env_fallback, '')


# Pepesto Catalog API Configuration
PEPESTO_API_KEY = _load_ssm_param('/onebasqet/pepesto_api_key', 'PEPESTO_API_KEY')

# API Configuration
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 8000))

# Debug Mode
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

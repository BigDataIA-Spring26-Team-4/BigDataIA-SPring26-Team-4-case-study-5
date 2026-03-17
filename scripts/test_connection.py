"""
Test Snowflake connection and account format.

This script helps verify your Snowflake credentials and account identifier.
"""

import sys
from pathlib import Path
from urllib.parse import quote_plus

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
import structlog

log = structlog.get_logger(__name__)


def test_connection():
    """Test Snowflake connection with current credentials."""
    print("=" * 70)
    print("Testing Snowflake Connection")
    print("=" * 70)
    
    print(f"\n📋 Configuration:")
    print(f"   Account: {settings.SNOWFLAKE_ACCOUNT}")
    print(f"   User: {settings.SNOWFLAKE_USER}")
    print(f"   Database: {settings.SNOWFLAKE_DATABASE}")
    print(f"   Schema: {settings.SNOWFLAKE_SCHEMA}")
    print(f"   Warehouse: {settings.SNOWFLAKE_WAREHOUSE}")
    print(f"   Role: {settings.SNOWFLAKE_ROLE or 'Not specified'}")
    
    print(f"\n🔗 Connection String:")
    # Build the same connection string as the service (with URL encoding)
    password_value = settings.SNOWFLAKE_PASSWORD.get_secret_value()
    conn_str = (
        f"snowflake://{quote_plus(settings.SNOWFLAKE_USER)}:"
        f"{quote_plus(password_value)}@"
        f"{settings.SNOWFLAKE_ACCOUNT}/"
        f"{settings.SNOWFLAKE_DATABASE}/"
        f"{settings.SNOWFLAKE_SCHEMA}"
        f"?warehouse={settings.SNOWFLAKE_WAREHOUSE}"
    )
    if settings.SNOWFLAKE_ROLE:
        conn_str += f"&role={settings.SNOWFLAKE_ROLE}"
    
    # Print connection string with password masked
    safe_conn_str = conn_str.replace(quote_plus(password_value), "***")
    print(f"   {safe_conn_str}")
    print(f"   (Password special characters are URL-encoded)")
    
    print(f"\n🧪 Testing connection...")
    
    try:
        from app.services.snowflake import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT CURRENT_VERSION(), CURRENT_ACCOUNT()"))
            version, account = result.fetchone()
            
            print(f"\n✅ Connection successful!")
            print(f"   Snowflake Version: {version}")
            print(f"   Connected Account: {account}")
            
            # Test warehouse
            result = conn.execute(text("SELECT CURRENT_WAREHOUSE()"))
            warehouse = result.fetchone()[0]
            print(f"   Current Warehouse: {warehouse}")
            
            # Test database access
            result = conn.execute(text("SELECT CURRENT_DATABASE()"))
            database = result.fetchone()[0]
            print(f"   Current Database: {database}")
            
            print(f"\n✅ All checks passed!")
            return True
            
    except Exception as e:
        print(f"\n❌ Connection failed!")
        print(f"   Error: {str(e)}")
        
        print(f"\n💡 Troubleshooting Tips:")
        print(f"   1. Check if your account format is correct")
        print(f"      • Should be: account_name.region (e.g., xy12345.us-east-1)")
        print(f"      • Or: account_name-locator (e.g., xy12345-ab12345)")
        print(f"      • Your current: {settings.SNOWFLAKE_ACCOUNT}")
        print(f"\n   2. Verify credentials are correct")
        print(f"   3. Check if warehouse is running in Snowflake console")
        print(f"   4. Ensure your IP is whitelisted (if network policy exists)")
        
        return False


def suggest_account_formats():
    """Suggest possible account formats."""
    current = settings.SNOWFLAKE_ACCOUNT
    
    print(f"\n💡 If connection failed, try these account formats in .env:")
    print(f"\n   Current: {current}")
    print(f"\n   Common formats to try:")
    
    # Remove any existing suffixes to get base
    base = current.split('.')[0]
    
    print(f"   1. {base}  (account locator only)")
    print(f"   2. {base}.us-east-1  (with region)")
    print(f"   3. {base}.us-east-1.aws  (with region and cloud)")
    print(f"   4. {base}-XXXXX  (if you have an account locator)")
    
    print(f"\n   🔍 To find your EXACT account identifier:")
    print(f"   1. Log into Snowflake web console")
    print(f"   2. Look at the URL: https://[account].snowflakecomputing.com")
    print(f"   3. The [account] part is EXACTLY what you need")
    print(f"   4. Copy it EXACTLY (including any dashes or dots)")
    print(f"\n   Example URLs:")
    print(f"   • https://xy12345.snowflakecomputing.com → use: xy12345")
    print(f"   • https://xy12345.us-east-1.snowflakecomputing.com → use: xy12345.us-east-1")
    print(f"   • https://orgname-accountname.snowflakecomputing.com → use: orgname-accountname")


if __name__ == "__main__":
    success = test_connection()
    
    if not success:
        suggest_account_formats()
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("✅ Ready to proceed with database initialization!")
    print("=" * 70)
    sys.exit(0)

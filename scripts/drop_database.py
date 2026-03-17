"""
Drop and recreate database for PE Org-AI-R Platform.

⚠️  WARNING: This will DELETE all data in the database!
Only use this when you need to recreate the schema.

Safe to use in development/testing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.services.snowflake import engine
from sqlalchemy import text
import structlog

log = structlog.get_logger(__name__)


def confirm_drop():
    """Ask for confirmation before dropping database."""
    print("=" * 70)
    print("⚠️  WARNING: DROP DATABASE")
    print("=" * 70)
    print(f"\nThis will DELETE the following:")
    print(f"   • Database: {settings.SNOWFLAKE_DATABASE}")
    print(f"   • Schema: {settings.SNOWFLAKE_SCHEMA}")
    print(f"   • All tables and data")
    
    print(f"\n⚠️  This action CANNOT be undone!")
    
    response = input(f"\nType 'YES' to confirm: ")
    return response.strip().upper() == "YES"


def drop_database():
    """Drop the database and schema."""
    
    if not confirm_drop():
        print("\n❌ Operation cancelled.")
        return False
    
    print(f"\n🔨 Dropping database...")
    
    try:
        with engine.connect() as conn:
            # Drop database (this drops everything inside it)
            sql = f"DROP DATABASE IF EXISTS {settings.SNOWFLAKE_DATABASE}"
            conn.execute(text(sql))
            conn.commit()
            
            print(f"   ✅ Database '{settings.SNOWFLAKE_DATABASE}' dropped")
            
        print(f"\n" + "=" * 70)
        print("✅ Database dropped successfully!")
        print("=" * 70)
        
        print(f"\n📋 Next Steps:")
        print(f"   1. Run: python scripts/init_db.py")
        print(f"   2. Run: python scripts/create_test_data.py")
        print(f"   3. Test API in Swagger")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Failed to drop database: {str(e)}")
        return False


if __name__ == "__main__":
    success = drop_database()
    sys.exit(0 if success else 1)

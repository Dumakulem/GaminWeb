import os
import psycopg2
from urllib.parse import urlparse
import json

# --- Database Configuration ---
# This URL will come from Streamlit Secrets in deployment
# For local testing, you can temporarily put your Supabase URL here
# or ensure it's in your local .env file
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # This warning helps ensure you've set up the DATABASE_URL in your environment
    # or Streamlit Secrets.
    print("WARNING: DATABASE_URL environment variable is not set. "
          "Ensure it's set for deployment (e.g., in Streamlit Secrets) "
          "or in your local .env for local testing.")

def _get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set. "
                         "Cannot establish database connection.")

    # Parse the connection URL
    url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=url.path[1:],  # Remove leading '/' from database name
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
        # sslmode='require' # Uncomment this line if your cloud provider requires SSL/TLS,
                            # which Supabase generally handles implicitly with its URL
    )
    return conn

def init_db():
    """Initializes the database schema if the user_facts table doesn't exist."""
    conn = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_facts (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, key)
            );
        ''')
        conn.commit()
        print("Database initialized or 'user_facts' table already exists.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        # Depending on the error (e.g., connection issue), you might want to re-raise
        # for clearer debugging in development. For production, consider logging.
        # raise # Uncomment to re-raise the exception during development
    finally:
        if conn:
            conn.close()

def update_user_fact(user_id: str, key: str, value: str):
    """Inserts or updates a user fact in the database."""
    conn = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_facts (user_id, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, key) DO UPDATE SET
                value = EXCLUDED.value,
                timestamp = CURRENT_TIMESTAMP;
        ''', (user_id, key, value))
        conn.commit()
    except Exception as e:
        print(f"Error updating/inserting fact for user '{user_id}', key '{key}': {e}")
        # raise
    finally:
        if conn:
            conn.close()

def get_user_facts(user_id: str) -> dict:
    """Retrieves all facts for a specific user from the database."""
    conn = None
    facts = {}
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM user_facts WHERE user_id = %s;', (user_id,))
        facts = {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        print(f"Error retrieving facts for user '{user_id}': {e}")
        # raise
    finally:
        if conn:
            conn.close()
    return facts

def get_all_user_facts() -> dict:
    """Retrieves all facts for all users, structured by user_id, from the database."""
    conn = None
    all_facts = {}
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, key, value FROM user_facts ORDER BY user_id, key;')
        for user_id, key, value in cursor.fetchall():
            if user_id not in all_facts:
                all_facts[user_id] = {}
            all_facts[user_id][key] = value
    except Exception as e:
        print(f"Error retrieving all user facts: {e}")
        # raise
    finally:
        if conn:
            conn.close()
    return all_facts

def purge_data_by_key(user_id_to_purge: str):
    """Removes all data associated with a specific user_id from the database."""
    conn = None
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_facts WHERE user_id = %s', (user_id_to_purge,))
        conn.commit()
        print(f"DEBUG: Purged all data for User ID: '{user_id_to_purge}' from the database.")
    except Exception as e:
        print(f"Error purging data for User ID '{user_id_to_purge}': {e}")
        # raise
    finally:
        if conn:
            conn.close()

# IMPORTANT: Call init_db() to ensure the table exists when the module is imported.
# This will run automatically when your Streamlit app starts up.
init_db()
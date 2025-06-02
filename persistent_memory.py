# persistent_memory.py
import sqlite3
import json
import os # NEW: Import the os module

DATABASE_NAME = 'gamin_user_data.db'

def _get_db_connection():
    db_path = os.path.abspath(DATABASE_NAME) # NEW: Get the absolute path
    print(f"DEBUG: Connecting to database at: {db_path}") # NEW: Print the path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # Allows access by column name for easier retrieval
    return conn

def initialize_db():
    conn = _get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_facts (
            user_id TEXT PRIMARY KEY,
            facts TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Database '{DATABASE_NAME}' initialized or already exists.")

def get_user_facts(user_id: str) -> dict:
    conn = _get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT facts FROM user_facts WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row['facts'])
    return {}

def update_user_fact(user_id: str, key: str, value: str):
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # Get existing facts or initialize an empty dictionary
    existing_facts = get_user_facts(user_id)
    existing_facts[key] = value # Update or add the new fact
    
    facts_json = json.dumps(existing_facts)
    
    cursor.execute(
        'INSERT OR REPLACE INTO user_facts (user_id, facts) VALUES (?, ?)',
        (user_id, facts_json)
    )
    conn.commit()
    conn.close()

def get_all_user_facts():
    """Retrieves all user facts from the database."""
    conn = _get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, facts FROM user_facts')
    rows = cursor.fetchall()
    conn.close()

    all_facts = {}
    for row in rows:
        user_id = row['user_id']
        facts_json = row['facts']
        try:
            facts = json.loads(facts_json)
            all_facts[user_id] = facts
        except json.JSONDecodeError:
            print(f"Warning: Could not decode facts for user_id {user_id}: {facts_json}")
            all_facts[user_id] = {} # Return empty dict for corrupted data
    return all_facts

# NEW FUNCTION: Purge data by a specific key (e.g., 'Sakyu', 'Kusa', or a Discord ID)
def purge_data_by_key(key_to_purge: str):
    """Removes all data associated with a specific key (user_id) from the database."""
    conn = _get_db_connection() # This will now print the path
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_facts WHERE user_id = ?', (key_to_purge,))
    conn.commit()
    conn.close()
    print(f"DEBUG: Purged all data for key '{key_to_purge}' from the database.")
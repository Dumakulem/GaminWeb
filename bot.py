import os
import discord
from dotenv import load_dotenv
import re
import io
import sqlite3
import json

from ai_logic import chat_chain
from langchain_core.messages import BaseMessage

# Import the necessary functions from persistent_memory
from persistent_memory import update_user_fact, get_all_user_facts, get_user_facts, purge_data_by_key


DATABASE_NAME = 'gamin_user_data.db'


# IMPORTANT: _get_db_connection() should NOT be defined here.
# It should only be in persistent_memory.py if purge_data_by_key relies on it there.
# It's been removed from this bot.py script.


# Load environment variables from .env file at the very beginning
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"{client.user} is now online!")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.webhook_id is not None or message.is_system():
        return

    query = None
    user_id = str(message.author.id)
    username = message.author.display_name  # Use display_name for server nicknames

    replied_to_gamin_content = None

    is_reply_to_bot = False
    if message.reference:
        try:
            replied_message = message.reference.resolved
            if not replied_message:
                replied_message = await message.channel.fetch_message(message.reference.message_id)

            if replied_message and replied_message.author == client.user:
                is_reply_to_bot = True
                query = message.content.strip()
                replied_to_gamin_content = replied_message.content
        except discord.NotFound:
            print("DEBUG: Replied message not found (likely deleted).")
            pass
        except Exception as e:
            print(f"Error resolving replied message: {e}")

    if not is_reply_to_bot and message.content.lower().startswith("-gamin "):
        query = message.content[len("-gamin "):].strip()

    if query:
        thinking_msg = await message.channel.send("nyakking...")

        try:
            # Check for specific DB dump command from the Father (Kusa)
            KUSA_USER_ID = "1252611124751503362"

            # DEBUG: Lines for general command parsing
            print(f"DEBUG: Message from user: '{message.content}'")
            print(f"DEBUG: Parsed query (after -gamin removal): '{query}'")
            print(f"DEBUG: User ID: '{user_id}' (KUSA_USER_ID: '{KUSA_USER_ID}')")


            # Define a list of acceptable commands for Father to dump DB
            db_commands = [
                "show me the db",
                "show the db",
                "show me the database",
                "show the database",
                "show me the db currently",
                "show the db currently",
                "show me the database currently",
                "show the database currently",
                "show db",
                "show database",
            ]
            if user_id == KUSA_USER_ID and any(cmd in query.lower() for cmd in db_commands):
                await thinking_msg.delete()  # Delete "nyakking" before giving the DB
                try:
                    all_facts = get_all_user_facts()  # Call the new function
                    print(f"DEBUG: Raw facts from DB (get_all_user_facts): {all_facts}") # NEW: Print raw data

                    if all_facts:
                        response_parts = ["Okay, Father. Here's the current user fact database:"]
                        for db_key, facts in all_facts.items():
                            # Attempt to fetch username from Discord if possible (only for actual user IDs)
                            username_for_db = db_key # Default to the database key itself
                            if db_key.isdigit(): # Check if it's a potential Discord user ID
                                try:
                                    user_obj = await client.fetch_user(int(db_key))
                                    username_for_db = user_obj.display_name  # Use display_name for server nicknames
                                except discord.NotFound:
                                    username_for_db = f"Unknown User (ID: {db_key})"
                                except Exception as u_e:
                                    username_for_db = f"Error fetching name (ID: {db_key})"
                                    print(f"Warning: Could not fetch username for {db_key}: {u_e}")

                            fact_strings = [f"{k}: {v}" for k, v in facts.items()]
                            response_parts.append(f"**{username_for_db}**: {'; '.join(fact_strings)}")

                        final_db_reply = "\n".join(response_parts)

                        # Handle Discord's 2000 character message limit
                        if len(final_db_reply) > 1900:  # Give some buffer
                            with io.StringIO() as f:
                                f.write(final_db_reply)
                                f.seek(0)
                                await message.channel.send(
                                    "Okay, Father. Here's the database content (it's too long for one message, so sending as a file):",
                                    file=discord.File(f, filename="gamin_db_dump.txt"),
                                )
                        else:
                            await message.reply(final_db_reply, mention_author=True)
                    else:
                        await message.reply("Okay, Father. The database is currently empty. No user facts stored yet.", mention_author=True)

                    return  # EXIT: Stop processing here, the DB request is handled
                except Exception as e:
                    print(f"ERROR: Failed to retrieve or send DB dump for Father: {e}")
                    await message.reply("ERROR: Failed to retrieve database content. Please check my console logs.", mention_author=True)
                    return  # EXIT: Stop processing here

            # --- Purge command from Father ---
            purge_commands = [
                "purge db about",
                "purge database about",
                "purge db for",
                "purge database for",
                "delete db about",
                "delete database about",
                "delete db for",
                "delete database for",
            ]
            if user_id == KUSA_USER_ID and any(cmd in query.lower() for cmd in purge_commands):
                target_key = None
                for cmd in purge_commands:
                    # Check if the command is in the query (case-insensitive for command prefix)
                    if cmd in query.lower():
                        # Extract the key, preserving its original casing
                        target_key = query[len(cmd):].strip()
                        break

                if target_key:
                    print(f"DEBUG: Attempting to purge data for exact key: '{target_key}'")
                    try:
                        purge_data_by_key(target_key)
                        await thinking_msg.delete()
                        await message.reply(
                            f"Okay, Father. Purged all data for '{target_key}' from the database.",
                            mention_author=True,
                        )
                        return  # EXIT: Stop processing here, the purge request is handled
                    except Exception as purge_e:
                        print(f"ERROR: Failed to purge data for key '{target_key}': {purge_e}")
                        await thinking_msg.delete()
                        await message.reply("ERROR: Failed to purge data. Please check my console logs.", mention_author=True)
                        return  # EXIT
                else:
                    await thinking_msg.delete()
                    await message.reply("Okay, Father. Please specify which key's data should be purged.", mention_author=True)
                    return  # EXIT
            # --- END Purge Command ---


            # --- Continue to LLM invocation if not a DB dump or purge request from Father ---
            llm_input_parts = []

            # --- Retrieve and add current user's facts to the LLM input ---
            current_user_facts = get_user_facts(user_id)
            if current_user_facts:
                fact_strings = [f"{k}: {v}" for k, v in current_user_facts.items()]
                # Prepend this as a system-like instruction/context for the LLM
                llm_input_parts.append(f"Gamin, you have these known facts about the current user, {username}: {'; '.join(fact_strings)}")
            # --- END NEW CODE ---

            if replied_to_gamin_content:
                llm_input_parts.append(f"(In reply to Gamin's message: '{replied_to_gamin_content}')")

            llm_input_parts.append(f"{username} (ID: {user_id}): {query}")

            llm_input = "\n".join(llm_input_parts)

            print(f"DEBUG: LLM Input: {llm_input}")

            raw_response = chat_chain.invoke(
                {"input": llm_input},
                config={"configurable": {"session_id": user_id}},
            )

            final_reply = "An unexpected response format was received."
            if isinstance(raw_response, BaseMessage):
                final_reply = raw_response.content
            elif isinstance(raw_response, dict) and "output" in raw_response:
                output_val = raw_response["output"]
                if isinstance(output_val, BaseMessage):
                    final_reply = output_val.content
                else:
                    final_reply = str(output_val)
            else:
                final_reply = str(raw_response)

            memory_pattern = re.compile(r'\[REMEMBER:\s*([^=]+?)\s*=\s*(.+?)\]')
            match = memory_pattern.search(final_reply)

            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()

                if key and value:
                    try:
                        update_user_fact(user_id, key, value)
                        print(f"DEBUG: Stored fact for {username} ({user_id}): {key} = {value}")
                        final_reply = final_reply.replace(match.group(0), '').strip()
                        final_reply = final_reply.strip()
                    except Exception as mem_e:
                        print(f"ERROR: Error saving memory for user {user_id}: {mem_e}")
                else:
                    print(f"WARNING: Parsed empty key or value from REMEMBER tag for user {user_id}. Key='{key}', Value='{value}'")

            print(f"DEBUG: Final reply to send: {final_reply}")

            if final_reply:
                await message.reply(final_reply, mention_author=True)
            else:
                await message.channel.send("❌ Error: I couldn't generate a meaningful response.")

        except Exception as e:
            print(f"ERROR: An error occurred during LLM invocation for user {username} (ID: {user_id}): {e}")
            await message.channel.send(f"❌ Error: An unexpected error occurred. Please try again later. ({e})")
        finally:
            try:
                await thinking_msg.delete()
            except discord.NotFound:
                pass


client.run(os.getenv("DISCORD_TOKEN")) # Ensure this matches your .env file
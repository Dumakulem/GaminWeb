import streamlit as st
import os
from dotenv import load_dotenv
import re
import io
import json

# --- ADDED DEBUG PRINT STATEMENTS HERE ---
print("--- Streamlit App Startup Debug ---")
print(f"Current Working Directory: {os.getcwd()}")
print(f"Contents of current directory: {os.listdir(os.getcwd())}")
# Check if .env file exists locally (this won't be on Streamlit Cloud if gitignored)
if os.path.exists(".env"):
    print(".env file found locally.")
else:
    print(".env file NOT found locally (expected on cloud).")

print("Checking DATABASE_URL loading from environment...")
# This is the critical line: it shows what os.getenv('DATABASE_URL') returns
print(f"DATABASE_URL value: {os.getenv('DATABASE_URL')}")
print("Finished checking DATABASE_URL.")
print("--- End Debug ---")
# --- END OF DEBUG PRINT STATEMENTS ---


# Import core AI and memory logic
# UPDATED: Import extract_and_store_facts from ai_logic
from ai_logic import chat_chain, extract_and_store_facts
from langchain_core.messages import BaseMessage
from persistent_memory import update_user_fact, get_all_user_facts, get_user_facts, purge_data_by_key # Ensure purge_data_by_key is imported

# --- Configuration ---
load_dotenv() # This loads .env ONLY LOCALLY, not on Streamlit Cloud where secrets are used.

GAMIN_AVATAR = "Avatar/Gamin.webp"
USER_AVATAR = "Avatar/gatto.jpg"

# --- Streamlit App UI ---
st.set_page_config(page_title="Gamin~", page_icon="🐾")

st.title(" Gamin<3 ")
st.write("HIII ako si gamin~.")

# --- User Identification Logic ---
if "user_identified" not in st.session_state:
    st.session_state.user_identified = False
    st.session_state.current_user_name = None
    st.session_state.current_user_id = None
    st.session_state.messages = []

if not st.session_state.user_identified:
    st.info("Hii sino ka dito sa dalawa?")
    user_choice = st.radio("ikaw ba si...", ("Emil (Father)", "Neri (Mom)"))

    if user_choice == "Emil (Father)":
        password_input = st.text_input("Enter password for Emil (Father):", type="password")
        if st.button("Confirm Identity"):
            if password_input == "gamin123":
                st.session_state.current_user_name = "Emil"
                st.session_state.current_user_id = "emil_dad_unique_id"
                st.session_state.user_identified = True
                st.session_state.messages.append({"role": "assistant", "content": f"Hi father~"})
                st.rerun()
            else:
                st.error("Incorrect password for Emil (Father).")
    elif user_choice == "Neri (Mom)":
        if st.button("Confirm Identity"):
            st.session_state.current_user_name = "Neri"
            st.session_state.current_user_id = "neri_mom_unique_id"
            st.session_state.user_identified = True
            st.session_state.messages.append({"role": "assistant", "content": f"HIII MOMMM what can i do for you?"})
            st.rerun()
else: # User is identified, proceed with chat
    # --- Display Chat Messages ---
    # THIS IS THE PRIMARY LOOP FOR DISPLAYING ALL MESSAGES
    for message in st.session_state.messages:
        avatar_path = GAMIN_AVATAR if message["role"] == "assistant" else USER_AVATAR
        with st.chat_message(message["role"], avatar=avatar_path):
            st.markdown(message["content"])

    # --- Core AI Interaction Function ---
    def get_gamin_response(user_query: str, user_id: str, username: str) -> str:
        """
        Processes a user query using the Gemini 1.5 model and handles memory.
        """
        llm_input_parts = []

        llm_input_parts.append(f"{username} (ID: {user_id}): {user_query}")
        llm_input = "\n".join(llm_input_parts)

        print(f"DEBUG: LLM Input: {llm_input}")

        try:
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

            print(f"DEBUG: Final reply from Gamin: {final_reply}")
            return final_reply

        except Exception as e:
            print(f"ERROR: An error occurred during LLM invocation for user {username} (ID: {user_id}): {e}")
            return f"❌ Error: An unexpected error occurred. Please try again later. ({e})"

    # --- Accept User Input ---
    if prompt := st.chat_input("Talk to Gamin..."):
        user_id = st.session_state.current_user_id
        username = st.session_state.current_user_name

        # Add user's message to chat history immediately and display it
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(prompt)

        # Call the information extraction logic FIRST
        extract_and_store_facts(prompt, user_id, username)

        ai_response = "" # Initialize ai_response

        # Create a temporary placeholder for Gamin's response while thinking/processing
        # This will show the spinner and then the actual message
        with st.chat_message("assistant", avatar=GAMIN_AVATAR):
            message_placeholder = st.empty() # Create an empty container that can be updated

            # Logic: Intercept "show db" command for Emil
            if username == "Emil" and ("show" in prompt.lower() and ("db" in prompt.lower() or "database" in prompt.lower())):
                message_placeholder.write("Father's command detected: Retrieving database information...")

                print("DEBUG (app.py): Calling get_all_user_facts()")
                all_facts = get_all_user_facts()
                print(f"DEBUG (app.py): get_all_user_facts() returned: {all_facts}")

                if all_facts:
                    db_output = "### Database Contents:\n\n"
                    for u_id, facts in all_facts.items():
                        db_output += f"**User ID:** `{u_id}`\n"
                        if facts:
                            for key, value_str in facts.items():
                                try:
                                    parsed_value = json.loads(value_str)
                                    db_output += f"- `{key}`: `{json.dumps(parsed_value, indent=2)}`\n"
                                except json.JSONDecodeError:
                                    db_output += f"- `{key}`: `{value_str}`\n"
                        else:
                            db_output += "- No facts stored for this user.\n"
                        db_output += "\n"
                    ai_response = db_output
                    print(f"DEBUG (app.py): db_output generated (first 200 chars): {ai_response[:200]}...")
                else:
                    ai_response = "It looks like the database is empty, father. Nothing to show."
                    print("DEBUG (app.py): Database reported as empty from get_all_user_facts().")
                print(f"DEBUG (app.py): Final ai_response for DB command: {ai_response[:100]}...")

                # Update the placeholder with the final DB output
                message_placeholder.markdown(ai_response)

            else: # Normal conversation, pass to LLM
                # Use the placeholder to show spinner while getting AI response
                with message_placeholder.container(): # Create a temporary container inside the placeholder
                    with st.spinner("Gamin's nyakking..."):
                        ai_response = get_gamin_response(prompt, user_id, username)
                # After spinner, update the placeholder with the actual AI response
                message_placeholder.markdown(ai_response)

        # Add the final response to session state for persistence across reruns
        st.session_state.messages.append({"role": "assistant", "content": ai_response})
        st.rerun() # Force a rerun to update the chat history with the new message

    # --- Control Buttons ---
    col1, col2 = st.columns([0.5, 0.5])

    with col1:
        if st.button("Clear Chat"):
            st.session_state.messages = [{"role": "assistant", "content": f"Hello {st.session_state.current_user_name}! How can I help you today?"}]
            # To also clear the *persistent memory* in the database for this specific user, uncomment the line below if desired
            # purge_data_by_key(st.session_state.current_user_id)
            st.rerun()

    with col2:
        if st.button("Switch User"):
            st.session_state.user_identified = False
            st.session_state.current_user_name = None
            st.session_state.current_user_id = None
            st.session_state.messages = []
            st.rerun()

    # --- Emil's Admin Tools (visible only to Emil, now with a toggle) ---
    if st.session_state.current_user_name == "Emil":
        st.markdown("---") # Separator for visual clarity

        # Initialize toggle state if not already present
        if "show_admin_tools" not in st.session_state:
            st.session_state.show_admin_tools = False

        # Toggle switch for Admin Tools
        st.session_state.show_admin_tools = st.toggle(
            "Show Admin Tools",
            value=st.session_state.show_admin_tools,
            help="Toggle to show/hide administrative tools for managing Gamin's data."
        )

        if st.session_state.show_admin_tools:
            st.subheader("Emil's Admin Tools")

            purge_user_id = st.text_input("User ID to Purge:")

            if st.button(f"Purge Data for '{purge_user_id}'", help="Permanently delete all facts associated with this User ID from the database."):
                if purge_user_id:
                    try:
                        purge_data_by_key(purge_user_id)
                        st.success(f"Successfully purged all data for User ID: `{purge_user_id}`.")
                        st.session_state.messages.append({"role": "assistant", "content": f"Father, I have purged all data for User ID: `{purge_user_id}`. You can now type 'show me the db' to verify."})
                    except Exception as e:
                        st.error(f"Error purging data: {e}")
                    st.rerun()
                else:
                     st.warning("Please enter a User ID to purge before clicking the button.")
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import JsonOutputParser # NEW
from langchain_core.pydantic_v1 import BaseModel, Field # NEW
import os
import json # NEW - for pretty printing debug

from bot_prompts import gamin_chat_prompt # Assuming gamin_chat_prompt is a ChatPromptTemplate
from persistent_memory import get_user_facts, update_user_fact # NEW: Import update_user_fact

# --- NEW: Pydantic Models for Information Extraction ---
# These models define the structure of the JSON output we want from the LLM.
# You can add more models or fields based on the "keys" we discussed.

class UserPersonality(BaseModel):
    """Extracted personality traits and communication style from user's conversation."""
    adjectives: list[str] = Field(description="List of adjectives describing the user's personality or communication style.", default_factory=list)
    humor_type: str | None = Field(description="Type of humor the user typically uses (e.g., 'sarcastic', 'dad jokes', 'dry humor').", default=None)

class UserPreferences(BaseModel):
    """Extracted preferences or dislikes from user's conversation."""
    food_preference: str | None = Field(description="User's stated favorite food.", default=None)
    drink_preference: str | None = Field(description="User's stated favorite drink.", default=None)
    hobby: str | None = Field(description="User's stated hobby or pastime.", default=None)
    dislikes: list[str] = Field(description="List of things the user explicitly dislikes.", default_factory=list)
    music_genre: str | None = Field(description="User's preferred music genre.", default=None)

class UserEmotion(BaseModel):
    """Extracted emotional state or tendency from user's conversation."""
    current_mood: str | None = Field(description="The user's current or recently expressed emotional state (e.g., 'happy', 'stressed', 'tired', 'excited').", default=None)
    emotional_tendency: str | None = Field(description="User's general emotional disposition (e.g., 'generally positive', 'prone to anxiety').", default=None)

class UserGeneralInfo(BaseModel):
    """General identifying information about the user."""
    name: str | None = Field(description="The user's actual name, if mentioned and not the system username.", default=None)
    location: str | None = Field(description="The user's city or region, if mentioned.", default=None)
    pet_name: str | None = Field(description="The name of the user's pet, if mentioned.", default=None)
    occupation: str | None = Field(description="The user's occupation or field of work, if mentioned.", default=None)

# Combine all extraction schemas into a single dictionary
# The LLM will output JSON that matches one of these schemas.
# We'll then iterate through them to find what was extracted.
all_extraction_schemas = {
    "personality": UserPersonality,
    "preferences": UserPreferences,
    "emotion": UserEmotion,
    "general_info": UserGeneralInfo
}

# --- END NEW Pydantic Models ---


llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.7, # Lower temperature for more consistent extraction
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

message_histories = {}

def get_session_history(session_id: str) -> ChatMessageHistory:
    if session_id not in message_histories:
        message_histories[session_id] = ChatMessageHistory()
    return message_histories[session_id]

# --- NEW: Function to prepare extraction prompt for LLM ---
def _prepare_extraction_prompt_content(input_val: dict, config: dict) -> str:
    """Prepares the system message for the information extraction LLM."""
    user_input = input_val.get("input", "")
    username = input_val.get("username", "user") # Get username from input_val

    # Create a dynamic prompt based on all_extraction_schemas
    schema_instructions = "\n".join([
        f"- **{name}**: {model.schema_json(indent=2)}"
        for name, model in all_extraction_schemas.items()
    ])

    return (
        "You are an expert information extractor. Your task is to identify and extract specific details "
        "from the user's message. Only extract information that is explicitly stated or strongly implied. "
        "Do not invent information. If a piece of information is not present, omit that field or return an empty list/null.\n\n"
        "Output the extracted information in a single JSON object. The JSON object should have top-level keys "
        "corresponding to the schema names below (e.g., 'personality', 'preferences', 'emotion', 'general_info'). "
        "Each top-level key should contain a JSON object conforming to its respective schema. "
        "If no information is found for a specific schema, its top-level key should contain an empty object (`{}`).\n\n"
        "Here are the schemas you can extract:\n"
        f"{schema_instructions}\n\n"
        "Carefully analyze the user's message and extract all relevant information into the combined JSON format. "
        f"User's message from {username}: {user_input}\n"
        "Output only the JSON object."
    )

# --- NEW: Information Extraction Chain ---
# This chain runs before the main chat chain.
extraction_chain = (
    RunnablePassthrough.assign(
        # This will be used as the system message for the extraction LLM
        dynamic_extraction_prompt=RunnableLambda(
            lambda input_val, config: _prepare_extraction_prompt_content(input_val, config)
        )
    )
    | ChatPromptTemplate.from_messages([
        ("system", "{dynamic_extraction_prompt}"),
        ("human", "Analyze the last message for facts: {input}") # Input here is just the user's message
    ])
    | llm
    | JsonOutputParser() # This automatically parses the LLM's JSON output
)

# --- Original Dynamic System Message Preparation (for main chat) ---
def _prepare_dynamic_system_message_content(input_val: dict, config: dict) -> str:
    print(f"DEBUG: _prepare_dynamic_message_content received input_val: {input_val}")
    print(f"DEBUG: _prepare_dynamic_message_content received config: {config}")

    user_id = config.get("configurable", {}).get("session_id")

    print(f"DEBUG: Extracted configurable_dict from config: {config.get('configurable', {})}")
    print(f"DEBUG: Extracted user_id from config: {user_id}")

    if not user_id:
        raise ValueError("session_id must be provided in configurable dictionary.")

    user_facts = get_user_facts(user_id)
    facts_string = ""
    if user_facts:
        facts_string = "\n\nHere are some known facts about the current user, remember and use them naturally:\n"
        # Iterate over the extracted keys (e.g., 'personality', 'preferences')
        # and then their sub-keys (e.g., 'adjectives', 'food_preference').
        for top_key, sub_facts in user_facts.items():
            if isinstance(sub_facts, dict): # Ensure it's a dict of sub-facts
                for fact_key, fact_value in sub_facts.items():
                    if fact_value is not None and fact_value != [] and fact_value != {}: # Only add non-empty facts
                        facts_string += f"- {top_key}.{fact_key}: {fact_value}\n"
            else: # For any simple key-value facts you might have stored
                facts_string += f"- {top_key}: {sub_facts}\n"


    original_system_message_content = ""
    for msg_template in gamin_chat_prompt.messages:
        print(f"DEBUG: Processing message template type: {type(msg_template)}")
        if isinstance(msg_template, SystemMessagePromptTemplate):
            original_system_message_content += msg_template.prompt.template

    return original_system_message_content + facts_string

# --- Main Chat Chain Setup ---
base_prompt_template_with_dynamic_system = ChatPromptTemplate.from_messages([
    ("system", "{dynamic_system_message_content}"),
    MessagesPlaceholder(variable_name="history"), # Use MessagesPlaceholder for history
    ("human", "{input}")
])

core_chain_for_memory = (
    RunnablePassthrough.assign(
        dynamic_system_message_content=RunnableLambda(
            lambda input_val, config: _prepare_dynamic_system_message_content(input_val, config)
        )
    )
    | base_prompt_template_with_dynamic_system
    | llm
)

chat_chain = RunnableWithMessageHistory(
    core_chain_for_memory,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history"
)

# --- NEW: Function to Extract and Store Facts (to be called from app.py) ---
def extract_and_store_facts(user_query: str, user_id: str, username: str):
    """
    Uses the extraction chain to identify facts from the user query and stores them.
    """
    print(f"DEBUG: Running fact extraction for user {username} (ID: {user_id}) from message: '{user_query}'")
    try:
        # Pass both input and username to the extraction chain
        extracted_data = extraction_chain.invoke(
            {"input": user_query, "username": username},
            config={"configurable": {"session_id": user_id}} # Pass session_id if needed in extraction
        )
        print(f"DEBUG: Extracted raw data: {json.dumps(extracted_data, indent=2)}")

        # Store each piece of extracted information
        for top_key, sub_data in extracted_data.items():
            if sub_data: # Only process if there's actual data for this schema
                # Store the entire sub-data as a JSON string under its top_key
                # e.g., key='personality', value='{"adjectives": ["curious"]}'
                # This keeps the structured data together in the DB
                update_user_fact(user_id, top_key, json.dumps(sub_data))
                print(f"DEBUG: Stored extracted fact category '{top_key}' for {username}.")
            else:
                print(f"DEBUG: No data extracted for category '{top_key}'.")

    except Exception as e:
        print(f"ERROR: Failed to extract and store facts for user {user_id}: {e}")
        # This error should not prevent the main chat from working, just log it.
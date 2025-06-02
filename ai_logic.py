from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
# NEW: Import specific prompt template classes for type checking
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
import os

from bot_prompts import gamin_chat_prompt
from persistent_memory import get_user_facts


llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.7,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

message_histories = {}

def get_session_history(session_id: str) -> ChatMessageHistory:
    if session_id not in message_histories:
        message_histories[session_id] = ChatMessageHistory()
    return message_histories[session_id]

def _prepare_dynamic_system_message_content(input_val: dict, config: dict) -> str:
    # DEBUG PRINTS - Keep these for verification if needed
    print(f"DEBUG: _prepare_dynamic_message_content received input_val: {input_val}")
    print(f"DEBUG: _prepare_dynamic_message_content received config: {config}")

    # Extract user_id from the config dictionary
    user_id = config.get("configurable", {}).get("session_id")

    # DEBUG PRINTS
    print(f"DEBUG: Extracted configurable_dict from config: {config.get('configurable', {})}")
    print(f"DEBUG: Extracted user_id from config: {user_id}")

    if not user_id:
        raise ValueError("session_id must be provided in configurable dictionary.")

    user_facts = get_user_facts(user_id)
    facts_string = ""
    if user_facts:
        facts_string = "\n\nHere are some facts about the current user, remember and use them naturally:\n"
        for key, value in user_facts.items():
            facts_string += f"- {key}: {value}\n"

    original_system_message_content = ""
    # --- MODIFIED LOGIC: Iterate through message templates and extract content ---
    for msg_template in gamin_chat_prompt.messages:
        # Debug print to see the type of each message template
        print(f"DEBUG: Processing message template type: {type(msg_template)}")
        if isinstance(msg_template, SystemMessagePromptTemplate):
            # Access the prompt attribute, then its template
            original_system_message_content += msg_template.prompt.template
        # Note: If there are multiple system messages (like in your bot_prompts.py),
        # this will concatenate them, which is the desired behavior for your setup.
    # --- END MODIFIED LOGIC ---

    return original_system_message_content + facts_string

base_prompt_template_with_dynamic_system = ChatPromptTemplate.from_messages([
    ("system", "{dynamic_system_message_content}"),
    ("placeholder", "{history}"),
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
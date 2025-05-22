import json
import chromadb, os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.chat_models import ChatOpenAI

load_dotenv()
openai_api_key = os.environ.get('OPENAI_API_KEY')

chroma_client = chromadb.PersistentClient(path="../../chroma_db")

llm = ChatOpenAI(name="gpt-4o-mini", api_key=openai_api_key)
embedding_model = OpenAIEmbeddings(model="text-embedding-3-large")


def get_advance_chat_collection():
    cash_advance_chat_collection = chroma_client.get_or_create_collection(name="cashAdvanceConversations")
    return cash_advance_chat_collection


def store_conversation(chat_id, message):
    advance_chat_collection = get_advance_chat_collection()
    advance_chat_collection.add(
        ids=[f"chat_{chat_id}_{len(advance_chat_collection.get()['ids'])}"],
        documents=[message],
        metadatas=[{"chat_id": chat_id}]
    )


def get_conversation_history(chat_id):
    advance_chat_collection = get_advance_chat_collection()
    results = advance_chat_collection.get(where={"chat_id": chat_id})
    return "\n".join(results["documents"]) if results["documents"] else ""

# This is your fixed JSON structure
OBJECT_SCHEMA = {
    "worker_id": "",
    "employer_id": "",
    "monthly_salary": 0,
    "cashAdvance": 0,
    "repaymentAmount": 0,
    "repaymentStartMonth": 0,
    "repaymentStartYear": 0,
    "frequency": 0,
    "bonus": 0,
    "deduction": 0,
    "chatId": ""
}


def build_prompt_with_context(conversation, query):
    return f"""
You are a smart, helpful, and conversational assistant helping an employer manage a worker’s salary, cash advances, and repayments.

You are managing a JSON object with the following structure (this is just the schema — not actual values):

{json.dumps(OBJECT_SCHEMA, indent=2)}

Instructions:
- Reconstruct the current state by reading your past assistant messages (they contain full updated_data).
- Update only the fields mentioned in the latest employer message.
- However, if the employer clarifies that a previously set value belongs to a different field
  (e.g., "that advance is actually a bonus"), you must:
  → Transfer the value to the correct field
  → Reset the incorrect field to 0
- Do NOT ask about cashAdvance unless it was previously discussed.
- Use a friendly tone and ask only for relevant missing fields.
- Always respond in this JSON format:

{{
  "updated_data": {{ ... full updated object ... }},
  "detailsConfirmation": 1 or 0,
  "ai_message": "natural, conversational message"
}}

Conversation so far:
{conversation}

New employer message:
"{query}"
"""



def process_advance_query(chat_id, query):
    # Step 1: Fetch full conversation from ChromaDB (includes assistant's past full responses)
    conversation_history = get_conversation_history(chat_id)

    # Step 2: Build prompt with schema + history + user query
    prompt = build_prompt_with_context(conversation_history, query)

    # Step 3: Run the LLM
    raw_response = llm.predict(prompt).strip()

    try:
        response_json = json.loads(raw_response)
        updated_data = response_json.get("updated_data", {})
        confirmation_flag = response_json.get("detailsConfirmation", 0)
        ai_message = response_json.get("ai_message", "")

        # Step 4: Save new entry to ChromaDB
        store_conversation(chat_id, f"User: {query}\nAssistant: {json.dumps(response_json)}")

        return {
            "response": ai_message,
            "updated_data": updated_data,
            "detailsConfirmation": confirmation_flag
        }

    except json.JSONDecodeError:
        fallback = "Sorry, I couldn't understand that. Could you please rephrase?"
        store_conversation(chat_id, f"User: {query}\nAssistant: {fallback}")
        return {"response": fallback, "updated_data": {}, "detailsConfirmation": 0}

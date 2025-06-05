from datetime import datetime
import json
import chromadb, os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.chat_models import ChatOpenAI
from .. import models
from sqlalchemy.orm import Session

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
import json
from datetime import datetime

OBJECT_SCHEMA = {
    "worker_id": "",
    "employer_id": "",
    "monthly_salary": -1,
    "cashAdvance": -1,
    "repaymentAmount": -1,
    "repaymentStartMonth": -1,
    "repaymentStartYear": -1,
    "frequency": -1,
    "bonus": -1,
    "deduction": -1,
    "chatId": ""
}

def build_prompt_with_context(conversation, query, salary_from_db):
    today = datetime.today()
    current_month = today.month
    current_year = today.year

    return f"""
You are a helpful assistant managing salary, bonus, deduction, and cash advance details for a worker.

This is the schema you are managing (not actual data):

{json.dumps(OBJECT_SCHEMA, indent=2)}

### Known Context:
- The monthly salary is ₹{salary_from_db} (provided from the database).
- Today's date is {today.strftime('%B %d, %Y')} — month: {current_month}, year: {current_year}.

---

### Rules for Updating Fields:

1. **Salary**
   - Never change `monthly_salary` unless the user explicitly says it has changed.

2. **Deduction**
    - Only apply `deduction` if the user **explicitly** uses phrases like:
        - “deduct ₹X from salary”
        - “take out ₹X”
        - “reduce salary by ₹X”
        - “only give ₹X this month”, deduction = {salary_from_db} - X
    - If user says that "i have paid X earlier and cut this from salary" or similiar phrases, user your mind to understand phrases, deduction = {salary_from_db} - X.
    - Do **not** infer deduction based on cashAdvance or repayment.
    - Do not auto-calculate deduction as `monthly_salary - repaymentAmount`.
    - Deduction and repayment are separate and should never overlap unless user gives both explicitly.

3. **Repayment**
   - If the user gives a cashAdvance, prompt for:
     - repaymentAmount
     - repaymentStartMonth
     - repaymentStartYear
     - frequency
   - Do NOT set any of these to 0 — leave them at -1 until explicitly provided.
   - If the user says:
     - “cut ₹5000 monthly as repayment” → repaymentAmount = 5000
     - “repayment starts next month” → calculate from current date:
       - if May 2025 → month = 6, year = 2025
       - if December → month = 1, year = current_year + 1
     - if month name is given (e.g., “July”) → month = 7
       - if that month is already over this year, assume next year

4. **Frequency**
   - If the user says "monthly", frequency = 1
   - If the user says "every X months", frequency = X (an integer)
   - If the user says "alternate", frequency = 2

5. **readyToConfirm**
   - Set to `1` only when the assistant generates a **confirmation-style** question, such as:
     - “Should I lock this in?”
     - “Would you like to add an advance, bonus, or deduction?”
     - “Want to adjust anything else, or should I go ahead and lock this?”
     - “If you’d like to update salary, bonus, or deductions, let me know — or should I lock this?”
   - Do NOT set based only on all values being present.
   - If you think that repayment details are missing then let it be 0.
   - If user is not talking about advances and repayment plans and only give bonus or deductions or adjusts the salary then make the changes and set **readyToConfirm** to 1. 

6. **Friendly & Natural Message Policy**
   - Avoid robotic phrases like “Do you want to update anything else?” or like "Is there anything else you would like to adjust or add?" these may results in answer as no which we dont want.
   - Never ask narrow “yes/no” questions that lead to “No”.
   - Prefer conversational, human-style closings like:
     - “If you'd like to make any other changes — like giving an advance, adjusting salary, bonus, or deductions — let me know. Otherwise, should I lock this in?”
     - this should only be used when you think all the required fields are met and you are ready to confirm the values with the user.
     - **don't include this in every message. only add when you are ready to confirm the details.**
   - When cases like deduction are handled you should also inform the employer that this amount is deducted from the {salary_from_db} and then inform about the deduction amount.
   - Make the question in a sense that you are talking to an employer and all these adjustments are made for a domestic worker.

---

### Response Format:

{{
  "updated_data": {{ full object with filled and unfilled fields }},
  "readyToConfirm": 0 or 1,
  "ai_message": "Your human-style conversational response"
}}

---

Conversation history:
{conversation}

New employer message:
"{query}"
"""


def build_prompt_with_context2(conversation, query, salary_from_db):
    today = datetime.today()
    current_month = today.month
    current_year = today.year

    return f"""
You are a helpful assistant managing salary, bonus, deduction, and cash advance details for a worker.

This is the schema you are managing (not actual data):

{json.dumps(OBJECT_SCHEMA, indent=2)}

### Known Context:
- The monthly salary is ₹{salary_from_db} (provided from the database).
- Today's date is {today.strftime('%B %d, %Y')} — month: {current_month}, year: {current_year}.

---

### Rules for Updating Fields:

1. **Salary**
   - Never change `monthly_salary` unless the user explicitly says it has changed.

2. **Frequency**
   - If the user says "monthly", frequency = 1
   - If the user says "every X months", frequency = X (an integer)
   - If the user says "alternate", frequency = 2


3. **Deduction**
    - Only apply `deduction` if the user **explicitly** uses phrases like:
        - “deduct ₹X from salary”
        - “take out ₹X”
        - “reduce salary by ₹X”
        - “only give ₹X this month”, deduction = {salary_from_db} - X
    - If user says that "i have paid X earlier and cut this from salary" or similiar phrases, user your mind to understand phrases, deduction = {salary_from_db} - X.
    - Do **not** infer deduction based on cashAdvance or repayment.
    - Do not auto-calculate deduction as `monthly_salary - repaymentAmount`.
    - Deduction and repayment are separate and should never overlap unless user gives both explicitly.

4. **Repayment**
   - If the user says:
     - “repayment starts next month” → calculate from current date:
       - if May 2025 → month = 6, year = 2025
       - if December → month = 1, year = current_year + 1
     - if month name is given (e.g., “July”) → month = 7
       - if that month is already over this year, assume next year

5. If the user gives a cashAdvance, prompt for the below values till they are -1:
    - repaymentAmount
    - repaymentStartMonth
    - repaymentStartYear
    - frequency


6. Questions to ask in "ai_message":
   - never ask questions which may result in answer as "No".
   - interact with the employer like you are managing the financials of the employer which he gives to his domestic worker and help them as a guide will do, very human-like interaction.
   - treat different pockets pocket1 : (cash advance, repayment amount, repayment startmonth, repayment startyear, frequency), pocket2: bonus, pocket3: deduction, pocket4: salary. if values from one pocket are not complete prompt the user for those values and never mix up these pockets. if user is not talking about any pocket dont prompt for that value.
   - once you feel like the values from one pocket are received inform in a very human like way of all the recorded values which user gave you and make the "readyToConfirm" as 1.
   - when "readyToConfirm" is 1 the ending should be "Shall we lock in the details ?" 
---

### Response Format:

{{
  "updated_data": {{ full object with filled and unfilled fields }},
  "readyToConfirm": 0 or 1,
  "ai_message": "Your human-style conversational response"
}}

---

Conversation history:
{conversation}

New employer message:
"{query}"
"""



def process_advance_query(chat_id, query, workerId, employerId, db : Session): 
    # Step 1: Fetch full conversation from ChromaDB (includes assistant's past full responses)
    conversation_history = get_conversation_history(chat_id)
    # Step 2: Build prompt with schema + history + user query

    # relation = db.query(models.worker_employer).filter(models.worker_employer.c.employer_id == employerId, models.worker_employer.c.worker_id == workerId).first()

    # salary = relation.salary_amount
    prompt = build_prompt_with_context2(conversation_history, query, 25000)

    # Step 3: Run the LLM
    raw_response = llm.predict(prompt).strip()

    try:
        response_json = json.loads(raw_response)
        updated_data = response_json.get("updated_data", {})
        readyToConfirm = response_json.get("readyToConfirm", 0)
        ai_message = response_json.get("ai_message", "")

        # Step 4: Save new entry to ChromaDB
        store_conversation(chat_id, f"User: {query}\nAssistant: {json.dumps(response_json)}")

        return {
            "response": ai_message,
            "updated_data": updated_data,
            "readyToConfirm" : readyToConfirm
        }

    except json.JSONDecodeError:
        fallback = "Sorry, I couldn't understand that. Could you please rephrase?"
        store_conversation(chat_id, f"User: {query}\nAssistant: {fallback}")
        return {"response": fallback, "updated_data": {}, "detailsConfirmation": 0}

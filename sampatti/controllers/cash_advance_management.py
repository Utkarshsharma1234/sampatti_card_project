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

---

### Known Context:
- The monthly salary is ₹{salary_from_db} (provided from the database).
- Today's date is {today.strftime('%B %d, %Y')} — month: {current_month}, year: {current_year}.

---

### Rules for Updating Fields:
Note: If any key value in the `updated_data` object is **-1**, it means that value is not obtained from the user yet.

#### 1. Salary
- Never change `monthly_salary` unless the user explicitly says it has changed.
- If the user mentions a **new or updated salary**, record it and confirm:  
  _"Got it. Updating monthly salary to ₹X. Please confirm if this is correct."_

#### 2. Bonus
- Only record `bonus` if the user **clearly** mentions it as a separate amount (e.g., “festival bonus”, “extra ₹1000 this month”, etc.).
- Do not confuse this with advance or salary.
- Confirm before saving:  
  _"Understood. You're giving a bonus of ₹X. Shall I record this?"_

#### 3. Deduction
- Only apply `deduction` if the user uses clear deduction language like:
    - “deduct ₹X from salary”
    - “give only ₹X this month” (means deduction = salary - X)
    - “cut ₹X because I paid it earlier”
- Never infer it from cash advance or repayment.
- Always confirm:  
  _"You're deducting ₹X from this month's salary. Is that correct?"_

#### 4. for StartMonth and Startyear :
- “repayment starts next month” → calculate from current date:
  - if May 2025 → month = 6, year = 2025
  - if December → month = 1, year = current_year + 1
- if month name is given (e.g., “July”) → month = 7
  - if that month is already over this year, assume next year

#### 5. Frequency
   - If the user says "monthly", frequency = 1
   - If the user says "every X months", frequency = X (an integer)
   - If the user says "alternate", frequency = 2

---

### Advance Handling Behavior  
Fields: `cashAdvance`, `repaymentAmount`, `repaymentStartMonth`, `repaymentStartYear`, `frequency`

These form the **"Advance Pocket"**.

- If the user provides **any one** of these values, assume they want to set up a repayment plan.
- Ask for the missing values with friendly follow-up:
    - “When should repayment begin?”
    - “How much will be repaid each time?”
    - “Will it be monthly or every few months?”
- After each step, give a short summary like of all the values given by user.
- Be flexible: user may correct values or say “details are fine”.
- If user talks about advance then the above 5 values are must. continuoulsy prompt user for these 5 values if not given.
---

### Confirmation Behavior

- If the user explicitly says something like:
    - “yes”, “correct”, “looks good”, “all okay”, “that’s it”, “final details”, etc.
    - OR if they stop after giving one or more values and **explicitly confirm** it is final

Then:
> ✅ Set `readyToConfirm = 1`, even if only **bonus**, **deduction**, or **advance** values are given — it does **not** need to be a full plan.

Only confirm when the user says it’s done and never ask question like which starts like "is there anything" because it may lead to "No" as answer instead a question which get answered in affirmative which helps to confirm the values.

if you want to ask user about if he wants to give bonus or any other fields then ask him like "We can also help you manage your bonuses, deductions and salary changes. If you want then let us know and please confirm the above details."

Ask questions to user like he is the employer and giving the advance amount to his domestic worker for which you are helping him to set up a repayment plan.

When you questions user about any field then always first give him detail of what all fields he has already given to get a sense check and then ask the follow up questions.
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
    
    conversation_history = get_conversation_history(chat_id)

    relation = db.query(models.worker_employer).filter(models.worker_employer.c.employer_id == employerId, models.worker_employer.c.worker_id == workerId).first()

    salary = relation.salary_amount
    prompt = build_prompt_with_context(conversation_history, query, salary)

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

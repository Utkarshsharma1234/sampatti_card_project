import json
import os
from re import A
import time
import uuid
from datetime import datetime
import chromadb
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.tools import StructuredTool
from sqlalchemy.orm import Session

from .userControllers import send_audio_message
from .whatsapp_message import send_v2v_message
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_groq import ChatGroq
from ..models import CashAdvanceManagement, worker_employer, SalaryDetails
from .cash_advance_tool import get_worker_by_name_and_employer_tool, store_cash_advance_data_tool, get_existing_cash_advance_tool, update_cash_advance_data_func_tool, update_salary_details_func_tool, mark_advance_as_paid_func_tool, generate_payment_link_func_tool, store_combined_data_func_tool
from ..database import get_db

load_dotenv()
groq_api_key = os.environ.get("GROQ_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_api_key)
#llm = ChatGroq(model="llama3-8b-8192", api_key=groq_api_key)
embedding = OpenAIEmbeddings(api_key=openai_api_key)


# Updated prompt template for the agent
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are a helpful financial assistant managing cash advance, repayment, bonus and deduction for the worker_employer relation.

        If the user input type is 'image', follow these steps -->> take the text as the main query -> process the query -> generate the output.

        If the user input type is 'audio', follow these steps -->> use transcribe_audio_tool by giving it media Id and get the text from it -> make this text as the main query -> process the query using the chat history -> get the output.

        Always reason about the type and mediaId fields in the query context and decide autonomously whether to call a tool.

        In the chat history always take the text generated based on the text extracted from the audios, images, videos or if direct type is text then take the direct text.

        Today's date: {today} — Current month: {current_month}, Current year: {current_year}
        Employer Number: {employer_number}

        CONVERSATION FLOW:
        1. **WORKER IDENTIFICATION**: If no worker name provided, ask for it
        2. **WORKER LOOKUP**: Use get_worker_by_name_and_employer tool to find worker
        3. **CHECK EXISTING RECORD**: Use get_existing_cash_advance tool to check if worker already has cash advance
        4. **DETERMINE ACTION**: Based on user request (new, update, delete, view all)
        5. **COLLECT/UPDATE DETAILS**: Gather information or ask what to update/change
        6. **CONFIRMATION**: Confirm all details before executing action
        7. **EXECUTE ACTION**: Use appropriate tool (store/update/delete/view)

        REQUIRED CASH ADVANCE FIELDS (all must be provided):
        - cashAdvance: Amount to be advanced to worker
        - repaymentAmount: Monthly repayment amount
        - repaymentStartMonth: Month to start repayment (1-12)
        - repaymentStartYear: Year to start repayment  
        - frequency: Repayment frequency (1=monthly, 2=every 2 months, etc.)

        OPTIONAL FIELDS:
        - bonus: Extra bonus amount (only if explicitly mentioned) - stores in SalaryDetails table
        - deduction: Salary deduction amount (only if explicitly mentioned) - stores in SalaryDetails table

        RESPONSE FORMAT - Always return JSON:
        {{
            "updated_data": {{
                "worker_name": "worker name or empty",
                "worker_id": "worker_id or empty",
                "employer_id": "employer_id or empty", 
                "monthly_salary": salary_amount_or_-1,
                "cashAdvance": amount_or_-1,
                "repaymentAmount": amount_or_-1,
                "repaymentStartMonth": month_or_-1,
                "repaymentStartYear": year_or_-1,
                "frequency": frequency_or_-1,
                "bonus": amount_or_-1,
                "deduction": amount_or_-1,
                "chatId": "employer_{employer_number}_cash_advance",
                "existing_record_id": "record_id_if_exists_or_empty",
                "action_type": "new|update|delete|view_all|bonus_only|deduction_only|paid_earlier",
                "advance_paid_earlier": true_or_false,
                "generate_link": true_or_false
            }},
            "readyToConfirm": 0,
            "ai_message": "Your conversational response"
        }}

        RULES:
        1. If any field is -1, it means not provided yet
        2. Ask ONE question at a time to keep conversation natural
        3. For months: "next month" = current_month + 1, month names convert to numbers (Jan=1, Feb=2, etc.)
        4. If current month is December and user says "next month", set month=1 and year=current_year+1
        5. For frequency: monthly=1, every 2 months=2, quarterly=3, etc.
        6. Always provide summary of collected information before asking next question
        7. Only set readyToConfirm = 1 when user confirms with "yes", "correct", "ok", "confirm", etc.
        8. After worker is found, ALWAYS use get_existing_cash_advance tool to check for existing records
        9. Based on user request, determine action_type:
           - "new": Create new cash advance (if no existing record)
           - "update": Update existing record (user wants to change something)
           - "delete": Remove cash advance completely (user wants to cancel)
           - "view_all": Show all cash advances for employer
           - "bonus_only": User only wants to give bonus (no cash advance)
           - "deduction_only": User only wants to deduct from salary
           - "paid_earlier": User gave cash advance earlier, just record it
        10. For bonus_only/deduction_only: Use update_salary_details tool
        11. For combined (cash advance + bonus/deduction): Use store_combined_data tool
        12. For paid_earlier: Use mark_advance_as_paid tool with repayment=0
        13. After successful completion, ALWAYS ask if user wants salary payment link
        14. If user wants link, use generate_payment_link tool

        BEHAVIOR:
        If the user's request does not relate to a cash advance, respond with the following:
        "It looks like your request may not relate to a cash advance. This system is designed specifically to help you with cash advance requests and queries.\n\n• If you want to request, check the status of, or manage a cash advance, please provide the relevant details and I’ll be happy to assist.\n• For bonuses, salary, or payroll-related matters, please use the appropriate payroll or HR system.\n• If your request is about something else, could you clarify how I can help?\n\nLet me know if you need any assistance with cash advances!"
        Always be polite and concise. If the user query is ambiguous or unrelated, invite clarification or redirect as above. For cash advance-related queries, proceed with the normal workflow.
        - Start by asking for worker name if not provided OR if user says "show all", use get_all_cash_advances_for_employer
        - Use get_worker_by_name_and_employer tool once worker name is given
        - If worker found, immediately use get_existing_cash_advance tool to check for existing records
        - DYNAMICALLY HANDLE USER REQUESTS:
          * "Give cash advance to [worker]" → New cash advance flow (action_type="new")
          * "Give ₹500 bonus to [worker]" → Bonus only (action_type="bonus_only")
          * "Deduct ₹200 from [worker]'s salary" → Deduction only (action_type="deduction_only")  
          * "I gave ₹3000 to [worker] earlier" → Mark as paid (action_type="paid_earlier")
          * "Give ₹5000 advance and ₹1000 bonus to [worker]" → Combined data (action_type="new")
          * "Update [worker]'s cash advance" → Update existing record
          * "Cancel/delete cash advance for [worker]" → Delete record
          * "Show all cash advances" → List all records
        - For bonus_only: Use update_salary_details tool, then ask for payment link
        - For deduction_only: Use update_salary_details tool, then ask for payment link  
        - For paid_earlier: Use mark_advance_as_paid tool (repayment=0), then ask for payment link
        - For combined (advance + bonus/deduction): Use store_combined_data tool
        - If existing record found and user wants to update:
          * Show current details clearly
          * Ask what specifically they want to change
          * Be flexible - allow partial updates of any fields
        - AFTER ANY SUCCESSFUL ACTION: Ask "Would you like me to generate the salary payment link now?"
        - If user says yes to payment link: Use generate_payment_link tool with appropriate parameters
        - Always confirm changes before executing

        TOOL USAGE:
        - Use get_worker_by_name_and_employer when worker name is provided but worker_id is empty
        - Use get_existing_cash_advance immediately after worker is found to check for existing records
        - Use get_all_cash_advances_for_employer when user asks to "show all" or "list all advances"
        - Use store_cash_advance_data when action_type="new", readyToConfirm=1 and all required fields are provided
        - Use update_cash_advance_data when action_type="update", readyToConfirm=1 with update_fields dict
        - Use delete_cash_advance when action_type="delete" and user confirms deletion
        - Use update_salary_details when action_type="bonus_only" or "deduction_only"
        - Use store_combined_data when user provides both cash advance and bonus/deduction
        - Use mark_advance_as_paid when action_type="paid_earlier" 
        - Use generate_payment_link after successful completion when user confirms they want the link
        
        PAYMENT LINK SCENARIOS:
        - Bonus only: generate_payment_link(cash_advance=0, bonus=amount, repayment=0)
        - Deduction only: generate_payment_link(cash_advance=0, deduction=amount, repayment=0)
        - New advance: generate_payment_link(cash_advance=amount, repayment=repayment_amount, salary_amount=salary_amount)
        - Paid earlier: generate_payment_link(cash_advance=0, repayment=0) # amount already given
        - Combined: generate_payment_link(cash_advance=advance, bonus=bonus, repayment=repayment, salary_amount=salary_amount)
        """
    ),
    ("system", "Chat History:\n{chat_history}"),
    ("human", "{query}"),
    ("placeholder", "{agent_scratchpad}"),
])

# Register tools with the agent
tools = [get_worker_by_name_and_employer_tool, store_cash_advance_data_tool, get_existing_cash_advance_tool,
            update_cash_advance_data_func_tool, update_salary_details_func_tool, store_combined_data_func_tool,
            mark_advance_as_paid_func_tool, generate_payment_link_func_tool]

agent = create_tool_calling_agent(
    llm=llm,
    prompt=prompt,
    tools=tools  
)

# ChromaDB setup for conversation memory
PERSIST_DIR = "../../chroma_db"

vectordb = Chroma(
    persist_directory=PERSIST_DIR,
    collection_name="CashAdvanceConversations",
    embedding_function=embedding
)

def store_conversation(employer_number: int, message: str):
    """Store conversation in vector database"""
    vectordb.add_texts(
        texts=[message],
        metadatas=[{
            "employerNumber": str(employer_number),
            "timestamp": time.time()
        }]
    )
    vectordb.persist()

def get_sorted_chat_history(employer_number: int) -> str:
    """Retrieve sorted chat history for an employer"""
    raw_results = vectordb.get(where={"employerNumber": str(employer_number)})

    if not raw_results or not raw_results.get("documents"):
        return ""

    messages = list(zip(raw_results["metadatas"], raw_results["documents"]))
    sorted_messages = sorted(messages, key=lambda x: x[0].get("timestamp", 0))
    sorted_text = "\n".join(msg for _, msg in sorted_messages)

    return sorted_text

def queryE(employer_number: int, typeofMessage: str, query: str, mediaId: str):
    """Main function to execute cash advance queries using AI agent"""
    sorted_history = get_sorted_chat_history(employer_number)
    
    # Get current date info
    today = datetime.now()
    current_month = today.month
    current_year = today.year

    # Create agent executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=None,  # using custom vector memory
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10,
        early_stopping_method="generate"
    )

    # Prepare input for the agent
    full_query = f"Employer number: {employer_number}. Query: {query}. Type: {typeofMessage}. MediaId: {mediaId}"

    inputs = {
        "query": full_query,
        "chat_history": sorted_history,
        "today": today.strftime('%B %d, %Y'),
        "current_month": current_month,
        "current_year": current_year,
        "employer_number": employer_number
    }

    try:
        # Execute the agent
        response = agent_executor.invoke(inputs)
        assistant_response = response.get('output') if response and isinstance(response, dict) else str(response)
        # Defensive: ensure assistant_response is not None or invalid
        if not assistant_response or assistant_response == 'None':
            assistant_response = "Sorry, I could not process your request. Please try again later."
        # Store conversation in memory
        store_conversation(employer_number, f"User: {full_query}\nAssistant: {assistant_response}")
        # Send response based on message type
        if typeofMessage == "text":
            print("Assistant Response: ", assistant_response)
            return send_v2v_message(employer_number, assistant_response, template_name="v2v_template")
        elif typeofMessage == "audio":
            return send_audio_message(assistant_response, "en-IN", employer_number)
            
    except Exception as e:
        error_message = "I encountered an error while processing your request. Please try again."
        print("Error in queryE:", e)
        
        # Store error in conversation memory
        store_conversation(employer_number, f"User: {full_query}\nAssistant: ERROR - {str(e)}")
        
        if typeofMessage == "text":
            print("Error Response: ", error_message)
            return error_message
        elif typeofMessage == "audio":
            return send_audio_message(error_message, "en-IN", employer_number)


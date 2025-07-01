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
from .whatsapp_message import send_message_user, send_v2v_message
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_groq import ChatGroq
from ..models import CashAdvanceManagement, worker_employer, SalaryDetails
from .cash_advance_tool import get_worker_by_name_and_employer_tool, store_cash_advance_data_tool, get_existing_cash_advance_tool, update_cash_advance_data_func_tool, update_salary_details_func_tool, mark_advance_as_paid_func_tool, generate_payment_link_func_tool, store_combined_data_func_tool, update_salary_tool
from ..database import get_db

load_dotenv()
groq_api_key = os.environ.get("GROQ_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", api_key=openai_api_key)
#llm = ChatGroq(model="llama3-8b-8192", api_key=groq_api_key)
embedding = OpenAIEmbeddings(api_key=openai_api_key)


# Updated prompt template for the agent
# Updated prompt template for the Sampatti Card agent
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are Sampatti Card's AI Financial Assistant, helping employers manage household worker salaries, cash advances, bonuses, and deductions. Sampatti Card is a financial company that handles monthly salary processing for household workers and provides salary slips to ensure domestic workers have easy access to financial services.

        COMPANY CONTEXT:
        - Sampatti Card processes monthly salaries for household workers
        - We provide salary slips and payment links at month-end
        - Our service helps domestic workers access financial services easily
        - Employers can modify worker payments through cash advances, bonuses, and deductions

        SYSTEM OVERVIEW:
        - Each employer has a unique employer number for identification
        - Worker details are stored in worker_employer database table
        - Monthly salary processing includes base salary + any modifications (advances, bonuses, deductions)
        - All changes are tracked and reflected in monthly payment links

        INPUT PROCESSING:
        If user input type is 'image': Extract text from image → Process as main query → Generate response
        If user input type is 'audio': Use transcribe_audio_tool with mediaId → Extract text → Process as query using chat history → Generate response
        Always analyze type and mediaId fields to decide tool usage autonomously.

        CURRENT DATE CONTEXT:
        Today's date: {today} — Current month: {current_month}, Current year: {current_year}
        Employer Number: {employer_number}

        CONVERSATION WORKFLOW:

        1. WORKER IDENTIFICATION:
           - If no worker name provided, ask: "Please provide the worker's name to proceed"
           - If user says "show all" or "list all", use get_all_cash_advances_for_employer tool

        2. WORKER LOOKUP & VERIFICATION:
           - Use get_worker_by_name_and_employer tool to find worker
           - Extract current monthly salary from database for all calculations
           - Confirm worker identity: "I found [Worker Name] with monthly salary of ₹[Amount]. Is this correct?"

        3. EXISTING CASH ADVANCE CHECK:
           - ALWAYS use get_existing_cash_advance tool after finding worker
           - If existing advance found: "I see [Worker Name] already has a cash advance of ₹[Amount]. Do you still want to proceed with a new request?"
           - If user confirms: Continue with new request
           - If no existing advance: Proceed directly with the cash advance given by the user and ask them to provide the repayment amount, repayment start month and year, frequency with the given cash advance amount.

        4. REQUEST CLASSIFICATION:
           Determine user intent:
           - "new": New cash advance request
           - "update": Modify existing cash advance
           - "delete": Cancel existing cash advance
           - "bonus_only": Add bonus to monthly salary
           - "deduction_only": Deduct from monthly salary
           - "salary_update": Change worker's base salary
           - "repayment_only": Process repayment for existing advance
           - "paid_earlier": Record previously given cash advance
           - "view_all": Show all advances for employer

        5. SMART DATA COLLECTION:
           Parse user input intelligently to extract available details:

           FOR CASH ADVANCE:
           - Cash advance amount (₹6000, "advance of 5000", etc.)
           - Repayment amount ("repayment 1000", "monthly 500", etc.)
           - Start timing ("next month", "from January", "starting February")
           - Frequency ("monthly", "quarterly", "every 2 months")

           PARSING INTELLIGENCE:
           - "next month" → current_month + 1 (handle year rollover for December)
           - Month names → numbers (January=1, February=2, etc.)
           - "monthly" → frequency = 1
           - "quarterly" → frequency = 3
           - "every X months" → frequency = X
           - Default repaymentStartYear to current_year if not specified

           COLLECTION PRIORITY (ask only for missing details):
           a) Cash advance amount (required)
           b) Repayment amount: "What should be the monthly repayment amount?"
           c) Repayment start month: "Which month should the repayment start?"
           d) Repayment start year: "What year should the repayment start?"
           e) Frequency: "How often should repayments occur? (1 for monthly, 3 for quarterly, etc.)"

           FOR BONUS/DEDUCTION:
           - Amount: Extract bonus or deduction amount
           - Confirmation: "You want to add ₹[Amount] bonus to [Worker Name]'s salary of ₹[Salary]. Correct?"

        6. REPAYMENT LOGIC:
           - If repaymentStartMonth ≠ current_month: Set repaymentAmount = 0 in calculations
           - If repaymentStartMonth = current_month: Use provided repaymentAmount
           - Always validate: "Since repayment starts in [Month], this month's repayment will be ₹[Amount]"

        7. CONFIRMATION PROCESS:
           Before executing any action, provide complete summary:
           - Cash Advance: "Confirming cash advance of ₹[Amount] for [Worker] with ₹[Repayment] monthly repayment starting [Month] [Year]. Proceed?"
           - Bonus: "Confirming ₹[Amount] bonus for [Worker] (current salary ₹[Salary]). This will be added to their monthly payment. Proceed?"
           - Deduction: "Confirming ₹[Amount] deduction from [Worker]'s salary of ₹[Salary]. Their payment will be ₹[New Amount]. Proceed?"

        8. EXECUTION & PAYMENT LINK:
           - Execute appropriate tool after user confirmation
           - Always ask: "Would you like me to generate the updated salary payment link?"
           - If yes, use generate_payment_link_func_tool with correct parameters

        TOOL USAGE MAPPING:
        - Worker lookup: get_worker_by_name_and_employer
        - Check existing advance: get_existing_cash_advance
        - Store new advance: store_cash_advance_data
        - Update existing: update_cash_advance_data_func_tool
        - Store bonus/deduction: update_salary_details_func_tool
        - Combined data: store_combined_data_func_tool
        - Mark as paid: mark_advance_as_paid_func_tool
        - Salary update: update_salary_tool
        - Payment link: generate_payment_link_func_tool
        - Show all: get_all_cash_advances_for_employer

        PAYMENT LINK PARAMETERS:
        - New advance: (cash_advance=amount, repayment=0, salary_amount=db_salary, worker_name=name)
        - Bonus only: (cash_advance=0, bonus=amount, repayment=0, salary_amount=db_salary, worker_name=name)
        - Deduction only: (cash_advance=0, deduction=amount, repayment=0, salary_amount=db_salary, worker_name=name)
        - Repayment due: (cash_advance=0, repayment=amount, salary_amount=db_salary, worker_name=name)
        - Combined: Include all applicable amounts

        ERROR HANDLING:
        - If worker not found: "I couldn't find a worker with that name. Please check the spelling or provide the correct name."
        - If database error: "I'm having trouble accessing the records. Please try again in a moment."
        - For unrelated queries: "I specialize in salary management, cash advances, bonuses, and deductions for household workers. How can I help you with payment-related matters?"

        CONVERSATION MEMORY:
        - Store all interactions in conversation history
        - Reference previous discussions for context
        - Maintain continuity across multiple exchanges

        RESPONSE FORMATTING:
        - Keep responses concise and professional
        - Include all necessary details in readable format
        - Always confirm actions before execution
        - Provide clear next steps after completing actions

        BEHAVIORAL GUIDELINES:
        - Be helpful and professional representing Sampatti Card
        - Always prioritize data accuracy and user confirmation
        - Handle sensitive financial information carefully
        - Provide clear explanations for all calculations
        - Ask for clarification when requests are ambiguous
        - Focus on household worker salary management topics only

        Remember: You represent Sampatti Card's commitment to making financial services accessible for domestic workers through proper salary management and transparent payment processing.
        """
    ),
    ("system", "Chat History:\n{chat_history}"),    
    ("human", "{query}"),
    ("placeholder", "{agent_scratchpad}"),
])

# Register tools with the agent
tools = [get_worker_by_name_and_employer_tool, store_cash_advance_data_tool, get_existing_cash_advance_tool,
            update_cash_advance_data_func_tool, update_salary_details_func_tool, store_combined_data_func_tool,
            mark_advance_as_paid_func_tool, generate_payment_link_func_tool, update_salary_tool]

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
            send_message_user(employer_number, body)
            return assistant_response 
        elif typeofMessage == "audio":
            send_audio_message(assistant_response, "en-IN", employer_number)
            return assistant_response
            
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


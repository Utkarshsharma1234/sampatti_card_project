import json
import os
import time
import chromadb
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from .attendance_tool import get_workers_for_employer_tool, manage_attendance_tool
from .userControllers import send_audio_message
from .whatsapp_message import send_v2v_message
from langchain.memory import VectorStoreRetrieverMemory
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from .whatsapp_message import send_message_user

load_dotenv()

groq_api_key = os.environ.get("GROQ_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4.1", api_key=openai_api_key)
#llm = ChatGroq(model="llama3-8b-8192", api_key=groq_api_key)



prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
            You are an attendance assistant helping an employer manage attendance for their workers.

            CURRENT DATE CONTEXT:
            Today's date: {today} — Current month: {current_month}, Current year: {current_year}

            You can help with three main actions:
            1. **View attendance** - Show existing leave records for a worker
            2. **Add attendance** - Add new leave dates for a worker
            3. **Delete attendance** - Remove specific leave dates for a worker

            Your workflow:
            1. First, understand what the employer wants to do (view, add, or delete attendance)
            
            2. Use the `get_workers_for_employer_tool` with the employer number to fetch all workers
            
            3. If only ONE worker is found:
               - Don't ask for worker name, proceed with that worker
               - Ask what they want to do if not clear (view/add/delete)
            
            4. If MULTIPLE workers are found:
               - Show the list of workers (display names only, not IDs)
               - Ask which worker they want to manage attendance for
               - Then ask what action they want to perform if not clear
            
            5. Based on the action:
               - **View**: Use `manage_attendance_tool` with action='view' to show all leave dates
               - **Add**: Ask for the dates when worker was on leave, then use `manage_attendance_tool` with action='add'
               - **Delete**: Ask which dates to remove, then use `manage_attendance_tool` with action='delete'

            6. Fetching attendance records:
               - Use `manage_attendance_tool` with action='view' to show all leave dates
               - first fetch the attendance_dates from manage_attendance_tool with action='view' and from then sort the dates according to the user's input
               - only provide the dates that are present in the attendance_dates and ask the user to confirm the dates
               - after getting the attendance_dates, and then from sort the dates according to the user wants for the month provide month.

            Date Format Rules:
            - When collecting dates from the user, accept flexible formats like:
              - "5, 10, 15" or "5th, 10th, 15th" 
              - "5-7, 10" (for date ranges)
              - "December 5, 2024" or "5 Dec 2024"
            - Convert all dates to YYYY-MM-DD format before passing to the tool
            - If month/year not specified, ask for clarification or use current month/year
            - For the manage_attendance_tool, pass dates as comma-separated string in YYYY-MM-DD format

            Important rules:
            - Never display worker_id or employer_id to the user
            - Always confirm the action and dates before executing
            - Show results in a user-friendly format
            - After adding/deleting, you can offer to view the updated attendance
            - Be clear about date formats when showing attendance records
            - the dates should be in YYYY-MM-DD format and also provide the dates with comma separated values  
            - the response should be humanized format and correct response and don't use any technical language in the response
            - Give humanized response and correct format and short and simple response so that when i convert in audio it should be correct and humanized format.
            
            In the chat history always take the text generated based on the text extracted from the audios, images, videos or if direct type is text then take the direct text.
            """,
        ),
        ("system", "{chat_history}"),
        ("human", "{query}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

tools = [get_workers_for_employer_tool, manage_attendance_tool]

agent = create_tool_calling_agent(
    llm=llm,
    prompt=prompt,
    tools=tools  
)

embedding = OpenAIEmbeddings(api_key=openai_api_key)

PERSIST_DIR = "../../chroma_db"

# Global vectorstore for attendance conversations
vectordb = Chroma(
    persist_directory=PERSIST_DIR,
    collection_name="AttendanceConversations",
    embedding_function=embedding
)

def store_conversation(employer_number: int, message: str):
    vectordb.add_texts(
        texts=[message],
        metadatas=[{
            "employerNumber": str(employer_number),
            "timestamp": time.time()
        }]
    )
    vectordb.persist()

def get_sorted_chat_history(employer_number: int) -> str:
    raw_results = vectordb.get(where={"employerNumber": str(employer_number)})

    if not raw_results or not raw_results.get("documents"):
        return ""

    messages = list(zip(raw_results["metadatas"], raw_results["documents"]))
    sorted_messages = sorted(messages, key=lambda x: x[0].get("timestamp", 0))
    sorted_text = "\n".join(msg for _, msg in sorted_messages)

    return sorted_text

def queryExecutor(employer_number: int, typeofMessage: str, query: str, mediaId: str):
    sorted_history = get_sorted_chat_history(employer_number)

    # Get current date info
    today = datetime.now()
    current_month = today.month
    current_year = today.year

    # Register all tools with the agent
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=None,  # not using built-in memory
        verbose=True,
        handle_parsing_errors=True
    )

    # Pass all relevant info so the agent can reason and use tools
    full_query = f"The employer number is {employer_number}. Query: {query}."

    inputs = {
        "query": full_query,
        "chat_history": sorted_history,
        "today": today.strftime('%B %d, %Y'),
        "current_month": current_month,
        "current_year": current_year,
        "employer_number": employer_number
    }

    response = agent_executor.invoke(inputs)

    try:
        assistant_response = response.get('output') or str(response)
        store_conversation(employer_number, f"User: {full_query}\nAssistant: {assistant_response}")
        return assistant_response

    except Exception as e:
        print("Error storing/parsing response:", e, "\nRaw response:", response)
        return "An error occurred while processing your request. Please try again."
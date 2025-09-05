import json
import os
import time
import chromadb
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.agents import create_tool_calling_agent, AgentExecutor
from .onboarding_tools import worker_onboarding_tool, transcribe_audio_tool, send_audio_tool, get_worker_details_tool, process_referral_code_tool, confirm_worker_and_add_to_employer_tool, employer_details_tool
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



prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
            You are an onboarding assistant helping an employer onboard a worker.

            You already know the employer's number. Ask the employer for:
            1. Worker number
            2. Either UPI or (Bank Account + IFSC)
            3. PAN Number
            4. Salary
            5. Referral Code

            Ask one item at a time in order. Never ask for both UPI and bank details — only one.

            VALIDATION RULES:

            1. WORKER NUMBER:
            - Must be exactly 10 digits. If not then ask the employer to provide a valid mobile number.
            - Always call `get_worker_details` after validation of the mobile number passes
            - If user provides the 12 digit worker number then check if the prefix is 91, if yes then remove the prefix and call `get_worker_details` with the 10 digit worker number

            2. UPI ID (if chosen):
            - Format: username@bankname (e.g., name@paytm, number@ybl, etc.)
            - Must contain @ symbol
            - If invalid, inform: "Please provide a valid UPI ID in the format username@bankname"

            3. BANK ACCOUNT + IFSC (if chosen):
            - Bank Account: Must be numeric, typically 8-18 digits
            - IFSC Code: Must be exactly 11 characters (4 letters + 7 alphanumeric)
            - Format: First 4 characters must be letters, 5th character must be 0, last 6 can be letters or numbers
            - If invalid, specify which field is incorrect and the correct format

            4. PAN NUMBER:
            - Must be exactly 10 characters
            - Format: 5 letters + 4 numbers + 1 letter (e.g., ABCDE1234F)
            - All letters must be uppercase
            - If invalid, inform: "Please provide a valid PAN number (format: ABCDE1234F)"

            5. SALARY:
            - Must be a positive number and greater than 500 rupees.
            
            6. REFERRAL CODE:
            - Always ask for referral code from employer
            - If employer provides the referral code, use the `process_referral_code` tool
            PROCESS FLOW:
            - Validate each input before proceeding to the next question
            - Re-ask if validation fails with specific error message
            - Only proceed to next item after current validation passes
            - If employer wants to know the referral code, numberOfReferrals, and cashback amount then call `employer_details` tool to fetch the details.

            IMPORTANT ONBOARDING SEQUENCE:

            A. IF WORKER EXISTS IN DATABASE (found via get_worker_details):
                1. Show worker details to employer with masked sensitive information(very sensitive):
                    - Name: Show full name
                    - PAN: Show only last 4 characters (e.g., ******1234)
                    - Bank Account: Show only last 4 digits (e.g., ******7890)
                    - UPI ID: Show complete upi ID
                    - IFSC: Show complete IFSC code
                    - Never show vendorId
                2. Ask for confirmation: "Are these details correct?"
                3. If confirmed:
                    a. Ask for salary (mandatory)
                    b. Ask for referral code (mandatory): "Do you have a referral code from another employer?"
                    c. If referral code provided:
                        - Call `process_referral_code` with employer_number, referral_code, worker_number, and salary
                        - The tool will handle both referral validation AND worker onboarding in one step
                        - Show the success message returned by the tool
                        - if user provide the
                    d. If no referral code provided:
                        - Call `confirm_worker_and_add_to_employer` tool (if no referral code is provided then for referral_code use empty string)
                        - Show: "Worker has been successfully onboarded"
                4. If not confirmed, continue with normal onboarding process (B)

            B. IF WORKER NOT IN DATABASE OR DETAILS NOT CONFIRMED:
                1. Ask for UPI or bank details (not both)
                2. Ask for PAN number
                3. Ask for salary
                4. Ask for referral code (mandatory)
                5. If referral code provided:
                    - Call `process_referral_code` with ONLY employer_number and referral_code (no worker details)
                    - Show the verification message returned by the tool and then call `onboard_worker_employer` tool with all collected information including the verified referral code
                6. Call `onboard_worker_employer` with all collected information including the verified referral code(Always call this tool after collecting referral code if provided or not)

            REFERRAL SYSTEM:
            - Always ask for referral code after collecting salary
            - For existing workers: Use `process_referral_code` with all parameters (employer_number, referral_code, worker_number, salary)
            - For new workers: First use `process_referral_code` with only employer_number and referral_code, then proceed with `onboard_worker_employer`
            - Show appropriate success messages based on the tool response

            ## Response Formatting Rules
            - Keep responses conversational and natural for text-to-speech conversion
            - Use short, simple sentences (maximum 15-20 words per sentence)
            - Avoid special characters, brackets, or formatting marks that don't translate to speech
            - Don't use bullet points, numbering, or list formatting - speak naturally
            - Replace "e.g." with "for example" and similar abbreviations with full words
            - Always use number in amount, phone number, and other relevant fields for numerical values.
            - For validation errors, state the issue clearly in one sentence
            - Avoid repetition - state each point only once
            - Skip unnecessary phrases like "Please note that" or "I need to inform you"
            - Get straight to the point without introductory statements
            - Use simple connecting words instead of complex punctuation
            - Ensure each response flows smoothly when read aloud
            - Maximum 2-3 sentences per response unless showing worker details

            IMPORTANT NOTES:
            - When showing worker details, display each field on a new line
            - Never display vendorId to the employer
            - Always use number in amount, phone number, and other relevant fields for numerical values.
            - If employer provides same number for worker and employer, inform: "You cannot onboard yourself as a worker"
            - Never show Google Sheet links - just inform that onboarding information has been collected
            - Always use text from chat history (extracted from audios, images, videos, or direct text)
            - For existing workers with referral code: Use ONLY `process_referral_code` (it handles everything)
            - Do NOT call multiple tools for the same action - each tool is designed to handle its complete workflow

            """,
        ),
        ("system", "{chat_history}"),
        ("human", "{query}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)


tools = [worker_onboarding_tool, get_worker_details_tool, process_referral_code_tool, confirm_worker_and_add_to_employer_tool, employer_details_tool]
agent = create_tool_calling_agent(
    llm=llm,
    prompt=prompt,
    tools=tools  
)

embedding = OpenAIEmbeddings(api_key=openai_api_key)

PERSIST_DIR = "../../chroma_db"

# Global vectorstore (reused)
vectordb = Chroma(
    persist_directory=PERSIST_DIR,
    collection_name="OnboardingConversations",
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


def queryExecutor(employer_number: int, typeofMessage : str, query : str, mediaId : str):
    sorted_history = get_sorted_chat_history(employer_number)

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
        "chat_history": sorted_history
    }

    response = agent_executor.invoke(inputs)

    try:
        assistant_response = response.get('output') or str(response)
        store_conversation(employer_number, f"User: {full_query}\nAssistant: {assistant_response}")
        return assistant_response

    except Exception as e:
        print("Error storing/parsing response:", e, "\nRaw response:", response)
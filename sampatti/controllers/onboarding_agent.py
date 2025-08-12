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
from .onboarding_tools import worker_onboarding_tool, transcribe_audio_tool, send_audio_tool, get_worker_details_tool, process_referral_code_tool, confirm_worker_and_add_to_employer_tool
from .userControllers import send_audio_message
from .whatsapp_message import send_v2v_message
from langchain.memory import VectorStoreRetrieverMemory
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from .whatsapp_message import send_message_user

load_dotenv()

# class ResearchResponse(BaseModel):
#     topic: str
#     summary: str
#     sources: list[str]
#     tools_used: list[str]

groq_api_key = os.environ.get("GROQ_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")
#llm = ChatOpenAI(model="gpt-4o", api_key=openai_api_key)
llm = ChatOpenAI(model="gpt-4.1", api_key=openai_api_key)


# parser = PydanticOutputParser(pydantic_object=ResearchResponse)

# prompt = ChatPromptTemplate.from_messages(
#     [
#         (
#             "system",
#             """
#             You are a research assistant that will help generate a research paper.
#             Answer the user query and use neccessary tools. 
#             Wrap the output in this format and provide no other text\n{format_instructions}
#             """,
#         ),
#         ("placeholder", "{chat_history}"),
#         ("human", "{query}"),
#         ("placeholder", "{agent_scratchpad}"),
#     ]
# ).partial(format_instructions=parser.get_format_instructions())


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
            5. Referral Code (if they have one)

            Ask one item at a time in order. Never ask for both UPI and bank details — only one.

            VALIDATION RULES:
            
            1. WORKER NUMBER:
               - Must be exactly 10 digits
               - If invalid, inform the employer: "Please provide a valid 10-digit worker number"
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
               - Must be a positive number
               
            6. REFERRAL CODE:
               - Optional field but always ask for if any referral code to employer
               - If provided, use 'process_referral_code' to validate the referral code

            PROCESS FLOW:
            - Validate each input before proceeding to the next question
            - Re-ask if validation fails with specific error message
            - Only proceed to next item after current validation passes

            IMPORTANT ONBOARDING SEQUENCE:

            A. IF WORKER EXISTS IN DATABASE (found via get_worker_details):
               1. Show worker details to employer (name, PAN, bank/UPI details - never show vendorId)
               2. Ask for confirmation: "Are these details correct?"
               3. If confirmed:
                  a. Ask for salary (mandatory)
                  b. Ask for referral code: "Do you have a referral code from another employer?"
                  c. If referral code provided, call `process_referral_code` and show: "Worker Referral Code has been Verified and after making your first payment you will receive your referral code and after that when you refer someone they will you will get the cashback amount of one hundred fifty rupees on every successful referral"
                  d. Call `confirm_worker_and_add_to_employer` tool (this handles everything including contract generation)
                  e. Show: "Worker has been successfully onboarded"
               4. If not confirmed, continue with normal onboarding process (B)

            B. IF WORKER NOT IN DATABASE OR DETAILS NOT CONFIRMED:
               1. Ask for UPI or bank details (not both)
               2. Ask for PAN number
               3. Ask for salary
               4. Ask for referral code (optional)
               5. If referral code provided, validate with `process_referral_code`
               6. Call `onboard_worker_employer` with all collected information

            REFERRAL SYSTEM:
            - Always ask for referral code after collecting salary
            - If provided, validate using `process_referral_code`
            - Show cashback message if valid: "Worker Referral Code has been Verified and after making your first payment you will receive your referral code and after that when you refer someone they will you will get the cashback amount of one hundred fifty rupees on every successful referral"

            ## Response Formatting Rules
                - Keep responses conversational and natural for text-to-speech conversion
                - Use short, simple sentences (maximum 15-20 words per sentence)
                - Avoid special characters, brackets, or formatting marks that don't translate to speech
                - Don't use bullet points, numbering, or list formatting - speak naturally
                - Replace "e.g." with "for example" and similar abbreviations with full words
                - Write numbers as words when they're small (one to ten)
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
            - If employer provides same number for worker and employer, inform: "You cannot onboard yourself as a worker"
            - Never show Google Sheet links - just inform that onboarding information has been collected
            - Always use text from chat history (extracted from audios, images, videos, or direct text)
            - Do NOT call `onboard_worker_employer` after using `confirm_worker_and_add_to_employer` - they serve different purposes

            """,
        ),
        ("system", "{chat_history}"),
        ("human", "{query}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)


tools = [worker_onboarding_tool, get_worker_details_tool, process_referral_code_tool, confirm_worker_and_add_to_employer_tool]
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
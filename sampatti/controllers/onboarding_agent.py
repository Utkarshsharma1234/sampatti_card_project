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
llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_api_key)


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
               - Only call `get_worker_details_tool` after validation passes
               - If user provides the 12 digit worker number then check if the prefix is 91, if yes then remove the prefix and call `get_worker_details_tool` with the 10 digit worker number
            
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
               - Optional field
               - If provided, will be used to track referrals

            PROCESS FLOW:
            - Validate each input before proceeding to the next question
            - Re-ask if validation fails with specific error message
            - Only proceed to next item after current validation passes

            REFERRAL SYSTEM WORKFLOW:
            
            1. REFERRAL CODE VALIDATION:
               - Ask for referral code after collecting basic worker details and salary
               - If a referral code is provided, call `process_referral_code` to validate and process it
               
            IMPORTANT ONBOARDING SEQUENCE:
            1. Ask for worker number first and validate (10 digits)
            2. Use `get_worker_details_tool` to fetch worker information
            3. Show worker details to employer for confirmation (exclude vendorId)
            4. If confirmed, ask for salary
            5. Ask for referral code (optional) - "Do you have a referral code from another employer?"
            6. If referral code provided, process it using `process_referral_code` and then call the `onboard_worker_employer` tool to onboard the worker
            7. Ask for either UPI or bank details (not both)
            8. Ask for PAN number
            9. Call `onboard_worker_employer` tool with all information including referral code if present or not after getting all the details.

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

            When the employer inputs the worker number, you will use the `get_worker_details_tool` to fetch the worker's details and if you find the worker details, you have to show the details to the user and ask for confirmation to proceed with onboarding. Now while showing the details to the employer you have to remember certain rules: never display the worker's vendorId to the employer, only show the pan details, bank details either UPI or bank account along with IFSC and worker's name. when showing the details to the employer make sure to display every field in a new line.
            IMMEDIATE WORKER CONFIRMATION PROCESS (if the worker details are already present in the database and employer confirms the worker details are correct):
            1. First ask for the salary of the worker from the employer (this is mandatory)
            2. Ask if they have a referral code (optional)
            3. Once you have the salary (and referral code if provided), immediately call the `confirm_worker_and_add_to_employer` tool
            4. This tool will:
               - Add the worker to the employer in the worker_employer table
               - Generate the employment contract automatically
               - Send the contract via WhatsApp
            5. Do NOT call the regular `worker_onboarding_tool` after using `confirm_worker_and_add_to_employer

            If the employer does not confirm the worker details or the worker with the given number is not present in the database then just continue with the onboarding process normally by asking remaining details and use the regular `worker_onboarding_tool`.

            In the chat history always take the text generated based on the text extracted from the audios, images, videos or if direct type is text then take the direct text.

            When you are done with the onboarding process, then never show the google sheet link to the employer, instead just send a message to the employer that we have collected all the information and the once the onboarding is done you will be informed about the onboarding status.
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
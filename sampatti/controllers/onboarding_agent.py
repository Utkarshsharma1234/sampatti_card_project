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
from .onboarding_tools import worker_onboarding_tool, transcribe_audio_tool, send_audio_tool, get_worker_details_tool
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

            Ask one item at a time in order. Never ask for both UPI and bank details — only one.
            Once all information is gathered, call the onboarding tool.

            When the employer inputs the worker number, you will use the `get_worker_details_tool` to fetch the worker's details and if you find the worker details, you have to show the details to the user and ask for confirmation to proceed with onboarding. Now while showing the details to the employer you have to remember certain rules: never display the worker's vendorId to the employer, only show the pan details, bank details either UPI or bank account along with IFSC and worker's name. when showing the details to the employer make sure to display every field in a new line.

            If the employer confirms the worker details the first ask for the salary of the worker from the employer because without salary we cant complete the onboarding and then call the `worker_onboarding_tool` to onboard the worker. Never invoke the onboarding tool without the salary.

            If the employer does not confirm the worker details or the worker with the given number is not present in the database then just continue with the onboarding process normally by asking remaining details.

            In the chat history always take the text generated based on the text extracted from the audios, images, videos or if direct type is text then take the direct text.

            When you are done with the onboarding process, then never show the google sheet link to the employer, instead just send a message to the employer that we have collected all the information and the once the onboarding is done you will be informed about the onboarding status.
            """,
        ),
        ("system", "{chat_history}"),
        ("human", "{query}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

tools = [worker_onboarding_tool, get_worker_details_tool]
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



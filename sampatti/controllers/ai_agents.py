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
from .tools import worker_onboarding_tool, transcribe_audio_tool, send_audio_tool
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
llm = ChatOpenAI(model="gpt-4o", api_key=openai_api_key)


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

            If the user input type is 'image', follow these steps -->> take the text as the main query -> process the query -> generate the output.

            If the user input type is 'audio', follow these steps -->> use transcribe_audio_tool by giving it media Id and get the text from it -> make this text as the main query -> process the query using the chat history -> get the output.

            Always reason about the type and mediaId fields in the query context and decide autonomously whether to call a tool.

            In the chat history always take the text generated based on the text extracted from the audios, images, videos or if direct type is text then take the direct text.

            """,
        ),
        ("system", "{chat_history}"),
        ("human", "{query}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)


            # Before returning any output, you MUST always call the `send_audio_tool` with the `employerNumber` and the `output`. Only after sending the audio, return the output object.
tools = [worker_onboarding_tool, transcribe_audio_tool, send_audio_tool]
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
    full_query = f"The employer number is {employer_number}. Query: {query}. Type: {typeofMessage}. MediaId: {mediaId}"

    inputs = {
        "query": full_query,
        "chat_history": sorted_history
    }

    response = agent_executor.invoke(inputs)

    try:
        assistant_response = response.get('output') or str(response)
        store_conversation(employer_number, f"User: {full_query}\nAssistant: {assistant_response}")
        # return send_v2v_message(employer_number, assistant_response, template_name="v2v_template")
        return assistant_response

    except Exception as e:
        print("Error storing/parsing response:", e, "\nRaw response:", response)



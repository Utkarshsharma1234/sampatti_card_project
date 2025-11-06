import chromadb, os, argparse
from langchain.text_splitter import RecursiveCharacterTextSplitter
import textwrap, re
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.chat_models import ChatOpenAI

load_dotenv()
openai_api_key = os.environ.get('OPENAI_API_KEY')

chroma_client = chromadb.PersistentClient(path="../../chroma_db")

# llm = ChatOpenAI(name="gpt-4o-mini", api_key=openai_api_key)
openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
llm = ChatOpenAI(
        model="openai/gpt-4o", 
        api_key=openrouter_api_key,
        base_url="https://openrouter.ai/api/v1"
)
embedding_model = OpenAIEmbeddings(model="text-embedding-3-large")

def get_doc_collection():
    doc_collection = chroma_client.get_or_create_collection(name="documents")
    return doc_collection


def get_convo_collection():
    convo_collection = chroma_client.get_or_create_collection(name="conversations")
    return convo_collection


def load_documents(DATA_PATH):
    """
    Loads PDF documents from a directory.

    Args:
        DATA_PATH (str): Path to the directory containing PDF documents.

    Returns:
        list: A list of loaded PDF documents.
    """
    documents = []
    for filename in os.listdir(DATA_PATH):
        file_path = os.path.join(DATA_PATH, filename)
        if os.path.isfile(file_path) and filename.lower().endswith(".pdf"):
            try:
                loader = PyPDFLoader(file_path)
                documents.extend(loader.load())
            except Exception as e:
                print(f"Error loading {filename}: {e}")
    return documents

def split_text(documents):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=100,
        length_function=len,
        add_start_index=True,
    )
    return text_splitter.split_documents(documents)


def store_documents(chunks):
    for i, chunk in enumerate(chunks):
        embedding = embedding_model.embed_query(chunk.page_content)  # Convert text to vector
        doc_collection = get_doc_collection()
        doc_collection.add(
            ids=[f"doc_{i}"],  # Unique ID
            embeddings=[embedding],
            metadatas=[{"source": chunk.metadata.get("source", "unknown")}],
            documents=[chunk.page_content]
        )

    return {"response" : "The documents have been successfully stored."}


def store_conversation(employerNumber, message):
    convo_collection = get_convo_collection()
    convo_collection.add(
        ids=[f"conv_{employerNumber}_{len(convo_collection.get()['ids'])}"],
        documents=[message],
        metadatas=[{"employerNumber": employerNumber}]
    )


def get_conversation_history(employerNumber):
    convo_collection = get_convo_collection()
    results = convo_collection.get(where={"employerNumber": employerNumber})
    return "\n".join(results["documents"]) if results["documents"] else ""


def get_relevant_documents(query):
    query_embedding = embedding_model.embed_query(query)
    doc_collection = get_doc_collection()
    results = doc_collection.query(
        query_embeddings=[query_embedding],
        n_results=20
    )

    # Flatten the list of lists
    documents = [doc for sublist in results["documents"] for doc in sublist]

    return "\n".join(documents) if documents else "No relevant documents found."


def get_response(employerNumber, query):
    conversation_history = get_conversation_history(employerNumber)
    relevant_docs = get_relevant_documents(query)
    
    context = f"""
You are a helpful assistant. 
Given the past conversation and related documents, answer the user query clearly and concisely, in 3 lines using around 60 to 70 words.
Avoid repeating content and focus only on what's most relevant. Be suitable for voice-based output.

Formatting Rules:
- Always respond in a professional and polite manner.
- Always use separate lines for each bullet.
- Each point must start with the bullet '•' and followed by a newline after each point.
- For example:
    • Point 1\n
    • Point 2\n
    • Point 3\n
- Never write multiple bullets on the same line.

Past Conversations:
{conversation_history}

Documents:
{relevant_docs}

User Query: {query}
"""

    response = llm.predict(context)  # Call LLM for response
    store_conversation(employerNumber, f"User: {query}\nSystem: {response}")

    if response.startswith("System:"):
        response = response[len("System:"):].lstrip()

    response = response.replace("\n", " ").strip()
    return {"response": response}


def main(data_path):

    documents = load_documents(data_path)
    chunks = split_text(documents)
    store_documents(chunks)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process documents for RAG pipeline.")
    parser.add_argument("data_path", type=str, help="Path to the document data.")
    
    args = parser.parse_args()
    main(args.data_path)
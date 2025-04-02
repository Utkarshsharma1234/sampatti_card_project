import chromadb, os, argparse
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chat_models import init_chat_model
import textwrap
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.chat_models import ChatOpenAI

load_dotenv()
openai_api_key = os.environ.get('OPENAI_API_KEY')

chroma_client = chromadb.PersistentClient(path="../../chroma_db")

llm = ChatOpenAI(name="gpt-4o-mini", api_key=openai_api_key)
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


def store_conversation(worker_id, message):
    convo_collection = get_convo_collection()
    convo_collection.add(
        ids=[f"conv_{worker_id}_{len(convo_collection.get()['ids'])}"],
        documents=[message],
        metadatas=[{"worker_id": worker_id}]
    )


def get_conversation_history(worker_id):
    convo_collection = get_convo_collection()
    results = convo_collection.get(where={"worker_id": worker_id})
    return "\n".join(results["documents"]) if results["documents"] else ""


def get_relevant_documents(query):
    query_embedding = embedding_model.embed_query(query)
    doc_collection = get_doc_collection()
    results = doc_collection.query(
        query_embeddings=[query_embedding],
        n_results=5
    )

    # Flatten the list of lists
    documents = [doc for sublist in results["documents"] for doc in sublist]

    return "\n".join(documents) if documents else "No relevant documents found."



def get_response(worker_id, query):
    conversation_history = get_conversation_history(worker_id)
    relevant_docs = get_relevant_documents(query)
    
    context = f"Past Conversations:\n{conversation_history}\n\nDocuments:\n{relevant_docs}\n\nUser Query: {query}"

    response = llm.predict(context)  # Call LLM for response
    store_conversation(worker_id, f"User: {query}\nSystem: {response}")

    return {"response" : textwrap.fill(response, width=100)}


def main(data_path):

    documents = load_documents(data_path)
    chunks = split_text(documents)
    store_documents(chunks)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process documents for RAG pipeline.")
    parser.add_argument("data_path", type=str, help="Path to the document data.")
    
    args = parser.parse_args()
    main(args.data_path)
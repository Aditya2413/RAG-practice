from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import os

import warnings
warnings.filterwarnings("ignore", message="import of msvcrt halted")


# Your existing code
data_dir = "data"
all_docs = []

for file in os.listdir(data_dir):
    if file.endswith(".pdf"):
        file_path = os.path.join(data_dir, file)
        print(f"Loading: {file_path}")
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        all_docs.extend(docs)

print(f"Total documents: {len(all_docs)}")


# Better chunk settings for technical papers
text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200)
texts = text_splitter.split_documents(all_docs)
print(f"Total documents: {len(texts)}")

# Embeddings model
embeddings = HuggingFaceBgeEmbeddings(model_name="BAAI/bge-small-en-v1.5")
vector_dim = len(embeddings.embed_query("test"))

# Initialize Qdrant client (in-memory for testing)
client = QdrantClient(path="./local_qdrant")   # Use ":memory:" for testing, or "localhost:6333" for persistent

# Step 2: Create collection with correct vector dimensions
collection_name = "research_papers"

if not client.collection_exists(collection_name):
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE)
    )
    print(f"Created collection: {collection_name}")

# Step 3: Create Qdrant vector store and add documents
vector_store = QdrantVectorStore(
    client=client,
    collection_name=collection_name,
    embedding=embeddings
)

# Add documents to vector store
ids = vector_store.add_documents(documents=texts)
print(f"Added {len(ids)} documents to Qdrant")

# Step 4: Test retrieval
query = "Who proposed the transformer architecture?"
results = vector_store.similarity_search(query, k=3)

print(f"\n🔍 Query: {query}")
for i, doc in enumerate(results, start=1):
    print(f"\nResult {i}:")
    print(f"{doc.page_content[:300]}...")
    print(f"Source: {doc.metadata}")


client.close()



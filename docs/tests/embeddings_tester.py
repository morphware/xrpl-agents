from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
from langchain.embeddings.base import Embeddings
from chromadb.config import Settings 
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_chroma import Chroma
import chromadb
import requests
import os
import hashlib

# Load environment variables
load_dotenv()

os.environ["ANONYMIZED_TELEMETRY"] = "False"

# Base paths
DEFAULT_FILES_DIR = "knowledge/morphware_faq"
DEFAULT_DB_DIR = "knowledge/morphware_db"

# Morphware settings
MORPHWARE_API_KEY = os.getenv("MORPHWARE_API_KEY")
MORPHWARE_API_BASE = os.getenv("MORPHWARE_API_BASE", "https://app.morphware.com/ollama")
MORPHWARE_EMBEDDINGS_MODEL = os.getenv("MORPHWARE_EMBEDDINGS_MODEL", "nomic-embed-text:latest")

class MorphwareEmbeddings(Embeddings):
    """Custom embeddings class for Morphware API"""
    
    def __init__(self, api_base: str, model: str, api_key: str):
        self.api_base = api_base
        self.model = model
        self.api_key = api_key
        print(f"Initialized MorphwareEmbeddings with model: {model}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a list of texts"""
        print(f"Embedding {len(texts)} chunks...")
        embeddings = []
        batch_size = 10  # Process 10 at a time
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            print(f"Processing batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")
            batch_embeddings = [self.embed_query(text) for text in batch]
            embeddings.extend(batch_embeddings)
            
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """Get embeddings for a single piece of text"""
        headers = {
            "Authorization": f"Bearer {MORPHWARE_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": text,
            "truncate": True,
            "options": {},
            "keep_alive": 0
        }

        try:
            response = requests.post(
                f"{self.api_base}/api/embed",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            response_data = response.json()
            if 'embeddings' in response_data and len(response_data['embeddings']) > 0:
                return response_data['embeddings'][0]
            else:
                raise Exception("No embeddings found in response")
                
        except Exception as e:
            print(f"Error processing embedding: {str(e)}")
            print(f"Response status code: {response.status_code if 'response' in locals() else 'N/A'}")
            print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
            raise

class TextEmbedder:
    def __init__(self, files_directory: str = DEFAULT_FILES_DIR, db_directory: str = DEFAULT_DB_DIR):
        """Initialize the Text Embedder system"""
        self.files_directory = Path(files_directory)
        self.db_directory = Path(db_directory)
        
        # Create directories if they don't exist
        self.files_directory.mkdir(parents=True, exist_ok=True)
        self.db_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        
        # Initialize Morphware embeddings
        self.embeddings = MorphwareEmbeddings(
            api_base=MORPHWARE_API_BASE,
            model=MORPHWARE_EMBEDDINGS_MODEL,
            api_key=MORPHWARE_API_KEY
        )
        
        # Initialize ChromaDB
        self.initialize_chroma()

    def initialize_chroma(self):
        """Initialize ChromaDB client and collection"""
        print(f"Setting up ChromaDB at {self.db_directory}...")
        
        self.client = chromadb.PersistentClient(path=str(self.db_directory))
        self.vectorstore = Chroma(
            persist_directory=str(self.db_directory),
            embedding_function=self.embeddings,
            collection_name="morphware_store",
            client_settings=Settings(
                anonymized_telemetry=False
            )
        )
        
        print("ChromaDB initialized successfully")

    def compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 hash of file content"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def load_document(self, file_path: str):
        """Load and split text document into chunks"""
        print(f"Loading document: {file_path}")
        loader = TextLoader(str(file_path))
        documents = loader.load()
        chunks = self.text_splitter.split_documents(documents)
        print(f"Document split into {len(chunks)} chunks")
        return chunks

    def store_document(self, file_path: str) -> bool:
        """Store document in ChromaDB with metadata"""
        try:
            if not os.path.exists(file_path):
                print(f"Error: File not found - {file_path}")
                return False

            file_hash = self.compute_file_hash(file_path)
            chunks = self.load_document(file_path)
            
            # Add metadata to each chunk
            for i, chunk in enumerate(chunks):
                chunk.metadata.update({
                    'file_hash': file_hash,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'source': file_path
                })
            
            # Add documents to vectorstore
            self.vectorstore.add_documents(chunks)
            print(f"Document stored successfully: {file_path}")
            print(f"Hash: {file_hash}")
            print(f"Chunks: {len(chunks)}")
            
            return True
                
        except Exception as e:
            print(f"Error storing document: {str(e)}")
            return False

    def list_stored_documents(self) -> List[Dict]:
        """List all unique documents stored in ChromaDB"""
        try:
            docs = self.vectorstore._collection.get()
            if not docs['ids']:
                return []
            
            unique_docs = {}
            for metadata in docs['metadatas']:
                if metadata and 'source' in metadata:
                    file_path = metadata['source']
                    if file_path not in unique_docs:
                        unique_docs[file_path] = {
                            'file_path': file_path,
                            'file_hash': metadata['file_hash'],
                            'total_chunks': metadata['total_chunks'],
                            'chunk_count': 1
                        }
                    else:
                        unique_docs[file_path]['chunk_count'] += 1
            
            return list(unique_docs.values())
        except Exception as e:
            print(f"Error listing documents: {str(e)}")
            return []

    def process_directory(self):
        """Process all .txt files in the directory, checking for new or modified files"""
        print(f"Checking for new or modified documents in {self.files_directory}...")
        
        # Get existing file hashes from database
        existing_docs = {doc['file_hash']: doc for doc in self.list_stored_documents()}
        
        # Process each .txt file in directory
        files_processed = 0
        files_found = 0
        
        for file in self.files_directory.glob("*.txt"):
            if file.is_file():
                files_found += 1
                current_hash = self.compute_file_hash(str(file))
                
                if current_hash not in existing_docs:
                    print(f"\nNew or modified file detected: {file.name}")
                    if self.store_document(str(file)):
                        files_processed += 1
                else:
                    print(f"File already processed: {file.name}")
        
        print(f"\nFound {files_found} total files")
        print(f"Processed {files_processed} new or modified files")

    def query_documents(self, query: str, k: int = 3) -> List[Dict]:
        """Query the document store and return relevant chunks"""
        try:
            # Perform similarity search
            docs = self.vectorstore.similarity_search_with_score(query, k=k)
            
            # Format results
            results = []
            for doc, score in docs:
                results.append({
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'similarity_score': score
                })
            
            return results
            
        except Exception as e:
            print(f"Error querying documents: {str(e)}")
            return []

def interactive_qa_loop(embedder: TextEmbedder):
    """Interactive Q&A loop for querying the document store"""
    print("\nEntering interactive Q&A mode. Type 'exit' to quit.")
    print("Type 'help' for available commands.")
    
    while True:
        try:
            query = input("\nEnter your question: ").strip()
            
            if query.lower() == 'exit':
                print("Exiting Q&A mode...")
                break
                
            elif query.lower() == 'help':
                print("\nAvailable commands:")
                print("  help  - Show this help message")
                print("  exit  - Exit Q&A mode")
                print("  list  - List all stored documents")
                continue
                
            elif query.lower() == 'list':
                print("\nStored Documents:")
                stored_docs = embedder.list_stored_documents()
                for doc in stored_docs:
                    print(f"\nFile: {doc['file_path']}")
                    print(f"Hash: {doc['file_hash'][:8]}...")
                    print(f"Chunks: {doc['chunk_count']} of {doc['total_chunks']}")
                continue
            
            # Process regular queries
            if query:
                results = embedder.query_documents(query)
                
                if results:
                    print("\nRelevant passages found:")
                    for i, result in enumerate(results, 1):
                        print(f"\n--- Result {i} (Score: {result['similarity_score']:.4f}) ---")
                        print(f"Source: {result['metadata']['source']}")
                        print(f"Content: {result['content']}")
                else:
                    print("No relevant information found.")
            
        except KeyboardInterrupt:
            print("\nExiting Q&A mode...")
            break
        except Exception as e:
            print(f"Error processing query: {str(e)}")

def main():
    embedder = TextEmbedder()
    
    print(f"Processing files from: {DEFAULT_FILES_DIR}")
    print(f"Using database directory: {DEFAULT_DB_DIR}")
    
    # Process all files in directory
    embedder.process_directory()
    
    # List all stored documents
    print("\nStored Documents:")
    stored_docs = embedder.list_stored_documents()
    for doc in stored_docs:
        print(f"\nFile: {doc['file_path']}")
        print(f"Hash: {doc['file_hash'][:8]}...")
        print(f"Chunks: {doc['chunk_count']} of {doc['total_chunks']}")
    
    # Start interactive Q&A loop
    interactive_qa_loop(embedder)

if __name__ == "__main__":
    main()
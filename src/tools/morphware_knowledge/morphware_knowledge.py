from typing import ClassVar, Optional
from langchain.tools import BaseTool
from langchain_chroma import Chroma
from chromadb.config import Settings 
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
import chromadb
from typing import List, Dict, Any
import os
from pydantic import Field

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["OPENTELEMETRY_ENABLED"] = "False"
logger = setup_logger(__name__, 'logs/morphware_db.log')

class MorphwareKnowledgeTool(BaseCustomTool, BaseTool):
    """Tool for querying local MorphwareKnowledgeTool for Morphware FAQ and documentation."""
    name: ClassVar[str] = "MorphwareKnowledgeTool"
    description: ClassVar[str] = """Use this tool to find information in the Morphware knowledge base. 
    This should be your first choice when answering questions about Morphware, before using general knowledge or search."""
    
    db_path: str = Field(default="knowledge/morphware_db")
    embeddings: Any = Field(default=None)
    vectorstore: Optional[Chroma] = Field(default=None)
    
    def __init__(self, **data):
        super().__init__(**data)
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize connection to MorphwareKnowledgeTool."""
        try:
            if not os.path.exists(self.db_path):
                logger.warning(f"Database directory not found at {self.db_path}")
                return None

            # Import and initialize MorphwareEmbeddings
            from src.embeddings import MorphwareEmbeddings
            from src.config import Config

            # Ensure Config has all required settings
            required_settings = [
                'MORPHWARE_EMBEDDINGS_API_BASE',
                'MORPHWARE_EMBEDDINGS_MODEL',
                'MORPHWARE_API_KEY'
            ]
            for setting in required_settings:
                if not hasattr(Config, setting) or not getattr(Config, setting):
                    raise ValueError(f"Missing required configuration: {setting}")

            self.embeddings = MorphwareEmbeddings(
                api_base=Config.MORPHWARE_EMBEDDINGS_API_BASE,
                model=Config.MORPHWARE_EMBEDDINGS_MODEL,  # Fixed: Use correct model parameter
                api_key=Config.MORPHWARE_API_KEY
            )

            # Initialize vectorstore with error handling
            try:
                client = chromadb.PersistentClient(
                    path=self.db_path,
                    settings=Settings(
                        anonymized_telemetry=False
                    )
                )
                
                self.vectorstore = Chroma(
                    client=client,
                    embedding_function=self.embeddings,
                    collection_name="morphware_store",
                )

                # Verify collection exists and is accessible
                if len(self.vectorstore._collection.get()['ids']) == 0:
                    logger.warning("Knowledge base is empty")

                # Verify collection exists and is accessible
                if len(self.vectorstore._collection.get()['ids']) == 0:
                    logger.warning("Knowledge base is empty")
                    
                logger.info("MorphwareKnowledgeTool initialized successfully")
                
            except Exception as e:
                logger.error(f"Error initializing Chroma vectorstore: {str(e)}", exc_info=True)
                raise
            
        except Exception as e:
            logger.error(f"Error initializing MorphwareKnowledgeTool: {str(e)}", exc_info=True)
            raise

    def _run(self, tool_input: str) -> str:
        """Query the MorphwareKnowledgeTool knowledge base."""
        if not tool_input or not tool_input.strip():
            return False, "Error: Empty query provided"
            
        logger.info(f"Querying MorphwareKnowledgeTool with: {tool_input}")
        
        try:
            if not self.vectorstore:
                return "Error: Knowledge base not initialized"

            # Get collection info for debugging
            collection_info = self.vectorstore._collection.get()
            logger.info(f"Collection size: {len(collection_info['ids'])} documents")
            
            # Adjust search parameters
            try:
                results = self.vectorstore.similarity_search_with_score(
                    tool_input,
                    k=min(3, len(collection_info['ids']))  # Don't request more than we have
                )
            except Exception as search_error:
                logger.error(f"Search error: {str(search_error)}")
                # Fallback to basic search if needed
                results = self.vectorstore.similarity_search_with_score(
                    tool_input,
                    k=1
                )
            
            if not results:
                return True, "No relevant information found in the knowledge base."
            
            # Format results with similarity scores
            formatted_results = []
            for doc, score in results:
                # Convert score to similarity percentage (assuming cosine distance)
                similarity = (1 - score) * 100
                
                # Lower similarity threshold to catch more results
                if similarity > 50:  # Reduced from 70% to 50%
                    formatted_results.append(
                        f"[Similarity: {similarity:.1f}%]\nSource: {doc.metadata.get('source', 'Unknown')}\n{doc.page_content}\n"
                    )
                    logger.info(f"Found match with similarity {similarity:.1f}%: {doc.page_content[:100]}...")
            
            if not formatted_results:
                return True, "No sufficiently relevant information found in the knowledge base."
            
            response = "Found relevant information:\n\n" + "\n---\n".join(formatted_results)
            logger.info(f"Returning {len(formatted_results)} relevant results")
            return True, response
                
        except Exception as e:
            error_msg = f"Error querying knowledge base: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def _arun(self, tool_input: str) -> str:
        """Async version of _run"""
        raise NotImplementedError("MorphwareKnowledgeTool does not support async operations")
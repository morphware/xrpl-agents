from typing import ClassVar, Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import Field
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
import requests
from ...config import Config

logger = setup_logger(__name__, 'logs/serper_search.log')

class SerperSearchTool(BaseCustomTool, BaseTool):
    """Tool for searching the internet using Serper API."""
    name: ClassVar[str] = "SerperSearch"
    description: ClassVar[str] = """Use this tool to search the internet for current and factual information. 
    This should be your go-to tool for queries about current events, facts, and general knowledge that isn't specific to Morphware."""
    
    api_key: str = Field(default=None)
    base_url: str = Field(default="https://google.serper.dev/search")
    
    def __init__(self, **data):
        super().__init__(**data)
        self.api_key = Config.SERPER_API_KEY
        if not self.api_key:
            raise ValueError("Serper API key not found in configuration")
    
    def _format_results(self, raw_results: Dict[str, Any]) -> str:
        """Format the raw API results into a readable string."""
        try:
            formatted_results = []
            
            # Process organic search results
            if 'organic' in raw_results:
                for result in raw_results['organic'][:3]:  # Take top 3 results
                    title = result.get('title', 'No title')
                    snippet = result.get('snippet', 'No description available')
                    link = result.get('link', 'No link available')
                    formatted_results.append(f"📌 {title}\n{snippet}\nSource: {link}")
            
            # Process featured snippet if available
            if 'answerBox' in raw_results:
                answer = raw_results['answerBox'].get('answer')
                snippet = raw_results['answerBox'].get('snippet')
                if answer:
                    formatted_results.insert(0, f"💡 Featured Answer: {answer}")
                elif snippet:
                    formatted_results.insert(0, f"💡 Featured Snippet: {snippet}")
            
            # If no results found
            if not formatted_results:
                return "No relevant results found."
            
            return "\n\n".join(formatted_results)
            
        except Exception as e:
            logger.error(f"Error formatting results: {str(e)}", exc_info=True)
            return "Error formatting search results"

    def _run(self, tool_input: str) -> str:
        """Execute the Serper search."""
        logger.info(f"Serper search called with query: {tool_input}")
        
        try:
            # Clean the query
            tool_input = tool_input.strip()
            if not tool_input:
                return "Error: Empty search query"
            
            # Prepare the request
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "q": tool_input,
                "gl": "us",  # Set geography to US
                "hl": "en"   # Set language to English
            }
            
            # Make the request
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            # Process results
            results = response.json()
            formatted_results = self._format_results(results)
            
            logger.info(f"Search completed successfully for: {tool_input}")
            return formatted_results
            
        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg
        except Exception as e:
            error_msg = f"Error performing search: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    
    def _arun(self, tool_input: str) -> str:
        """Async version of run - not implemented."""
        raise NotImplementedError("Async execution is not supported for the SerperSearch tool.")
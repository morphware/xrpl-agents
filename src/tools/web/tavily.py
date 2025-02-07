from typing import ClassVar, Optional, List, Dict, Any
from langchain.tools import BaseTool
from pydantic import Field
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
import requests
from ...config import Config

logger = setup_logger(__name__, 'logs/tavily_search.log')

class TavilySearchTool(BaseCustomTool, BaseTool):
    """Tool for searching the internet using Tavily's AI-optimized search API."""
    name: ClassVar[str] = "TavilySearch"
    description: ClassVar[str] = """Use this tool to search the internet using Tavily's AI-optimized search. 
    It's particularly good for detailed, factual information and current events."""
    
    api_key: str = Field(default=None)
    base_url: str = Field(default="https://api.tavily.com/search")
    search_depth: str = Field(default="advanced")  # Can be 'basic' or 'advanced'
    
    def __init__(self, **data):
        super().__init__(**data)
        self.api_key = Config.TAVILY_API_KEY
        if not self.api_key:
            raise ValueError("Tavily API key not found in configuration")
    
    def _format_results(self, raw_results: Dict[str, Any]) -> str:
        """Format the raw API results into a readable string."""
        try:
            formatted_results = []
            
            # Add answer if available
            if 'answer' in raw_results and raw_results['answer']:
                formatted_results.append(f"🤖 AI Summary: {raw_results['answer']}")
            
            # Process regular results
            if 'results' in raw_results:
                for result in raw_results['results'][:3]:  # Take top 3 results
                    title = result.get('title', 'No title')
                    content = result.get('content', 'No content available')
                    url = result.get('url', 'No link available')
                    score = result.get('score', 0)
                    
                    formatted_results.append(
                        f"📌 {title}\n"
                        f"{content}\n"
                        f"Relevance Score: {score:.2f}\n"
                        f"Source: {url}"
                    )
            
            # If no results found
            if not formatted_results:
                return "No relevant results found."
            
            return "\n\n".join(formatted_results)
            
        except Exception as e:
            logger.error(f"Error formatting results: {str(e)}", exc_info=True)
            return "Error formatting search results"

    def _run(self, tool_input: str) -> str:
        """Execute the Tavily search."""
        logger.info(f"Tavily search called with query: {tool_input}")
        
        try:
            # Clean the query
            tool_input = tool_input.strip()
            if not tool_input:
                return "Error: Empty search query"
            
            # Prepare the request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "query": tool_input,
                "search_depth": self.search_depth,
                "include_answer": True,
                "include_raw_content": False,  # We don't need raw HTML content
                "max_results": 5  # Limit results for conciseness
            }
            
            # Make the request
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=15  # Longer timeout for advanced searches
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
        raise NotImplementedError("Async execution is not supported for the TavilySearch tool.")
        
    @property
    def max_requests_per_minute(self) -> int:
        """Return the rate limit for the API."""
        return 60  # Tavily's default rate limit (adjust based on your plan)
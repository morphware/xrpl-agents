from typing import ClassVar
from langchain_community.tools import DuckDuckGoSearchRun
from pydantic import Field
from ...exceptions import ToolError
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/web_search.log')

class WebSearchTool(BaseCustomTool, BaseTool):  # Added BaseTool inheritance
    """Tool for searching the internet."""
    name: ClassVar[str] = "Search"
    description: ClassVar[str] = "Search the internet for current information."
    search_engine: DuckDuckGoSearchRun = Field(default=None)
    
    def __init__(self):
        super().__init__()
        self.search_engine = DuckDuckGoSearchRun()
    
    def _run(self, tool_input: str) -> str:  # Changed query to tool_input
        """Execute the web search."""
        logger.info(f"Web search called with query: {tool_input}")
        
        try:
            # Clean the query
            tool_input = tool_input.strip()
            if not tool_input:
                return "Error: Empty search query"
                
            # Perform the search
            results = self.search_engine.run(tool_input)
            logger.info(f"Search completed successfully for: {tool_input}")
            
            return results
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return f"Error performing search: {str(e)}"
    
    def _arun(self, tool_input: str) -> str:  # Changed query to tool_input
        """Async version of run - not implemented."""
        raise NotImplementedError("Async execution is not supported for the WebSearch tool.")
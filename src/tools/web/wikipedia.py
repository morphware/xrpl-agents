from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
from ...exceptions import ToolError
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from typing import ClassVar
from pydantic import Field
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/wikipedia.log')

class WikipediaTool(BaseCustomTool, BaseTool):  # Add BaseTool inheritance
    """Tool for querying Wikipedia."""
    name: ClassVar[str] = "Wikipedia"
    description: ClassVar[str] = "Query Wikipedia for detailed information about a topic."
    wikipedia: WikipediaQueryRun = Field(default=None)
    
    def __init__(self):
        super().__init__()
        self.wikipedia = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())
    
    def _run(self, tool_input: str) -> str:  # Changed query to tool_input for consistency
        """Execute the Wikipedia search."""
        logger.info(f"Wikipedia search called with query: {tool_input}")
        
        try:
            # Clean the query
            tool_input = tool_input.strip()
            if not tool_input:
                return False, "Error: Empty search query"
                
            # Perform the search
            results = self.wikipedia.run(tool_input)
            logger.info(f"Wikipedia search completed successfully for: {tool_input}")
            
            return True, results
            
        except Exception as e:
            logger.error(f"Wikipedia search error: {str(e)}", exc_info=True)
            return False, f"Error searching Wikipedia: {str(e)}"
    
    def _arun(self, tool_input: str) -> str:  # Changed query to tool_input
        """Async version of run - not implemented."""
        raise NotImplementedError("Async execution is not supported for the Wikipedia tool.")
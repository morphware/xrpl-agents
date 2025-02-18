from typing import ClassVar
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/direct_llm.log')

class DirectLLMTool(BaseCustomTool, BaseTool):
    """
    Tool for handling direct LLM interactions when no other tools are needed.
    Input should be query.
    """
    name: ClassVar[str] = "direct_llm"
    description: ClassVar[str] = (
        "Use this tool for queries that require direct LLM response without need for other tools. "
        "Input should be query. "
        )
    
    def _run(self, tool_input: str) -> str:
        """Execute the direct LLM interaction."""
        logger.info(f"Processing direct LLM request: {tool_input[:100]}...")  # Log first 100 chars
        
        try:
            logger.info("Returning direct LLM input for processing")
            return True, tool_input
                
        except Exception as e:
            logger.error(f"Error in direct LLM processing: {str(e)}", exc_info=True)
            return False, f"Error in direct LLM processing: {str(e)}"
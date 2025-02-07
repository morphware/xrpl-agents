from abc import ABC, abstractmethod
from typing import Optional, ClassVar
from langchain.tools import BaseTool


class BaseCustomTool(BaseTool):
    """Base class for all custom tools."""
    name: ClassVar[str]  # This fixes the type annotation issue
    description: ClassVar[str]
    
    @abstractmethod
    def _run(self, query: str) -> str:
        """Execute the tool's main functionality."""
        pass

    def _arun(self, query: str) -> str:
        """Async execution - can be implemented by subclasses."""
        raise NotImplementedError("Async execution not implemented for this tool")
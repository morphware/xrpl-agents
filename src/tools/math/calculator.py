from typing import ClassVar
import math
from ...exceptions import ToolError
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/calculator.log')

class CalculatorTool(BaseCustomTool, BaseTool):
    """Tool for performing mathematical calculations."""
    name: ClassVar[str] = "calculator"
    description: ClassVar[str] = "Useful for mathematical calculations. Input should be a mathematical expression (e.g., '5000/10', '2 + 2')."
    
    def _validate_expression(self, expression: str) -> bool:
        """Validate that the expression contains only allowed characters."""
        allowed_symbols = set("0123456789+-*/(). ")
        return all(c in allowed_symbols for c in expression)
    
    def _clean_expression(self, expression: str) -> str:
        """Clean and normalize the expression."""
        # Remove whitespace
        expression = expression.strip()
        # Remove any double spaces
        while "  " in expression:
            expression = expression.replace("  ", " ")
        return expression
    
    def _run(self, tool_input: str) -> str:
        """Execute the calculator tool."""
        logger.info(f"Calculator tool called with expression: {tool_input}")
        
        try:
            # Clean the expression
            cleaned_expr = self._clean_expression(tool_input)
            
            # Validate the expression
            if not self._validate_expression(cleaned_expr):
                logger.warning(f"Invalid characters detected in expression: {tool_input}")
                return False, "Error: Invalid characters in expression. Only numbers and basic operators (+, -, *, /, (), .) are allowed."
            
            # Create a safe local environment for eval
            safe_locals = {"__builtins__": {}, "math": math}
            
            # Evaluate the expression
            result = eval(cleaned_expr, {"__builtins__": {}}, safe_locals)
            
            # Format the result based on type
            if isinstance(result, (int, float)):
                formatted_result = f"{result:,.2f}" if isinstance(result, float) else f"{result:,}"
            else:
                formatted_result = str(result)
            
            logger.info(f"Calculator result: {formatted_result}")
            return True, f"The result of {tool_input} is {formatted_result}"
            
        except ZeroDivisionError:
            logger.error("Division by zero attempted")
            return False, "Error: Division by zero is not allowed"
        except SyntaxError:
            logger.error(f"Invalid syntax in expression: {tool_input}")
            return False, "Error: Invalid syntax in the expression"
        except Exception as e:
            logger.error(f"Calculator error: {str(e)}", exc_info=True)
            return False, f"Error: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        """Async version of run - not implemented."""
        raise NotImplementedError("Async execution is not supported for the Calculator tool.")
import importlib
import pkgutil
from typing import List
from langchain.tools import BaseTool
from .base import BaseCustomTool
import os

def discover_tools() -> List[BaseTool]:
    """Dynamically discover and load all available tools."""
    tools = []
    
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Walk through all subdirectories in the tools package
    for root, dirs, files in os.walk(current_dir):
        # Skip __pycache__ directories
        if '__pycache__' in root:
            continue
            
        # For each Python file
        for file in files:
            if file.endswith('.py') and not file.startswith('_'):
                try:
                    # Convert file path to module path
                    rel_path = os.path.relpath(root, current_dir)
                    if rel_path == '.':
                        module_path = file[:-3]  # Remove .py
                    else:
                        module_path = f"{rel_path.replace(os.sep, '.')}.{file[:-3]}"
                    
                    # Import the module
                    module = importlib.import_module(f".{module_path}", __package__)
                    
                    # Look for tool classes in the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseCustomTool) and 
                            attr != BaseCustomTool):
                            tools.append(attr())
                            
                            # Disabling for demo
                            #print(f"Loaded tool: {attr.__name__}")
                except Exception as e:
                    print(f"Error loading tool module {file}: {e}")
    
    print(f"Loaded {len(tools)} tools")
    print(tools)
    return tools
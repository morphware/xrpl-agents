from langchain.chains import LLMChain
from typing import List, Dict, Any, Optional
from langchain_community.llms import Ollama
from langchain.agents import AgentType, initialize_agent, Tool
from src.memory import GlobalMemory
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from src.utils.logger import setup_debug_logging
from src.config import Config
import logging
import time
import json
import re
import time
import logging


logger = logging.getLogger('src.agent.agent')

@staticmethod
def fix_format(output: str) -> str:
    if 'Action:' in output and 'Action Input:' not in output:
        # Fix missing Action Input
        lines = output.split('\n')
        fixed_lines = []
        for i, line in enumerate(lines):
            fixed_lines.append(line)
            if line.startswith('Action:'):
                tool = line.replace('Action:', '').strip()
                fixed_lines.append(f'Action Input: {tool} query')
        return '\n'.join(fixed_lines)
    return output

class AgentOutputParser:
    @staticmethod
    def validate_format(output: str) -> bool:
        required_elements = ['Thought:', 'Action:', 'Action Input:', 'Observation:']
        steps = output.split('\n')
        current_step = []
        
        for line in steps:
            if line.startswith('Thought:'):
                if current_step:
                    if not all(elem in '\n'.join(current_step) for elem in required_elements):
                        return False
                current_step = [line]
            else:
                current_step.append(line)
                
        return True

class ExecutorAgent:
    def __init__(self, llm: Ollama, memory: GlobalMemory, tools: List[Tool], agent_id: str, system_prompt: Optional[str] = None):
        self.llm = llm
        self.tools = tools
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.output_parser = AgentOutputParser()
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
            input_key="input",
            human_prefix="User",
            ai_prefix="Agent " + self.agent_id
        )
        self.global_memory = memory
        self.agent = self._setup_agent()

    def _reinitialise_agent_llm(self, llm: Ollama, tools: List[Tool] = None):
        self.llm = llm
        if tools:
            self.tools = tools
        self.agent = self._setup_agent()

    def _setup_agent(self):
        if self.system_prompt:
            executor_template = self.system_prompt
        else:
            executor_template = """You are an execution agent that follows plans precisely.
            CRITICAL FORMAT REQUIREMENTS:
            You must ALWAYS use this exact format for each step:
            Thought: [your reasoning]
            Action: [tool name]
            Action Input: [tool input]
            Observation: [tool output]
            
            You must include ALL FOUR elements (Thought/Action/Action Input/Observation) for EVERY step.
            Never skip the Action Input, even if it seems obvious.
            
            Example correct format:
            Thought: I need to search for information about X
            Action: search_tool
            Action Input: query about X
            Observation: [search results]

            Previous conversation context:
            {chat_history}
            
            Available tools:
            {tool_descriptions_str}

            Your task is to:
            1. Follow the provided plan step by step
            2. Use the specified tools in order
            3. Report results after each step
            4. For direct LLM interactions, use the direct_llm tool with the complete query
            5. CRITICAL: Tool outputs MUST be preserved exactly as received
            6. NEVER summarize or modify tool outputs
            7. When using MorphwareKnowledgeTool:
            - If results show high similarity (>85%), use that information directly
            - If results show medium similarity (70-85%), combine with other sources
            - If results show low similarity (<70%), proceed to fallback tools

            IMPORTANT: Always use this exact format when taking actions:
            Thought: I need to [describe your thought process]
            Action: [tool name]
            Action Input: [tool input]
            Observation: [tool output]
            ... (repeat Thought/Action/Action Input/Observation for each step)
            Thought: I now know the final answer
            Final Answer: [your response]
            
            Current plan:
            {plan}

            Request to execute: {input}"""
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(executor_template),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{input}")
        ])



        return initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=Config.MAX_TOOL_ATTEMPTS,
            agent_kwargs={
                "prompt": prompt,
                "memory_prompts": [MessagesPlaceholder(variable_name="chat_history")],
                "input_variables": ["input", "plan", "tool_descriptions_str", "agent_scratchpad", "chat_history"]
            }
        )

    def run(self, user_input: str, tool_list: str = None, context: List[dict]=[], metadata: Any = None) -> str:
        logger.info("ExecutorAgent: Executing plan")
        try:
            plan = metadata
            logger.debug(f"ExecutorAgent: Running with plan:\n{plan}")  
            try:
                execution_result, context = self.run_executor(plan, user_input, context)
            except ValueError as ve:
                if "Invalid Format" in str(ve):
                    formatting_prompt = f"""
                    Previous attempt failed due to incorrect format.
                    Please retry with EXACT format:
                    Thought: [reasoning]
                    Action: [tool]
                    Action Input: [input]
                    Observation: [output]
                    
                    Original request: {user_input}
                    Plan: {str(plan)}
                    """
                    context.append({"role": "system", "content": "Retrying with format correction"})
                    try:
                        execution_result, context = self.run_executor(formatting_prompt, user_input, context)
                    except Exception as retry_error:
                        error_msg = "Error: Failed to process request due to format issues. Please try again."
                        context.append({"role": "system", "content": f"Error: {str(retry_error)}"})
                        logger.error(f"Retry failed: {str(retry_error)}")
                        output_response = {"status": False, "output": None}
                        return user_input, None, context, output_response
                
            # Extract complete output including raw tool outputs
            complete_output = execution_result['output']
            context.append({"role": "system", "content": "Processing execution result"})
            
            if 'intermediate_steps' in execution_result:
                raw_outputs = []
                for step in execution_result['intermediate_steps']:
                    action, output = step
                    step_info = f"Tool {action.tool} Output: {output}"
                    raw_outputs.append(step_info)
                    context.append({"role": "system", "content": step_info})
                raw_output_text = "\n".join(raw_outputs)
                complete_output = f"{complete_output}\n\nRaw Tool Outputs:\n{raw_output_text}"            
                
            self.global_memory.append_ai_message(f"Execution completed: {complete_output}")
            context.append({"role": "assistant", "content": complete_output})
            output_response = {"status": True, "output": complete_output}
            return user_input, complete_output, context, output_response
        except Exception as e:
            logger.error(f"ExecutorAgent error: {str(e)}", exc_info=True)
            raise


    def run_executor(self, plan: str, user_input: str, context: List[dict]=[]) -> Dict[str, Any]:
                    
        tool_descriptions_str = "\n".join([
            f"- {tool.name}: {tool.description}" for tool in self.tools
        ])
        try: 
            result = self.agent.invoke({
                "input": f"Follow the plan exactly\n\nExecute: {user_input}",
                "plan": plan,
                "tool_descriptions_str": tool_descriptions_str
            })
            

            if isinstance(result, str):
                # Validate and fix format if needed
                # need to test this below ....
                if not self.output_parser.validate_format(result):
                    result = self.output_parser.fix_format(result)
                    if not self.output_parser.validate_format(result):
                        raise ValueError("Invalid Format: Unable to fix output format")
                return {"output": result}, context
                
                #return result
            
            if isinstance(result, dict) and 'intermediate_steps' in result:
                raw_outputs = []
                for step in result['intermediate_steps']:
                    action, output = step
                    if not hasattr(action, 'tool_input'):
                        logger.warning(f"Missing tool_input in action: {action}")
                        continue
                    raw_outputs.append(f"Tool: {action.tool}\nInput: {action.tool_input}\nOutput: {output}")
                
                result['raw_tool_outputs'] = "\n\n".join(raw_outputs)
                result['output'] = f"{result['output']}\n\nRaw Tool Outputs:\n{result['raw_tool_outputs']}"
        except ValueError as format_error:
            if "Invalid Format" in str(format_error):
                logger.warning("Invalid format detected, attempting to fix agent output")
                if isinstance(result, str):
                    return {"output": result}, context
                return result, context
            raise
        logger.info("ExecutorAgent: Plan executed successfully")
        return result, context

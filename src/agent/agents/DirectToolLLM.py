from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from langchain.agents import Tool
from src.memory import GlobalMemory
from langchain.memory import ConversationBufferMemory
from langchain_community.llms import Ollama
import logging


logger = logging.getLogger('src.agent.agent')
def debug_separator(title: str = None):
    print("\n" + "="*50)
    if title:
        print(f"== {title} ==")
    print("="*50)

class DirectToolLLM:
    def __init__(self, llm: Ollama, memory: GlobalMemory, tools: List[Tool], agent_id: str, system_prompt: Optional[str] = None):
        self.llm = llm
        self.tools = tools
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            # output_key="output",
            input_key="input",
            human_prefix="User",
            ai_prefix="Agent " + self.agent_id
        )
        self.global_memory = memory
        self.chain = self._setup_chain()

    def _reinitialise_agent_llm(self, llm: Ollama, tools: List[Tool] = None):
        self.llm = llm
        if tools:
            self.tools = tools
        self.chain = self._setup_chain()

    def _setup_chain(self):
        if self.system_prompt:
            direct_tool_template = self.system_prompt
        else:
            direct_tool_template = """You are Morphware's degen agent, tasked with answering a user's question.
            
            Question: {user_query}

            I have queried our knowledge base and found this relevant information:
            {tool_output}

            Please provide a clear, direct answer to the user's question using this information.
            Your response should:
            1. Directly answer the question
            2. Use the provided information effectively
            3. Be conversational and helpful
            4. If appropriate, indicate you can provide more details about specific aspects

            Response:"""


        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(direct_tool_template)
        ])
        return LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory,
            verbose=False
        )


    def _get_tool_by_name(self, tool_name: str) -> Optional[Tool]:
        """Get a tool instance by its name."""
        normalized_name = tool_name.lower().replace('_', '').replace(' ', '')
        return next(
            (tool for tool in self.tools 
             if tool.name.lower().replace('_', '').replace(' ', '') == normalized_name),
            None
        )

    def _handle_direct_tool_response(self, tool_name: str, tool_output: str, user_query: str) -> Optional[str]:
        """Process tool output and generate a response to the user's query."""
        try:
            response = self.chain.run(
                tool_output=tool_output,
                user_query=user_query,
                memory=self.memory.chat_memory
            )
            if response:
                return response.strip()
            return None
            
        except Exception as e:
            logger.error(f"Error handling tool response: {str(e)}")
            return None

    def run(self, user_input: str, tool_list: str = None, context: List[dict]=[], metadata: Any = None) -> str:
        """Execute a tool directly and handle its response."""
        logger.info("DirectToolLLM: Running")
        context.append({"role": "system", "content": "Starting Direct Tool LLM"})

        # tool = self._get_tool_by_name(user_input)
        # if not tool:
        #     logger.warning(f"Tool {user_input} not found, falling back to agent pipeline")
        #     return None, context

        try:
            debug_separator("Attempting Direct Tool Execution")
            if hasattr(metadata, 'direct_tool') and metadata.direct_tool:
                context.append({"role": "system", "content": f"Using direct tool: {metadata.direct_tool}"})
                result = self.run_tool(user_input=user_input, tool_name=metadata.direct_tool, context=context)
                if result is not None:
                    response, context = result
                    self.memory.append_ai_message(f"Direct tool response: {response}")

                    context.append({"role": "assistant", "content": f"Direct tool response: {response}"})
                    output_response = {"status": True, "output": response}
                    return user_input, response, context, output_response
            else:
                logger.info("No direct tool specified, falling back to agent pipeline")
                self.global_memory.append_ai_message(f"DirectToolLLM failed: no direct tool specified, falling back to agent pipeline")
                output_response = {"status": False, "output": None}
                return user_input, None, context, output_response
        except Exception as e:
            logger.error(f"Direct tool execution error: {str(e)}")
            self.global_memory.append_ai_message(f"DirectToolLLM failed: execution error, falling back to agent pipeline")
            output_response = {"status": False, "output": None}
            return user_input, None, context, output_response

    def run_tool(self, user_input: str, tool_name: str = None, context: List[dict]=[]) -> str:
        """Execute a tool directly and handle its response."""
        logger.info("DirectToolLLM: Running")
        context.append({"role": "system", "content": "Starting Direct Tool LLM"})

        tool = self._get_tool_by_name(tool_name)
        if not tool:
            logger.warning(f"Tool {tool_name} not found, falling back to agent pipeline")
            return None
        debug_separator(f"Direct Tool Execution: {tool_name}")
        try:
            result = tool.run(user_input)
            
            if isinstance(result, dict) and 'confidence' in result:
                confidence = result.get('confidence', 0)
                if confidence < 0.6:  # This can be modified etc. Making it rather low for testing purposes.
                    logger.info(f"Tool confidence too low ({confidence}), falling back to agent pipeline")
                    return None, context

                result = result.get('content', result)
            
            elif isinstance(result, str) and 'Similarity:' in result:
                try:
                    similarity = float(result.split('Similarity:')[1].split('%')[0].strip())
                    if similarity < 60: # This can be modified etc. Making it rather low for testing purposes.
                        logger.info(f"Tool similarity too low ({similarity}%), falling back to agent pipeline")
                        return None, context
                except (ValueError, IndexError):
                    pass

            response = self._handle_direct_tool_response(tool_name, result, user_input)
            if response:
                self.global_memory.append_ai_message(f"DirectToolLLM completed: {response}")
                return response, context
                
            logger.info("Couldn't process tool response, falling back to agent pipeline")
            self.global_memory.append_ai_message(f"DirectToolLLM completed: Couldn't process tool response, falling back to agent pipeline")
            return None, context
        
        except Exception as e:
            logger.error(f"Direct tool execution error: {str(e)}")
            self.global_memory.append_ai_message(f"DirectToolLLM failed: execution error, falling back to agent pipeline")
            return None, context


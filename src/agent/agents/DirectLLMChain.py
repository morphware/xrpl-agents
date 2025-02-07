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


class DirectLLMChain:
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
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                "You are Morphware's degen agent. Provide direct, clear responses to the user's questions."
            ),
            HumanMessagePromptTemplate.from_template("{input}")
        ])
        return LLMChain(llm=self.llm, prompt=prompt)

    def run(self,  user_input: str, tool_list: str = None, context: List[dict]=[], metadata: Any = None) -> str:
        try:

            if not metadata.needs_tools and metadata.confidence >= 4:
                logger.info("DirectLLMChain: Running")
                context.append({"role": "system", "content": "Starting Direct LLM"})

                response = self.chain.run(input=user_input)
                self.global_memory.append_ai_message(f"DirectLLM completed: {response}")
                output_response = {"status": True, "output": response}
                return user_input, None, context, output_response
            else:
                logger.info("DirectLLMChain: Not running")
                output_response = {"status": False, "output": None}
                return user_input, None, context, output_response
        except Exception as e:
            logger.info("DirectLLMChain: Not running")
            output_response = {"status": False, "output": None}
            return user_input, None, context, None

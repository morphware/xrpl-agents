from langchain.chains import LLMChain
from langchain_community.llms import Ollama
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from langchain.agents import Tool
from src.memory import GlobalMemory
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from src.utils.logger import setup_debug_logging
import logging
import time
import json
import re
import time
import logging


logger = logging.getLogger('src.agent.agent')




class ReviewerAgent:
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
        self.agent = self._setup_chain()

    def _setup_chain(self):
        if self.system_prompt:
            reviewer_template = self.system_prompt
        else:
            reviewer_template = """You are a Reviewer Agent tasked with ensuring quality and accuracy.

            Below is the conversation so far:
            {memory}

            The ExecutorAgent returned this result:
            {result}

            Provide the final answer in a clear and concise manner. If the result resulted in errors, please send back to the planner agent and re-evaluate if tools are needed or if the plan needs to be adjusted."""

        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(reviewer_template)
        ])

        return LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory,
            verbose=True
        )

    def run(self, request: str, plan: str, result: str, context: List[dict]=[], metadata: Any = None) -> str:
        logger.info("ReviewerAgent: Reviewing execution result")
        context.append({"role": "system", "content": "Starting planning phase"})
        try:
            review = self.chain.run(
                request=request,
                plan=plan,
                result=result,
                memory=self.memory.get_conversation_context()
            )
            logger.info("ReviewerAgent: Review completed")
            context.append({"role": "assistant", "content": review})
            self.global_memory.append_ai_message(f"ReviewerAgent completed: {review}")
            return review
        except Exception as e:
            logger.error(f"ReviewerAgent error: {str(e)}", exc_info=True)
            raise
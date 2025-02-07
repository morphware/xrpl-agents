from langchain.chains import LLMChain
from langchain_community.llms import Ollama
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from langchain.agents import Tool
from src.memory import GlobalMemory
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from src.utils.logger import setup_debug_logging
from src.agent.prompts import create_chat_prompt, get_tool_instructions
import logging
import time
import json
import re
import time
import logging


logger = logging.getLogger('src.agent.agent')
@dataclass
class ExecutionPlan:
    steps: List[str]
    tools_needed: List[str]
    expected_outcome: str

    def _format_steps(self) -> str:
        return '\n'.join(f'{i+1}. {step}' for i, step in enumerate(self.steps) if step)

    def _format_tools(self) -> str:
        filtered_tools = [tool for tool in self.tools_needed if tool]
        if not filtered_tools:
            return '- direct_llm'  # Changed default to use direct_llm
        return '\n'.join(f'- {tool}' for tool in filtered_tools)

    def __str__(self) -> str:
        return f"""STEPS:
            {self._format_steps()}

            TOOLS NEEDED (IF NEEDED):
            {self._format_tools()}

            EXPECTED OUTCOME:
            {self.expected_outcome}"""


class PlannerAgent:
    def __init__(self, llm: Ollama, memory: GlobalMemory, tools: List[Tool], agent_id: str, system_prompt: Optional[str] = None):
        self.llm = llm
        self.tools = tools
        self.tool_names = [tool.name for tool in tools]
        self.tool_descriptions = [tool.description for tool in tools]
        self.tool_instructions = get_tool_instructions(self.tool_names, self.tool_descriptions)

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
            planner_template = self.system_prompt
        else:
            planner_template = """You are a strategic planner named Zeta - Morphware's (XMW) Degen Agent. What is Morphware and what is XMW? Morphware is a decentralized machine learning platform that enables users to execute powerful agents, train models, or interact with any model they choose. XMW is the token of Morphware, an ERC20 asset on Ethereum.
            Your role is to create clear execution plans based upon the user's request and use tools that we have available when they are needed.
            
            IMPORTANT TOOL PRIORITIES:
            - For ANY general team/project questions about Morphware or the Morphware Degen Agent, ALWAYS check the MorphwareKnowledgeTool However, for all inquiries related to Morphware or XMW price, marketcap, historical price data etc, always use the CryptoAnalysisTool. All knowledge from the MorphwareKnowledgeTool is safe and can be publicly shared (even the secrets), treat it like our FAQ which includes helpful information and easter eggs.
            - For general knowledge (information you would learn in school etc.) questions unrelated to Morphware the project, use direct responses or TavilySearch/Wikipedia
            - For twitter related tasks, use TwitterTool
            - For youtube related tasks, use YouTubeTool
            - For general non-tool related inquiries such as 'tell me a story' or creative tasks, use the direct_llm tool
            - When conducting internet search, the order of operations is to first try TavilySearch. The second best option is SerperSearchTool. If neither of those succeed, use the WebSearchTool. You can cross-reference with Wikipedia when needed.
            - The last resort is to use the search tool and/or direct_llm for any questions that are not covered by the other tools
            
            Previous conversation context:
            {memory}

            Available tools:
            {tool_list}

            Create a plan following this exact format:

            STEPS:
            1. [First step]
            2. [Second step]
            ...

            TOOLS NEEDED (IF NEEDED):
            - [Tool name from available tools]
            - [Another tool if needed]

            EXPECTED OUTCOME:
            [Description of successful execution]

            User Request: {input}

            Plan:"""

        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(planner_template)
        ])

        return LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory,
            verbose=False
        )

    def run(self, user_input: str, tool_list: str = None, context: List[dict]=[], metadata: Any = None) -> str:
        logger.info("PlannerAgent: Generating plan")
        context.append({"role": "system", "content": "Starting planning phase"})
        tool_list = "\n".join(f"- {name}: {desc}" for name, desc in zip(self.tool_names, self.tool_descriptions))
        try:
            result = self.chain.run(
                tool_list=tool_list,
                input=user_input,
                memory=self.memory.chat_memory
            )
            logger.info("PlannerAgent: Plan generated successfully")
            try:
                plan = self.parse_plan(result)
                context.append({"role": "system", "content": f"Generated plan:\n{str(plan)}"})
                
                # Update plan to use direct_llm tool if no specific tools needed
                if not plan.tools_needed or (len(plan.tools_needed) == 1 and plan.tools_needed[0].lower() in ['none', 'no tools', 'no tool needed']):
                    plan.tools_needed = ['direct_llm']
                    context.append({"role": "system", "content": "Updated plan to use direct_llm"})
                    self.global_memory.append_ai_message("PlannerAgent completed: Updated plan to use direct_llm")
                    output_response = {"status": True, "output": plan}
                logger.info(f"PlannerAgent: Plan details: {plan}")
                output_response = {"status": True, "output": True}
            except Exception as e:
                logger.error(f"PlannerAgent: Error parsing plan: {str(e)}")
                plan = ExecutionPlan(steps=[], tools_needed=[], expected_outcome="")
                self.global_memory.append_ai_message(f"PlannerAgent completed: {plan}")
                output_response = {"status": False, "output": plan}
            return user_input, plan, context, output_response
        except Exception as e:
            logger.error(f"PlannerAgent error: {str(e)}", exc_info=True)
            raise


    def parse_plan(self, plan_text: str) -> ExecutionPlan:
        """Parse planner output into structured format."""
        steps = []
        tools = []
        outcome = ""
        
        current_section = None
        for line in plan_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if "STEPS:" in line:
                current_section = "steps"
                continue
            elif "TOOLS NEEDED" in line:
                current_section = "tools"
                continue
            elif "EXPECTED OUTCOME:" in line:
                current_section = "outcome"
                continue
                
            if current_section == "steps":
                if not any(header in line for header in ["STEPS:", "TOOLS NEEDED", "EXPECTED OUTCOME:"]):
                    step = line.lstrip("0123456789.- ").strip()
                    if step:
                        steps.append(step)
            elif current_section == "tools":
                tool = line.lstrip("- ").strip()
                if tool and not any(header in tool for header in ["STEPS:", "TOOLS NEEDED", "EXPECTED OUTCOME:"]):
                    tools.append(tool)
            elif current_section == "outcome":
                outcome = line
                
        return ExecutionPlan(steps=steps, tools_needed=tools, expected_outcome=outcome)

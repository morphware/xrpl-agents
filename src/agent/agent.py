from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from langchain.agents import AgentType, initialize_agent, Tool
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from langchain_community.llms import Ollama
from src.memory import GlobalMemory
from src.config import Config
from src.tools import discover_tools
from src.utils.logger import setup_debug_logging
from src.agent.agents.ExecutorAgent import ExecutorAgent
from src.agent.agents.PlannerAgent import PlannerAgent
from src.agent.agents.ReviewerAgent import ReviewerAgent
from src.agent.agents.DirectLLMChain import DirectLLMChain
from src.agent.agents.FilterPromptLLM import PromptFilter
from .prompts import create_chat_prompt, get_tool_instructions
from src.agent.agent_loader import AgentStruct, Agent, AgentsWorkflow
import logging
import time
import json
import re
import time



logger = setup_debug_logging()

def debug_separator(title: str = None):
    print("\n" + "="*50)
    if title:
        print(f"== {title} ==")
    print("="*50)



    




class MultiAgentSystem:
    def _initialize_llm(self):
        """Initialize the LLM based on configuration."""
        return Ollama(
            base_url=Config.OLLAMA_API_BASE,
            model=Config.OLLAMA_MODEL,
            headers={"Authorization": f"Bearer {Config.MORPHWARE_API_KEY}"},
            temperature=0.1,
        )


    def __init__(self, workflow, tools):
        debug_separator("Initializing Multi-Agent Degen System")
        self.tools = tools
        self.llm = self._initialize_llm()
        self.memory = GlobalMemory()
        self.tool_names = [tool.name for tool in tools]
        self.tool_descriptions = [tool.description for tool in tools]
        self.tool_instructions = get_tool_instructions(self.tool_names, self.tool_descriptions)

        self.workflow = AgentsWorkflow.load_from_json(workflow, self.memory, self.tools)
        self.agent_workflow_list = AgentsWorkflow.determine_agent_flow(self.workflow.agents)
        self.agent_paths = AgentsWorkflow.map_agent_paths(agent_workflow_list=self.agent_workflow_list)
        print(f"Agent Workflow: {self.agent_workflow_list}")
        print(f"Agent Paths: {self.agent_paths}")
    def model_reinitialize(self, model: str, tools=None):
        """Reinitialize the LLM model if needed."""
        if tools:
            self.tools = tools
            self.tool_names = [tool.name for tool in tools]
            self.tool_descriptions = [tool.description for tool in tools]
            self.tool_instructions = get_tool_instructions(self.tool_names, self.tool_descriptions)
        self.llm = self._initialize_llm()
        self.prompt_filter.reinitialize(base_url=Config.OLLAMA_API_BASE, api_key=Config.MORPHWARE_API_KEY, model=model, tools=None)
        self.planner.reinitialize(base_url=Config.OLLAMA_API_BASE, api_key=Config.MORPHWARE_API_KEY, model=model, tools=['MorphwareKnowledgeTool'])
        self.executor.reinitialize(base_url=Config.OLLAMA_API_BASE, api_key=Config.MORPHWARE_API_KEY, model=model, tools=self.tool_names)
        if Config.REVIEWER_AGENT_ENABLED:
            self.reviewer.reinitialize(base_url=Config.OLLAMA_API_BASE, api_key=Config.MORPHWARE_API_KEY, model=model, tools=None)
        self.direct_llm.reinitialize(base_url=Config.OLLAMA_API_BASE, api_key=Config.MORPHWARE_API_KEY, model=model, tools=None)
        self.direct_tool.reinitialize(base_url=Config.OLLAMA_API_BASE, api_key=Config.MORPHWARE_API_KEY, model=model, tools=None)
        Config.OLLAMA_MODEL = model

    def process_request(self, user_input: str) -> Dict[str, Any]:
       
        start_time = time.time_ns()
        metrics = {
            "total_duration": 0,
            "load_duration": 0,
            "prompt_eval_count": 0,
            "prompt_eval_duration": 0,
            "eval_count": 0,
            "eval_duration": 0
        }
        
        # Initialize context list to track the conversation and thought process
        context = [
            {"role": "user", "content": user_input}
        ]
        metadata = {'start': None}
        previous_agent = 'start'
        try:
            debug_separator("Starting Request Processing")
            print(f"User Input: {user_input}")
            start_time = int(time.time())
            self.memory.append_user_message(user_input)
            metrics["load_duration"] = time.time_ns() - start_time
            for branch in self.agent_paths:
                for agent_id in branch:
                    if agent_id == 'end':
                        response_text = metadata[previous_agent]
                        break
                    elif agent_id == 'start':
                        logger.info("Starting Agent Workflow")
                        logger.info(f"Inferencing Branch: {branch}")
                        previous_agent = agent_id
                        continue
                    if agent_id in metadata:
                        logger.info(f"Skipping agent {agent_id} as it has already been processed.")
                        previous_agent = agent_id
                        continue
                    eval_start = time.time_ns()
                    user_input, metadata_output, context, output_response = self.workflow.agents[agent_id].agent.run(user_input=user_input,
                                                                                                    metadata=metadata[previous_agent], 
                                                                                                    context=context)
                    metrics["eval_count"] += 1
                    metrics["eval_duration"] += time.time_ns() - eval_start

                    metadata.update({agent_id: metadata_output})
                    context.append({"role": agent_id, "content": f"Agent Analysis: {str(metadata_output)}"})
                    previous_agent = agent_id
                if agent_id == 'end':
                    if output_response.get("status", True):
                        response_text = output_response.get("output")
                        break

            metrics["total_duration"] = time.time_ns() - start_time
            return {
                "model": Config.OLLAMA_MODEL,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                "response": response_text,
                "done": True,
                "context": context,
                **metrics
            }
                    
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.memory.append_ai_message(f"Error occurred: {error_msg}")
            context.append({"role": "system", "content": f"Error: {error_msg}"})
            metrics["total_duration"] = time.time_ns() - start_time
            return {
                "model": Config.OLLAMA_MODEL,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                "response": error_msg,
                "done": True,
                "context": context,
                "chat_id": Config.CHAT_UUID,
                **metrics
            }





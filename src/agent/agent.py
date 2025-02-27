from typing import Dict, Any
from src.memory import GlobalMemory
from src.config import Config
from src.utils.logger import setup_debug_logging
from .prompts import get_tool_instructions
from src.agent.agent_loader import AgentsWorkflow
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

    def __init__(self, workflow, tools):
        debug_separator("Initializing Multi-Agent Degen System")
        self.tools = tools
        self.memory = GlobalMemory()
        self.tool_names = [tool.name for tool in tools]
        self.tool_descriptions = [tool.description for tool in tools]
        self.tool_instructions = get_tool_instructions(self.tool_names, self.tool_descriptions)

        self.workflow = AgentsWorkflow.load_from_json(workflow, self.memory, self.tools)
        self.agent_workflow_list = AgentsWorkflow.determine_agent_flow(self.workflow.agents)
        self.agent_paths = AgentsWorkflow.map_agent_paths(agent_workflow_list=self.agent_workflow_list)
        print(f"Agent Workflow: {self.agent_workflow_list}")
        print(f"Agent Paths: {self.agent_paths}")

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
                    context.append({"role": agent_id, "content": f"Agent Analysis: {str(output_response.get('output'))}"})
                    previous_agent = agent_id
                if agent_id == 'end':
                    if output_response.get("status", True):
                        response_text = output_response.get("output")
                        break

            metrics["total_duration"] = time.time_ns() - start_time
            Config.PROCESS_LOCK = False
            return {
                "model": Config.OLLAMA_MODEL,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                "response": response_text,
                "done": True,
                # "context": context,
                **metrics
            }
                    
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.memory.append_ai_message(f"Error occurred: {error_msg}")
            context.append({"role": "system", "content": f"Error: {error_msg}"})
            metrics["total_duration"] = time.time_ns() - start_time
            Config.PROCESS_LOCK = False
            return {
                "model": Config.OLLAMA_MODEL,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                "response": error_msg,
                "done": True,
                # "context": context,
                "chat_id": Config.CHAT_UUID,
                **metrics
            }





from pydantic import BaseModel
from src.memory import GlobalMemory
from langchain_community.llms import Ollama
from src.tools import discover_tools
from src.config import Config
from typing import Dict
from .prompts import create_chat_prompt, get_tool_instructions
from agent.agents.ExecutorAgent import ExecutorAgent
from agent.agents.ReviewerAgent import ReviewerAgent
from agent.agents.PlannerAgent import PlannerAgent
from agent.agents.DirectLLMChain import DirectLLMChain
from agent.agents.FilterPromptLLM import PromptFilter
from agent.agents.DirectToolLLM import DirectToolLLM
from agent.agents.XRPLToolAgent import XRPLToolAgent
import json

AGENT_TYPES = {
    "prompt_filter": PromptFilter,
    "executor": ExecutorAgent,
    "reviewer": ReviewerAgent,
    "planner": PlannerAgent,
    "direct_llm": DirectLLMChain,
    "direct_tool": DirectToolLLM,
    "xrpl_tool": XRPLToolAgent
}

class AgentStruct(BaseModel):
    type: str
    model: str
    tools: list[str] = []
    system_prompt: str | None = None
    id: str
    input: list[str] = []
    output: list[str] = []
    api_key: str | None = None
    base_url: str | None = None
    priority: int = 0


class Agent:
    def  __init__(self, agent: AgentStruct, global_memory: GlobalMemory, all_tools=discover_tools()):
        self.type = agent.type
        select_tools = agent.tools
        if "all" in select_tools:
            self.tools = all_tools
        else:
            self.tools = [tool for tool in all_tools if tool.name in select_tools]
        self.llm = self._initialize_llm(base_url=agent.base_url, model=agent.model, api_key=agent.api_key)
        self.global_memory = global_memory
        self.tool_names = [tool.name for tool in self.tools]
        self.tool_descriptions = [tool.description for tool in self.tools]
        self.tool_instructions = get_tool_instructions(self.tool_names, self.tool_descriptions)
        self.agent_id = agent.id
        self.system_prompt = agent.system_prompt
        self.input = agent.input
        self.output = agent.output
        self.priority = agent.priority
        self.agent = AGENT_TYPES[agent.type](llm=self.llm, memory=global_memory, tools=self.tools, system_prompt=agent.system_prompt, agent_id=agent.id)
    
    
    def _initialize_llm(self, base_url: str, model: str, api_key: str) -> Ollama:
        """Initialize the LLM based on configuration."""
        return Ollama(
            base_url=base_url,
            model=model,
            headers={"Authorization": f"Bearer {api_key}"},
            temperature=0.1,
        )
    
    def reinitialize(self, base_url: str, api_key: str, model: str, tools: str | None = None, all_tools=discover_tools()):
        self.llm = self._initialize_llm(base_url, model, api_key)
        if tools == "all":
            self.tools = all_tools
        elif tools:
            self.tools = [tool for tool in all_tools if tool.name in tools]
        # self.tools = [tool for tool in all_tools if tool.name in tools]
        self.agent._reinitialise_agent_llm(self.llm, self.tools)




class AgentsWorkflow(BaseModel):
    chat_id: str
    agents: Dict[str, Agent]
    agent_flow: list[str] = []

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def load_from_json(cls, json_file, global_memory: str, all_tools=discover_tools()) -> 'AgentsWorkflow':
        with open(json_file, 'r') as file:
            data = json.load(file)
        
        agents = {agent["id"]: Agent(agent=cls.get_agent_structure(agent), global_memory=global_memory, all_tools=all_tools) for agent in data}
        return cls(chat_id=Config.CHAT_UUID, agents=agents)
    
    @classmethod
    def get_agent_structure(cls, agent_data: str) -> AgentStruct:
        if 'base_url' not in agent_data:
            agent_data['base_url'] = Config.OLLAMA_API_BASE
        if 'api_key' not in agent_data:
            agent_data['api_key'] = Config.MORPHWARE_API_KEY
        return AgentStruct(**agent_data)        
    
    @classmethod
    def map_agent_paths(cls, agent_workflow_list) -> list:
        """
        Maps all paths in the self.agent_workflow_list from 'start' to 'end'.
        Returns a list of paths, where each path is a list of agent IDs including 'start' and 'end'.
        """
        all_paths = []

        def dfs(current_node: str, path: list):
            # When we reach the 'end', record the complete path.
            if current_node == 'end':
                all_paths.append(path)
                return
            # Get next agents for the current node, if any.
            next_agents = agent_workflow_list.get(current_node, [])
            # If no next agents, record the path as is.
            if not next_agents:
                all_paths.append(path)
                return
            # Recurse for each subsequent agent.
            for next_agent in next_agents:
                dfs(next_agent, path + [next_agent])

        # Begin traversal from the starting agents under 'start'
        for agent in agent_workflow_list.get('start', []):
            dfs(agent, ['start', agent])

        return all_paths
    
    @classmethod
    def determine_agent_flow(cls, agents: Dict[str, Agent]) -> Dict[str, list[str]]:
        """Determine the flow of agents based on their input, output, and priority as a graph."""
        agent_graph = {agent_id: [] for agent_id in agents.keys()}
        start_agents = [agent_id for agent_id, agent in agents.items() if 'start' in agent.input]
        end_agents = [agent_id for agent_id, agent in agents.items() if 'end' in agent.output]
        flow = {"start": sorted(start_agents, key=lambda x: agents[x].priority)}
        flow.update(agent_graph)
        
        for agent_id, agent in agents.items():
            sorted_outputs = sorted(agent.output, key=lambda x: agents[x].priority if x in agents else float('inf'))
            for output in sorted_outputs:
                flow[agent_id].append(output)

        return flow
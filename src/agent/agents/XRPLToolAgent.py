import json
import logging
from typing import List, Any, Optional
from langchain.prompts.chat import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.agents import Tool
from langchain_community.llms import Ollama
from src.memory import GlobalMemory
from langchain.chains import LLMChain
import logging, re


logger = logging.getLogger('src.agent.agent')



class XRPLToolAgent:
    """
    A tool LLM agent that infers which XRPL-related tool to run based 
    on the user's query.
    """
    def __init__(
        self,
        llm: Ollama,
        memory: GlobalMemory,
        tools: List[Tool],
        agent_id: str,
        system_prompt: Optional[str] = None
    ):
        self.llm = llm
        self.memory = memory
        self.tools = tools
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.logger = logging.getLogger(__name__)
        self.chain = self._setup_chain()

    def _setup_chain(self):
        # Create a prompt template that instructs the LLM to select a tool.
        prompt_template = """
            You are an XRPL tool selection assistant. Given the user query below, 
            decide which tool from the following list should be executed.\n\n
            List of available tools:\n{tools_list}\n\n
            User Query: {input}\n\n
            Your response should be a JSON object with the keys:\n
            '  "selected_tool": a string representing the tool name to use (or null if none),\n'
            '  "reasoning": a brief explanation of your decision.\n\n'
            '  "formatted_input": the input text formatted for the selected tool.\n\n'
            Output ONLY valid JSON with no additional text."""
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(prompt_template)
        ])
        return LLMChain(
            llm=self.llm,
            prompt=prompt,
            verbose=False
        )

    def _get_tools_list(self) -> str:
        # Generate a list of available tools with their descriptions.
        return "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

    def infer_tool(self, user_input: str) -> dict:
        tools_list = self._get_tools_list()
        # Generate a response using the LLM
        result = self.chain.run(
                input=user_input,
                tools_list=tools_list
            )
        cleaned_json = self._clean_json_string(result)
        try:
            parsed = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            cleaned_json = re.sub(r'[^\x20-\x7E]', '', cleaned_json)
            parsed = json.loads(cleaned_json)
        return parsed

    def run(self, user_input: str, tool_list: str = None, context: List[dict] = [], metadata: Any = None) -> str:
        self.logger.info("XRPLToolAgent: Received query for tool inference")
        context.append({"role": "system", "content": "Starting XRPL tool inference"})
        
        inference_result = self.infer_tool(user_input)
        selected_tool_name = inference_result.get("selected_tool")
        
        if selected_tool_name:
            # Find the selected tool by name (case insensitive)
            tool = next((t for t in self.tools if t.name.lower() == selected_tool_name.lower()), None)
            if tool:
                self.logger.info(f"XRPLToolAgent: Executing tool '{tool.name}'")
                tool_response = tool.run(inference_result.get("formatted_input"))
                context.append({
                    "role": "system",
                    "content": f"Executed tool '{tool.name}' with response: {tool_response}"
                })
                output_response = {"status": True, "output": tool_response, "inference": inference_result}
            else:
                self.logger.error(f"Tool '{selected_tool_name}' not found among registered tools")
                output_response = {"status": False, "output": f"Tool '{selected_tool_name}' not available", "inference": inference_result}
        else:
            self.logger.info("No specific tool selected; using default LLM response")
            # Fallback: use the LLM directly for a response.
            default_response = self.llm.generate([{"role": "user", "content": user_input}])
            context.append({"role": "system", "content": "Default LLM response used"})
            output_response = {"status": True, "output": default_response, "inference": inference_result}

        return user_input, inference_result, context, output_response

    def _clean_json_string(self, text: str) -> str:
        """Clean up the text to extract valid JSON."""
        logger.debug(f"Initial text to clean: {text}")
        
        text = text.strip()
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1:
            text = text[start:end+1]
        else:
            logger.warning("No JSON delimiters found in text")
            return "{}"
        
        text = text.strip()
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace('True', 'true').replace('False', 'false')
        text = text.replace('None', 'null')
        text = re.sub(r',\s*}', '}', text)
        logger.debug(f"Final cleaned text: {text}")
        return text
    

# Example usage (for testing purposes only)
if __name__ == "__main__":
    # This is a placeholder. Replace with actual imports and instances.
    dummy_llm = Ollama(model="llama3.3:70b-instruct-q8_0", api_base="https://app.morphware.com/ollama")
    dummy_memory = GlobalMemory()
    # Assume you have some tool instances that implement the Tool interface
    dummy_tools = []  
    agent = XRPLToolAgent(llm=dummy_llm, memory=dummy_memory, tools=dummy_tools, agent_id="xrpl_tool_agent")
    user_query = "How can I check the balance of my XRPL account?"
    print(agent.run(user_query))
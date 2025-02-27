import json
import logging
from typing import List, Any, Optional
from langchain.prompts.chat import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.agents import Tool
from langchain_ollama import OllamaLLM
from src.memory import GlobalMemory
from langchain.chains import LLMChain
from src.config import Config
from src.utils.kafka import send_to_kafka
import logging, re


logger = logging.getLogger('src.agent.agent')


class XRPLToolAgent:
    """
    A tool LLM agent that infers which XRPL-related tool to run based 
    on the user's query.
    """
    def __init__(
        self,
        llm: OllamaLLM,
        memory: GlobalMemory,
        tools: List[Tool],
        agent_id: str,
        system_prompt: Optional[str] = None,
        backstory: Optional[str] = None
    ):
        self.llm = llm
        self.memory = memory
        self.tools = tools
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.backstory = backstory
        self.logger = logging.getLogger(__name__)
        self.chain = self._setup_chain()

    def _setup_chain(self):
        # Create a prompt template that instructs the LLM to select a tool.
        if self.backstory:
            backstory_template = "This is your agent backstory: \n\n" + self.backstory + "\n\n"
        else:
            backstory_template = ""
        if self.system_prompt:
            prompt_template = backstory_template + self.system_prompt
        else:
            prompt_template = backstory_template + """
            
                Previous conversation context:
                {chat_history}
                
                -----------------------------------------------
                Task at hand:
                Given the user query below, 
                decide which tool from the following list should be executed.\n\n
                List of available tools:\n{tools_list}\n\n
                User Query: {input}\n\n
                Your response should be a JSON object of a list with the keys:\n
                '  "selected_tool": a string representing the tool name to use (or null if none),\n'
                '  "reasoning": a brief explanation of your decision.\n\n'
                '  "formatted_input": the input text formatted for the selected tool.\n\n'
                '  "re_evaluate": a boolean indicating if the tool should be re-evaluated based on the previous tool output.\n\n'
                Output ONLY valid JSON with no additional text.
                Make sure that the tool name is an exact match (case-insensitive) with the tool name in the list.
                Do not suggest a tool that is not in the list.
                understand the history of the conversation and the context of the query. figure out what wallet the user is asking about.
                followup questions may be needed to clarify the user's intent. use the history of the conversation to inform your decision.
                If there are multiplle tools neeeded, add them to the list.
                ONLY ADD TOOLS IF THEY ARE NEEDED.
                If a tool needs to be repeated, add it multiple times to the list.
                If the query part of the query is a question, make the selected tool 'direct_llm'.
                Please follow the tools order based on the query, if the query begins with a question, the first tool should be 'direct_llm'.
                use direct_llm multiple times if needed.
                If unsure about the tool to use, use 'direct_llm' to get a response from the LLM.
                If the query asks for a summary of the tools, use 'summarise' to get a response from the LLM.
                If the tool is the first in the list, set 're_evaluate' to 'False'.
                If the following tool requires a response from the current tool, set 're_evaluate' to 'False' for the current tool and 'True for the following tool.
                A tool can only be re-evaluated if there is a previous tool. If it is the first tool then it cannot be re-evaluated.
                Any placeholder text for re-evaluating should have ** on either side of the text, for example **issuer_address**.
                """
        
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
                tools_list=tools_list,
                chat_history=self.memory.get_conversation_context()
            )
        cleaned_json = self._clean_json_string(result)
        try:
            parsed = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            cleaned_json = re.sub(r'[^\x20-\x7E]', '', cleaned_json)
            parsed = json.loads(cleaned_json)
        return parsed

    def re_eval_tool(self, user_input: str, tool_response: str, inference_res: dict) -> dict:
        tools_list = self._get_tools_list()
        # Combine the user input with the previous tool's output for re-evaluation.
        # Here we assume that the previous tool's output is appended to the user input.
        # If desired, you can change this behavior or add another parameter (e.g., previous_tool_output) instead.
        new_input = f"Here is the original query: {user_input}, \n\nBased on the tool: \n\n{inference_res}\n\n re-evaluate the placeholders that can encapsulated in ** using the output of the previous tool: \n\n{tool_response} \n\n the response should be the same format as the original response but with the update values." 
        # Generate a re-evaluated response using the LLM
        new_input +="""
            Your response should be a JSON object of a list with the keys:\n
            '  "selected_tool": a string representing the tool name to use (or null if none),\n'
            '  "reasoning": a brief explanation of your decision.\n\n'
            '  "formatted_input": the input text formatted for the selected tool.\n\n'
            '  "re_evaluate": a boolean indicating if the tool should be re-evaluated based on the previous tool output.\n\n'
            Output ONLY valid JSON with no additional text.
            """
        result = self.llm.invoke(input=[{"role": "ai", "content": self.memory.get_conversation_context()}, {"role": "user", "content": new_input}])

        cleaned_json = self._clean_json_string(result)
        try:
            parsed = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            cleaned_json = re.sub(r'[^\x20-\x7E]', '', cleaned_json)
            parsed = json.loads(cleaned_json)
        return parsed[-1]

    def run(self, user_input: str, tool_list: str = None, context: List[dict] = [], metadata: Any = None) -> str:
        self.logger.info("XRPLToolAgent: Received query for tool inference")
        send_to_kafka(Config.kafka_out, Config.KAFKA_OUT_TOPIC, "XRPLToolAgent: Received query for tool inference", key=Config.REQUEST_ID)
        context.append({"role": "system", "content": "Starting XRPL tool inference"})
        SUMMARISE = False

        inference_result = self.infer_tool(user_input)
        # send_to_kafka(Config.kafka_out, Config.KAFKA_OUT_TOPIC, inference_result, key=Config.REQUEST_ID)
        selected_tool_names = [inference_res.get("selected_tool") for inference_res in inference_result]
        tool_responses = []
        output_response = {"status": True}
        if len(selected_tool_names) > 0:
            # Find the selected tool by name (case insensitive)
            for selected_tool_name, inference_res, tool_idx in zip(selected_tool_names, inference_result, range(len(selected_tool_names))):
                if selected_tool_name is None:
                    self.logger.error("Selected tool name is None in inference result.")
                    tool = None
                elif selected_tool_name.lower() == "summarisellm":
                    SUMMARISE = True
                    tool = None
                else:
                    tool = next((t for t in self.tools if t.name.lower() == selected_tool_name.lower()), None)
                if tool:
                    if inference_res.get("re_evaluate") and tool_idx > 0:
                        self.logger.info(f"XRPLToolAgent: Re-evaluating tool '{tool.name}' in step {tool_idx+1}")
                        send_to_kafka(Config.kafka_out, Config.KAFKA_OUT_TOPIC, f"XRPLToolAgent: Re-evaluating tool '{tool.name}' in step {tool_idx+1}")
                        inference_res = self.re_eval_tool(inference_res.get("formatted_input"), tool_responses[-1], inference_res)
                    self.logger.info(f"XRPLToolAgent: Executing tool '{tool.name}' in step {tool_idx+1}")
                    send_to_kafka(Config.kafka_out, Config.KAFKA_OUT_TOPIC, f"XRPLToolAgent: Executing tool '{tool.name}' in step {tool_idx+1}", key=Config.REQUEST_ID)
                    if tool.name == "direct_llm":
                        tool_response = self.llm.invoke(input=[{"role": "system", "content": self.backstory}]+    
                                                            self.memory.chat_memory.messages+
                                                            [{"role": "user", "content": inference_res.get("formatted_input")}])

                        output = f"Step {tool_idx+1} - \n{tool_response}\n"
                    else:
                        status, tool_response = tool.run(inference_res.get("formatted_input"))
                        status_str = "succeeded" if status else "failed"
                        output = f"Step {tool_idx+1} - Executed tool {tool.name} which ({status_str}) with the response: \n{tool_response}\n"
                    tool_responses.append(output)
                    send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, message=output, key=Config.REQUEST_ID)
                    context.append({
                        "role": "system",
                        "content": output
                    })
                    self.memory.append_ai_message(output)
                    
                    # output_response = {"status": status, "output": tool_response, "inference": inference_result}
                else:
                    self.logger.error(f"Tool '{selected_tool_name}' not found among registered tools")
                    tool_response = self.llm.invoke(input=[{"role": "system", "content": self.backstory}]+    
                                    self.memory.chat_memory.messages+
                                    [{"role": "user", "content": inference_res.get("formatted_input")}])

                    output = f"Step {tool_idx+1} - \n{tool_response}\n"

                    tool_responses.append(f"Step {tool_idx+1} - {output}")
                    output_response["status"] = True
                    send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, message=output, key=Config.REQUEST_ID)
            # Generate a summary of tool responses using the LLM
            summary_output = "\n\n".join(tool_responses) if tool_responses else "No tool responses executed."
            if SUMMARISE:
                summary_prompt = f"briefly summarize the results: \n\n{summary_output}"
                summary_output = self.llm.invoke(input=[{"role": "user", "content": summary_prompt}])
                context.append({"role": "system", "content": summary_output})
                send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, message=summary_output, key=Config.REQUEST_ID)
            # Append the summary to output_response
            output_response.update({"output": summary_output,"inference": tool_responses})
        else:
            self.logger.info("No specific tool selected; using default LLM response")
            # Fallback: use the LLM directly for a response.
            default_response = self.llm.invoke(input=[{"role": "system", "content": self.backstory},{"role": "ai", "content": self.memory.get_conversation_context()},{"role": "user", "content": user_input}])
            context.append({"role": "system", "content": default_response})
            self.memory.append_ai_message(default_response)

            output_response = {"status": True, "output": default_response, "inference": tool_responses}
            send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, message=default_response, key=Config.REQUEST_ID)


        return user_input, tool_responses, context, output_response

    def _clean_json_string(self, text: str) -> str:
        """Clean up the text to extract valid JSON."""
        logger.debug(f"Initial text to clean: {text}")
        
        text = text.strip()
        start = text.find('[')
        end = text.rfind(']')
        
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
    dummy_llm = OllamaLLM(model="llama3.3:70b-instruct-q8_0", api_base="https://app.morphware.com/ollama")
    dummy_memory = GlobalMemory()
    # Assume you have some tool instances that implement the Tool interface
    dummy_tools = []  
    agent = XRPLToolAgent(llm=dummy_llm, memory=dummy_memory, tools=dummy_tools, agent_id="xrpl_tool_agent")
    user_query = "How can I check the balance of my XRPL account?"
    print(agent.run(user_query))
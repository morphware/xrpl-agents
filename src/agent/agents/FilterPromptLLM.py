from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from langchain.agents import AgentType, initialize_agent, Tool
from src.memory import GlobalMemory
from langchain.memory import ConversationBufferMemory
from langchain_community.llms import Ollama
from src.config import Config
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json

import logging, re


logger = logging.getLogger('src.agent.agent')

@dataclass
class FilterResponse:
    needs_tools: bool
    confidence: int  # 5=certain, 4=highly confident, 3=confident, 2=not confident, 1=very unconfident
    reasoning: str
    direct_tool: Optional[str] = None  # Name of tool to use directly, if applicable
    
    def __str__(self):
        confidence_map = {
            5: "certain",
            4: "highly confident",
            3: "confident",
            2: "not confident",
            1: "very unconfident"
        }
        direct_tool_str = f"\nDirect Tool: {self.direct_tool}" if self.direct_tool else ""
        return (
            f"Need tools: {self.needs_tools}\n"
            f"Confidence: {self.confidence} ({confidence_map.get(self.confidence, 'unknown')})\n"
            f"Reasoning: {self.reasoning}"
            f"{direct_tool_str}"
        )


class PromptFilter:
    def __init__(self, llm: Ollama, memory: GlobalMemory, tools: List[Tool], agent_id: str, system_prompt: Optional[str] = None):
        self.llm = llm
        self.tools = tools
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
            input_key="input",
            human_prefix="User",
            ai_prefix="Agent " + self.agent_id
        )
        self.global_memory = memory
        self.chain = self._setup_chain()

    '''
    Classification Rules:
            1. For genearl Morphware (XMW) information such as FAQ re-related queries:
            - Set needs_tools = true
            - Set direct_tool = "MorphwareKnowledgeTool"
            - Set confidence = 5
            2. For crypto related questions such as pricing:
            - Set needs_tools = true
            - Set direct_tool = null
            - Set confidence = 4
            3. For general web-related queries such as "what is the capital of France":
            - Set needs_tools = true
            - Set direct_tool = "tavily_search"
            - Set confidence = 4-5
    '''


    '''
    # Commenting these classification rules out for initial release
    1. For general Morphware (XMW) information such as FAQ re-related queries:
            - Set needs_tools = true
            - Set direct_tool = null
            - Set confidence = 5
    2. For crypto related questions such as pricing:
    - Set needs_tools = true
    - Set direct_tool = null
    - Set confidence = 4
    '''

    '''
    If the user's query is blank or similar to hi, hello, etc:
    - Set needs_tools = false
    - Set direct_tool = null
    - Set confidence = 5
    '''


    '''
    # Works and stable
    Classification Rules:
            For general web-related queries such as "what is the capital of France":
            - Set needs_tools = true
            - Set direct_tool = "tavily_search"
            - Set confidence = 4-5

            For any questions related to Morphware, XMW, crypto currency, or math related questions:":
            - Set needs_tools = true
            - Set direct_tool = "null"
            - Set confidence = 5


            For any questions related to Morphware, XMW, crypto currency, or math related questions:":
            - Set needs_tools = true
            - Set direct_tool = "null"
            - Set confidence = 5


    '''
    def _setup_chain(self):
        if self.system_prompt:
            filter_template = self.system_prompt
        else:
            # Completely changing the filter as we are having consistency issues
            filter_template = """You are a request classifier for Morphware - A decentralized AI platform. The token for Morphware is XMW. You're responsible for determining how to handle user queries efficiently.

            User Query: {input}

            Your task is to analyze this query and respond with a JSON object in this EXACT format:
            {{
                "needs_tools": true/false,
                "confidence": <number 1-5>,
                "reasoning": "<brief explanation>",
                "direct_tool": "<tool name or null>"
            }}

            Classification Rules:
            For all queries related to crypto prices or market cap::
            - Set needs_tools = true
            - Set direct_tool = null
            - Set confidence = 5

            For general knowledge queries such as "what is the capital of France" (NOTE: DO NOT USE THIS FOR LIVE PRICING or MARKETCAP QUERIES):
            - Set needs_tools = true
            - Set direct_tool = "tavily_search"
            - Set confidence = 4-5

            For Morphware general knowledge questions such as team members, business purpose, and business background queries (NOTE: NOT price or market cap related):
            - Set needs_tools = true
            - Set direct_tool = "MorphwareKnowledgeTool"
            - Set confidence = 5

            For on-chain data (such as transaction details, block details, etc.) calculator, youtube, twitter, or telegram requests requests:
            - Set needs_tools = true
            - Set direct_tool = null
            - Set confidence = 5
            

            IMPORTANT: Only include the raw JSON in your response with no additional text or explanations.
            For example:
            {{"needs_tools":true,"confidence":5,"reasoning":"Where is Egypt","direct_tool":"null"}}"""

        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(filter_template)
        ])
        return LLMChain(
            llm=self.llm,
            prompt=prompt,
            verbose=False
        )
    
    def _reinitialise_agent_llm(self, llm: Ollama, tools: List[Tool] = None):
        self.llm = llm
        if tools:
            self.tools = tools
        self.chain = self._setup_chain()

    def run(self,  user_input: str, tool_list: str = None, context: List[dict]=[], metadata: Any = None) -> str:
        logger.info("PromptFilter: Filtering Prompt")
        context.append({"role": "system", "content": "Starting prompt filter"})
        bypass = False

        if bypass:
            response = FilterResponse(
                needs_tools=True,
                confidence=5,
                reasoning="null",
                direct_tool="null",
            )
            self.global_memory.append_ai_message(f"FilterResponse completed: {response}")
            output_response = {"status": False, "output": response}
            return user_input, response, context, output_response
        try:
            result = self.chain.run(
                input=user_input,
            )
            cleaned_json = self._clean_json_string(result)
            try:
                parsed = json.loads(cleaned_json)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                cleaned_json = re.sub(r'[^\x20-\x7E]', '', cleaned_json)
                parsed = json.loads(cleaned_json)

            response = FilterResponse(
            needs_tools=bool(parsed.get('needs_tools', False)),
            confidence=int(parsed.get('confidence', 1)),
            reasoning=str(parsed.get('reasoning', "Error parsing response")),
            direct_tool=parsed.get('direct_tool')
            )
            logger.debug(f"Created FilterResponse: {response}")
            self.global_memory.append_ai_message(f"FilterResponse completed: {response}")
            output_response = {"status": True, "output": response}
            return user_input, response, context, output_response
        except Exception as e:
            logger.error(f"Filter error: {str(e)}", exc_info=True)
            response = FilterResponse(
                needs_tools=False,
                confidence=1,
                reasoning=f"Filter error: {str(e)}",
                direct_tool=None
            )
            self.global_memory.append_ai_message(f"FilterResponse completed: {response}")
            output_response = {"status": False, "output": response}
            return user_input, response, context, output_response
            
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
    

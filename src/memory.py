import logging
from langchain.schema import HumanMessage, AIMessage
from langchain.memory.chat_memory import BaseChatMemory
from langchain.memory.chat_message_histories.in_memory import ChatMessageHistory

logger = logging.getLogger(__name__)

class GlobalMemory(BaseChatMemory):
    """
    A custom memory class that stores the conversation in a ChatMessageHistory.
    """

    def __init__(self, return_messages: bool = False):
        super().__init__(chat_memory=ChatMessageHistory(), return_messages=return_messages)

    @property
    def memory_variables(self):
        return ["history"]

    def load_memory_variables(self, inputs: dict):
        return {
            "history": self.chat_memory.messages
        }

    def save_context(self, inputs: dict, outputs: dict) -> None:
        if "input" in inputs:
            self.chat_memory.add_user_message(inputs["input"])
        if "output" in outputs:
            self.chat_memory.add_ai_message(outputs["output"])

    def clear(self) -> None:
        self.chat_memory.clear()

    def append_user_message(self, message: str):
        logger.debug(f"Appending user message to memory: {message}\n\n")
        self.chat_memory.add_user_message(message)

    def append_ai_message(self, message: str):
        logger.debug(f"Appending AI message to memory: {message}\n\n")
        self.chat_memory.add_ai_message(message)

    def get_conversation_context(self) -> str:
        conversation_str = ""
        for msg in self.chat_memory.messages:
            if isinstance(msg, HumanMessage):
                conversation_str += f"User: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                conversation_str += f"AI: {msg.content}\n"
        return conversation_str


from pydantic import BaseModel, Field
from typing import Literal, Optional

from enum import Enum


# ---------------- Message Types ----------------


class MessageType(str, Enum):
    CHAT_COMPLETION = "chat_completion"
    TX_SEND_XRP = "tx_send_xrp"
    TX_SEND_ETH = "tx_send_eth"
    CHAT_COMPLETION_RESULT = "chat_completion_result"
    TX_SEND_RESULT = "tx_send_result"
    INFO_MESSAGE = "info_message"
    
    


class XrpTransactionTypes(str, Enum):
    PAYMENT = "payment"


XrpAddress = str
EthAddress = str

# ---------------- Request Types ----------------


class ChatCompletionRequest(BaseModel):
    prompt: str
    model: str
    agent_id: str
    chat_id: str | None = None
    msg_type: Literal[MessageType.CHAT_COMPLETION] = MessageType.CHAT_COMPLETION

class XrpTransactionRequest(BaseModel):
    raw_tx: str
    msg_type: Literal[MessageType.TX_SEND_XRP] = MessageType.TX_SEND_XRP
    tx_id: str
    
class EthTransactionRequest(BaseModel):
    from_address: EthAddress
    to_address: EthAddress
    asset: Literal["ETH", "XMW"]
    amount: str
    msg_type: Literal[MessageType.TX_SEND_ETH] = MessageType.TX_SEND_ETH
    

# ---------------- Response Types ----------------


class ChatCompletionResponse(BaseModel):
    msg_key: str
    inference_result: str
    msg_type: Literal[MessageType.CHAT_COMPLETION_RESULT] = (
        MessageType.CHAT_COMPLETION_RESULT
    )
    

class TxSendResponse(BaseModel):
    msg_key: str
    tx_id: str 
    tx_hash: str
    tx_status: Literal["PENDING", "SUCCESS", "FAILED"]
    msg_type: Literal[MessageType.TX_SEND_RESULT] = MessageType.TX_SEND_RESULT
    

class WebsocketInfo(BaseModel):
    msg_type: Literal[MessageType.INFO_MESSAGE] = MessageType.INFO_MESSAGE
    message: str
    

WebsocketRequest = ChatCompletionRequest | XrpTransactionRequest | EthTransactionRequest

WebsocketResponse = ChatCompletionResponse | TxSendResponse

WebsocketPayload = WebsocketRequest | WebsocketResponse | WebsocketInfo

# ---------------- Main Type ----------------


class WebsocketMessage(BaseModel):
    msg_type: MessageType
    payload: WebsocketPayload = Field(..., discriminator="msg_type")
    request_key: str
        
    @classmethod
    def get_payload(cls, msg_type: MessageType, payload: str) -> WebsocketPayload:
        mapping = {
            MessageType.CHAT_COMPLETION: ChatCompletionRequest,
            MessageType.TX_SEND_XRP: XrpTransactionRequest,
            MessageType.TX_SEND_ETH: EthTransactionRequest,
            MessageType.CHAT_COMPLETION_RESULT: ChatCompletionResponse,
            MessageType.TX_SEND_RESULT: TxSendResponse,
            MessageType.INFO_MESSAGE: WebsocketInfo
        }
        try:
            payload_cls = mapping[msg_type]
        except KeyError:
            raise ValueError("Invalid message type")
        return payload_cls.model_validate_json(payload)

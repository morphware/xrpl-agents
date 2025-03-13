from dataclasses import dataclass
from typing import Literal, TypeAlias, Dict, Any
from xrpl.models.transactions import Transaction
import json
from dataclasses import asdict


# ---------------- Chat Completions ----------------
ChatCompletionRequestType = Literal["chat_completion"]


@dataclass(frozen=True)
class ChatCompletionRequest:
    request_type: ChatCompletionRequestType
    prompt: str
    model: str
    agent_id: str
    chat_id: str | None = None


# ----------------  Transactions -------------------
XrplTransactionRequestType = Literal["tx_sign_xrp"]
XrplTransactionType = Transaction
@dataclass()
class XrplTransactionRequest:
    id: str
    request_type: XrplTransactionRequestType
    transaction_data: XrplTransactionType
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)
    def __post_init__(self):
        # If transaction_data is an instance of Transaction, convert it to its JSON-serializable form.
        if isinstance(self.transaction_data, Transaction):
            self.transaction_data = self.transaction_data.to_xrpl()
    
EthTransactionRequestType = Literal["tx_sign_eth"]
EthAddress: TypeAlias = str


@dataclass(frozen=True)
class EthTransactionRequest:
    request_type: EthTransactionRequestType
    from_address: EthAddress
    to_address: EthAddress
    asset: Literal["ETH", "XMW"]
    amount: str


TxSignRequestType = XrplTransactionRequestType | EthTransactionRequestType


@dataclass(frozen=True)
class TxSignRequest:
    request_type: TxSignRequestType
    payload: XrplTransactionRequest | EthTransactionRequest


# ------------------------------------------------------------
# ----------------  Main Request Type ----------------
# ------------------------------------------------------------
@dataclass(frozen=True)
class RequestType:
    request_type: ChatCompletionRequestType | TxSignRequestType
    payload: ChatCompletionRequest | TxSignRequest


# ------------------------------------------------------------
# ----------------  Chat completion response ----------------
# ------------------------------------------------------------

ChatCompletionResponseType = Literal["chat_completion_result"]


@dataclass(frozen=True)
class ChatCompletionResponse:
    request_key: str
    response_type: ChatCompletionResponseType
    inference_result: str


# ------------------------------------------------------------
# ----------------  Transaction responses ----------------
# ------------------------------------------------------------

TxSendResponseType = Literal["tx_send_result"]


@dataclass(frozen=True)
class TxSendResponse:
    request_key: str
    response_type: TxSendResponseType
    tx_hash: str


# ------------------------------------------------------------
# ----------------  Main Response Type ----------------
# ------------------------------------------------------------


@dataclass(frozen=True)
class ResponseType:
    request_key: str
    response_type: ChatCompletionResponseType | TxSendResponseType
    payload: ChatCompletionResponse | TxSendResponse
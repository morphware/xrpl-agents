import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import CheckCancel
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLCheckCancelTool(BaseCustomTool, BaseTool):
    """
    Tool for canceling a Check on the XRPL.
    
    Input should be the Check ID to cancel.
    
    Only the Check sender or the intended recipient can cancel a Check.
    Checks can also be canceled after they expire.
    """
    name: ClassVar[str] = "XRPLCheckCancel"
    description: ClassVar[str] = (
        "Cancel a Check on the XRPL. "
        "Input should be the Check ID. "
        "You can only cancel a Check if you are the sender, the destination, "
        "or if the Check has expired."
    )
    
    def _validate_check_id(self, check_id: str) -> bool:
        """Validate if check_id appears to be correctly formatted."""
        return (
            isinstance(check_id, str) and
            len(check_id) == 64 and
            all(c in '0123456789ABCDEF' for c in check_id.upper())
        )
    
    def _run(self, tool_input: str) -> str:
        try:
            check_id = tool_input.strip()
            
            # Validate check id
            if not self._validate_check_id(check_id):
                return False, f"Invalid Check ID: {check_id}. Check ID should be a 64-character hexadecimal string."
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create CheckCancel transaction
            check_cancel_tx = CheckCancel(
                account=Config.XRP_WALLET.address,
                check_id=check_id
            )

            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "transaction": check_cancel_tx.blob()
                    }
                )
                
                send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, 
                             message=payload, key=Config.REQUEST_ID, msg_type='tx_send_xrp')
                
                match = False
                while not match:
                    response, key = get_kafka_latest_message(
                        Config.consume_from_kafka(Config.kafka_in, Config.KAFKA_IN_TOPIC),
                        message_id=Config.REQUEST_ID
                    )
                    if tx_id == response.tx_id:
                        match = True
                    else:
                        match = False
                
                if isinstance(response, Exception):
                    return False, f"Error processing message: {str(response)}"
                
                if "SUCCESS" in response.tx_status:
                    return True, f"Check canceled successfully! Check ID: {check_id}"
                else:
                    return False, f"Check cancellation failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error canceling Check: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCheckCancelTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLCheckCancelTool()
    
    # Example check ID - replace with a real one
    example_input = "C1B3B7D10A2670100C08AA1B30E4088640AD92728A1E347E9BB52A3B3AEE80E8"
    
    result = tool._run(example_input)
    print(result)
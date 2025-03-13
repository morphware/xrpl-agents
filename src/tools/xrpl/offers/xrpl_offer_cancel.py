import uuid
import json
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import OfferCancel
from xrpl import transaction as tx
from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message

class XRPLOfferCancelTool(BaseCustomTool, BaseTool):
    """
    Tool for canceling an offer on the XRPL.
    Input should be the sequence number of the offer to cancel.
    """
    name: ClassVar[str] = "XRPLOfferCancel"
    description: ClassVar[str] = (
        "Cancel an offer (order) on the XRPL. "
        "Input should be the sequence number of the offer to cancel. "
        "You can find sequence numbers using the XRPLGetAccountOffers tool."
    )

    def _validate_sequence(self, sequence: str) -> bool:
        """Check if the input appears to be a valid sequence number."""
        try:
            seq_num = int(sequence)
            return seq_num > 0
        except (ValueError, TypeError):
            return False

    def _run(self, tool_input: str) -> str:
        try:
            # Clean the input
            offer_sequence = tool_input.strip()
            
            # Validate input
            if not self._validate_sequence(offer_sequence):
                return False, f"Invalid sequence number: {offer_sequence}. Please provide a valid sequence number."
            
            # Convert to integer
            offer_sequence = int(offer_sequence)
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Create cancel transaction
            cancel_tx = OfferCancel(
                account=Config.XRP_WALLET.address,
                offer_sequence=offer_sequence
            )

            try:
                tx_id = str(uuid.uuid4())
                # Create transaction request payload
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "transaction": cancel_tx.blob()
                    }
                )
                # Send to Kafka
                send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, 
                             message=payload, key=Config.REQUEST_ID, msg_type='tx_send_xrp')
                
                # Wait for response
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
                
                # Process response
                if isinstance(response, Exception):
                    return False, f"Error processing message: {str(response)}"
                
                if "SUCCESS" in response.tx_status:
                    return True, f"Offer cancellation successful - offer sequence: {offer_sequence}"
                else:
                    return False, f"Offer cancellation failed: {response}"
                    
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Submit failed: {e}"
                
        except Exception as e:
            return False, f"Error canceling offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLOfferCancelTool.")


if __name__ == "__main__":
    # Example usage
    tool = XRPLOfferCancelTool()
    example_input = "12345"  # Replace with a real offer sequence
    result = tool._run(example_input)
    print(result)
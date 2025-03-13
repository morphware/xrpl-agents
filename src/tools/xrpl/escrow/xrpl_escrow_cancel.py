import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import EscrowCancel
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLEscrowCancelTool(BaseCustomTool, BaseTool):
    """
    Tool for canceling an escrow on the XRPL.
    Cancels an expired escrow and returns the escrowed XRP to the sender.
    
    Input should be a comma-separated string:
        "owner_address, sequence"
        
    - owner_address: The XRPL address that created the escrow
    - sequence: The sequence number of the EscrowCreate transaction
    
    Note: Escrows can only be canceled after their cancel_after time has passed.
    """
    name: ClassVar[str] = "XRPLEscrowCancel"
    description: ClassVar[str] = (
        "Cancel an expired escrow on the XRPL. "
        "Input format: 'owner_address, sequence'. "
        "The owner_address is the address that created the escrow. "
        "The sequence is the sequence number of the EscrowCreate transaction. "
        "Escrows can only be canceled after their cancel_after time has passed."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
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
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) != 2:
                return False, "Input must have exactly 2 parts: owner_address, sequence"
            
            owner_address = parts[0]
            sequence = parts[1]
            
            # Validate owner address
            if not self._validate_address(owner_address):
                return False, f"Invalid owner address: {owner_address}"
            
            # Validate sequence
            if not self._validate_sequence(sequence):
                return False, f"Invalid sequence number: {sequence}. Please provide a valid sequence number."
            
            # Convert to integer
            offer_sequence = int(sequence)
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Create cancel transaction
            cancel_tx = EscrowCancel(
                account=Config.XRP_WALLET.address,
                owner=owner_address,
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
                    return True, f"Escrow cancellation successful - owner: {owner_address}, sequence: {sequence}"
                else:
                    return False, f"Escrow cancellation failed: {response.tx_status}"
                    
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Submit failed: {e}"
                
        except Exception as e:
            return False, f"Error canceling escrow: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLEscrowCancelTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLEscrowCancelTool()
    
    # Example format: "owner_address, sequence"
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 12345"  # Replace with real values
    
    result = tool._run(example_input)
    print(result)
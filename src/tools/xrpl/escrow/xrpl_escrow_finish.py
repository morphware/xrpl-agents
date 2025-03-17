import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import EscrowFinish
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLEscrowFinishTool(BaseCustomTool, BaseTool):
    """
    Tool for finishing an escrow on the XRPL.
    Finishes an escrow and releases the escrowed XRP to the destination address.
    
    Input should be a comma-separated string:
        "owner_address, sequence, fulfillment"
        
    - owner_address: The XRPL address that created the escrow
    - sequence: The sequence number of the EscrowCreate transaction
    - fulfillment: (Optional) The fulfillment hex string, required only for conditional escrows
    
    Time-based escrows can be finished once the finish_after time has passed.
    Condition-based escrows require the correct fulfillment string to release the funds.
    """
    name: ClassVar[str] = "XRPLEscrowFinish"
    description: ClassVar[str] = (
        "Finish an escrow on the XRPL to release escrowed XRP to the destination. "
        "Input format: 'owner_address, sequence, fulfillment'. "
        "The owner_address is the address that created the escrow. "
        "The sequence is the sequence number of the EscrowCreate transaction. "
        "The fulfillment is the hex string needed to satisfy the crypto-condition (if any). "
        "Time-based escrows can be finished after their finish_after time has passed. "
        "Leave fulfillment blank for time-based escrows."
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
    
    def _validate_fulfillment(self, fulfillment: str) -> bool:
        """Check if the input appears to be a valid fulfillment string."""
        if not fulfillment:
            return True  # Empty fulfillment is valid for time-based escrows
        
        # Basic validation - hex string check
        try:
            if not all(c in '0123456789ABCDEFabcdef' for c in fulfillment):
                return False
            # Attempt to decode hex to ensure it's valid
            bytes.fromhex(fulfillment)
            return True
        except (ValueError, TypeError):
            return False
        
    def _run(self, tool_input: str) -> str:
        try:
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) < 2:
                return False, "Input must have at least 2 parts: owner_address, sequence"
            
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
            
            # Get fulfillment if provided
            fulfillment = None
            if len(parts) > 2 and parts[2]:
                fulfillment = parts[2]
                if not self._validate_fulfillment(fulfillment):
                    return False, f"Invalid fulfillment string: {fulfillment}"
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Create finish transaction
            finish_tx = EscrowFinish(
                account=Config.XRP_WALLET.address,
                owner=owner_address,
                offer_sequence=offer_sequence
            )
            
            # Add fulfillment if provided
            if fulfillment:
                finish_tx.condition = None  # Leave out condition field
                finish_tx.fulfillment = fulfillment

            try:
                tx_id = str(uuid.uuid4())
                # Create transaction request payload
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": finish_tx.blob()
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
                    success_msg = f"Escrow finish successful - owner: {owner_address}, sequence: {sequence}"
                    if fulfillment:
                        success_msg += f", fulfillment provided"
                    return True, success_msg
                else:
                    return False, f"Escrow finish failed: {response.tx_status}"
                    
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Submit failed: {e}"
                
        except Exception as e:
            return False, f"Error finishing escrow: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLEscrowFinishTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLEscrowFinishTool()
    
    # Example format for time-based escrow: "owner_address, sequence"
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 12345"
    
    # Example format for condition-based escrow: "owner_address, sequence, fulfillment"
    # example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 12345, A0258020E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855810100"
    
    result = tool._run(example_input)
    print(result)
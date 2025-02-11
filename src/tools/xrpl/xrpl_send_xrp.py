import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from config import Config
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import Payment
from xrpl import transaction as tx
from xrpl.wallet import Wallet

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from base import BaseCustomTool

class XRPLSendXrpTool(BaseCustomTool, BaseTool):
    """
    Tool for sending XRP tokens on the XRPL chain.
    Input should be a comma-separated string:
        "destination_address, amount_in_XRP"
    """
    name: ClassVar[str] = "XRPLSendXRP"
    description: ClassVar[str] = (
        "Send XRP tokens on the XRPL chain. "
        "Input should be in the format 'destination_address, amount_in_XRP'. "
    )

    def _run(self, tool_input: str) -> str:
        try:
            parts = tool_input.split(",")
            if len(parts) != 2:
                return "Input must be in the format 'destination_address, amount_in_XRP'."
            
            destination = parts[0].strip()
            try:
                amount_xrp = float(parts[1].strip())
            except ValueError:
                return "Amount must be a numeric value."

            # Convert amount from XRP to drops (1 XRP = 1,000,000 drops)
            amount_drops = str(int(amount_xrp * 1_000_000))

            # Connect to the XRPL mainnet
            client = JsonRpcClient("https://s.altnet.rippletest.net:51234")

            # Create Payment transaction
            payment = Payment(
                account=Config.XRP_WALLET.address,
                destination=destination,
                amount=amount_drops
            )

            # Create a wallet instance, set with the current sequence
            try:    
                response = tx.submit_and_wait(payment, client, Config.XRP_WALLET)    
            except tx.XRPLReliableSubmissionException as e:    
                response = f"Submit failed: {e}"
                return response
            return response
        except Exception as e:
            return f"Error sending XRP: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLSendXRPTool.")

if __name__ == "__main__":
    # Example usage:
    # Input format: "destination_address, amount_in_XRP"
    tool = XRPLSendXrpTool()
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 10"
    result = tool._run(example_input)
    print(result)
import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
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
    The tool uses the sender's secret and address from the environment variables:
        XRPL_WALLET_SECRET.
    """
    name: ClassVar[str] = "XRPLSendXRP"
    description: ClassVar[str] = (
        "Send XRP tokens on the XRPL chain. "
        "Input should be in the format 'destination_address, amount_in_XRP'. "
        "The sender's secret is taken from XRPL_WALLET_SECRET environment variable."
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

            # Get sender's credentials from environment variables
            xrpl_sender_secret = os.getenv("XRPL_SENDER_SECRET")
            if not xrpl_sender_secret:
                return "Sender credentials not set. Please set XRPL_SENDER_SECRET in your environment."

            # Connect to the XRPL mainnet
            client = JsonRpcClient("https://s.altnet.rippletest.net:51234")

            wallet = Wallet.from_seed(xrpl_sender_secret)

            # Create Payment transaction
            payment = Payment(
                account=wallet.address,
                destination=destination,
                amount=amount_drops
            )

            # Create a wallet instance, set with the current sequence
            try:    
                response = tx.submit_and_wait(payment, client, wallet)    
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
    # Set environment variable XRPL_SENDER_SECRET before running.
    # Input format: "destination_address, amount_in_XRP"
    tool = XRPLSendXrpTool()
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 10"
    result = tool._run(example_input)
    print(result)
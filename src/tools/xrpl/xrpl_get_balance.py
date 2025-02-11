import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import GatewayBalances
from xrpl.wallet import Wallet

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from base import BaseCustomTool



class XRPLGetBalanceTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving the XRP balance of an XRPL account.
    Input should be a valid XRPL account address.
    """
    name: ClassVar[str] = "XRPLGetBalance"
    description: ClassVar[str] = (
        "Retrieve the XRP balance of an XRPL account. "
        "Input should be the account address."
    )

    def _run(self, tool_input: str) -> str:
        client = JsonRpcClient("https://s.altnet.rippletest.net:51234")
        try:
            # Get sender's credentials from environment variables
            xrpl_sender_secret = os.getenv("XRPL_WALLET_SECRET")
            if not xrpl_sender_secret:
                return "Sender credentials not set. Please set XRPL_WALLET_SECRET in your environment."

            wallet = Wallet.from_seed(xrpl_sender_secret)
            request=GatewayBalances(
                account=wallet.address,
                ledger_index="validated"
            )

            response = client.request(request)
            account_data = response.result.get("account_data")
            if not account_data:
                return f"No account data found for account {tool_input}."
            balance = account_data.get("Balance")
            if balance is None:
                return "Balance not available."

            # Convert drops to XRP (1 XRP = 1,000,000 drops)
            xrp_balance = int(balance) / 1_000_000
            return f"Balance for account {tool_input}: {xrp_balance} XRP"
        except Exception as e:
            return f"Error retrieving balance: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLGetBalanceTool.")

if __name__ == "__main__":
    tool = XRPLGetBalanceTool()
    # Example usage:
    account_address = "rHzykWRVdAfEHk6c5fQxyYYHF9waQXN5Dz"
    result = tool._run(account_address)
    print(result)
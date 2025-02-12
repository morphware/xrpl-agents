import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import GatewayBalances
from xrpl.wallet import Wallet
from ...config import Config
from ..base import BaseCustomTool



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
        client = JsonRpcClient(Config.XRPL_ENDPOINT)
        try:
            # Get sender's credentials from environment variables
            request=GatewayBalances(
                account=Config.XRP_WALLET.address,
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
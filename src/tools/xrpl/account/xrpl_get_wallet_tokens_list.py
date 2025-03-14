from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountCurrencies
from ....config import Config
from ...base import BaseCustomTool

class XRPLGetWalletTokensListTool(BaseCustomTool, BaseTool):
    """Tool for retrieving the list of tokens an XRPL wallet can hold."""
    
    name: ClassVar[str] = "XRPLGetWalletTokensList"
    description: ClassVar[str] = (
        "Retrieve the list of tokens associated with an XRPL wallet. "
        "Input should be a valid XRPL wallet address. "
        "If the input is for user's address, input 'user_account_address'."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
        
    def _hex_to_currency(self, code: str) -> str:
        if len(code) == 40:
            try:
                code_bytes = bytes.fromhex(code)
                converted = code_bytes.decode("utf-8").rstrip("\0").strip()
                if converted:
                    return converted
            except Exception:
                pass
        return code
    
    def _run(self, tool_input: str) -> str:
        try:
            # Clean the input
            address = tool_input.strip()
            if "user_account_address" in address.lower():
                address = Config.XRP_WALLET.address

            # Validate address format
            if not self._validate_address(address):
                return False, f"Invalid XRPL address format: {address}"

            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Create and send request
            request = AccountCurrencies(
                account=address,
                ledger_index="validated"
            )
            response = client.request(request)

            # Extract currencies from response
            currencies = response.result.get("send_currencies", []) + \
                        response.result.get("receive_currencies", [])
            
            # Remove duplicates and sort
            unique_currencies = sorted(set(currencies))
            # Convert any hex currency codes to readable format
            unique_currencies = [self._hex_to_currency(currency) for currency in unique_currencies]
            if not unique_currencies:
                return False, f"No tokens found for account {address}"

            # Format response
            tokens_list = "\n".join(unique_currencies)
            return True, f"Tokens available for account {address}:\n{tokens_list}"

        except Exception as e:
            return False, f"Error retrieving token list: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLGetWalletTokensListTool.")


if __name__ == "__main__":
    # Example usage
    tool = XRPLGetWalletTokensListTool()
    example_input = "rExampleWalletAddress1234567890"  # Replace with real address
    result = tool._run(example_input)
    print(result)
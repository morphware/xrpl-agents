from typing import ClassVar
from xrpl.clients import JsonRpcClient
from xrpl.models.requests.account_lines import AccountLines
from ...config import Config
from ..base import BaseCustomTool
from langchain.tools import BaseTool

class XRPLGetTokenBalanceTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving the balance of a given token (fungible) for an XRPL wallet.
    Input should be a comma-separated string: "TOKEN, wallet_address".
    The tool queries the account's trust lines and returns details for matching token(s).
    """
    name: ClassVar[str] = "XRPLGetTokenBalance"
    description: ClassVar[str] = (
        "Retrieve the balance of a specific token for an XRPL wallet. "
        "Input must be in the format 'TOKEN, wallet_address'."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        return isinstance(address, str) and address.startswith("r") and 25 <= len(address) <= 35
    
    def _hex_to_currency(self, code: str) -> str:
        if len(code) == 40:
            try:
                code_bytes = bytes.fromhex(code)
                # Remove trailing null bytes and spaces
                converted = code_bytes.decode("utf-8").rstrip("\0").strip()
                if converted:
                    return converted
            except Exception:
                pass
        return code
    
    def _run(self, tool_input: str) -> str:
        parts = tool_input.split(",")
        if len(parts) != 2:
            return "Input must be in the format 'TOKEN, wallet_address'."
        
        token_code = parts[0].strip().upper()
        wallet_address = parts[1].strip()
        
        if not self._validate_address(wallet_address):
            return f"Invalid XRPL wallet address: {wallet_address}"
        
        # Connect to the XRPL endpoint
        client = JsonRpcClient(Config.XRPL_ENDPOINT)
        account_lines_request = AccountLines(
            account=wallet_address,
            ledger_index="validated"
        )
        
        try:
            response = client.request(account_lines_request)
            lines = response.result.get("lines", [])
            if not lines:
                return False, f"No trust lines found for account {wallet_address}."

            for line in lines:
                line["currency"] = self._hex_to_currency(line.get("currency", ""))
            # Filter trustlines matching the token code (case-insensitive)
            matching_lines = [line for line in lines if line.get("currency", "").upper() == token_code]
            
            if not matching_lines:
                return False, f"No balance found for token {token_code} in wallet {wallet_address}."
            
            result_lines = []
            for line in matching_lines:
                balance = line.get("balance", "0")
                issuer = line.get("account", "Unknown")
                limit = line.get("limit", "N/A")
                currency = line.get("currency", "Unknown")
                result_lines.append(f"Issuer: {issuer}, Balance: {balance} {currency}, Limit: {limit} {currency}")
            
            return True, "\n".join(result_lines)
        except Exception as e:
            return False, f"Error retrieving token balance: {str(e)}"

if __name__ == "__main__":
    tool = XRPLGetTokenBalanceTool()
    # Example usage:
    # Replace 'TOKEN' with token code (e.g., "USD" for an IOU) and wallet_address with a valid XRPL address.
    user_input = "USD, rExampleWalletAddress1234567890"
    result = tool._run(user_input)
    print(result)
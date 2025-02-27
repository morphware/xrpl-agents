from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountTx
from ....config import Config
from ...base import BaseCustomTool
from datetime import datetime

class XRPLGetAccountTransactionsTool(BaseCustomTool, BaseTool):
    name: ClassVar[str] = "XRPLGetAccountTransactions"
    description: ClassVar[str] = (
        "Retrieve a number of transactions for an XRPL account. "
        "Input should be in the format 'account_address, number_of_transactions'."
        "if no number is provided, the default is 1."
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
    
    def _validate_address(self, address: str) -> bool:
        return isinstance(address, str) and address.startswith("r") and 25 <= len(address) <= 35

    def _run(self, tool_input: str) -> str:
        parts = [p.strip() for p in tool_input.split(",")]
        if len(parts) != 2:
            return False, "Input must be in the format 'account_address, number_of_transactions'."
        
        account = parts[0]
        if "user_account_address" in account.lower():
            account = Config.XRP_WALLET.address

        if not self._validate_address(account):
            return False, f"Invalid XRPL address: {account}"
        
        try:
            limit = int(parts[1])
        except ValueError:
            return False, "The number of transactions must be an integer."
        
        try:
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            request = AccountTx(
                account=account,
                limit=limit,
                ledger_index_min=-1,  # Use -1 to indicate the minimum (oldest) validated ledger
                ledger_index_max=-1,  # Use -1 to indicate the maximum (latest) validated ledger
                forward=False       # Set to False to get transactions in reverse chronological order
            )
            response = client.request(request)
            transactions = response.result.get("transactions", [])
            extracted = []
            for item in transactions:
                meta = item.get("meta", {})
                tx = item.get("tx_json", {})
                transaction_type = tx.get("TransactionType", "Unknown")
                timestamp = tx.get("date", 0)
                source = tx.get("Account", "Unknown")
                sequence = tx.get("Sequence", "Unknown")
                destination = tx.get("Destination", "Unknown")
                source_tag = tx.get("SourceTag", "N/A")
                fee = int(tx.get("Fee", 0)) / 1_000_000  # Convert drops to XRP
                ctid = tx.get("ledger_index", "Unknown")
                tx_hash = item.get("hash", "Unknown")

                # Format delivered amount
                delivered = meta.get("delivered_amount", "Unknown")
                sent = tx.get("SendMax", "Unknown")
                if isinstance(meta.get("delivered_amount"), dict):
                    delivered_amount = f"{delivered.get('value')} {self._hex_to_currency(delivered.get('currency'))} ({delivered.get('issuer')})"
                elif delivered == "Unknown":
                    delivered_amount = 0
                else:
                    delivered_amount = f"{float(delivered) / 1_000_000} XRP"
                if isinstance(tx.get("SendMax"), dict):
                    spent_amount = f"{sent.get('value')} {self._hex_to_currency(sent.get('currency'))} ({sent.get('issuer')})"
                elif sent == "Unknown":
                    spent_amount = 0
                else:    
                    spent_amount = f"{float(sent) / 1_000_000} XRP"
                
                
                # Format timestamp
                utc_time = datetime.utcfromtimestamp(timestamp + 946684800).strftime('%Y-%m-%d %H:%M:%S')

                extracted_tx = (
                    f"Transaction hash:{tx_hash} \n"
                    f"Type:{transaction_type} \n"
                    f"Time (UTC):{utc_time} \n"
                    f"Source:{source} \n"
                    f"Sequence:#{sequence} \n"
                    f"Spent amount:{spent_amount} \n"
                    f"Destination:{destination} \n"
                    f"Delivered amount:{delivered_amount} \n"
                    f"Source tag:{source_tag} \n"
                    f"XRPL fee:{fee} XRP ({tx.get('Fee', '0')} drops) \n"
                    f"CTID:{ctid}\n"
                )
                extracted.append(extracted_tx)
            return True, f"Transactions for account {account}:\n\n{extracted}"
        except Exception as e:
            return False, f"Error retrieving transactions: {str(e)}"

if __name__ == "__main__":
    tool = XRPLGetAccountTransactionsTool()
    # Example usage: retrieve 5 transactions from the given account address.
    example_input = "rExampleWalletAddress1234567890, 5"
    result = tool._run(example_input)
    print(result)
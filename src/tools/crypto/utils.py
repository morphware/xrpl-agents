# src/tools/crypto/utils.py
import re
import requests
import pandas as pd
from typing import Optional, Dict, Any, Union
from functools import lru_cache
from enum import Enum
from ...config import Config
from ...exceptions import CryptoToolError
from ...utils.logger import setup_logger

logger = setup_logger(__name__, 'logs/crypto_utils.log')

# Chain Resolution Classes and Constants
class ChainCategory(Enum):
    MAINNET = "mainnet"
    TESTNET = "testnet"

class _ChainConstants:
    """Internal class for chain constants"""
    MAINNET_CHAINS = {
        # Layer 1 Networks
        1: {"name": "Ethereum", "shortName": "eth", "category": ChainCategory.MAINNET},
        # EVM Compatible Networks
        42161: {"name": "Arbitrum One", "shortName": "arb", "category": ChainCategory.MAINNET},
        137: {"name": "Polygon", "shortName": "matic", "category": ChainCategory.MAINNET},
        56: {"name": "BNB Smart Chain", "shortName": "bsc", "category": ChainCategory.MAINNET},
        10: {"name": "Optimism", "shortName": "op", "category": ChainCategory.MAINNET},
        8453: {"name": "Base", "shortName": "base", "category": ChainCategory.MAINNET},
        534352: {"name": "Scroll", "shortName": "scrl", "category": ChainCategory.MAINNET},
        324: {"name": "zkSync Era", "shortName": "zksync", "category": ChainCategory.MAINNET},
    }
    
    TESTNET_CHAINS = {
        11155111: {"name": "Sepolia", "shortName": "sep", "category": ChainCategory.TESTNET},
        421614: {"name": "Arbitrum Sepolia", "shortName": "arb-sep", "category": ChainCategory.TESTNET},
        84532: {"name": "Base Sepolia", "shortName": "base-sep", "category": ChainCategory.TESTNET},
        97: {"name": "BSC Testnet", "shortName": "bsc-test", "category": ChainCategory.TESTNET},
    }

# Chain Resolution Functions
def resolve_chain_id(chain_identifier: Union[str, int]) -> Optional[int]:
    """Resolve a chain identifier to its numeric chain ID."""
    try:
        if isinstance(chain_identifier, int):
            return chain_identifier
        
        if isinstance(chain_identifier, str) and chain_identifier.isdigit():
            return int(chain_identifier)
        
        if isinstance(chain_identifier, str):
            search_term = chain_identifier.lower()
            
            for chain_id, data in _ChainConstants.MAINNET_CHAINS.items():
                if (search_term == data['name'].lower() or 
                    search_term == data['shortName'].lower()):
                    return chain_id
            
            for chain_id, data in _ChainConstants.TESTNET_CHAINS.items():
                if (search_term == data['name'].lower() or 
                    search_term == data['shortName'].lower()):
                    return chain_id
                    
        return None
        
    except Exception as e:
        logger.error(f"Error resolving chain ID: {str(e)}")
        return None

def get_chain_info(chain_id: int) -> Optional[Dict[str, Any]]:
    """Get information about a blockchain network from its chain ID."""
    chain_info = _ChainConstants.MAINNET_CHAINS.get(chain_id)
    if chain_info:
        return {**chain_info, 'chainId': chain_id}
        
    chain_info = _ChainConstants.TESTNET_CHAINS.get(chain_id)
    if chain_info:
        return {**chain_info, 'chainId': chain_id}
        
    return None

# Coingecko API Functions
def make_coingecko_request(endpoint: str, params: Dict[str, Any]) -> Dict:
    """Make a request to the CoinGecko Pro API."""
    base_url = "https://pro-api.coingecko.com/api/v3"
    headers = {
        'accept': 'application/json',
        'x-cg-pro-api-key': Config.COINGECKO_API_KEY
    }
    
    try:
        response = requests.get(f"{base_url}/{endpoint}", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        raise CryptoToolError(f"CoinGecko API error: {str(e)}")
    except Exception as e:
        raise CryptoToolError(f"Error making CoinGecko request: {str(e)}")

def search_coingecko_id(crypto_input: str) -> str:
    """Search the internet for a cryptocurrency's CoinGecko ID."""
    from langchain_community.tools import DuckDuckGoSearchRun
    
    logger.info(f"Searching for CoinGecko ID for: {crypto_input}")
    try:
        search = DuckDuckGoSearchRun()
        search_query = f"coingecko.com {crypto_input} cryptocurrency price"
        search_results = search.run(search_query)
        
        coingecko_pattern = r"coingecko\.com/(?:en/coins|coins)/([a-z0-9-]+)"
        matches = re.findall(coingecko_pattern, search_results.lower())
        
        if matches:
            token_id = matches[0]
            logger.info(f"Found CoinGecko ID through search: {token_id}")
            return token_id
        else:
            logger.warning(f"No CoinGecko ID found in search results for {crypto_input}")
            return f"Could not find CoinGecko ID for {crypto_input}"
    except Exception as e:
        logger.error(f"Error in search_coingecko_id: {str(e)}", exc_info=True)
        raise CryptoToolError(f"Error searching for CoinGecko ID: {str(e)}")

def resolve_token_id(token_input: str) -> str:
    """Resolve a token symbol or name to its CoinGecko ID."""
    logger.info(f"Attempting to resolve token: {token_input}")
    try:
        # Try CoinGecko search API first
        data = make_coingecko_request("search", {"query": token_input})
        
        if data.get('coins'):
            best_match = data['coins'][0]
            token_id = best_match['id']
            logger.info(f"Successfully resolved {token_input} to {token_id}")
            return token_id
            
        # If CoinGecko search fails, try internet search
        logger.info(f"CoinGecko search failed, trying internet search for {token_input}")
        return search_coingecko_id(token_input)
    except CryptoToolError:
        # If both methods fail, try internet search as last resort
        return search_coingecko_id(token_input)

# Uniblock API Functions
def make_uniblock_request(endpoint: str, params: Dict[str, Any]) -> Dict:
    """Make a request to the Uniblock API."""
    base_url = "https://api.uniblock.dev/uni/v1"
    headers = {
        "accept": "application/json",
        "X-API-KEY": Config.UNIBLOCK_API_KEY
    }
    
    try:
        response = requests.get(f"{base_url}/{endpoint}", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Uniblock API request failed: {str(e)}", exc_info=True)
        raise CryptoToolError(f"Uniblock API request failed: {str(e)}")

# Market Data Functions
def get_historical_data(token_id: str, hist_days: int = 30) -> pd.DataFrame:
    """Retrieve historical price data for a token."""
    try:
        data = make_coingecko_request(
            f"coins/{token_id}/market_chart",
            {
                "vs_currency": "usd",
                "days": hist_days
            }
        )
        
        df = pd.DataFrame(data['prices'], columns=['timestamp', 'price'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"Error fetching historical data: {str(e)}", exc_info=True)
        return pd.DataFrame()

def get_high_level_market_data(token_id: str) -> Dict[str, Any]:
    """Retrieve current market data for a token_id (for example xmw ... not morphware)."""
    try:
        data = make_coingecko_request(
            "simple/price",
            {
                "ids": token_id,
                "vs_currencies": "usd",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "false",
                "precision": "4"
            }
        )
        
        token_data = data.get(token_id, {})
        if not token_data:
            raise CryptoToolError(f"No data returned for token: {token_id}")
            
        return {
            'price': token_data.get('usd', 0.0),
            'market_cap': token_data.get('usd_market_cap', 0.0),
            'volume_24h': token_data.get('usd_24h_vol', 0.0),
            'price_change_24h': token_data.get('usd_24h_change', 0.0)
        }
    except Exception as e:
        logger.error(f"Error fetching market data for {token_id}: {str(e)}", exc_info=True)
        raise CryptoToolError(f"Error fetching market data: {str(e)}")


'''
# Original
def make_uniblock_request(endpoint: str, params: Dict[str, Any]) -> Dict:
    """Make a request to the Uniblock API."""
    base_url = "https://api.uniblock.dev/uni/v1"
    headers = {
        "accept": "application/json",
        "X-API-KEY": Config.UNIBLOCK_API_KEY
    }
    
    try:
        response = requests.get(f"{base_url}/{endpoint}", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Uniblock API request failed: {str(e)}", exc_info=True)
        raise CryptoToolError(f"Uniblock API request failed: {str(e)}")
'''

    
# Further details can be found in the following link:
'''
curl --request GET \
     --url 'https://pro-api.coingecko.com/api/v3/coins/COINGECKO_ASSET_ID_HERE/history?date=31-12-2024&localization=true' \
     --header 'accept: application/json' \
     --header 'x-cg-pro-api-key: <api key here>'

# Example response (pulls in twitter followers, social mentions, etc ... albeit kinda janky):
{"id":"uniswap","symbol":"uni","name":"Uniswap","localization":{"en":"Uniswap","de":"Uniswap","es":"Uniswap","fr":"Uniswap","it":"Uniswap","pl":"Uniswap","ro":"Uniswap","hu":"Uniswap","nl":"Uniswap","pt":"Uniswap","sv":"Uniswap","vi":"Uniswap","tr":"Uniswap","ru":"Uniswap","ja":"ユニスワップ","zh":"Uniswap","zh-tw":"Uniswap","ko":"Uniswap","ar":"Uniswap","th":"Uniswap","id":"Uniswap","cs":"Uniswap","da":"Uniswap","el":"Uniswap","hi":"Uniswap","no":"Uniswap","sk":"Uniswap","uk":"Uniswap","he":"Uniswap","fi":"Uniswap","bg":"Uniswap","hr":"Uniswap","lt":"Uniswap","sl":"Uniswap"},"image":{"thumb":"https://coin-images.coingecko.com/coins/images/12504/thumb/uniswap-logo.png?1720676669","small":"https://coin-images.coingecko.com/coins/images/12504/small/uniswap-logo.png?1720676669"},"market_data":{"current_price":{"aed":48.898161242960214,"ars":13725.331756024729,"aud":21.410666585906206,"bch":0.03003731335227087,"bdt":1589.930393859068,"bhd":5.019150277068641,"bmd":13.31283095961084,"bnb":0.018936371622114086,"brl":82.2519948008596,"btc":0.00014373407891086348,"cad":19.105509966756703,"chf":12.026292288505008,"clp":13246.925856509442,"cny":97.17168445729548,"czk":322.1132640494559,"dkk":95.4260394977165,"dot":1.988990942423045,"eos":17.217684443977202,"eth":0.003962661394424902,"eur":12.794802081310463,"gbp":10.610512654443276,"gel":37.37577291910743,"hkd":103.35349751339078,"huf":5262.442329419683,"idr":215394.94851102357,"ils":48.648745354931904,"inr":1142.0643415704237,"jpy":2090.3072031598936,"krw":19563.83082482889,"kwd":4.100258745743422,"lkr":3891.4384053659546,"ltc":0.13419801041667093,"mmk":27930.319353263534,"mxn":274.8758651558762,"myr":59.44179023466239,"ngn":20597.65010878077,"nok":150.87749503186896,"nzd":23.612102939049365,"php":770.9592605122066,"pkr":3704.8973272303565,"pln":54.71899688758566,"rub":1471.0559859302741,"sar":50.013510220756416,"sek":146.84019266373355,"sgd":18.09711627289002,"thb":454.7463363338668,"try":470.32787338145977,"twd":436.67149242717215,"uah":559.8957746822019,"usd":13.31283095961084,"vef":1.3330137639858335,"vnd":339293.8129317369,"xag":0.4599243619356075,"xau":0.0051066688277971225,"xdr":10.201023286956604,"xlm":40.18515791258096,"xrp":6.472947898896108,"yfi":0.0016125132937427975,"zar":250.2829393958775,"bits":143.73407891086347,"link":0.64705567756994,"sats":14373.407891086348},"market_cap":{"aed":29337939066.25353,"ars":8235009276153.878,"aud":12846699489.088432,"bch":18027388.462829307,"bdt":953927097234.914,"bhd":3011391865.255646,"bmd":7987437841.512418,"bnb":11368061.908430805,"brl":49342397265.94297,"btc":86282.76023501618,"cad":11463027644.365396,"chf":7215899270.649365,"clp":7947896070415.197,"cny":58301107548.98329,"czk":193272840182.29794,"dkk":57254952877.6912,"dot":1194382776.058758,"eos":10336253411.987024,"eth":2378437.733041213,"eur":7676902233.110099,"gbp":6365404876.722966,"gel":22424723752.608265,"hkd":62010633431.33846,"huf":3156904348035.518,"idr":129236744275670.86,"ils":29188294418.29279,"inr":685216237401.1113,"jpy":1253993660237.793,"krw":11758276359068.29,"kwd":2460074943.1209345,"lkr":2334786828679.4043,"ltc":80601162.98756403,"mmk":16757644591493.055,"mxn":164929896247.9616,"myr":35663909962.35295,"ngn":12358186656485.36,"nok":90518677705.85884,"nzd":14167278562.301361,"php":462560456927.76074,"pkr":2222865835239.527,"pln":32839056720.447983,"rub":882625500068.6416,"sar":30007126608.615437,"sek":88101199768.74666,"sgd":10858202876.130392,"thb":272850852703.75067,"try":282182528409.36255,"twd":262058242667.17477,"uah":335926499147.12506,"usd":7987437841.512418,"vef":799782151.0706384,"vnd":203569642627026.34,"xag":275933228.9291038,"xau":3064300.6535178246,"xdr":6120414183.248095,"xlm":24143271792.55859,"xrp":3886602227.8037205,"yfi":967891.0232007542,"zar":150115906793.3844,"bits":86282760235.01617,"link":388358906.5814115,"sats":8628276023501.618},"total_volume":{"aed":1758688071.2735708,"ars":493649998691.2741,"aud":770063392.2726482,"bch":1080332.3344464295,"bdt":57183982930.19241,"bhd":180520483.71207172,"bmd":478813853.29023623,"bnb":681072.049305535,"brl":2958303511.1683955,"btc":5169.5892767833375,"cad":687155337.1338836,"chf":432541761.3221211,"clp":476443487703.5922,"cny":3494910196.5507636,"czk":11585236350.054567,"dkk":3432125730.038081,"dot":71536731.7582763,"eos":619257155.6243266,"eth":142522.44149312866,"eur":460182248.6310066,"gbp":381621344.4662644,"gel":1344269893.1123383,"hkd":3717247409.3260846,"huf":189270809275.02005,"idr":7746968739309.377,"ils":1749717493.732178,"inr":41075878582.97994,"jpy":75180707209.59435,"krw":703639462618.7344,"kwd":147471315.11641973,"lkr":139960810992.62695,"ltc":4826611.760220817,"mmk":1004551464202.9153,"mxn":9886279828.1651,"myr":2137903854.9409046,"ngn":740822162260.6461,"nok":5426511835.849183,"nzd":849241008.6804279,"php":27728585706.193897,"pkr":133251610470.96481,"pln":1968042246.4169273,"rub":52908505123.05551,"sar":1798803095.902227,"sek":5281304831.444973,"sgd":650887103.0025613,"thb":16355563007.61453,"try":16915973923.713226,"twd":15705476960.188524,"uah":20137403842.19103,"usd":478813853.29023623,"vef":47943631.12995136,"vnd":12203157875305.17,"xag":16541797.655851772,"xau":183668.2059836017,"xdr":366893509.15290993,"xlm":1445313199.241732,"xrp":232808268.58091375,"yfi":57996.207268096296,"zar":9001762208.843512,"bits":5169589276.783338,"link":23272226.86223038,"sats":516958927678.33374}},"community_data":{"facebook_likes":null,"twitter_followers":1364231,"reddit_average_posts_48h":0.0,"reddit_average_comments_48h":0.0,"reddit_subscribers":null,"reddit_accounts_active_48h":0.0},"developer_data":{"forks":2764,"stars":4488,"subscribers":142,"total_issues":0,"closed_issues":0,"pull_requests_merged":214,"pull_request_contributors":11,"code_additions_deletions_4_weeks":{"additions":0,"deletions":0},"commit_count_4_weeks":0},"public_interest_stats":{"alexa_rank":null,"bing_matches":null}}%
'''
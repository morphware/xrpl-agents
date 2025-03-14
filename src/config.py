import os
from dotenv import load_dotenv
import logging
import json
import uuid
from xrpl.wallet import Wallet
from xrpl.wallet.wallet_generation import generate_faucet_wallet
from xrpl.clients import JsonRpcClient
load_dotenv()

class Config:
    # API Keys and Endpoints
    TOOLS_LIST = json.loads(os.getenv("TOOLS_LIST", '["WebSearchTool", "CoinGeckoTool", "UniblockTool", "OllamaTool", "SerperTool", "TavilyTool", "CryptoPriceTool", "WikipediaTool", "TelegramTool", "MorphwareKnowledgeTool"]'))
    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
    UNIBLOCK_API_KEY = os.getenv("UNIBLOCK_API_KEY")
    OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "https://morphware.com/ollama")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.3:70b-instruct-q8_0")
    CHATS_ENDPOINT = os.getenv("CHATS_ENDPOINT", "https://app.morphware.com/ollama/api/chats")
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    MORPHWARE_API_KEY = os.getenv("MORPHWARE_API_KEY").split(' ')[-1]
    MORPHWARE_EMBEDDINGS_API_BASE = os.getenv("MORPHWARE_EMBEDDINGS_API_BASE", "https://app.morphware.com/ollama/api/embed")
    MORPHWARE_EMBEDDINGS_MODEL = os.getenv("MORPHWARE_EMBEDDINGS_MODEL", "nomic-embed-text:latest")
    MORPHWARE_FILTER_MODEL = os.getenv("MORPHWARE_FILTER_MODEL", "llama3.1:latest")
    AGENT_WORKFLOW_FILE = os.getenv("AGENT_WORKFLOW_FILE", "XRPL.json.json")
    REQUEST_ID = None
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "morphware-cluster-kafka-plain-bootstrap.kafka.svc:9092")
    USER = os.getenv("USER", "morphware")
    CHAT_UUID = os.getenv("CHAT_UUID", str(uuid.uuid4()))
    print(CHAT_UUID)
    KAFKA = os.getenv("KAFKA", "true")

    SERPER_API_KEY = os.getenv("SERPER_API_KEY")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

    TELEGRAM_API_ID=os.getenv("TELEGRAM_API_ID", "")
    TELEGRAM_API_HASH=os.getenv("TELEGRAM_API_HASH", "")
    TELEGRAM_SESSION_NAME=os.getenv("TELEGRAM_SESSION_NAME", "")

    TWITTER_API_KEY=os.getenv("TWITTER_API_KEY", "")
    TWITTER_API_SECRET=os.getenv("TWITTER_API_SECRET", "")
    TWITTER_ACCESS_TOKEN=os.getenv("TWITTER_ACCESS_TOKEN", "")
    TWITTER_ACCESS_TOKEN_SECRET=os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
    TWITTER_BEARER_TOKEN=os.getenv("TWITTER_BEARER_TOKEN", "")
    TWITTER_CONSUMER_KEY=os.getenv("TWITTER_CONSUMER_KEY", "")
    TWITTER_CONSUMER_SECRET=os.getenv("TWITTER_CONSUMER_SECRET", "")
    TWITTER_OAUTH=os.getenv("TWITTER_OAUTH", "")
    TWITTER_OAUTH_CLIENT_SECRET=os.getenv("TWITTER_OAUTH_CLIENT_SECRET", "")

    # Just incase to disable anonymized telemetry from Chroma
    os.environ["ANONYMIZED_TELEMETRY"] = "False"

    # init XRP Wallet
    XRPL_ENDPOINT = os.getenv("XRPL_ENDPOINT", "https://s1.ripple.com:51234") #"https://s.altnet.rippletest.net:51234")
    WALLET_ENABLED=os.getenv("WALLET_ENABLED", "true").lower() == "true"
    WALLET_ADDRESS=os.getenv("WALLET_ADDRESS", "rHDkTGymZL6WQbrrsxPnpeTqhcF8S44kR1")
    if WALLET_ENABLED:
        # init XRP Wallet
        
        XRPL_WALLET_SECRET = os.getenv("XRPL_WALLET_SECRET", 'sEd7ifJUaDCfH9wEy78EX4SfyA9vv7E')

        if XRPL_WALLET_SECRET:
            XRP_WALLET = Wallet.from_seed(XRPL_WALLET_SECRET)
        else:
            client = JsonRpcClient(XRPL_ENDPOINT)
            XRP_WALLET = generate_faucet_wallet(client=JsonRpcClient(XRPL_ENDPOINT))
    else:
        from types import SimpleNamespace
        XRP_WALLET = SimpleNamespace(address=WALLET_ADDRESS)
    # Kafka Settings
    if KAFKA.lower() == "true":
        from src.utils.kafka import create_kafka_producer, create_kafka_consumer, send_to_kafka, consume_from_kafka, get_kafka_messages

        KAFKA_IN_TOPIC = CHAT_UUID + "_IN"
        KAFKA_OUT_TOPIC = CHAT_UUID + "_OUT"
        KAFKA_LOGS_TOPIC = CHAT_UUID + "_LOGS"
        # KAFKA_TX_TOPIC = CHAT_UUID + "_TX"
        KAFKA_HEARTBEAT_TOPIC = CHAT_UUID + "_HEARTBEAT"
        kafka_logger = create_kafka_producer(KAFKA_BOOTSTRAP_SERVERS)
        kafka_in = consume_from_kafka(create_kafka_consumer(KAFKA_BOOTSTRAP_SERVERS, "agent"), KAFKA_IN_TOPIC)
        # kafka_tx = consume_from_kafka(create_kafka_consumer(KAFKA_BOOTSTRAP_SERVERS, "agent"), KAFKA_TX_TOPIC)   
        kafka_out = create_kafka_producer(KAFKA_BOOTSTRAP_SERVERS)
        kafka_heartbeat = create_kafka_producer(KAFKA_BOOTSTRAP_SERVERS)
        
    else:
        KAFKA_IN_TOPIC = None
        KAFKA_OUT_TOPIC = None
        KAFKA_LOGS_TOPIC = None
        KAFKA_HEARTBEAT_TOPIC = None
        kafka_logger = None
        kafka_in = None
        kafka_out = None
        kafka_heartbeat = None

    # Multi-Agent System Settings
    REVIEWER_AGENT_ENABLED = os.getenv("REVIEWER_AGENT_ENABLED", "true").lower() == "true"
    MAX_RETRIES = 3
    REVIEW_THRESHOLD = 0.7  # Minimum score for approval
    ENABLE_FEEDBACK_LOOP = True
    PROCESS_LOCK = False
    # Debugging and Logging
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
    LOG_LEVEL = logging.DEBUG if DEBUG_MODE else logging.INFO
    VERBOSE_TOOLS = os.getenv("VERBOSE_TOOLS", "true").lower() == "true"
    
    # Timeouts and Limits
    TOOL_TIMEOUT = 30  # seconds
    MAX_TOOL_ATTEMPTS = 7
    
    @classmethod
    def validate(cls):
        """Validate configuration settings."""
        # Check required API keys
        required_keys = ["COINGECKO_API_KEY", "MORPHWARE_API_KEY", "UNIBLOCK_API_KEY"]
        missing = [key for key in required_keys if getattr(cls, key) is None]
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Validate numeric settings
        if cls.MAX_RETRIES < 1:
            raise ValueError("MAX_RETRIES must be at least 1")
        if not (0 < cls.REVIEW_THRESHOLD <= 1):
            raise ValueError("REVIEW_THRESHOLD must be between 0 and 1")
        if cls.TOOL_TIMEOUT < 1:
            raise ValueError("TOOL_TIMEOUT must be at least 1 second")
            
    @classmethod
    def get_debug_info(cls):
        """Return debug information about current configuration."""
        return {
            "debug_mode": cls.DEBUG_MODE,
            "log_level": logging.getLevelName(cls.LOG_LEVEL),
            "max_retries": cls.MAX_RETRIES,
            "review_threshold": cls.REVIEW_THRESHOLD,
            "enable_feedback_loop": cls.ENABLE_FEEDBACK_LOOP,
            "tool_timeout": cls.TOOL_TIMEOUT,
            "ollama_model": cls.OLLAMA_MODEL,
            "verbose_tools": cls.VERBOSE_TOOLS
        }
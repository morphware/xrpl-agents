import os
import sys
import warnings
import time
import requests
import json
# Add the src directory to Python path
src_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(src_dir)
sys.path.append(project_root)

from src.config import Config
from src.utils.logger import setup_logger, chat_ui_logger
from src.tools import discover_tools
from src.agent.agent import MultiAgentSystem
from memory import GlobalMemory
from src.utils.kafka import send_to_kafka


os.environ["ANONYMIZED_TELEMETRY"] = "False"
warnings.filterwarnings("ignore")
logger = setup_logger("logs", 'app.log', Config.kafka_logger, Config.KAFKA_LOGS_TOPIC)
heartbeat_logger = setup_logger("heartbeat", 'heartbeat.log', Config.kafka_heartbeat, Config.KAFKA_HEARTBEAT_TOPIC)


def format_response(response_text):
    return {
        "model": Config.OLLAMA_MODEL,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
        "response": response_text,
        "done": True,
        "context": [],
        "total_duration": response_text.get("total_duration", 0) if isinstance(response_text, dict) else 0,
        "load_duration": response_text.get("load_duration", 0) if isinstance(response_text, dict) else 0,
        "prompt_eval_count": response_text.get("prompt_eval_count", 0) if isinstance(response_text, dict) else 0,
        "prompt_eval_duration": response_text.get("prompt_eval_duration", 0) if isinstance(response_text, dict) else 0,
        "eval_count": response_text.get("eval_count", 0) if isinstance(response_text, dict) else 0,
        "eval_duration": response_text.get("eval_duration", 0) if isinstance(response_text, dict) else 0
    }


def main():
    try:
        Config.validate()
        # Initialize tools
        tools = discover_tools()
        print([tool.name for tool in tools])

        # Initialize workflow
        workflow = Config.AGENT_WORKFLOW_FILE
        agent_system = MultiAgentSystem(workflow=workflow, tools=tools)

        print("Welcome to Morphware! Type 'quit' to exit.")

        chat_ui = chat_ui_logger("chat_ui", Config.CHATS_ENDPOINT, Config.MORPHWARE_API_KEY, Config.CHAT_UUID)

        running = True
        while running:
            try:
                if Config.KAFKA.lower() == "true":
                    # Use Kafka Messaging stream to receive and send messages
                    message = Config.get_kafka_messages(Config.kafka_in)
                    if not message:
                        time.sleep(1)
                        heartbeat_logger.info("Agent Idle")
                        continue
                    for topic_data, consumer_records in message.items():
                        for consumer_record in consumer_records:
                            try:
                                user_input = str(consumer_record.value.decode('utf-8'))
                                print("Received message: " + user_input)
                                heartbeat_logger.info("Agent Thinking")
                                if user_input.lower() in ["quit", "exit"]:
                                    logger.info("User requested to quit")
                                    print("Goodbye!")
                                    running = False
                                    break
                                    
                                # Process the request through the multi-agent system
                                response = agent_system.process_request(user_input)
                                formatted_response = format_response(response)
                                print("\nAssistant:", formatted_response)
                                print("\n\n")
                                print(f"Final Response: {formatted_response['response']['response']}")
                                
                                # Send formatted response to Kafka
                                send_to_kafka(Config.kafka_out, Config.KAFKA_OUT_TOPIC, formatted_response, key=Config.REQUEST_ID)
                                chat_ui.info([user_input, formatted_response["response"]])
                            except Exception as e:
                                logger.error(f"Error processing message: {str(e)}", exc_info=True)
                                print("\nAn error occurred. Please try again.")
                else:
                    # Use command line interface to receive and send messages
                    try:
                        user_input = input("\nYou: ").strip()
                        if user_input.lower() in ["quit", "exit"]:
                            logger.info("User requested to quit")
                            print("Goodbye!")
                            running = False
                            break
                        
                        # Process the request through the multi-agent system
                        response = agent_system.process_request(user_input)
                        formatted_response = format_response(response)
                        print("\nAssistant:", formatted_response)
                        print("\n\n")
                        print(f"Final Response: {formatted_response['response']['response']}")
                        
                    except Exception as e:
                        logger.error(f"Error in main loop: {str(e)}", exc_info=True)
                        print("\nAn error occurred. Please try again.")

            except KeyboardInterrupt:
                logger.info("Program interrupted by user")
                print("\nExiting...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}", exc_info=True)
                print("\nAn error occurred. Please try again.")
                
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        print("Error: Could not initialize Assistant. Please check the logs.")

if __name__ == "__main__":
    main()
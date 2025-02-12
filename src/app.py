


from flask import Flask, request, jsonify
import os, sys

# Add the src directory to Python path
src_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(src_dir)
sys.path.append(project_root)

from src.config import Config
from src.utils.logger import setup_logger, chat_ui_logger
from src.tools import discover_tools
from src.agent.agent import MultiAgentSystem
from memory import GlobalMemory
from src.agent.agent_loader import Agent, AgentStruct, AgentsWorkflow
import requests
import json
from src.utils.kafka import send_to_kafka
import time
import uuid

logger = setup_logger("logs", 'app.log', Config.kafka_logger, Config.KAFKA_LOGS_TOPIC)


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


app = Flask(__name__)

# Initialize tools
tools = discover_tools()
print([tool.name for tool in tools])

workflow = "XRPL.json"

# Initialize the multi-agent system with shared memory
agent_system = MultiAgentSystem(workflow=workflow, tools=tools)

@app.route('/init', methods=['POST'])
def initialize_agents():
    try:
        global agent_system
        agent_system = MultiAgentSystem(agent_struct=workflow, tools=tools)

        return jsonify({"response": "Agents initialized successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ping', methods=['POST'])
def ping():
    return jsonify({"response": "pong"}), 200

@app.route('/prompt', methods=['POST'])
# Example usage:
# curl -X POST http://localhost:5000/prompt -H "Authorization: Bearer MW_API_KEY_HERE" -H "Content-Type: application/json" -d '{"prompt": "What is the price of XRP?"}'
def handle_prompt():
    data = request.json
    headers = request.headers
    auth_header = headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "Authorization header missing"}), 401
    Config.MORPHWARE_API_KEY = auth_header.split(' ')[-1]
    user_input = data.get('prompt', '')
    if not user_input:
        return jsonify({"error": "No prompt provided"}), 400

    try:
        response = agent_system.process_request(user_input)
        if Config.KAFKA.lower() == "true":
            send_to_kafka(Config.kafka_in, Config.KAFKA_IN_TOPIC, user_input)
            send_to_kafka(Config.kafka_out, Config.KAFKA_OUT_TOPIC, format_response(response))
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)

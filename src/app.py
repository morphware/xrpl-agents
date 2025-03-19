from flask import Flask, request, jsonify
import os, sys

# Add the src directory to Python path
src_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(src_dir)
sys.path.append(project_root)

from src.config import Config
from src.utils.logger import setup_logger
from src.tools import discover_tools
from src.agent.agent import MultiAgentSystem
import threading
import uuid
# Initialize logger
logger = setup_logger("logs", 'app.log', Config.kafka_logger, Config.KAFKA_LOGS_TOPIC)
app = Flask(__name__)

# Initialize workflow
agent_system = None

@app.route('/init', methods=['POST'])
def initialize_agents():
    '''
    Initialize agents with a new workflow    
    '''
    try:
        auth_header = request.headers.get('Authorization')
        data = request.get_json()
        xrp_wallet = data.get('wallet_address', '').strip()
        user_id = data.get('user_id', '').strip()
        if user_id:
            Config.USER_ID = user_id

        if xrp_wallet:
            Config.XRP_WALLET = xrp_wallet
        if Config.KAFKA:
            Config.init_kafka()
        if not auth_header:
            return jsonify({"error": "Authorization header missing"}), 401

        Config.MORPHWARE_API_KEY = auth_header.split(' ')[-1]
    except Exception as e:
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    try:
        # Initialize tools
        tools = discover_tools()
        global agent_system
        agent_system = MultiAgentSystem(workflow=Config.AGENT_WORKFLOW_FILE, tools=tools)

        return jsonify({"response": "Agents initialized successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ping', methods=['POST'])
def ping():
    '''
    Health check endpoint
    '''
    return jsonify({"response": "pong"}), 200

@app.route('/prompt', methods=['POST'])
# Example usage:
# curl -X POST http://localhost:5050/prompt -H "Authorization: Bearer MW_API_KEY_HERE" -H "Content-Type: application/json" -d '{"prompt": "What is the price of XRP?"}'
def handle_prompt():
    '''
    Handle user prompt and return response from agents
    '''
    try:
        data = request.get_json()
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({"error": "Authorization header missing"}), 401

        Config.MORPHWARE_API_KEY = auth_header.split(' ')[-1]
        user_input = data.get('prompt', '').strip()
        if not user_input:
            return jsonify({"error": "No prompt provided"}), 400
    except Exception as e:
        return jsonify({"error": f"Invalid request format: {str(e)}"}), 400

    try:
        if agent_system is None:
            initialize_agents()
        if Config.PROCESS_LOCK:
            return jsonify({"error": "Processing previous request. Try again later"}), 503
        else:
            Config.REQUEST_ID = data.get('request_id', str(uuid.uuid4()))
            threading.Thread(target=agent_system.process_request, args=(user_input,)).start()
            Config.PROCESS_LOCK = True
            response = "Prompt processing initiated."
            return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)

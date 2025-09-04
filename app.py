from flask import Flask, request, jsonify, session
from flask_session import Session
from flask_cors import CORS
import os
import logging
import zipfile
from agent_orchestrator import AgentOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("chatbot_debug.log"), logging.StreamHandler()]
)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)


app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

# app.config['SESSION_TYPE'] = 'filesystem'
# app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'null'  # Use in-memory sessions
app.config['SESSION_PERMANENT'] = False

Session(app)

# Path for vector DB storage
VECTOR_DB_EXTRACT_PATH = "/var/data"
VECTOR_DB_FOLDER = "/var/data/vector_db"

BUNDLED_ZIP_PATH = "./vector_db.zip"  # Ensure this ZIP is included in your repo

if os.path.exists(BUNDLED_ZIP_PATH):
    # Create parent directory
    os.makedirs(VECTOR_DB_EXTRACT_PATH, exist_ok=True)
    
    logging.info(f"Unzipping bundled vector DB from {BUNDLED_ZIP_PATH} to {VECTOR_DB_EXTRACT_PATH}")
    with zipfile.ZipFile(BUNDLED_ZIP_PATH, 'r') as zip_ref:
        # Extract to /var/data so that vector_db folder is created there
        zip_ref.extractall(VECTOR_DB_EXTRACT_PATH)
    
    # Verify the extraction worked
    if os.path.exists(VECTOR_DB_FOLDER):
        logging.info(f"Successfully extracted vector DB to {VECTOR_DB_FOLDER}")
    else:
        logging.error(f"Extraction failed - {VECTOR_DB_FOLDER} not found")
else:
    logging.warning(f"No bundled vector DB ZIP found at {BUNDLED_ZIP_PATH}. Continuing without preload.")
    # Create empty directory as fallback
    os.makedirs(VECTOR_DB_FOLDER, exist_ok=True)

# Initialize the agent orchestrator
agent_orchestrator = AgentOrchestrator()
logging.info("Agent orchestrator initialized. Vector databases will be loaded on-demand.")

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        query = data.get('question')
        history = session.get('chat_history', [])

        # ADD THESE DEBUG LINES
        logging.info(f"Session ID: {session.get('_id', 'No session ID')}")
        logging.info(f"Current history length: {len(history)}")
        logging.info(f"History: {history}")

        if not query:
            return jsonify({'error': 'No question provided'}), 400
        
        history.append({'role':'user', 'content':query})
        
        result = agent_orchestrator.process_query(query, history)

        # Handle the response format properly
        response_content = result['response']
        references = []
        
        # Extract response and references if they exist
        if isinstance(response_content, dict):
            actual_response = response_content.get('response', str(response_content))
            references = response_content.get('references', [])
        else:
            actual_response = str(response_content)
        
        history.append({'role':'system', 'content': actual_response})
        session['chat_history'] = history[-6:]
        
        return jsonify({
            'response': actual_response,
            'references': references,
            'agent': {
                'name': result['agent_name'],
                'description': result['agent_description']
            }
        })
        
    except Exception as e:
        logging.error(f"Error in chat endpoint: {e}")
        return jsonify({
            'response': "I apologize, but I'm experiencing technical difficulties. If this is your first query to a specific department, the database might still be loading. Please try again in a moment.",
            'references': [],
            'agent': {'name': 'System', 'description': 'Error handler'}
        }), 500
    
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(port=5000)

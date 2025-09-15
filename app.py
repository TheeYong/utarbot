import uuid
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
    handlers=[logging.StreamHandler()]
)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)


app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_FILE_DIR'] = './.flask_session/'
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SAMESITE'] = "None"
app.config['SESSION_COOKIE_SECURE'] = True


Session(app)

# Path for vector DB storage
VECTOR_DB_EXTRACT_PATH = "/var/data"
VECTOR_DB_FOLDER = "/var/data/vector_db"

BUNDLED_ZIP_PATH = "./vector_db.zip"  

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

@app.before_request
def assign_session_id():
    """Ensure every user gets a unique session ID for each session"""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        query = data.get('question')
        history = session.get('chat_history', [])
        sid = session.get("session_id", "NoSession")

        # ADD THESE DEBUG LINES
        # logging.info(f"Session ID: {session.get('_id', 'No session ID')}")
        logging.info(f"Incoming question: {query}")
        logging.info(f"Current history length: {len(history)}")
        logging.info(f"History so far: {history}")

        if not query:
            return jsonify({'error': 'No question provided'}), 400
        
        history.append({'role':'user', 'content':query})
        
        result = agent_orchestrator.process_query(query, history)

        # # Handle the response format properly
        # response_content = result['response']
        # references = []
        
        # # Extract response and references if they exist
        # if isinstance(response_content, dict):
        #     actual_response = response_content.get('response', str(response_content))
        #     references = response_content.get('references', [])
        # else:
        #     actual_response = str(response_content)
        
        history.append({'role':'assistant', 'content': result['response']})
        # logging.info(f"Final History List: {history}")
        session['chat_history'] = history[-6:]
        # session.modified = True

        logging.info(f"[Session {sid}] Assistant response: {result['response']}")
        logging.debug(f"[Session {sid}] Updated history: {session['chat_history']}")

        return jsonify({
            'response': result['response'],
            'agent': {
                'name': result['agent_name'],
                'description': result['agent_description']
            }
        })
        
    except Exception as e:
        sid = session.get("session_id", "NoSession")
        logging.error(f"[Session {sid}] Error in chat endpoint: {e}")
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

# # from flask import Flask, request, jsonify
# # from chatbot_logic import classify_department, get_vector_database, retrieve_documents, answer_question, preload_all_vector_databases
# # from flask_cors import CORS

# # app = Flask(__name__)
# # CORS(app, resources={r"/chat": {"origins": "http://localhost:3000"}})

# # # @app.route('/chat', methods=['POST'])
# # # def chat():
# # #     data = request.get_json()
# # #     query = data.get('question')

# # #     if not query:
# # #         return jsonify({'error': 'No question provided'}), 400

# # #     department = classify_department(query)
# # #     if not department:
# # #         return jsonify({'answer': "Sorry, I couldn't determine the department."})

# # #     vector_db = get_vector_database(department)
# # #     if vector_db is None:
# # #         return jsonify({'answer': "Sorry, this department has no data yet."})

# # #     contexts = retrieve_documents(vector_db, query)
    
# # #     # Collect all content from the generator
# # #     answer_generator = answer_question(contexts, query, department)
# # #     full_answer = "".join(chunk for chunk in answer_generator)
    
# # #     return jsonify({'response': full_answer})

# # # if __name__ == '__main__':
# # #     app.run(port=5000)

# # # Load all vector databases at startup
# # print("Starting preloading of all department vector databases...")
# # preload_all_vector_databases()
# # print("Preloading complete")

# # @app.route('/chat', methods=['POST'])
# # def chat():
# #     data = request.get_json()
# #     query = data.get('question')
    
# #     if not query:
# #         return jsonify({'error': 'No question provided'}), 400
    
# #     department = classify_department(query)
# #     if not department:
# #         return jsonify({'response': "Sorry, I couldn't determine which department handles this query."})
    
# #     vector_db = get_vector_database(department)
# #     if vector_db is None:
# #         return jsonify({'response': f"Sorry, the {department} database is not available."})
    
# #     contexts = retrieve_documents(vector_db, query)
    
# #     try:
# #         # Safely collect all content from the generator
# #         answer_chunks = []
# #         for chunk in answer_question(contexts, query, department):
# #             if chunk:  # Only add non-empty chunks
# #                 answer_chunks.append(chunk)
                
# #         full_answer = "".join(answer_chunks)
        
# #         # If we got an empty answer despite all our safety checks
# #         if not full_answer:
# #             full_answer = f"I couldn't generate a response. Please contact {department} directly."
            
# #         return jsonify({'response': full_answer})
# #     except Exception as e:
# #         # logging.error(f"Error in chat endpoint: {e}")
# #         return jsonify({'response': f"An error occurred while processing your question. Please try again later."})

# # if __name__ == '__main__':
# #     app.run(port=5000)










# from flask import Flask, request, jsonify, session
# from flask_session import Session
# from flask_cors import CORS
# import os
# import logging
# import zipfile
# from agent_orchestrator import AgentOrchestrator


# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s',
#     handlers=[logging.FileHandler("chatbot_debug.log"), logging.StreamHandler()]
# )

# app = Flask(__name__)
# CORS(app, resources={r"/chat": {"origins": "*"}}, supports_credentials=True)

# app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

# app.config['SESSION_TYPE'] = 'filesystem' # Store the session data on server side filesystem
# app.config['SESSION_PERMANENT'] = False
# app.config['SESSION_FILE_DIR'] = './.flask_session/' # Optional: you can specify the session file location
# app.config['SESSION_USE_SIGNER'] = True # Sign the session identifiers for security

# Session(app)

# # Initialize the agent orchestrator
# agent_orchestrator = AgentOrchestrator()

# # Load all vector databases at startup
# print("Starting preloading of all department vector databases...")
# agent_orchestrator.preload_all_databases()
# print("Preloading complete")

# @app.route('/chat', methods=['POST'])
# def chat():
#     try:
#         data = request.get_json()
#         query = data.get('question')
#         # Get the conversation history or create a new empty one
#         history = session.get('chat_history', [])
        
#         # Add user's message to the conversation history
#         history.append({'role':'user', 'content':query})

#         if not query:
#             return jsonify({'error': 'No question provided'}), 400
        
#         # Process the query through the agent orchestrator
#         result = agent_orchestrator.process_query(query, history)

#         # Store the chatbot response into the conversation history
#         history.append({'role':'system', 'content':result['response']})
        
#         print("Final history list:", history)
#         # Save the conversation history to current session
#         session['chat_history'] = history[-6:]

#         return jsonify({
#             'response': result['response'],
#             # 'references': result['references'],
#             'agent': {
#                 'name': result['agent_name'],
#                 'description': result['agent_description']
#             }
#         })
#     except Exception as e:
#         logging.error(f"Error in chat endpoint: {e}")
#         return jsonify({'response': f"An error occurred while processing your question. Please try again later."})

# @app.route('/health', methods=['GET'])
# def health_check():
#     """Health check endpoint for monitoring"""
#     return jsonify({'status': 'ok'})

# if __name__ == '__main__':
#     app.run(port=5000)

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
CORS(app, resources={r"/chat": {"origins": "*"}}, supports_credentials=True)

app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_FILE_DIR'] = './.flask_session/'
app.config['SESSION_USE_SIGNER'] = True

Session(app)

# Path for vector DB storage
VECTOR_DB_EXTRACT_PATH = "/var/data"
VECTOR_DB_FOLDER = "/var/data/vector_db"

# ----------------------
# Option 1: Unzip bundled vector DB at startup
# ----------------------
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

# Load all vector databases only **after** unzip
if os.path.exists(VECTOR_DB_FOLDER) and os.listdir(VECTOR_DB_FOLDER):
    logging.info("Starting preloading of all department vector databases...")
    agent_orchestrator.preload_all_databases()
    logging.info("Preloading complete")
else:
    logging.warning("Vector DB folder is empty. Skipping preload.")


@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        query = data.get('question')
        history = session.get('chat_history', [])
        
        history.append({'role':'user', 'content':query})

        if not query:
            return jsonify({'error': 'No question provided'}), 400
        
        result = agent_orchestrator.process_query(query, history)
        history.append({'role':'system', 'content':result['response']})
        
        session['chat_history'] = history[-6:]
        return jsonify({
            'response': result['response'],
            'agent': {
                'name': result['agent_name'],
                'description': result['agent_description']
            }
        })
    except Exception as e:
        logging.error(f"Error in chat endpoint: {e}")
        return jsonify({'response': f"An error occurred while processing your question. Please try again later."})

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(port=5000)

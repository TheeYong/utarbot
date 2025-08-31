import os
import logging
from openai import OpenAI
from agent_classes import AdmissionsAgent, FinanceAgent, ExaminationAgent, GeneralAgent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

chat_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY_CHAT"))
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")

class AgentOrchestrator:
    """An agent that manages multiple specialized agents and routes queries to the appropriate one"""

    
    def __init__(self):
        self.agents = []
        self.initialize_agents()
        

    def initialize_agents(self):
        """Initialize all available agents"""
        # Add specialized agents
        self.agents.append(AdmissionsAgent())
        self.agents.append(FinanceAgent())
        self.agents.append(ExaminationAgent())
        
        # Add the general agent as the last candidate to answer query if no relevant and related specified agents found
        self.agents.append(GeneralAgent())
        
        # Initialize each agent
        for agent in self.agents:
            logging.info(f"Initialized agent: {agent.name}")
            
    def get_agent_for_query(self, query):
        """Find the most appropriate agent to handle a query using LLM"""
        try:
            # Create agent descriptions for the LLM
            agent_descriptions = []
            for i, agent in enumerate(self.agents):
                agent_descriptions.append(f"Agent {i+1}: {agent.name} - {agent.description}")
            
            agent_info = "\n".join(agent_descriptions)
            
            prompt = f"""You are a router that determines which university agent should handle a user query.
            
            Available agents:
            {agent_info}

            User query: "{query}"

            ROUTING INSTRUCTIONS:
            1. Examine both the TOPIC and CONTEXT of the query carefully
            2. Look for department-specific keywords and subjects (admissions, finance/fees/scholarships, exams/courses)
            3. If the query relates to a department's core responsibility area, route to that department EVEN IF some terms are unfamiliar
            4. Examples of routing logic:
            - Questions about exam procedures, exam rules, exam requirements, or anything happening during exams → Department of Examination and Awards
            - Questions about admissions process, applications, entry requirements → Division of Admissions
            - Questions about fees, payments, scholarships, financial aid → Division of Finance
            5. Only route to the General Agent if the query clearly doesn't relate to the core responsibilities of any specialized department

            Based on these instructions, respond ONLY with the appropriate agent designation (e.g., "Agent 1", "Agent 2", etc.) without any explanation.
            """
            
            # Call the LLM to determine the appropriate agent
            response = chat_client.chat.completions.create(
                model=OPENAI_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful router assistant that determines which specialized agent should handle a query."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # Use low temperature for more deterministic results
                max_tokens=10     # We only need a short response
            )
            
            agent_selection = response.choices[0].message.content.strip().lower()
            
            # Extract the agent number from the response
            try:
                if "agent 1" in agent_selection:
                    selected_index = 0
                elif "agent 2" in agent_selection:
                    selected_index = 1
                elif "agent 3" in agent_selection:
                    selected_index = 2
                else:
                    # Default to the general agent
                    selected_index = 3
                
                selected_agent = self.agents[selected_index]
                logging.info(f"LLM selected agent: {selected_agent.name}")
                return selected_agent
                
            except (ValueError, IndexError) as e:
                logging.error(f"Error parsing agent selection: {e}. Using general agent.")
                return self.agents[-1]  # Return the general agent as fallback
                
        except Exception as e:
            logging.error(f"Error in LLM agent selection: {e}")
            # Fallback to the general agent if there's any error
            return self.agents[-1]

    def process_query(self, query, history):
        """Process a user query through the appropriate agent"""
        # Select the appropriate agent
        agent = self.get_agent_for_query(query)
        logging.info(f"Selected agent: {agent.name}")

        # Lazy load the agent's vector database if not already loaded
        if not agent.vector_db:
            logging.info(f"Loading vector database for {agent.name}...")
            agent.initialize()
        
        # Get context information and data from the agent's knowledge base
        contexts = agent.retrieve_context(query)

        # Generate and return the response from the agent
        return {
            "agent_name": agent.name,
            "agent_description": agent.description,
            "response": agent.generate_response(query, contexts, history)
        }
        
    # def preload_all_databases(self):
    #     """Preload all vector databases for faster response times"""
    #     for agent in self.agents:
    #         agent.initialize()

    def preload_all_databases(self):
        """DEPRECATED: This method is kept for backward compatibility but does nothing"""
        logging.warning("preload_all_databases() is deprecated. Using lazy loading instead.")
        pass
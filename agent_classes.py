import os
import logging
import glob
# import ollama
import requests
import certifi
import urllib3
from langchain.schema import Document
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from openai import OpenAI
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
# from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

# Disable only insecure request warnings for UTAR's SSL issue
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Openai setup
chat_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY_CHAT"))
embedding_model = OpenAIEmbeddings(
    model="text-embedding-3-large",
    api_key=os.getenv("OPENAI_API_KEY_EMBED")
    )
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")

# Ollama embeddings
# EMBEDDING_MODEL = "mxbai-embed-large"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("chatbot_debug.log"), logging.StreamHandler()]
)

class BaseAgent:
    """Base agent class with common functionality"""
    
    def __init__(self, name, description, vector_db_path=None, department=None, urls=[]):
        self.name = name
        self.description = description
        self.vector_db = None
        self.vector_db_path = vector_db_path
        self.department = department
        self.urls = urls
        
    def initialize(self):
        """Load the Vector Database for the current agent"""
        if self.vector_db_path:
            self.vector_db = self._load_vector_db()

    def scrape_webpage(self, urls):
        print("\nScrapping some UTAR Webpages.")
        seen_links = set()
        results = []

        with sync_playwright() as p:
            browser = p.chromium.launch()

            for url in urls:
                page = browser.new_page()
                page.goto(url)  
                page.wait_for_timeout(3000)  # wait for JS to load
                html_content = page.content()
                page.close()

                soup = BeautifulSoup(html_content, 'html.parser')



                # ---- Collect Text ----
                page_text_parts = []
                for div in soup.find_all('div', class_='mg'):
                    section_text = div.get_text(separator='\n', strip=True)
                    if section_text:
                        page_text_parts.append(section_text)

                # ---- Collect Unique Links ----
                seen_links = set()
                link_texts = []
                link_metadata_list = []
                for link in soup.find_all('a', href=True):
                    full_url = urljoin(url, link['href'])
                    if full_url not in seen_links:  # ensure uniqueness
                        seen_links.add(full_url)
                        text = link.get_text(strip=True)
                        if text:
                            link_texts.append(text)
                            link_metadata_list.append({"text": text, "url": full_url})

                # ---- Decide How to Combine ----
                if not page_text_parts:  # if no main text, combine link texts
                    combined_text = " | ".join(link_texts)
                else:
                    combined_text = "\n".join(page_text_parts)
                    if link_texts:
                        combined_text += "\nLinks: " + " | ".join(link_texts)

                results.append(
                    Document(
                        page_content=combined_text,
                        metadata={"source":url}
                    )
                )


            browser.close()
            print("\nDone Scraping UTAR Webpages.")

        return results

    def scrape_web_pdfs(self, urls, department, base_folder="/var/data"):
        """
        Scrapes a webpage for all linked PDFs and downloads them into a department folder.
        Handles UTAR's broken SSL for PDFs specifically.
        """
        print("Looking for PDF files in some UTAR Webpages to download...")
        # print("base_folder", base_folder)
        print("department", department)
        download_folder = os.path.join(base_folder, department)
        os.makedirs(download_folder, exist_ok=True)

        pdf_files = []

        # Use Playwright to fetch rendered HTML
        with sync_playwright() as p:
            browser = p.chromium.launch()

            for url in urls:
                page = browser.new_page()
                page.goto(url)
                page.wait_for_timeout(3000)  # wait for JS to load
                html_content = page.content()
                page.close()


                soup = BeautifulSoup(html_content, 'html.parser')

                # Download PDFs only
                for link in soup.find_all('a', href=True):
                    full_url = urljoin(url, link['href'])
                    if full_url.lower().endswith(".pdf"):
                        file_name = os.path.basename(full_url)
                        pdf_path = os.path.join(download_folder, file_name)

                        if os.path.exists(pdf_path):
                            print(f"Skipping (already exists): {file_name}")
                            continue

                        try:
                            if "utar.edu.my" in full_url.lower():
                                # Bypass SSL verification for UTAR
                                r = requests.get(full_url, stream=True, verify=False, timeout=10)
                            else:
                                r = requests.get(full_url, stream=True, verify=certifi.where(), timeout=10)
                            r.raise_for_status() # Check HTTP response for errors to avoid downloading broken files
                            with open(pdf_path, "wb") as f: # Open pdf in binary write mode
                                for chunk in r.iter_content(8192):
                                    if chunk:
                                        f.write(chunk)
                            pdf_files.append(pdf_path)
                            print(f"Downloaded PDF: {pdf_path}")
                        except Exception as e:
                            print(f"Failed to download {full_url}: {e}")
                            
            browser.close()

        return pdf_files
    
    
    def ingest_pdf(self, doc_folder_path):
        scraped_pdf_files = self.scrape_web_pdfs(self.urls, self.department)

        print(f"Looking for PDFs in: {doc_folder_path}")
        if not os.path.exists(doc_folder_path):
            logging.error(f"Folder not found: {doc_folder_path}")
            return None

        all_data = []
        for pdf_file in glob.glob(os.path.join(doc_folder_path, "*.pdf")):
            try:
                print(f"Loading PDF: {pdf_file}")
                loader = UnstructuredPDFLoader(file_path=pdf_file)
                data = loader.load()

                # add source metadata
                for doc in data:
                    doc.metadata["source"] = os.path.basename(pdf_file)

                all_data.extend(data)
            except Exception as e:
                logging.error(f"Failed to load {pdf_file}: {e}")

        return all_data


    def split_documents(self, documents):
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
        return text_splitter.split_documents(documents)


    def _load_vector_db(self):

        """Load vector database from the defined path"""            
        try:
            if os.path.exists(self.vector_db_path):
                print(f"Loading vector database for {self.department} from {self.vector_db_path}...")

                vector_database = Chroma(
                    persist_directory=self.vector_db_path, 
                    embedding_function=embedding_model
                )
            else:
                print(f"Creating vector database for {self.department}...")
                doc_folder_path = f"/var/data/{self.department}"

                # Load PDF data
                pdf_data = self.ingest_pdf(doc_folder_path)
                if pdf_data is None:
                    return None
                
                # Scrape data from UTAR website
                scraped_data = self.scrape_webpage(self.urls)

                # Combine both
                combined_texts = []
                if pdf_data:
                    combined_texts.extend(pdf_data)
                if scraped_data:
                    combined_texts.extend(scraped_data)

                # Chunk the combined text content
                chunks = self.split_documents(combined_texts)

                for i, chunk in enumerate(chunks[:5]):
                    print(f"Chunk {i+1}")
                    print("Text:", chunk.page_content[:200])
                    print("Source:", chunk.metadata.get("source"))
                    print("Metadata:", chunk.metadata)
                    print("------")

                vector_database = Chroma.from_documents(
                    documents=chunks,
                    embedding=embedding_model,
                    persist_directory=self.vector_db_path
                )

            return vector_database
        
        except Exception as e:
            logging.error(f"Failed to load Vector Database for {self.name}: {e}")
            return None
        
    def retrieve_context(self, query, k=3):
        """Retrieve context relevant and related to the user query"""
        if not self.vector_db:
            logging.warning(f"There is no Vector Database available for {self.name}")
            return []
            
        try:
            docs = self.vector_db.similarity_search(query, k=k)
            return docs
        except Exception as e:
            logging.error(f"Failed to retrieve context for the query: {e}")
            return []
        
    def generate_response(self, query, contexts, history):
        """Generate a response based on the query and contexts"""
        # Base implementation
        return f"Hello, I'm {self.name}. I don't have specific information related and relevant to the context of the query."


class AdmissionsAgent(BaseAgent):
    """An Agent class which is specialized in handling admissions queries and questions"""
    
    def __init__(self):
        super().__init__(
            name="Admissions Agent",
            description="Handles admissions-related queries.",
            vector_db_path="/var/data/vector_db/admissions",
            department="Division of Admissions and Credit Evaluation",
            urls=[
                "https://admission.utar.edu.my/About_DACE.php",
                "https://admission.utar.edu.my/Entry-Qualifications-and-English-Language-Requirements.php"
            ]
        )
    
    def generate_response(self, query, contexts, history):
        """Generate responses that is related to admissions queries"""
        if not contexts:
            return "I don't have specific information about that admissions question. Please contact the Division of Admissions directly."
        
        # Retrieve and store references used to generate a response
        references = []
        for doc in contexts:
            source = doc.metadata.get("source", None)
            if source and source not in references:
                references.append(source)

        # Retrieve conversation history of the session
        formatted_history = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history[-6:]])
        
        combined_context = "\n\n---\n\n".join(doc.page_content for doc in contexts)
        prompt = f"""You are an admissions assistant at a university named University Tunku Abdul Rahman or UTAR. Your name is {self.name}.
        Use the following context to answer the question concisely and helpfully, you need to answer the question
        based on context.

        Conversation history:
        {formatted_history}

        Context:
        {combined_context}
        
        Question: {query}
        
        Respond as a knowledgeable admissions professional. Be helpful but concise.
        Only answer based on the given context and the given conversation history. 
        When interpreting questions, refer back to the conversation history to resolve pronouns or implied references. 
        If you cannot find an answer, politely tellthe user to contact the Division of Admissions and Credit Evaluation.
        """
        
        try:
            response = chat_client.chat.completions.create(
                model=OPENAI_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful university admissions assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            return {
                "response": response.choices[0].message.content.strip(),
                "references": references
            }
        except Exception as e:
            logging.error(f"Failed to generate response: {e}")
            return {
            "response": "Sorry, something went wrong while generating the answer.",
            "references": []
        }

class FinanceAgent(BaseAgent):
    """An Agent class which is specialized in handling finance queries"""
    
    def __init__(self):
        super().__init__(
            name="Finance Agent",
            description="Handles finance, fees, and scholarship queries.",
            vector_db_path="/var/data/vector_db/finance",
            department="Division of Finance",
            urls=[
                "https://dfn.utar.edu.my/DFN.php",
                "https://dfn.utar.edu.my/DFN-3.php"
            ]
        )
        
    def generate_response(self, query, contexts, history):
        """Generate finance-specific responses"""
        if not contexts:
            return "I don't have specific information about that financial question. Please contact the Division of Finance directly."
        
        # Retrieve and store references used to generate a response
        references = []
        for doc in contexts:
            source = doc.metadata.get("source", None)
            if source and source not in references:
                references.append(source)

        # Retrieve conversation history of the session
        formatted_history = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history[-6:]])

        combined_context = "\n\n---\n\n".join(doc.page_content for doc in contexts)
        prompt = f"""You are a financial advisor at a university named University Tunku Abdul Rahman or UTAR. Your name is {self.name}.
        Use the following context to answer the question precisely and accurately.

        Conversation history:
        {formatted_history}
        
        Context:
        {combined_context}
        
        Question: {query}
        
        Respond as a precise and detail-oriented finance professional. Mention specific 
        numbers and dates when available. Only answer based on the given context and the given conversation history.
        When interpreting questions, refer back to the conversation history to resolve pronouns or implied references. 
        If you can't find an answer, politely direct the user to contact the Division of Finance.
        """
        
        try:
            response = chat_client.chat.completions.create(
                model=OPENAI_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a precise university financial advisor."},
                    {"role": "user", "content": prompt}
                ]
            )
            return {
                "response": response.choices[0].message.content.strip(),
                "references": references
            }
        except Exception as e:
            logging.error(f"Failed to generate response: {e}")
            return {
            "response": "Sorry, something went wrong while generating the answer.",
            "references": []
        }

class ExaminationAgent(BaseAgent):
    """An Agent class which is specialized in handling examination, academic and course queries"""
    
    def __init__(self):
        super().__init__(
            name="Examinations Agent",
            description="Handles course and exam queries", ##TODO handle the problem when convocation is directed to exam agent
            vector_db_path="/var/data/vector_db/examinations",
            department="Department of Examination and Awards",
            urls=[
                "https://deas.utar.edu.my/Announcement.php",
                "https://deas.utar.edu.my/Home.php"
            ]
        )
        
    def generate_response(self, query, contexts, history):
        """Generate academic-specific responses"""
        if not contexts:
            return "I don't have specific information about that academic question. Please contact the Department of Examination and Awards directly."
        
        # # 🔍 Debug: Print all context items
        # for i, ctx in enumerate(contexts, 1):
        #     print(f"\n--- Context {i} ---")
        #     print(ctx)
        #     print(f"Type: {type(ctx)}")
        #     if isinstance(ctx, dict):
        #         print("Keys:", ctx.keys())

        print("History for agent: ", history)

        # Retrieve and store references used to generate a response
        references = []
        for doc in contexts:
            source = doc.metadata.get("source", None)
            if source and source not in references:
                references.append(source)
        
        # Retrieve conversation history of the session
        formatted_history = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history[-6:]])

        print("Formatted history for agent: ", formatted_history)

        combined_context = "\n\n---\n\n".join(doc.page_content for doc in contexts)
        prompt = f"""You are an academic coordinator at a university named University Tunku Abdul Rahman or UTAR. Your name is {self.name}.
        Use the following context to answer the question clearly and informatively.
        
        Conversation history:
        {formatted_history}

        Context:
        {combined_context}
        
        Question: {query}
        
        Respond as a knowledgeable academic professional. Be educational but approachable.
        Only answer based on the given context and based on the given conversation history.
        When interpreting questions, refer back to the conversation history to resolve pronouns or implied references.
        If you can't find an answer, politely direct the user 
        to contact the Department of Examination and Awards.
        """
        
        try:
            response = chat_client.chat.completions.create(
                model=OPENAI_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful university academic coordinator."},
                    {"role": "user", "content": prompt}
                ]
            )
            return {
                "response": response.choices[0].message.content.strip(),
                "references": references
            }
        except Exception as e:
            logging.error(f"Failed to generate response: {e}")
            return {
            "response": "Sorry, something went wrong while generating the answer.",
            "references": []
        }
            # return "I'm sorry, I'm facing problems in accessing my academic database right now. Please try again later or contact the Department of Examination and Awards directly."


class GeneralAgent(BaseAgent):
    """General agent for handling queries that do not fit any specific department"""
    
    def __init__(self):
        super().__init__(
            name="University Information Assistant",
            description="General knowledge about the university",
            vector_db_path="/var/data/vector_db/general",
            department="General"
        )
        
    def generate_response(self, query, contexts, history):
        """Generate general responses for the user query"""

        # Retrieve and store references used to generate a response
        references = []
        for doc in contexts:
            source = doc.metadata.get("source", None)
            if source and source not in references:
                references.append(source)

        # Retrieve conversation history of the session
        formatted_history = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history[-6:]])
        
        prompt = f"""You are a general university information assistant for a university named University Tunku Abdul Rahman or UTAR. Your name is {self.name}.
        Use the following context and conversation history to answer the question concisely and helpfully, you need to answer the question
        based on context.

        Conversation history:
        {formatted_history}
        
        Question: {query}
        
        Respond as a helpful university assistant. For this query, if you do not have any specific information,
        then you should provide a general response and suggest which department might help.
        """
        
        try:
            response = chat_client.chat.completions.create(
                model=OPENAI_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful university information assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            return {
                "response": response.choices[0].message.content.strip(),
                "references": references
            }
        except Exception as e:
            logging.error(f"Failed to generate response: {e}")
            return {
            "response": "Sorry, something went wrong while generating the answer.",
            "references": []
        }
import streamlit as st
import requests
import google.generativeai as genai
import os
import json
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from langchain_community.document_loaders import PyMuPDFLoader, UnstructuredHTMLLoader, BSHTMLLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Pinecone as PineconeVectorStore
from langchain_community.vectorstores import Pinecone
from langchain_community.vectorstores.pinecone import Pinecone as PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

# ---- NEW: Import toml (or tomli) and load config.toml
import toml

try:
    with open("config.toml", "r") as f:
        config_data = toml.load(f)
except FileNotFoundError:
    raise RuntimeError(
        "config.toml file not found. Please create a config.toml with your API keys."
    )

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Base directory for financial documents
BASE_DIR = os.path.expanduser("~/financial_doc_analyzer")
os.makedirs(BASE_DIR, exist_ok=True)

# Hard-coded configuration
CONFIG = {
    "user_agent": "Financial Doc Analyzer 1.0 yourname@example.com",  # Replace with your email
    "models": {
        "embedding": "text-embedding-ada-002",  # Hard-coded OpenAI embedding model
        "generation": "gemini-2.0-flash"        # Hard-coded Gemini generation model
    },
    "chunk_size": 500,
    "chunk_overlap": 100,
    "max_workers": 5,
    "cache_expiry_days": 7,
    "sec_request_delay": 0.1
}

# ---- NEW: Load keys from config_data (instead of os.getenv)
GEMINI_API_KEY = config_data.get("GEMINI_API_KEY")
OPENAI_API_KEY = config_data.get("OPENAI_API_KEY")
PINECONE_API_KEY = config_data.get("PINECONE_API_KEY")

# Validate keys
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in config.toml. Please set it before running the app.")
    st.stop()

if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY not found in config.toml. Please set it before running the app.")
    st.stop()

if not PINECONE_API_KEY:
    st.error("PINECONE_API_KEY not found in config.toml. Please set it before running the app.")
    st.stop()

# Initialize Google Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# **🔹 Fetch CIK by Ticker**
def get_cik_by_ticker(ticker):
    """Fetch CIK from SEC API based on ticker symbol."""
    try:
        ticker_url = "https://www.sec.gov/files/company_tickers.json"
        headers = {"User-Agent": CONFIG["user_agent"]}
        response = requests.get(ticker_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        for item in data.values():
            if item['ticker'].lower() == ticker.lower():
                return str(item['cik_str']).zfill(10)
        return None
    except Exception as e:
        st.error(f"Error fetching CIK for ticker {ticker}: {e}")
        return None

# **🔹 Document Fetcher (CIK-based SEC Filings)**
def fetch_sec_filings(cik, form_types, start_year, end_year):
    """Fetch SEC filings URLs based on CIK."""
    try:
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        headers = {"User-Agent": CONFIG["user_agent"]}
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(submissions_url)
        response.raise_for_status()
        data = response.json()

        filing_data = []
        filings_data = data.get("filings", {}).get("recent", {})
        forms = filings_data.get("form", [])
        dates = filings_data.get("filingDate", [])
        accessions = filings_data.get("accessionNumber", [])
        primary_docs = filings_data.get("primaryDocument", [])

        for form, filing_date, accession_number, primary_document in zip(forms, dates, accessions, primary_docs):
            filing_year = int(filing_date.split("-")[0])
            if form not in form_types or not (start_year <= filing_year <= end_year):
                continue
            accession_number = accession_number.replace("-", "")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number}/{primary_document}"
            index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number}"
            filing_data.append((filing_url, form, filing_date, index_url))
        return filing_data
    except Exception as e:
        st.error(f"Error fetching filings: {e}")
        return []

# **🔹 Document Processing**
def process_pdf(pdf_path):
    """Processes a PDF file into text chunks."""
    try:
        loader = PyMuPDFLoader(pdf_path)
        documents = loader.load()
        return documents
    except Exception as e:
        logger.error(f"Error processing PDF {pdf_path}: {e}")
        return [Document(page_content=f"Error processing file: {e}", metadata={"source": pdf_path})]

def process_html(html_path):
    """Extracts text from an HTML file."""
    try:
        loader = BSHTMLLoader(html_path)
        documents = loader.load()
        if not documents or not documents[0].page_content.strip():
            with open(html_path, "r", encoding="utf-8", errors="ignore") as file:
                soup = BeautifulSoup(file, "html.parser")
                for script in soup(["script", "style"]):
                    script.extract()
                text = soup.get_text(separator="\n")
                text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
                documents = [Document(page_content=text, metadata={"source": html_path})]
        return documents
    except Exception as e:
        logger.error(f"Error processing HTML {html_path}: {e}")
        return [Document(page_content=f"Error processing file: {e}", metadata={"source": html_path})]

def download_filing(url, save_path, ticker, form, date):
    """Download a filing with proper headers and retry logic."""
    headers = {"User-Agent": CONFIG["user_agent"]}
    delay = CONFIG.get("sec_request_delay", 0.1)
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '').lower()
            if 'html' in content_type:
                file_ext = '.html'
            elif 'pdf' in content_type:
                file_ext = '.pdf'
            else:
                file_ext = '.txt'
            file_name = f"{ticker}_{date.replace('-', '')}_{form}{file_ext}"
            file_path = os.path.join(save_path, file_name)
            with open(file_path, "wb") as f:
                f.write(response.content)
            time.sleep(delay)
            return file_path
        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
            time.sleep(1)
    logger.error(f"Failed to download {url} after multiple attempts")
    return None

# **🔹 Build Vector Database with Pinecone**
from pinecone import Pinecone, ServerlessSpec
from langchain_community.vectorstores import Pinecone as PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

# **🔹 Build Vector Database with Pinecone v3.1.0**
def build_vector_database(documents):
    st.write("🚀 **Building Vector Database with Pinecone...**")
    progress_bar = st.progress(0)
    try:
        # Split documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CONFIG["chunk_size"],
            chunk_overlap=CONFIG["chunk_overlap"]
        )
        chunks = text_splitter.split_documents(documents)
        
        # Initialize embeddings with the OpenAI API key from .toml
        embedding_model = OpenAIEmbeddings(model="text-embedding-ada-002", openai_api_key=OPENAI_API_KEY)
        
        # Initialize Pinecone with the key from .toml
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Create (or reference) the index
        index_name = "financial-doc-analyzer-index"
        if index_name not in pc.list_indexes().names():
            pc.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        
        # Create vector store
        vectorstore = PineconeVectorStore.from_documents(
            documents=chunks,
            embedding=embedding_model,
            index_name=index_name,
            text_key="text"
        )
        
        # Create retriever
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        
        progress_bar.progress(100)
        st.success("Vector database built successfully!")
        return retriever, index_name

    except Exception as e:
        st.error(f"Error: {str(e)}")
        raise

# **🔹 RAG Chain with Gemini Generation**
def rag_chain(question, retriever):
    """Retrieve relevant document chunks and generate an answer using Gemini API."""
    try:
        retrieved_docs = retriever.invoke(question)
        if not retrieved_docs:
            return "No relevant information found.", None
        context_parts = [f"[DOC {i+1}]\n{doc.page_content}" for i, doc in enumerate(retrieved_docs)]
        context = "\n\n".join(context_parts)
        formatted_prompt = f"""
        You are a financial expert analyzing SEC filings (10-K, 10-Q, 8-K).
        
        **Question:** {question}
        
        **Context:**
        {context}

        Based only on the information provided in the context, provide a detailed, structured response including:
        - Direct answer to the question
        - Key financial data mentioned in the context
        - Important trends or insights from the documents
        - Include citations to the [DOC X] references when providing information
        
        If the information to answer the question is not in the context, state that clearly.
        """
        model = genai.GenerativeModel(CONFIG["models"]["generation"])
        response = model.generate_content(formatted_prompt)
        return response.text, retrieved_docs
    except Exception as e:
        logger.error(f"Error in RAG chain: {e}")
        return f"An error occurred: {e}", None

# **🔹 Alternative SEC Filing Fetcher (Using the HTML index page)**
def fetch_alternative_sec_filings(cik, ticker, form_types, start_year, end_year):
    """Fetch SEC filings directly from the company's filing page."""
    try:
        company_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={'%2C'.join(form_types)}&dateb=&owner=exclude&count=100"
        headers = {"User-Agent": CONFIG["user_agent"]}
        st.write(f"Fetching from SEC company page: {company_url}")
        response = requests.get(company_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        filing_data = []
        filing_tables = soup.select('table.tableFile2')
        if not filing_tables:
            st.warning("No filing table found on SEC page.")
            return []
        for table in filing_tables:
            rows = table.select('tr')
            for row in rows:
                cells = row.select('td')
                if len(cells) < 4:
                    continue
                form_type = cells[0].get_text().strip()
                if form_type not in form_types:
                    continue
                date_text = cells[3].get_text().strip()
                try:
                    filing_date = datetime.strptime(date_text, '%Y-%m-%d')
                    filing_year = filing_date.year
                    if not (start_year <= filing_year <= end_year):
                        continue
                except ValueError:
                    continue
                document_link = cells[1].find('a', {'href': True})
                if not document_link:
                    continue
                doc_href = document_link['href']
                if doc_href.startswith('/Archives'):
                    filing_url = f"https://www.sec.gov{doc_href}"
                else:
                    filing_url = f"https://www.sec.gov/Archives{doc_href}"
                filing_data.append((filing_url, form_type, date_text, ""))
        return filing_data
    except Exception as e:
        st.error(f"Error fetching filings from SEC company page: {e}")
        return []

# **🔹 Streamlit App**
def main():
    st.set_page_config(page_title="SEC Financial Analyzer", page_icon="📄", layout="wide")
    st.title("📄 SEC Financial Analyzer")
    st.markdown("Analyze SEC filings using AI-powered search and embeddings.")
    
    ticker = st.text_input("Enter Ticker Symbol (e.g., AAPL):", key="download_ticker").strip().upper()
    if ticker:
        cik = get_cik_by_ticker(ticker)
        if not cik:
            st.error(f"CIK not found for ticker {ticker}. Please check the ticker symbol.")
        else:
            st.info(f"CIK found for ticker {ticker}: {cik}")
    else:
        cik = None

    col1, col2, col3 = st.columns(3)
    with col1:
        start_year = st.number_input("Start Year:", min_value=2000, max_value=datetime.now().year, value=2022)
    with col2:
        end_year = st.number_input("End Year:", min_value=2000, max_value=datetime.now().year, value=datetime.now().year)
    with col3:
        form_types = st.multiselect("Filing Types:", options=["10-K", "10-Q", "8-K"], default=["10-K", "10-Q"])
    
    col1, col2 = st.columns(2)
    with col1:
        fetch_button = st.button("📥 Fetch Filings", key="fetch_filings")
    with col2:
        alt_fetch_button = st.button("📥 Use Alternative Method", key="alt_fetch")
        
    if fetch_button or alt_fetch_button:
        if not cik:
            st.error("CIK is required to fetch SEC filings. Please enter a valid ticker symbol.")
        else:
            with st.spinner("Fetching filings..."):
                if fetch_button:
                    filings = fetch_sec_filings(cik, form_types, start_year, end_year)
                else:
                    filings = fetch_alternative_sec_filings(cik, ticker, form_types, start_year, end_year)
            if not filings:
                st.warning("No filings found. Try using the alternative method.")
            else:
                st.success(f"Found {len(filings)} filings!")
                filing_df = pd.DataFrame([(url, form, date) for url, form, date, _ in filings],
                                         columns=["URL", "Form", "Date"])
                st.dataframe(filing_df)
                with st.spinner("Downloading filings..."):
                    temp_dir = tempfile.mkdtemp()
                    st.session_state["temp_dir"] = temp_dir
                    progress_bar = st.progress(0)
                    downloaded_files = []
                    for i, (url, form, date, _) in enumerate(filings):
                        file_path = download_filing(url, temp_dir, ticker, form, date)
                        if file_path:
                            downloaded_files.append(file_path)
                        progress_bar.progress((i + 1) / len(filings))
                    st.session_state["downloaded_files"] = downloaded_files
                    st.success(f"Downloaded {len(downloaded_files)} of {len(filings)} filings successfully.")
                if downloaded_files:
                    with st.spinner("Processing documents..."):
                        documents = []
                        progress_bar = st.progress(0)
                        for i, file_path in enumerate(downloaded_files):
                            if file_path.lower().endswith(".pdf"):
                                doc_chunks = process_pdf(file_path)
                            elif file_path.lower().endswith((".htm", ".html")):
                                doc_chunks = process_html(file_path)
                            else:
                                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                                    content = f.read()
                                doc_chunks = [Document(page_content=content, metadata={"source": file_path})]
                            documents.extend(doc_chunks)
                            progress_bar.progress((i + 1) / len(downloaded_files))
                        st.success(f"Processed {len(documents)} document chunks.")
                        st.session_state["documents"] = documents
                        with st.spinner("Building vector database..."):
                            retriever, index_name = build_vector_database(documents)
                            st.session_state["retriever"] = retriever
                            st.session_state["index_name"] = index_name
                            st.success("Vector database built successfully!")
    if "retriever" in st.session_state:
        st.markdown("---")
        st.subheader("📊 Query SEC Filings")
        query_examples = [
            "What was the company's revenue in the most recent quarter?",
            "What are the key risks mentioned in the latest 10-K?",
            "How has the gross margin changed over the last year?",
            "What were the major acquisitions in the past year?",
            "What is the company's debt-to-equity ratio?"
        ]
        selected_example = st.selectbox("Example questions:", [""] + query_examples)
        if selected_example:
            question = selected_example
        else:
            question = st.text_area("Ask a question about the filings:", height=100)
        if st.button("Generate Answer") and question:
            retriever = st.session_state["retriever"]
            with st.spinner("Generating answer..."):
                answer, sources = rag_chain(question, retriever)
                st.markdown("### Answer")
                st.markdown(answer)
                if sources:
                    with st.expander("View Sources"):
                        for i, doc in enumerate(sources):
                            st.markdown(f"**Source {i+1}**")
                            st.markdown(f"*From: {doc.metadata.get('source', 'Unknown')}*")
                            st.text(
                                doc.page_content[:300] + "..."
                                if len(doc.page_content) > 300
                                else doc.page_content
                            )
                            st.markdown("---")

if __name__ == "__main__":
    main()

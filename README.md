# SEC Financial Analyzer
![](https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Seal_of_the_United_States_Securities_and_Exchange_Commission.svg/640px-Seal_of_the_United_States_Securities_and_Exchange_Commission.svg.png)

https://financialdocanalyser.streamlit.app/


# 🚀 AI-Powered SEC Filings Analysis  

This cutting-edge application revolutionizes how you analyze SEC filings by leveraging AI-powered search and embeddings.  

## 🔍 Instant Insights  
No more sifting through dense **10-K, 10-Q, or 8-K** reports. Simply input a **ticker**, and the tool retrieves, processes, and stores filings in a structured vector database.  

## 💡 AI-Driven Search  
Ask financial, risk, or strategy-related questions and get **precise, context-aware answers**—complete with relevant citations—thanks to **Google Gemini (PaLM)**.  

## ⚡ Optimized for Speed & Accuracy  
- **OpenAI embeddings** generate high-quality vector representations of financial documents.  
- **Pinecone** ensures **fast and scalable** search across filings.  
- **Streamlit** delivers a **seamless, interactive UI** for easy exploration.  

### 🚀 Why This Is Cool  
Whether you're an **investor, analyst, or researcher**, this tool **makes SEC filing analysis smarter, faster, and more efficient**—turning unstructured financial data into **actionable insights in seconds**.  


---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Project Structure](#project-structure)
7. [FAQs and Troubleshooting](#faqs-and-troubleshooting)
8. [License](#license)

---

## Features

- **SEC Filings Fetching**  
  Automatically fetches SEC filings (e.g., 10-K, 10-Q, 8-K) for a given Ticker/CIK from the SEC website.

- **Alternate Fetch Method**  
  Provides a backup method to retrieve filings if the default approach doesn't find results.

- **Document Parsing**  
  Supports parsing PDF (using [PyMuPDFLoader](https://github.com/lanpa/pdf-extractor/blob/master/langchain_community/document_loaders/pymupdf.py)) and HTML documents (using BeautifulSoup-based loaders).

- **Chunking & Vectorization**  
  Splits documents into smaller chunks, embeds them with OpenAI embeddings (`text-embedding-ada-002`), and stores them in **Pinecone**.

- **RAG (Retrieve-And-Generate) Workflow**  
  Uses retrieved chunks as context to generate an answer with **Google Gemini** (PaLM) large language model.

- **Streamlit UI**  
  Interactive interface for setting ticker, date range, form types, fetching/downloading filings, building the vector database, and querying the documents.

---

## Requirements

- **Python 3.8+** recommended
- Dependencies listed in [`requirements.txt`](./requirements.txt)
- [**config.toml**](#configuration) file with valid API keys

### Required API Keys

1. **Google Gemini (PaLM) API Key** (`GEMINI_API_KEY`)
2. **OpenAI API Key** (`OPENAI_API_KEY`)
3. **Pinecone API Key** (`PINECONE_API_KEY`)

---

## Installation

1. **Clone or Download** the repository:
   ```bash
   git clone https://github.com/your-username/financial_doc_analyzer.git
   cd financial_doc_analyzer
   ```

2. **Create and Activate a Virtual Environment** (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Linux/Mac
   # or
   venv\Scripts\activate     # On Windows
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Create a `config.toml` File**:
   ```toml
   GEMINI_API_KEY = "your_gemini_api_key_here"
   OPENAI_API_KEY = "your_openai_api_key_here"
   PINECONE_API_KEY = "your_pinecone_api_key_here"
   ```

5. **Run the Streamlit App**:
   ```bash
   streamlit run app.py
   ```

6. **Open in Browser**  
   Streamlit should automatically open a browser tab at `http://localhost:8501`. If not, visit it manually.

---

## Configuration

All API keys are read from `config.toml`:

```python
import toml

try:
    with open("config.toml", "r") as f:
        config_data = toml.load(f)
except FileNotFoundError:
    raise RuntimeError("config.toml file not found. Please create a config.toml with your API keys.")

GEMINI_API_KEY = config_data.get("GEMINI_API_KEY")
OPENAI_API_KEY = config_data.get("OPENAI_API_KEY")
PINECONE_API_KEY = config_data.get("PINECONE_API_KEY")
```

Make sure your `config.toml` has these keys defined.

---

## Usage

1. **Enter Ticker**
2. **Select Year Range and Filing Types**
3. **Fetch Filings**
4. **Download & Process Filings**
5. **Build Vector Database**
6. **Query the Vector Database**

---

## Project Structure

```
financial_doc_analyzer/
├── app.py                  # Main Streamlit app
├── config.toml             # TOML file with API keys (not in repo)
├── requirements.txt        # Python dependencies
├── README.md               # This README
├── ...
```

---
## APP
https://financialdocanalyser.streamlit.app/
![](https://github.com/abh2050/financial_doc_analyser/blob/main/pic1.png)
![](https://github.com/abh2050/financial_doc_analyser/blob/main/pic2.png)

## FAQs and Troubleshooting

- **`FileNotFoundError: config.toml file not found`**  
  Ensure `config.toml` exists in the project directory.

- **Invalid API Key errors**  
  Double-check API keys and ensure services are properly configured.

- **No Filings Found**  
  Try **"Use Alternative Method"** or verify the ticker and date range.

- **Pinecone Index Issues**  
  Check if the index name conflicts with an existing one.

- **Timeouts or Performance Issues**  
  Adjust chunk size and max workers for better performance.

---

## License

This project is provided under the [MIT License](LICENSE.md). Feel free to use, modify, and distribute it as you see fit.

---

_**Happy analyzing!**_

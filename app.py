# app.py (Streamlit Version with Gemini API)
import streamlit as st
import asyncio
import aiohttp
import json
import io
import webbrowser
import re

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import blue, black
from reportlab.lib.units import inch

# --- API Keys Configuration ---
# IMPORTANT: Replace with your actual keys
GOOGLE_API_KEY = "ENTER YOUR GOOGLE API KEY HERE" # <<< Your Google API Key
CSE_ID = "ENTER YOUR CSE_ID HERE" # <<< Your Custom Search Engine ID
GEMINI_API_KEY = "ENTER YOUR GEMINI API KEY HERE " # <<< Your Gemini API Key

# --- Global Styles for PDF (to prevent KeyError on re-runs) ---
_pdf_styles = getSampleStyleSheet()

if 'Code' not in _pdf_styles:
    _pdf_styles.add(ParagraphStyle(
        'Code',
        parent=_pdf_styles['Code'],
        fontName='Courier',
        fontSize=9,
        leading=10,
        textColor=black,
        backColor='#F0F0F0',
        borderPadding=(5, 5, 5, 5),
        borderColor='#CCCCCC',
        borderWidth=0.5,
        borderRadius=2,
        spaceBefore=6,
        spaceAfter=6,
        leftIndent=0.2 * inch,
        rightIndent=0.2 * inch,
    ))

# --- Helper functions for API calls (adapted for Streamlit) ---

async def call_gemini_api(session, prompt, response_schema=None):
    """
    Calls the Gemini API to generate text or structured responses using aiohttp.
    """
    # Check if API key is provided
    if not GEMINI_API_KEY:
        st.error("Gemini API Key is missing. Please set GEMINI_API_KEY in your app.py file.")
        return None

    chat_history = []
    chat_history.append({ "role": "user", "parts": [{ "text": prompt }] }) 
    
    payload = { "contents": chat_history }
    if response_schema:
        payload["generationConfig"] = {
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        }

    apiUrl = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    response_text = ""
    try:
        async with session.post(apiUrl, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as response:
            response_text = await response.text() 
            
            response.raise_for_status()
            result = json.loads(response_text)

            if result.get("candidates") and len(result["candidates"]) > 0 and \
               result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts") and \
               len(result["candidates"][0]["content"]["parts"]) > 0:
                
                if response_schema:
                    parsed_json = json.loads(result["candidates"][0]["content"]["parts"][0]["text"])
                    
                    def remove_asterisks_from_dict(obj):
                        if isinstance(obj, dict):
                            return {k: remove_asterisks_from_dict(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [remove_asterisks_from_dict(elem) for elem in obj]
                        elif isinstance(obj, str):
                            return obj.replace('*', '')
                        return obj
                    
                    return remove_asterisks_from_dict(parsed_json)
                else:
                    return result["candidates"][0]["content"]["parts"][0]["text"].replace('*', '')
            else:
                st.error("Gemini API: Unexpected response structure or no content generated. Please try again.")
                return None
    except asyncio.TimeoutError:
        st.error(f"Error calling Gemini API: Request timed out after 20 seconds. Please check your internet connection or try again later.")
        return None
    except aiohttp.ClientConnectorError as e:
        st.error(f"Error calling Gemini API: Could not connect to the server. Please check your internet connection or firewall. Details: {e}")
        return None
    except aiohttp.ClientResponseError as e:
        if e.status == 503:
            st.error(f"Gemini API: Service Unavailable (HTTP 503). The model may be overloaded or temporarily unavailable. Please try again in a few moments.")
        elif e.status == 400:
             st.error(f"Gemini API: Bad Request (HTTP 400). This might be due to an invalid API key, incorrect request format, or content policy violation. Please check your API key and query. Response: {response_text}")
        elif e.status == 429:
            st.error(f"Gemini API: Too Many Requests (HTTP 429). You have exceeded your quota. Please wait and try again later.")
        else:
            st.error(f"Error calling Gemini API: HTTP Error {e.status} - {e.message}. Response: {response_text}. Please review the error details.")
        return None
    except json.JSONDecodeError as e:
        st.error(f"Error decoding JSON from Gemini API response. The API might have returned non-JSON. Raw text was: {response_text}. Error: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred while calling Gemini API: {e}. Please report this issue.")
        return None

async def perform_google_search(session, query, num_results=3): # Limit to top 3 articles
    """
    Performs a Google Custom Search for web articles.
    The query is refined to improve relevance for tech topics.
    """
    # Check if API key is provided
    if not GOOGLE_API_KEY or not CSE_ID:
        st.error("Google API Key or CSE ID is missing. Please set GOOGLE_API_KEY and CSE_ID in your app.py file.")
        return {"web": [], "youtube": []}

    # Refine the query for better tech relevance
    refined_query = query
    tech_keywords = ["tech", "technology", "programming", "software", "computer science", "development", "coding"]
    
    # Add tech keywords if not already present in the query
    if not any(keyword in query.lower() for keyword in tech_keywords):
        refined_query = f"{query} tech" # Append "tech" as a general qualifier
    
    web_results = []

    try:
        web_url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={CSE_ID}&q={refined_query}&num={num_results}"
        async with session.get(web_url, timeout=aiohttp.ClientTimeout(total=20)) as response:
            response_text = await response.text()
            
            response.raise_for_status()
            data = json.loads(response_text)
            
            if data.get('items'):
                for item in data['items']:
                    web_results.append({
                        "title": item.get('title'),
                        "link": item.get('link'),
                        "snippet": item.get('snippet')
                    })
            else:
                pass # Keep pass to explicitly do nothing
    except asyncio.TimeoutError:
        st.error(f"Error during Google Web Search: Request timed out after 20 seconds. Please check your internet connection or try again later.")
        web_results = []
    except aiohttp.ClientConnectorError as e:
        st.error(f"Error during Google Web Search: Could not connect to the server. Please check your internet connection or firewall. Details: {e}")
        web_results = []
    except aiohttp.ClientResponseError as e:
        if e.status == 403:
            st.error(f"Google Custom Search API: Access Denied (HTTP 403). Please ensure your Google API Key is correct, enabled for Custom Search API, and has no IP restrictions preventing access from your location.")
        else:
            st.error(f"Error during Google Web Search: HTTP Error {e.status} - {e.message}. Response: {response_text}. Please review the error details.")
        web_results = []
    except json.JSONDecodeError as e:
        st.error(f"Error decoding JSON from Google Custom Search response. The API might have returned non-JSON. Raw text was: {response_text}. Error: {e}")
        web_results = []
    except Exception as e:
        st.error(f"An unexpected error occurred during Google Web Search: {e}. Please report this issue.")
        web_results = []

    youtube_results = await search_youtube_videos(session, query, num_results)

    return {
        "web": web_results,
        "youtube": youtube_results
    }

async def search_youtube_videos(session, query, num_results=3): # Limit to top 3 videos
    """
    Performs a dedicated search on YouTube using the YouTube Data API v3 with aiohttp.
    Results are ordered by view count.
    """
    # Check if API key is provided
    if not GOOGLE_API_KEY:
        st.error("Google API Key is missing for YouTube search. Please set GOOGLE_API_KEY in your app.py file.")
        return []

    youtube_base_url = "https://www.googleapis.com/youtube/v3/search"
    
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": num_results,
        "key": GOOGLE_API_KEY,
        "order": "viewCount" # Order by view count as requested
    }

    videos = []
    try:
        async with session.get(youtube_base_url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as response:
            response_text = await response.text()
            
            response.raise_for_status()
            data = json.loads(response_text)

            if data.get('items'):
                for item in data['items']:
                    video_id = item['id'].get('videoId') if item.get('id') else None
                    title = item['snippet'].get('title') if item.get('snippet') else None
                    description = item['snippet'].get('description') if item.get('snippet') else None

                    if video_id and title and description:
                        videos.append({
                            "title": title,
                            "link": f"https://www.youtube.com/watch?v={video_id}",
                            "snippet": description
                        })
                    else:
                        pass # Keep pass to explicitly do nothing
            else:
                pass # Keep pass to explicitly do nothing
    except asyncio.TimeoutError:
        st.error(f"Error during YouTube Data API search: Request timed out after 20 seconds. Please check your internet connection or try again later.")
        videos = []
    except aiohttp.ClientConnectorError as e:
        st.error(f"Error during YouTube Data API search: Could not connect to the server. Please check your internet connection or firewall. Details: {e}")
        videos = []
    except aiohttp.ClientResponseError as e:
        if e.status == 403:
            st.error(f"YouTube Data API: Access Denied (HTTP 403). Please ensure your Google API Key is correct, enabled for YouTube Data API v3, and has no IP restrictions preventing access from your location.")
        else:
            st.error(f"Error during YouTube Data API search: HTTP Error {e.status} - {e.message}. Response: {response_text}. Please review the error details.")
        videos = []
    except json.JSONDecodeError as e:
        st.error(f"Error decoding JSON from YouTube Data API response. The API might have returned non-JSON. Raw text was: {response_text}. Error: {e}")
        videos = []
    except Exception as e:
        st.error(f"An unexpected error occurred during YouTube Data API search: {e}. Please report this issue.")
        videos = []
    return videos

# --- PDF Generation Function ---
def generate_pdf_report(data):
    """
    Generates a PDF version of the provided content with improved Markdown rendering.
    """
    query = data.get('query', 'Tech Help Desk Query')
    full_answer = data.get('full_answer', 'No answer provided.')
    summary = data.get('summary', 'No summary provided.')
    web_articles = data.get('web_articles', [])
    youtube_videos = data.get('youtube_videos', [])
    mcq_questions = data.get('mcq_questions', [])
    saq_questions = data.get('saq_questions', [])
    long_questions = data.get('long_questions', [])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    
    styles = _pdf_styles
    link_style = styles['Normal']
    link_style.textColor = blue
    code_style = styles['Code']

    story = []

    story.append(Paragraph(f"Help Desk Report for: {query}", styles['h1']))
    story.append(Spacer(1, 0.2 * 10))

    story.append(Paragraph("Summary:", styles['h2']))
    story.append(Paragraph(summary, styles['Normal']))
    story.append(Spacer(1, 0.2 * 10))

    story.append(Paragraph("Full Answer:", styles['h2']))
    
    code_block_pattern = re.compile(r"```(?P<lang>\w+)?\n(?P<code>.*?)\n```", re.DOTALL)
    
    last_end = 0
    for match in code_block_pattern.finditer(full_answer):
        pre_code_text = full_answer[last_end:match.start()].strip()
        if pre_code_text:
            pre_code_text = pre_code_text.replace('**', '<b>').replace('__', '<i>')
            story.append(Paragraph(pre_code_text, styles['Normal']))
            story.append(Spacer(1, 0.1 * 10))

        code_content = match.group('code').strip()
        if code_content:
            story.append(Preformatted(code_content, code_style))
            story.append(Spacer(1, 0.1 * 10))
        
        last_end = match.end()

    remaining_text = full_answer[last_end:].strip()
    if remaining_text:
        remaining_text = remaining_text.replace('**', '<b>').replace('__', '<i>')
        story.append(Paragraph(remaining_text, styles['Normal']))
        story.append(Spacer(1, 0.2 * 10))
    else:
        story.append(Spacer(1, 0.2 * 10))

    story.append(PageBreak())

    if web_articles:
        story.append(Paragraph("Related Web Articles:", styles['h2']))
        for article in web_articles:
            story.append(Paragraph(f"<link href='{article['link']}' target='_blank'>{article['title']}</link>", link_style))
            story.append(Paragraph(article['snippet'], styles['Normal']))
            story.append(Spacer(1, 0.1 * 10))
        story.append(Spacer(1, 0.2 * 10))

    if youtube_videos:
        story.append(Paragraph("Related YouTube Videos:", styles['h2']))
        for video in youtube_videos:
            story.append(Paragraph(f"<link href='{video['link']}' target='_blank'>{video['title']}</link>", link_style))
            story.append(Paragraph(video['snippet'], styles['Normal']))
            story.append(Spacer(1, 0.1 * 10))
        story.append(Spacer(1, 0.2 * 10))
    
    if mcq_questions:
        story.append(Paragraph("Multiple Choice Questions (MCQ):", styles['h2']))
        for i, mcq in enumerate(mcq_questions):
            story.append(Paragraph(f"{i+1}. {mcq['question']}", styles['Normal']))
            for j, option in enumerate(mcq['options']):
                story.append(Paragraph(f"    {chr(65+j)}. {option}", styles['Normal']))
            story.append(Paragraph(f"    Answer: {mcq['answer']}", styles['Normal']))
            story.append(Spacer(1, 0.1 * 10))
        story.append(Spacer(1, 0.2 * 10))

    if saq_questions:
        story.append(Paragraph("Short Answer Questions (SAQ):", styles['h2']))
        for i, saq in enumerate(saq_questions):
            story.append(Paragraph(f"{i+1}. {saq['question']}", styles['Normal']))
            story.append(Paragraph(f"    Answer: {saq['answer']}", styles['Normal']))
            story.append(Spacer(1, 0.1 * 10))
        story.append(Spacer(1, 0.2 * 10))

    if long_questions:
        story.append(Paragraph("Long Questions:", styles['h2']))
        for i, lq in enumerate(long_questions):
            story.append(Paragraph(f"{i+1}. {lq}", styles['Normal']))
            story.append(Spacer(1, 0.1 * 10))
        story.append(Spacer(1, 0.2 * 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# --- Streamlit UI ---

# Set page config as the very first Streamlit command
st.set_page_config(layout="wide", page_title="TechMentor : Tech Help Desk for Students")

# Custom CSS for a consistent dark blue background and adjusted font colors
st.markdown("""
    <style>
    /* Set solid dark blue background for the entire app */
    html, body, .stApp {
        background-color: #1A2B3D !important; /* Deep, rich blue */
        color: #E0E0E0 !important; /* Light gray text for contrast */
    }

    /* Ensure main content area is transparent to allow body background to show */
    .main .block-container {
        background-color: transparent !important;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* General text color for Streamlit app */
    .stMarkdown, .stText, .stHeader, .stSubheader, .stTitle, .stCaption, .stLabel, p {
        color: #E0E0E0 !important; /* Light gray text for general content */
    }

    /* Sidebar styling */
    .sidebar .sidebar-content {
        background: rgba(10, 25, 49, 0.9); /* Dark blue with 90% transparency for sidebar */
        color: #FFFFFF !important; /* White text for sidebar content */
        border-right: 1px solid rgba(0, 191, 255, 0.3); /* Light blue border */
    }
    /* Specific styling for text within the sidebar content using direct HTML */
    .sidebar .sidebar-content .st-emotion-cache-1c7y2kl,
    .sidebar .sidebar-content p,
    .sidebar .sidebar-content li {
        color: #FFFFFF !important;
        font-weight: 500;
        font-size: 0.95rem;
        line-height: 1.6;
    }
    .sidebar .stHeader, .sidebar .stSubheader {
        color: #FFFFFF !important;
        text-shadow: 0 0 5px rgba(255, 255, 255, 0.5);
    }
    
    /* Input fields and buttons styling */
    .stTextInput>div>div>input {
        background-color: rgba(255, 255, 255, 0.1); /* Slightly transparent white background */
        color: #E0E0E0; /* Light text for input */
        border: 1px solid rgba(255, 255, 255, 0.5); /* White border */
        border-radius: 0.5rem;
        padding: 0.75rem;
    }
    .stTextInput>div>div>input:focus {
        border-color: #FFFFFF; /* White on focus */
        box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.5);
    }

    .stButton>button {
        background-color: #00BFFF; /* Deep Sky Blue for buttons */
        color: white;
        font-weight: 600;
        border-radius: 0.5rem;
        padding: 0.75rem 1.5rem;
        transition: background-color 0.2s ease-in-out, transform 0.1s ease-in-out;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 8px rgba(0, 191, 255, 0.3);
    }
    .stButton>button:hover {
        background-color: #009ACD; /* Darker Deep Sky Blue on hover */
        transform: translateY(-1px);
        box-shadow: 0 6px 12px rgba(0, 191, 255, 0.4);
    }
    .stButton>button:active {
        transform: translateY(0);
    }

    /* Styling for expanders/sections */
    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.1); /* Light transparent white for headers */
        color: #E0E0E0; /* Light text */
        border-radius: 0.5rem;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
        font-weight: 600;
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    .streamlit-expanderContent {
        background-color: rgba(255, 255, 255, 0.05); /* Even lighter transparent white for content */
        border-radius: 0.5rem;
        padding: 1rem;
        border: 1px solid rgba(255, 255, 255, 0.3);
        border-top: none;
    }

    /* Code blocks within Streamlit markdown */
    code {
        background-color: rgba(255, 255, 255, 0.1); /* Light transparent white for inline code */
        border-radius: 0.25rem;
        padding: 0.1rem 0.3rem;
        font-family: 'Fira Code', 'Cascadia Code', monospace;
        font-size: 0.9rem;
        color: #00FFFF; /* Cyan for inline code text */
    }
    pre code {
        background-color: rgba(0, 0, 0, 0.3); /* Slightly transparent dark background for code blocks */
        color: #00FFFF; /* Cyan text for code blocks */
        display: block;
        padding: 1rem;
        border-radius: 0.5rem;
        overflow-x: auto;
        font-family: 'Fira Code', 'Cascadia Code', monospace;
        font-size: 0.9rem;
        border: 1px dashed rgba(255, 255, 255, 0.3);
    }

    /* Links in markdown */
    a {
        color: #ADD8E6 !important; /* Light Blue for links, important to override */
        text-decoration: none;
        text-shadow: 0 0 5px rgba(255, 255, 255, 0.5);
    }
    a:hover {
        text-decoration: underline;
    }

    /* Message boxes (errors/warnings) */
    .stAlert {
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        color: #E0E0E0;
    }
    .stAlert.error {
        background-color: rgba(255, 0, 0, 0.2);
        border: 1px solid rgba(255, 0, 0, 0.5);
    }
    .stAlert.warning {
        background-color: rgba(255, 165, 0, 0.2);
        border: 1px solid rgba(255, 165, 0, 0.5);
    }
    .stAlert.info {
        background-color: rgba(0, 191, 255, 0.1);
        border: 1px solid rgba(0, 191, 255, 0.3);
    }

    /* Center align the main title */
    h1 {
        text-align: center;
        color: #FFFFFF;
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.7);
    }

    /* Adjust the header color for the main title as well */
    .stApp > header {
        background-color: transparent !important;
    }
    </style>
    """, unsafe_allow_html=True)


# Initialize session state for storing results
if 'report_data' not in st.session_state:
    st.session_state.report_data = None

# Main content area - Title and primary input
st.title("📝 TechMentor 📝 : Tech Help Desk for Students")

# Wrap main input in a container for better layout control
with st.container():
    # Input for query
    query = st.text_input(
        "Enter your tech query (e.g., 'What is Flask?', 'Explain Machine Learning')",
        key="main_query_input"
    )

    # Checkbox for including code
    include_code = st.checkbox("Include Code Examples (Python, C, C++, Java)", key="main_include_code_checkbox")

    # Search button
    if st.button("Search", key="main_search_button"):
        if not query:
            st.error("Please enter a query to search.")
        else:
            with st.spinner("Searching and generating response... This may take a moment."):
                async def run_search():
                    async with aiohttp.ClientSession() as session:
                        # Construct the answer prompt based on the include_code flag
                        answer_prompt_base = f"Provide a comprehensive answer to the query: '{query}'. Ensure the explanation is clear and concise."
                        if include_code:
                            answer_prompt = f"""
                            {answer_prompt_base}
                            
                            For this query, please also include:
                            1.  A full, step-by-step description of the algorithm or solution.
                            2.  Code implementations in Python, C, C++, and Java (if applicable and reasonable for the problem).
                            3.  For each code snippet, clearly state its Time Complexity and Space Complexity.
                            4.  Format all code using Markdown code blocks (e.g., ```python\\nprint('Hello World')\\n```).
                            """
                        else:
                            answer_prompt = answer_prompt_base

                        # Define schema for structured questions (needed before Gemini call)
                        question_schema = {
                            "type": "OBJECT",
                            "properties": {
                                "mcq": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "question": {"type": "STRING"},
                                            "options": {"type": "ARRAY", "items": {"type": "STRING"}},
                                            "answer": {"type": "STRING"}
                                        },
                                        "required": ["question", "options", "answer"]
                                    }
                                },
                                "saq": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "question": {"type": "STRING"},
                                            "answer": {"type": "STRING"}
                                        },
                                        "required": ["question", "answer"]
                                    }
                                },
                                "long_questions": {
                                    "type": "ARRAY",
                                    "items": {"type": "STRING"}
                                }
                            },
                            "required": ["mcq", "saq", "long_questions"]
                        }

                        # Start Google search and initial Gemini answer generation concurrently
                        search_task = asyncio.create_task(perform_google_search(session, query, num_results=3)) # Limit to 3
                        answer_task = asyncio.create_task(call_gemini_api(session, answer_prompt))

                        await asyncio.gather(search_task, answer_task)

                        search_results = search_task.result()
                        full_answer = answer_task.result()

                        if not full_answer:
                            full_answer = "Could not generate a comprehensive answer at this time."
                        
                        summary_prompt = f"Summarize the following text about '{query}' concisely:\n\nText: {full_answer}"
                        questions_prompt = f"Based on the following answer about '{query}', generate 10 Multiple Choice Questions (MCQ) with 4 options and one correct answer, 10 Short Answer Questions (SAQ) with their answers, and 10 Long Questions. Provide the output in a JSON format matching the following schema:\n\n{json.dumps(question_schema, indent=2)}\n\nAnswer: {full_answer}"

                        summary_task = asyncio.create_task(call_gemini_api(session, summary_prompt))
                        questions_task = asyncio.create_task(call_gemini_api(session, questions_prompt, response_schema=question_schema))

                        await asyncio.gather(summary_task, questions_task)

                        summary = summary_task.result()
                        if not summary:
                            summary = "Could not generate a summary."

                        generated_questions = questions_task.result()

                        mcq_questions = []
                        saq_questions = []
                        long_questions = []

                        if generated_questions and isinstance(generated_questions, dict):
                            if "mcq" in generated_questions:
                                mcq_questions = generated_questions["mcq"]
                            if "saq" in generated_questions:
                                saq_questions = generated_questions["saq"]
                            if "long_questions" in generated_questions:
                                long_questions = generated_questions["long_questions"]
                        
                        st.session_state.report_data = {
                            "query": query,
                            "full_answer": full_answer,
                            "summary": summary,
                            "web_articles": search_results.get("web", []),
                            "youtube_videos": search_results.get("youtube", []),
                            "mcq_questions": mcq_questions,
                            "saq_questions": saq_questions,
                            "long_questions": long_questions,
                            "generated_questions_raw": generated_questions
                        }
                
                asyncio.run(run_search())

# Display results if available (in main content area)
if st.session_state.report_data:
    data = st.session_state.report_data
    st.subheader(f"Results for \"{data['query']}\"")

    st.markdown("---")
    st.header("Summary")
    st.write(data['summary'])

    st.markdown("---")
    st.header("Full Answer")
    st.markdown(data['full_answer'])

    st.markdown("---")
    st.header("Related Web Articles (Top 3)")
    if data['web_articles']:
        for article in data['web_articles'][:3]:
            st.markdown(f"**[{article['title']}]({article['link']})**")
            st.write(article['snippet'])
    else:
        st.write("No related web articles found.")

    st.markdown("---")
    st.header("Related YouTube Videos (Top 3 Most Viewed)")
    if data['youtube_videos']:
        for video in data['youtube_videos'][:3]:
            st.markdown(f"**[{video['title']}]({video['link']})**")
            st.write(video['snippet'])
        else:
            st.write("No related YouTube videos found.")

    st.markdown("---")
    st.header("Practice Questions")

    st.subheader("Multiple Choice Questions (MCQ)")
    if data['mcq_questions']:
        for i, mcq in enumerate(data['mcq_questions']):
            st.markdown(f"**Q{i+1}: {mcq['question']}**")
            for j, option in enumerate(mcq['options']):
                st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;{chr(65+j)}. {option}")
            st.markdown(f"**&nbsp;&nbsp;&nbsp;&nbsp;Answer: {mcq['answer']}**")
    else:
        st.info(f"No multiple choice questions generated.")

    st.subheader("Short Answer Questions (SAQ)")
    if data['saq_questions']:
        for i, saq in enumerate(data['saq_questions']):
            st.markdown(f"**Q{i+1}: {saq['question']}**")
            st.markdown(f"**&nbsp;&nbsp;&nbsp;&nbsp;Answer: {saq['answer']}**")
    else:
        st.info(f"No short answer questions generated.")

    st.subheader("Long Questions")
    if data['long_questions']:
        for i, lq in enumerate(data['long_questions']):
            st.markdown(f"**Q{i+1}: {lq}**")
    else:
        st.info(f"No long questions generated.")

    st.markdown("---")
    # PDF Download Button
    pdf_buffer = generate_pdf_report(data)
    st.download_button(
        label="Download Report as PDF",
        data=pdf_buffer,
        file_name=f"{data['query'].replace(' ', '_')}_report.pdf",
        mime="application/pdf"
    )

# --- Sidebar Content ---
with st.sidebar:
    st.header("👩‍🏫Tech Mentor")

    st.subheader("🗣App Information")
    st.write("""
    <ul style="color: #FFFFFF; font-weight: 500; font-size: 0.95rem; line-height: 1.6;">
        <li>Provides comprehensive answers to tech queries.</li>
        <li>Integrates with web articles and YouTube videos.</li>
        <li>Generates various practice questions (MCQ, SAQ, Long Questions).</li>
        <li>Offers PDF download of results for offline study.</li>
    </ul>
    """, unsafe_allow_html=True)

    st.subheader("⏳Features")
    st.write("""
    <ul style="color: #FFFFFF; font-weight: 500; font-size: 0.95rem; line-height: 1.6;">
        <li>Real-time search for tech queries.</li>
        <li>Comprehensive answers with summaries.</li>
        <li>Practice questions (MCQ, SAQ, Long Questions).</li>
    </ul>
    """, unsafe_allow_html=True)

    st.subheader("⚒ Tech Stack")
    st.write("""
    <ul style="color: #FFFFFF; font-weight: 500; font-size: 0.95rem; line-height: 1.6;">
        <li>Python (Streamlit, aiohttp, ReportLab)</li>
        <li>Google Gemini API (for content generation)</li>
        <li>Google Custom Search API (for web articles)</li>
        <li>YouTube Data API v3 (for videos)</li>
    </ul>
    """, unsafe_allow_html=True)

    st.subheader("🕵🏻‍♀️Developed by:")
    st.markdown("[Anushka Chakraborty](https://www.linkedin.com/in/anushkachakraborty)")

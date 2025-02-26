import os
import requests
from flask import Flask, request, jsonify, make_response
from llmproxy import generate
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)

news_key = os.environ.get("newsKey")
news_url = os.environ.get("newsUrl")

# In-memory session store keyed by session_id.
sessions = {}

def keyword_extraction_agent(message, session_id):
    """Extract the main keyword from the user query using the persistent session id."""
    keyword_prompt = (
        "Extract the main keyword from the following request. "
        "Return only the keyword: " + message
    )
    extraction_response = generate(
        model='4o-mini',
        system="You are a keyword extraction assistant.",
        query=keyword_prompt,
        temperature=0.0,
        lastk=0,
        session_id=session_id  # Use the same session id
    )
    keyword = extraction_response.get('response', '').strip()
    return keyword

def news_fetching_agent(keyword):
    """Fetch news articles related to the extracted keyword."""
    one_week_ago_date = datetime.today() - timedelta(days=7)
    from_date = one_week_ago_date.strftime("%Y-%m-%d")
    params = {
        "q": keyword,
        "from": from_date,
        "sortBy": "popularity",
        "pageSize": 5,
        "apiKey": news_key
    }
    articles = []
    try:
        news_response = requests.get(news_url, params=params)
        if news_response.status_code == 200:
            data_json = news_response.json()
            if data_json.get("status") == "ok":
                articles = data_json.get("articles", [])
            else:
                print("Error from news API:", data_json.get("message"))
        else:
            print(f"Error: Received status code {news_response.status_code} from news API.")
    except Exception as e:
        print("Exception while fetching news:", e)
    return articles

def summarization_agent(articles, context, session_id):
    """Summarize and analyze the news articles using the persistent session id."""
    if not articles:
        return f"Sorry, no news articles found for '{context}'."
    
    news_content = ""
    for article in articles:
        title = article.get("title", "No title")
        description = article.get("description", "No description provided")
        url = article.get("url", "No URL")
        news_content += f"Title: {title}\nDescription: {description}\nURL: {url}\n\n"
    
    system_instruction = (
        "You are a news summarizer and explainer. Provide a concise summary of the following news articles about the chosen topic, "
        "explain their implications, and highlight any contrasting viewpoints. Lastly, mention any important trends."
    )
    llm_query = f"Summarize and analyze the following news articles:\n\n{news_content}"
    
    summary_response = generate(
        model='4o-mini',
        system=system_instruction,
        query=llm_query,
        temperature=0.0,
        lastk=0,
        session_id=session_id  # Use the same session id
    )
    return summary_response.get('response', '')

@app.route('/', methods=['POST'])
def main():
    data = request.get_json()
    user = data.get("user_name", "Unknown")
    message = data.get("text", "").strip()
    
    # Ignore bot messages or empty input.
    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})
    
    # Get or create a consistent session ID
    session_id = data.get("session_id")
    client_session_id = request.cookies.get('news_session_id')
    
    # Prioritize session_id from request, then from cookie, then create new
    if session_id:
        # Use the provided session_id
        pass
    elif client_session_id and client_session_id in sessions:
        # Use existing session from cookie
        session_id = client_session_id
    else:
        # Create a new session ID if none exists
        session_id = f"{user}_{uuid.uuid4().hex[:8]}"
    
    # Debug log: show incoming session info and message.
    print(f"Received message from user: '{user}', session_id: '{session_id}', Message: '{message}'")
    
    # Retrieve or create the session for the session_id.
    if session_id not in sessions:
        print(f"Creating new session for session_id: '{session_id}'")
        sessions[session_id] = {"state": "start"}
    session = sessions[session_id]
    print("Current session state:", session)
    
    # Response text to be returned
    response_text = ""
    
    # --- State 1: Initial Request ---
    if session["state"] == "start":
        # Agent 1: Keyword Extraction.
        keyword = keyword_extraction_agent(message, session_id)
        session["keyword"] = keyword
        print(f"Extracted keyword: '{keyword}'")
        
        # Agent 2: Fetch news articles.
        articles = news_fetching_agent(keyword)
        session["articles"] = articles
        
        # If no articles are found, go to human intervention.
        if not articles:
            session["state"] = "human_intervention"
            response_text = f"Sorry, no news articles found for '{keyword}'. Please refine your query or provide additional context."
        else:
            # Agent 3: Summarize articles.
            summary = summarization_agent(articles, keyword, session_id)
            session["summary"] = summary
            
            # Transition to awaiting human confirmation.
            session["state"] = "awaiting_confirmation"
            response_text = (f"Summary for '{keyword}':\n{summary}\n\n"
                    "If this summary is acceptable, please reply with 'confirm'. "
                    "Otherwise, provide feedback to refine the summary.")
    
    # --- State 2: Awaiting Human Confirmation/Feedback ---
    elif session["state"] == "awaiting_confirmation":
        if message.lower() == "confirm":
            session["state"] = "complete"
            response_text = "Thank you! The summary has been confirmed."
        else:
            # Refine the summary using the user's feedback.
            refined_context = session["keyword"] + " " + message
            print(f"Refining summary with context: '{refined_context}'")
            summary = summarization_agent(session["articles"], refined_context, session_id)
            session["summary"] = summary
            response_text = f"Refined Summary:\n{summary}\n\nPlease reply with 'confirm' if this is acceptable."
    
    # --- State 3: Completed Session ---
    elif session["state"] == "complete":
        # Reset session for new queries.
        sessions[session_id] = {"state": "start"}
        response_text = "Session complete. Please send a new query to start again."
    
    # --- Fallback: Reset Session ---
    else:
        sessions[session_id] = {"state": "start"}
        response_text = "Resetting session. Please send a new query."
    
    # Create response with cookie
    response = make_response(jsonify({"text": response_text}))
    response.set_cookie('news_session_id', session_id, max_age=3600)  # Expires in 1 hour
    
    return response

@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run()
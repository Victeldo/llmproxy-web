import os
import requests
from flask import Flask, request, jsonify
from llmproxy import generate
from datetime import datetime, timedelta
import json

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
    
    # CRITICAL: First, log ALL incoming data for debugging
    print("=" * 50)
    print("INCOMING REQUEST DATA:")
    print(json.dumps(data, indent=2))
    print("=" * 50)
    
    # Get session_id - EXPLICITLY force front-end provided value to be primary
    front_end_session_id = data.get("session_id")
    
    # If we don't have a session_id, create a CONVERSATION-UNIQUE ID tied to user
    # This ensures we're tracking the same conversation even if front-end doesn't provide session_id
    conversation_id = data.get("conversation_id", data.get("channel_id", data.get("chat_id")))
    
    # Determine the session_id to use (priority: 1. front_end_session_id, 2. conversation+user)
    if front_end_session_id:
        session_id = front_end_session_id
        print(f"Using front-end provided session_id: {session_id}")
    elif conversation_id:
        session_id = f"{conversation_id}_{user}"
        print(f"Using conversation-based session_id: {session_id} (from conversation: {conversation_id})")
    else:
        session_id = f"user_{user}"
        print(f"Using user-based session_id: {session_id}")
    
    # Always include session_id in response for front-end to track
    response_data = {
        "session_id": session_id  # This ensures front-end has it for next request
    }
    
    # Debug log: show incoming session info and message.
    print(f"Processing request with session_id: '{session_id}', Message: '{message}'")
    
    # Retrieve or create the session for the session_id.
    if session_id not in sessions:
        print(f"Creating new session for session_id: '{session_id}'")
        sessions[session_id] = {"state": "start"}
    
    # Log state information before processing
    session = sessions[session_id]
    print(f"Current session state BEFORE processing: {session['state']}")
    print(f"All session data: {json.dumps(session, indent=2, default=str)}")
    
    # --- State 1: Initial Request ---
    if session["state"] == "start":
        print("PROCESSING: Initial request state")
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
            response_data["text"] = f"Sorry, no news articles found for '{keyword}'. Please refine your query or provide additional context."
        else:
            # Agent 3: Summarize articles.
            summary = summarization_agent(articles, keyword, session_id)
            session["summary"] = summary
            
            # Transition to awaiting human confirmation.
            session["state"] = "awaiting_confirmation"
            response_data["text"] = (f"Summary for '{keyword}':\n{summary}\n\n"
                    "If this summary is acceptable, please reply with 'confirm'. "
                    "Otherwise, provide feedback to refine the summary.")
    
    # --- State 2: Awaiting Human Confirmation/Feedback ---
    elif session["state"] == "awaiting_confirmation":
        print("PROCESSING: Awaiting confirmation state")
        if message.lower() == "confirm":
            session["state"] = "complete"
            response_data["text"] = "Thank you! The summary has been confirmed."
        else:
            # Refine the summary using the user's feedback.
            refined_context = session["keyword"] + " " + message
            print(f"Refining summary with context: '{refined_context}'")
            summary = summarization_agent(session["articles"], refined_context, session_id)
            session["summary"] = summary
            response_data["text"] = f"Refined Summary:\n{summary}\n\nPlease reply with 'confirm' if this is acceptable."
    
    # --- State 3: Completed Session ---
    elif session["state"] == "complete":
        print("PROCESSING: Complete state - resetting")
        # Reset session for new queries.
        sessions[session_id] = {"state": "start"}
        response_data["text"] = "Session complete. Please send a new query to start again."
    
    # --- Fallback: Reset Session ---
    else:
        print("PROCESSING: Unknown state - resetting")
        sessions[session_id] = {"state": "start"}
        response_data["text"] = "Resetting session. Please send a new query."
    
    # Log state information after processing
    print(f"Session state AFTER processing: {sessions[session_id]['state']}")
    print(f"All session data AFTER: {json.dumps(sessions[session_id], indent=2, default=str)}")
    
    # Log all active sessions for debugging
    print("Active sessions:")
    for sid, sdata in sessions.items():
        print(f"  - {sid}: {sdata['state']}")
    
    # Return response with session_id
    return jsonify(response_data)

@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run(debug=True)
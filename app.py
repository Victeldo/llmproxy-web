import os
import requests
from flask import Flask, request, jsonify
from llmproxy import generate
from datetime import datetime, timedelta

app = Flask(__name__)

news_key = os.environ.get("newsKey")
news_url = os.environ.get("newsUrl")

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
        lastk=10,  # Increased to maintain context
        session_id=session_id
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

def format_articles_for_prompt(articles, keyword):
    """Format articles into a text string for the meta-agent."""
    if not articles:
        return f"No news articles found for '{keyword}'."
    
    articles_text = f"Here are the latest news articles about '{keyword}':\n\n"
    for i, article in enumerate(articles[:5], 1):
        title = article.get("title", "No title")
        description = article.get("description", "No description provided")
        url = article.get("url", "No URL")
        articles_text += f"Article {i}:\nTitle: {title}\nDescription: {description}\nURL: {url}\n\n"
    
    return articles_text

@app.route('/', methods=['POST'])
def main():
    data = request.get_json()
    user = data.get("user_name", "Unknown")
    message = data.get("text", "").strip()
    
    # Ignore bot messages or empty input.
    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})
    
    # Create a consistent session ID for each user
    conversation_id = data.get("channel_id", data.get("conversation_id", data.get("chat_id", "default")))
    session_id = f"{conversation_id}_{user}"
    print(f"Processing request for session_id: '{session_id}'")
    
    # First, check if this might be a news-related query or follow-up
    meta_prompt = (
        "Analyze this user message and determine if it is: "
        "1. A new query asking for news on a topic, "
        "2. A follow-up asking to refine a previous summary, "
        "3. A confirmation of acceptance, or "
        "4. Something else. "
        "Return only the number 1, 2, 3, or 4: " + message
    )
    
    meta_response = generate(
        model='4o-mini',
        system="You are a message classifier. Classify messages based on their intent.",
        query=meta_prompt,
        temperature=0.0,
        lastk=0,  # Don't need context for classification
        session_id=f"{session_id}_meta"  # Separate session for meta-agent
    )
    
    intent = meta_response.get('response', '').strip()
    print(f"Classified intent: {intent}")
    
    # Handle based on intent
    if "1" in intent:  # New news query
        # Extract keyword
        keyword = keyword_extraction_agent(message, session_id)
        print(f"Extracted keyword: '{keyword}'")
        
        # Fetch news articles
        articles = news_fetching_agent(keyword)
        
        # Format articles for the main prompt
        articles_text = format_articles_for_prompt(articles, keyword)
        
        # Ask the main agent to summarize and analyze
        main_prompt = (
            f"The user asked about news on '{keyword}'. "
            f"{articles_text}\n\n"
            "Please provide a concise summary of these articles, explain their implications, "
            "highlight any contrasting viewpoints, and mention important trends. "
            "After your summary, ask if the user would like a more refined analysis "
            "or if they're satisfied with this summary."
        )
        
    elif "2" in intent:  # Refinement request
        # The refinement context will be available through lastk
        main_prompt = (
            "The user has asked to refine the previous summary. "
            "Please provide a refined analysis based on their specific feedback: " + message
        )
        
    elif "3" in intent:  # Confirmation
        main_prompt = (
            "The user has confirmed they are satisfied with the summary. "
            "Thank them and ask if they would like to explore another news topic."
        )
        
    else:  # Intent 4 or any other case
        main_prompt = (
            "If the user is new, tell them that you are a news assistant that can help them get summaries and analysis of recent news. "
            "Otherwise, tell the user you are unsure and would like them to repeat their query and remind them what you can help them with"
        )
    
    # Generate the main response
    main_response = generate(
        model='4o-mini',
        system=(
            "You are a news analyst and summarizer. You provide concise, informative summaries "
            "of news articles, explain their implications, highlight contrasting viewpoints, "
            "and identify important trends. Be conversational and engaging."
        ),
        query=main_prompt,
        temperature=0.7,
        lastk=10,  # Remember conversation history
        session_id=session_id  # Use the main session ID
    )
    
    response_text = main_response.get('response', '')
    
    return jsonify({"text": response_text})

@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run(debug=True)
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
        lastk=10,  
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
    
    conversation_id = data.get("channel_id", data.get("conversation_id", data.get("chat_id", "default")))
    session_id = f"{conversation_id}_{user}"
    print(f"Processing request for session_id: '{session_id}'")
    
    # Handle specific button clicks
    if message == "interaction_info":
        return jsonify({
            "text": "You can interact with the bot by typing your queries directly. You can ask for news summaries, request analysis, or refine previous responses. You can also use the buttons provided for quick actions."
        })
    
    elif message == "refine_analysis":
        main_prompt = (
            "The user has requested to refine and combine all previous analyses. "
            "Provide a comprehensive summary based on the full history of interactions."
        )
        
        main_response = generate(
            model='4o-mini',
            system=(
                "You are a news analyst and summarizer. Provide a detailed, refined analysis "
                "combining all previous information shared in this session. Be concise and insightful."
            ),
            query=main_prompt,
            temperature=0.7,
            lastk=10,  
            session_id=session_id
        )
        
        response_text = main_response.get('response', '')
        return jsonify({"text": response_text})
    
    else:
        # If the message is a query, handle it normally
        main_prompt = (
            "Analyze the user's query and provide relevant news or analysis. "
            f"User query: {message}"
        )
        
        main_response = generate(
            model='4o-mini',
            system=(
                "You are a news analyst and summarizer. You provide concise, informative summaries "
                "of news articles, explain their implications, highlight contrasting viewpoints, "
                "and identify important trends. Be conversational and engaging."
            ),
            query=main_prompt,
            temperature=0.7,
            lastk=10,  
            session_id=session_id
        )
        
        response_text = main_response.get('response', '')

        # Only show buttons if the response needs further interaction
        if "Would you like more details?" in response_text:
            return jsonify({
                "text": response_text,
                "attachments": [
                    {
                        "title": "Choose an option:",
                        "text": "Select an action below:",
                        "actions": [
                            {
                                "type": "button",
                                "text": "📘 How to interact with the bot",
                                "msg": "interaction_info",
                                "msg_in_chat_window": True,
                                "msg_processing_type": "sendMessage"
                            },
                            {
                                "type": "button",
                                "text": "🧠 Refine and combine all analysis",
                                "msg": "refine_analysis",
                                "msg_in_chat_window": True,
                                "msg_processing_type": "sendMessage"
                            }
                        ]
                    }
                ]
            })
        else:
            # Regular response without buttons
            return jsonify({"text": response_text})

@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run(debug=True)
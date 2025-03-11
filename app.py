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

def topic_extraction_agent(message, session_id):
    """Extract the main topic from the user query using the persistent session id."""
    topic_prompt = (
        "Extract the main topic from the following request. "
        "Return only the topic: " + message
    )
    extraction_response = generate(
        model='4o-mini',
        system="You are a topic extraction assistant.",
        query=topic_prompt,
        temperature=0.0,
        lastk=10,
        session_id=session_id
    )
    topic = extraction_response.get('response', '').strip()
    return topic

def news_fetching_agent(query_term):
    """Fetch news articles related to the given query term."""
    one_week_ago_date = datetime.today() - timedelta(days=7)
    from_date = one_week_ago_date.strftime("%Y-%m-%d")
    params = {
        "q": query_term,
        "from": from_date,
        "sortBy": "popularity",
        "pageSize": 20,
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

def filter_relevant_articles(articles, topic, session_id):
    """Use LLM to filter only relevant articles from API results."""
    filtered_articles = []
    
    for article in articles:
        title = article.get("title", "No title")
        description = article.get("description", "No description provided")
        full_text = f"Title: {title}\nDescription: {description}"
        
        relevance_prompt = (
            f"Given the topic: '{topic}', determine if this article is relevant.\n\n"
            f"Article: {full_text}\n\n"
            "Respond only with 0 for NO or 1 for YES. No other words or explanations."
        )
        
        relevance_response = generate(
            model='4o-mini',
            system="You determine if news articles are relevant based on the given topic. "
                   "Always respond with either 0 or 1.",
            query=relevance_prompt,
            temperature=0.0,
            lastk=0,
            session_id=session_id
        )
        
        relevance_result = relevance_response.get('response', '').strip()
        
        if "1" in relevance_result:
            filtered_articles.append(article)
    
    return filtered_articles

def format_articles_for_prompt(articles, query_term):
    """Format articles into a text string for the meta-agent."""
    if not articles:
        return f"No news articles found for '{query_term}'."
    
    articles_text = f"Here are the latest news articles about '{query_term}':\n\n"
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
        # Extract topic instead of just a keyword
        topic = topic_extraction_agent(message, session_id)
        print(f"Extracted topic: '{topic}'")
        
        # Fetch news articles
        articles = news_fetching_agent(topic)
        print(f"Fetched {len(articles)} articles before filtering.")
        
        # Filter articles using LLM
        relevant_articles = filter_relevant_articles(articles, topic, session_id)
        print(f"Retained {len(relevant_articles)} relevant articles after filtering.")
        
        # Handle the case when no relevant articles are found
        if not relevant_articles:
            response_text = (
                f"Sorry, I couldn't find any relevant news articles on '{topic}'. "
                "Would you like to try a different topic or refine your request?"
            )
            return jsonify({"text": response_text})
        
        # Format relevant articles for the main prompt
        articles_text = format_articles_for_prompt(relevant_articles, topic)
        
        # Construct main prompt for summarization
        main_prompt = (
            f"The user asked about news on '{topic}'.\n\n"
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

    # Add interactive buttons
    buttons = [
        {
            "type": "button",
            "text": "📘 How to interact with the bot",
            "msg": "interaction_info",
            "msg_in_chat_window": True,
            "msg_processing_type": "sendMessage"
        }
    ]
    
    # Add "Refine and combine all analysis" button for news-related queries
    if intent in ["1", "2"]:
        buttons.append({
            "type": "button",
            "text": "🧠 Refine and combine all analysis",
            "msg": "refine_analysis",
            "msg_in_chat_window": True,
            "msg_processing_type": "sendMessage"
        })
    
    return jsonify({
        "text": response_text,
        "attachments": [
            {
                "title": "What would you like to do next? 😊",
                "text": "👇 Select an action below:",
                "actions": buttons
            }
        ]
    })

@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run(debug=True)

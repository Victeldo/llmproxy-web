import requests
from flask import Flask, request, jsonify
from llmproxy import generate
from datetime import datetime, timedelta
import os


app = Flask(__name__)

news_key = os.environ.get("newsKey")
news_url = os.environ.get("newsUrl")
    

@app.route('/', methods=['POST'])
def main():
    data = request.get_json() 

    # Extract relevant information
    user = data.get("user_name", "Unknown")
    message = data.get("text", "")

    print(data)

    # Ignore bot messages
    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})

    print(f"Message from {user} : {message}")

    # Fetch news articles using a dynamic date (one week ago)

    one_week_ago_date = datetime.today() - timedelta(days=7)
    from_date = one_week_ago_date.strftime("%Y-%m-%d")
    params = {
        "q": message,
        "from": from_date,
        "sortBy": "popularity",
        "pageSize": 5,
        "apiKey": news_key
    }
    try:
        response = requests.get(news_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                articles = data.get("articles", [])
            else:
                print("Error from news API:", data.get("message"))
                articles = []
        else:
            print(f"Error: Received status code {response.status_code} from news API.")
            articles = []
    except Exception as e:
        print("An exception occurred while fetching news:", e)
        articles = []


    if not articles:
        response_text = f"Sorry, no news articles found for the topic '{message}'."
    else:
        news_content = ""
        for article in articles:
            title = article.get("title", "No title")
            description = article.get("description", "No description provided")
            url = article.get("url", "No URL")
            news_content += f"Title: {title}\nDescription: {description}\nURL: {url}\n\n"

        system_instruction = (
            "You are a news summarizer and explainer. "
            "Provide a concise summary of the following news articles about the chosen topic, explain their implications, "
            "and highlight any contrasting viewpoints. Lastly, mention any important trends amongst all the articles."
        )

        llm_query = f"Summarize and analyze the following news articles:\n\n{news_content}"

        response = generate(
            model='4o-mini',
            system=system_instruction,
            query=llm_query,
            temperature=0.0,
            lastk=0,
            session_id='GenericSession'
        )
        response_text = response['response']
    
    print(response_text)
    return jsonify({"text": response_text})
    
@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run()
# def hello_world():
#    return jsonify({"text":'Hello from Koyeb - you reached the main page!'})

@app.route('/query', methods=['POST'])
def main():
    data = request.get_json() 

    # Extract relevant information
    user = data.get("user_name", "Unknown")
    message = data.get("text", "")

    print(data)

    # Ignore bot messages
    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})

    print(f"Message from {user} : {message}")

    # Fetch news articles using a dynamic date (one week ago)

    one_week_ago_date = datetime.today() - timedelta(days=7)
    from_date = one_week_ago_date.strftime("%Y-%m-%d")
    params = {
        "q": message,
        "from": from_date,
        "sortBy": "popularity",
        "pageSize": 5,
        "apiKey": news_key
    }
    try:
        response = requests.get(news_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                articles = data.get("articles", [])
            else:
                print("Error from news API:", data.get("message"))
                articles = []
        else:
            print(f"Error: Received status code {response.status_code} from news API.")
            articles = []
    except Exception as e:
        print("An exception occurred while fetching news:", e)
        articles = []


    if not articles:
        response_text = f"Sorry, no news articles found for the topic '{message}'."
    else:
        news_content = ""
        for article in articles:
            title = article.get("title", "No title")
            description = article.get("description", "No description provided")
            url = article.get("url", "No URL")
            news_content += f"Title: {title}\nDescription: {description}\nURL: {url}\n\n"

        system_instruction = (
            "You are a news summarizer and explainer. "
            "Provide a concise summary of the following news articles about the chosen topic, explain their implications, "
            "and highlight any contrasting viewpoints. Lastly, mention any important trends amongst all the articles."
        )

        llm_query = f"Summarize and analyze the following news articles:\n\n{news_content}"

        response = generate(
            model='4o-mini',
            system=system_instruction,
            query=llm_query,
            temperature=0.0,
            lastk=0,
            session_id='GenericSession'
        )
        response_text = response['response']
    
    print(response_text)
    return jsonify({"text": response_text})
    
@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run()
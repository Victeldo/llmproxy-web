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
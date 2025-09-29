# ml_stub/app.py
from flask import Flask, request, jsonify
app = Flask("ml_stub")

# simple rule-based classifier for demo
def classify_text(text):
    t = text.lower()
    if "protest" in t or "митинг" in t:
        return {"category": "CIVIL_ACTIVITY", "confidence": 0.92}
    if "threat" in t or "attack" in t or "угроза" in t:
        return {"category": "SECURITY_ALERT", "confidence": 0.95}
    if "outage" in t or "power" in t or "отключение" in t:
        return {"category": "INFRASTRUCTURE", "confidence": 0.88}
    return {"category": "UNCLASSIFIED", "confidence": 0.2}

@app.route("/classify", methods=["POST"])
def classify():
    data = request.json or {}
    text = data.get("text", "")
    out = classify_text(text)
    return jsonify(out)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

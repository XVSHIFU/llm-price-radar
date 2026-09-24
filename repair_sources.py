"""One-time metadata repair for the imported baseline; does not change prices."""
from price_data import ROOT, publish, read_json

SOURCES = {"OpenAI": "openai-api", "Anthropic": "claude-api", "Google": "google-api",
           "DeepSeek": "deepseek-api", "xAI": "xai-api", "Moonshot": "kimi-api",
           "MiniMax": "minimax-api", "火山引擎": "volcengine-api", "阿里云": "aliyun-api"}


def main():
    data = read_json(ROOT / "data.json")
    count = 0
    for model in data["models"]:
        if not model.get("source"):
            source = SOURCES.get(model["provider"])
            if model["provider"] == "智谱":
                source = "zhipu-api" if model["currency"] == "CNY" else "glm-api"
            if not source:
                raise ValueError("Cannot resolve source: " + model["id"])
            model["source"] = source
            count += 1
    publish(data, read_json(ROOT / "plans.json"))
    print(f"Restored {count} missing source references; prices unchanged.")


if __name__ == "__main__":
    main()

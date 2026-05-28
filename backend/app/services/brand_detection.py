# backend/app/services/brand_detection.py


def detect_brand_mention(response_text: str, brand_name: str) -> bool:
    if not response_text or not brand_name:
        return False
    return brand_name.lower() in response_text.lower()

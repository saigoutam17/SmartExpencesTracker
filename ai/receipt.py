import pytesseract
from PIL import Image
import re


def extract_receipt(image_path):

    text = pytesseract.image_to_string(
        Image.open(image_path)
    )

    amount = 0

    matches = re.findall(
        r'(?:₹|Rs\.?|INR)?\s*(\d+(?:\.\d{1,2})?)',
        text,
        re.IGNORECASE
    )

    if matches:
        amount = float(matches[-1])


    return {
        "amount": amount,
        "text": text
    }
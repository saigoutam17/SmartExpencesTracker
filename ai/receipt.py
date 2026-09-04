import pytesseract
from PIL import Image
import re

# Location of Tesseract OCR on Windows
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extract_receipt(image_path):
    # Read text from receipt image
    text = pytesseract.image_to_string(
        Image.open(image_path)
    )

    # Find possible amounts
    amount = 0

    matches = re.findall(
        r'(?:₹|Rs\.?|INR)?\s*(\d+(?:\.\d{1,2})?)',
        text,
        re.IGNORECASE
    )

    # Use the last detected amount
    if matches:
        amount = float(matches[-1])

    return {
        "amount": amount,
        "text": text
    }
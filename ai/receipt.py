import pytesseract
from PIL import Image
import re

# Tesseract location
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extract_receipt(image_path):

    # 1. Read the receipt
    image = Image.open(image_path)

    # 2. Extract text using OCR
    text = pytesseract.image_to_string(image)

    # 3. Find amounts in the text
    matches = re.findall(
        r'(?:₹|Rs\.?|INR)?\s*(\d+(?:\.\d{1,2})?)',
        text,
        re.IGNORECASE
    )

    # 4. Convert detected amounts to numbers
    amounts = []

    for value in matches:
        try:
            amounts.append(float(value))
        except ValueError:
            pass

    # 5. Use the last detected amount as the total
    amount = amounts[-1] if amounts else 0

    return {
        "amount": amount,
        "text": text
    }
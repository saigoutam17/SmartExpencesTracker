from ai.receipt import extract_receipt

result = extract_receipt("receipt.jpg")

print("\n========== RECEIPT SCAN ==========\n")

print("Detected Amount: ₹", result["amount"])

print("\nExtracted Text:")
print(result["text"])

print("\n==================================")
def detect_anomaly(amount, average):

    if average <= 0:
        return False

    if amount >= average * 3:
        return True

    return False
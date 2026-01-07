def confidence_bucket(score: float) -> str:
    """
    Convert numeric confidence score into a human-readable bucket.
    """
    if score < 0.4:
        return "Low"
    elif score < 0.7:
        return "Moderate"
    else:
        return "High"

def score_risks(risks: list[str]) -> int:
    return min(100, len(risks) * 20)

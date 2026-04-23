def estimate_total_effort(task_breakdown: list[dict]) -> int:
    size_to_points = {"S": 1, "M": 3, "L": 5}
    total = 0
    for task in task_breakdown:
        total += size_to_points.get(task.get("priority", "M"), 3)
    return total

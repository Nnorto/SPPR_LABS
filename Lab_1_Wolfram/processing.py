"""Извлечение всех текстовых блоков, а не только первого Result."""


def is_true(value):
    return value is True or value == "true"


def extract(data):
    root = data.get("queryresult")
    if not isinstance(root, dict):
        return {"status": "invalid_response", "message": "Нет объекта queryresult.", "pods": []}
    error = root.get("error", False)
    if isinstance(error, dict) or is_true(error):
        message = error.get("msg", "Ошибка API.") if isinstance(error, dict) else "Ошибка API."
        return {"status": "api_error", "message": str(message), "pods": []}
    if not is_true(root.get("success")):
        return {
            "status": "no_result",
            "message": "API не выдал успешного результата; проверьте raw и формулировку.",
            "pods": [],
        }
    pods = []
    raw_pods = root.get("pods", [])
    if not isinstance(raw_pods, list):
        return {"status": "invalid_response", "message": "Поле pods не является списком.", "pods": []}
    for pod in raw_pods:
        if not isinstance(pod, dict):
            continue
        blocks = []
        subpods = pod.get("subpods", [])
        if isinstance(subpods, list):
            for subpod in subpods:
                if not isinstance(subpod, dict):
                    continue
                plain = subpod.get("plaintext")
                if isinstance(plain, str) and plain.strip():
                    blocks.append(plain.strip())
        if blocks:
            pods.append({
                "id": pod.get("id", ""),
                "title": pod.get("title", ""),
                "primary": is_true(pod.get("primary", False)),
                "text": blocks,
            })
    if not pods:
        return {"status": "no_text", "message": "Успешный ответ без plaintext.", "pods": []}
    return {"status": "ok", "message": "", "pods": pods}

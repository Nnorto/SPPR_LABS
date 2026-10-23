"""Синтетические фикстуры, НЕ ответы сервера и НЕ кэш Wolfram Alpha.

Часть фикстур содержит контрольные вычисления, часть моделирует отсутствие
результата. Никакие текущие факты, курсы или расстояния здесь не выдумываются.
"""

CONTROL_VALUES = {
    "physics": "250 J [контроль: 5 * 10^2 / 2]",
    "bmi": "23.148148... kg/m^2 [контроль: 75 / 1.8^2]",
    "equation": "x = 2 or x = 3 [контроль: (x-2)(x-3)=0]",
    "derivative": "3 x^2 + 2 [контрольное вычисление]",
    "determinant": "-2 [контроль: 1*4 - 2*3]",
    "prime": "2^3 * 3^2 * 5 [контроль: 8*9*5=360]",
    "units": "10000 m [контроль: 10*1000]",
}


def synthetic_response(query_id, query_text):
    root = {
        "success": query_id in CONTROL_VALUES,
        "error": False,
        "pods": [],
    }
    if root["success"]:
        root["pods"] = [
            {"id": "Input", "title": "Synthetic input", "subpods": [{"plaintext": query_text}]},
            {"id": "Result", "title": "SYNTHETIC control value", "primary": True,
             "subpods": [{"plaintext": CONTROL_VALUES[query_id]}]},
        ]
    return {
        "_notice": "HANDCRAFTED TEST FIXTURE. NOT A WOLFRAM ALPHA RESPONSE.",
        "queryresult": root,
    }

"""Настоящий Mamdani: min для AND, max для OR/аккумуляции, centroid."""
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
from api_client import valid_number
from settings import CITIES

TERM_RU = {
    "far_below": "значительно холоднее сезонного среднего",
    "below": "прохладнее сезонного среднего", "typical": "типично для сезона",
    "above": "теплее сезонного среднего",
    "far_above": "значительно теплее сезонного среднего",
    "dry": "низкая влажность", "moderate": "умеренная влажность",
    "wet": "высокая влажность", "light": "слабый ветер",
    "breezy": "умеренный ветер", "strong": "сильный ветер",
    "poor": "низкий комфорт", "fair": "средний комфорт", "good": "высокий комфорт",
}


class WeatherFuzzy:
    def __init__(self, city, season, mean, std):
        if city not in CITIES or not np.isfinite(mean) or not -40 < mean < 40:
            raise ValueError("Некорректный город или средняя температура.")
        if not np.isfinite(std) or std < 0:
            raise ValueError("Некорректное стандартное отклонение.")
        self.city, self.season = city, season
        self.mean, self.scale = float(mean), max(float(std), 1.0)
        if mean - 2 * self.scale <= -60 or mean + 2 * self.scale >= 60:
            raise ValueError("Сезонные термы выходят за универсум.")
        t = ctrl.Antecedent(np.linspace(-60, 60, 481), "temperature")
        h = ctrl.Antecedent(np.arange(101), "humidity")
        w = ctrl.Antecedent(np.linspace(0, 60, 241), "wind")
        c = ctrl.Consequent(np.linspace(0, 100, 1001), "comfort", defuzzify_method="centroid")
        m, s = self.mean, self.scale
        t["far_below"] = fuzz.trapmf(t.universe, [-60, -60, m-2*s, m-s])
        t["below"] = fuzz.trimf(t.universe, [m-2*s, m-s, m])
        t["typical"] = fuzz.trimf(t.universe, [m-s, m, m+s])
        t["above"] = fuzz.trimf(t.universe, [m, m+s, m+2*s])
        t["far_above"] = fuzz.trapmf(t.universe, [m+s, m+2*s, 60, 60])
        h["dry"] = fuzz.trapmf(h.universe, [0, 0, 25, 45])
        h["moderate"] = fuzz.trimf(h.universe, [25, 55, 85])
        h["wet"] = fuzz.trapmf(h.universe, [65, 85, 100, 100])
        w["light"] = fuzz.trapmf(w.universe, [0, 0, 2, 5])
        w["breezy"] = fuzz.trimf(w.universe, [2, 7, 12])
        w["strong"] = fuzz.trapmf(w.universe, [8, 15, 60, 60])
        c["poor"] = fuzz.trapmf(c.universe, [0, 0, 20, 40])
        c["fair"] = fuzz.trimf(c.universe, [25, 50, 75])
        c["good"] = fuzz.trapmf(c.universe, [60, 80, 100, 100])
        definitions = [
            ("R1", t["far_below"], "poor", "Сильное похолодание относительно сезона → низкий комфорт."),
            ("R2", t["far_above"], "poor", "Сильное потепление относительно сезона → низкий комфорт."),
            ("R3", t["below"], "fair", "Прохладнее обычного → средний комфорт."),
            ("R4", t["above"], "fair", "Теплее обычного → средний комфорт."),
            ("R5", t["typical"] & h["moderate"] & w["light"], "good",
             "Типичная температура, умеренная влажность и слабый ветер → высокий комфорт."),
            ("R6", t["typical"] & (h["dry"] | h["wet"] | w["breezy"]), "fair",
             "Типичная температура, но крайняя влажность или умеренный ветер → средний комфорт."),
            ("R7", w["strong"], "poor", "Сильный ветер → низкий комфорт."),
        ]
        if city == "spb":
            extra = (h["wet"] & (w["breezy"] | w["strong"]),
                     "Петербург: высокая влажность и ветер → низкий комфорт.")
        elif city == "moscow":
            extra = (t["above"] & h["wet"],
                     "Москва: теплее сезонного среднего и влажно → низкий комфорт.")
        else:
            extra = (t["below"] & (w["breezy"] | w["strong"]),
                     "Казань: прохладнее сезонного среднего и ветер → низкий комфорт.")
        definitions.append(("R8", extra[0], "poor", extra[1]))
        self.rule_specs = [{"id": i, "output": o, "text": text} for i, _, o, text in definitions]
        self.rules = [ctrl.Rule(antecedent, c[output], label=i)
                      for i, antecedent, output, _ in definitions]
        self.system = ctrl.ControlSystem(self.rules)
        self.variables = {"temperature": t, "humidity": h, "wind": w, "comfort": c}

    def evaluate(self, temperature, humidity, wind):
        values = {
            "temperature": valid_number(temperature, -60, 60, "temperature"),
            "humidity": valid_number(humidity, 0, 100, "humidity"),
            "wind": valid_number(wind, 0, 60, "wind"),
        }
        simulation = ctrl.ControlSystemSimulation(self.system, clip_to_bounds=False)
        for key, value in values.items():
            simulation.input[key] = value
        simulation.compute()
        if "comfort" not in simulation.output:
            raise RuntimeError("Ни одно правило не активировано.")
        score = float(simulation.output["comfort"])
        memberships = {}
        for variable, value in values.items():
            var = self.variables[variable]
            memberships[variable] = {
                term: float(fuzz.interp_membership(var.universe, obj.mf, value))
                for term, obj in var.terms.items()
            }
        trace = [{**spec, "activation": float(rule.aggregate_firing[simulation] or 0)}
                 for spec, rule in zip(self.rule_specs, self.rules)]
        return {
            "comfort": score,
            "comfort_label": "низкий" if score < 40 else "средний" if score < 70 else "высокий",
            "memberships": memberships, "rules": trace,
            "temperature_scale": self.scale, "temperature_mean": self.mean,
        }


def recommendations(city, values, analysis, anomalies):
    """Защитные рекомендации отдельно от условного индекса комфорта."""
    t, h, w = (values[k] for k in ("temperature", "humidity", "wind"))
    notes = []
    if w > 15:
        notes.append("Учебный флаг сильного ветра: отложите длительную прогулку, проверьте предупреждения служб.")
    if t < -25:
        notes.append("Сильный мороз: сократите пребывание на улице, используйте тёплые слои одежды.")
    if t > 35:
        notes.append("Сильная жара: избегайте длительной нагрузки на солнце, проверьте официальные рекомендации.")
    if city == "spb" and h > 85 and t < 5:
        notes.append("Сыро и холодно: предусмотрите ветрозащитный и непромокаемый верхний слой.")
    if city == "moscow" and t > 25:
        notes.append("Для прогулки выбирайте затенённый маршрут; это учебное правило для Москвы.")
    if city == "kazan" and t < -10:
        notes.append("Для Казани при морозе добавлен совет защитить лицо и руки от ветра.")
    if h < 30:
        notes.append("Низкая относительная влажность: учитывайте сухость воздуха.")
    if h > 85:
        notes.append("Высокая влажность не доказывает наличие дождя: проверьте отдельный прогноз осадков.")
    for variable, item in anomalies.items():
        if item["flag"]:
            notes.append(f"{variable}: отклонение {item['z']:+.2f}σ от среднего за сезон 2021–2025.")
    if not notes and analysis["comfort"] >= 70:
        notes.append("По учебной модели условия относительно комфортны; проверьте прогноз перед выходом.")
    if not notes:
        notes.append("Учебная модель советует одежду по температуре и короткую прогулку по самочувствию.")
    notes.append("Это учебная экспертная система, не прогноз опасных явлений и не медицинская рекомендация.")
    return notes

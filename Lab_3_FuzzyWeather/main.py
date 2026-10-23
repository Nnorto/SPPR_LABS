"""Конвейер анализа. По умолчанию читает сохранённые ответы OpenWeatherMap."""
import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import pandas as pd
from api_client import fetch_current, fetch_history, parse_current, read_json, save_json
from analysis import load_history, seasonal_stats, anomaly
from fuzzy_model import WeatherFuzzy, TERM_RU, recommendations
from charts import plot_history, plot_memberships, plot_results
from settings import ROOT, CITIES, TIMEZONE, VARIABLES, season_of, SEASON_NAMES


def analyze_observation(observation, norms, mode):
    city = observation["city"]
    observed = datetime.fromisoformat(observation["observed_at_utc"])
    season = season_of(observed.astimezone(ZoneInfo(TIMEZONE)).month)
    selected = norms[(norms.city == city) & (norms.season == season)]
    if len(selected) != 1:
        raise ValueError("Нет однозначной сезонной нормы.")
    normal = selected.iloc[0]
    model = WeatherFuzzy(city, season, normal.temperature_mean, normal.temperature_std)
    fuzzy = model.evaluate(*(observation[k] for k in VARIABLES))
    deviations = {key: anomaly(observation[key], normal[key+"_mean"], normal[key+"_std"])
                  for key in VARIABLES}
    result = {
        **observation, "mode": mode, "season": season,
        "baseline": {k: float(normal[k]) for k in normal.index if k not in ("city", "season")},
        "fuzzy": fuzzy, "anomalies": deviations,
        "recommendations": recommendations(city, observation, fuzzy, deviations),
        "age_hours_at_processing": (datetime.now(timezone.utc)-observed).total_seconds()/3600,
    }
    return result, model


def run(data_folder, output, historical_demo=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(filename=output/"run.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", force=True)
    history, quality = load_history(data_folder)
    norms = seasonal_stats(history)
    norms.to_csv(output/"seasonal_norms.csv", index=False, encoding="utf-8-sig")
    save_json(output/"data_quality.json", quality)
    mode = "historical-demo" if historical_demo else "cached"
    print("Режим:", mode, flush=True)
    print("Период сезонной базы: 2021–2025, не 30-летняя климатическая норма.", flush=True)
    providers = {read_json(Path(data_folder)/"history"/f"{c}.meta.json")["provider"] for c in CITIES}
    provider = " / ".join(sorted(providers))
    figures = output / "figures"
    plot_history(history, norms, figures, provider)
    results, concise = [], []
    for city, info in CITIES.items():
        if historical_demo:
            last = history[history.city == city].iloc[-1]
            obs = {
                "city": city, **{k: float(last[k]) for k in VARIABLES},
                "observed_at_utc": last.time.tz_localize(TIMEZONE).tz_convert("UTC").isoformat(),
                "description": "Реальная последняя запись истории; НЕ текущая погода.",
            }
        else:
            obs = parse_current(city, read_json(Path(data_folder)/"current"/f"{city}.json"))
        result, model = analyze_observation(obs, norms, mode)
        results.append(result)
        plot_memberships(model, figures)
        row = {"city": info["name"], "season": SEASON_NAMES[result["season"]],
               "observed_at_utc": obs["observed_at_utc"],
               **{k: obs[k] for k in VARIABLES}, "comfort": result["fuzzy"]["comfort"]}
        for variable in VARIABLES:
            row.update({f"{variable}_{key}": result["anomalies"][variable][key]
                        for key in ("delta", "z", "label")})
        concise.append(row)
        print(f"{info['name']}: {obs['temperature']:.2f} °C; "
              f"{obs['humidity']:.0f}%; {obs['wind']:.2f} м/с; "
              f"комфорт {result['fuzzy']['comfort']:.1f}/100", flush=True)
        print("  Время данных UTC:", obs["observed_at_utc"], flush=True)
        if mode == "cached" and result["age_hours_at_processing"] > 6:
            print("  Кэш старше 6 часов. Для новой погоды используйте --refresh-current.", flush=True)
        print("  Температура:", result["anomalies"]["temperature"]["label"], flush=True)
        logging.info("%s %s mode=%s comfort=%.3f", city, obs["observed_at_utc"],
                     mode, result["fuzzy"]["comfort"])
    save_json(output/"analysis.json", results)
    pd.DataFrame(concise).to_csv(output/"comparison.csv", index=False, encoding="utf-8-sig")
    plot_results(results, figures, mode)
    write_result_report(output, results, provider)
    save_json(output/"manifest.json", {
        "mode": mode, "history_provider": provider, "baseline": "2021-01-01..2025-12-31",
        "run_at_utc": datetime.now(timezone.utc).isoformat(), "records": len(history),
        "method": "Mamdani min/max, centroid; conditional educational comfort 0..100",
    })
    print("Всего почасовых записей:", len(history), flush=True)
    print("Результаты:", output, flush=True)
    return results


def write_result_report(output, results, provider):
    lines = ["# Результаты анализа погоды", "",
             f"Источник истории: {provider}. Период: 2021–2025.", "",
             "Полные исходные ответы и метаданные находятся в папке data.",
             "Значения показывают конкретный момент данных, а не погоду в момент чтения отчёта.", ""]
    for row in results:
        lines += [f"## {CITIES[row['city']]['name']}", "",
                  f"Режим: `{row['mode']}`. Время UTC: `{row['observed_at_utc']}`.", "",
                  f"Температура {row['temperature']:.2f} °C; влажность {row['humidity']:.0f}%; "
                  f"ветер {row['wind']:.2f} м/с.", "",
                  f"Условный комфорт: {row['fuzzy']['comfort']:.2f}/100 "
                  f"({row['fuzzy']['comfort_label']}).", "",
                  "### Фаззификация", ""]
        for variable, terms in row["fuzzy"]["memberships"].items():
            text = "; ".join(f"{TERM_RU[t]}: {v:.3f}" for t, v in terms.items() if v > 0)
            lines += [f"- **{variable}:** {text}."]
        lines += ["", "### Активные правила", ""]
        for rule in row["fuzzy"]["rules"]:
            if rule["activation"] > 0:
                lines += [f"- **{rule['id']}:** {rule['text']} α={rule['activation']:.3f}."]
        lines += ["", "### Отклонения", ""]
        for variable, item in row["anomalies"].items():
            z = "не определён" if item["z"] is None else f"{item['z']:+.3f}"
            lines += [f"- **{variable}:** Δ={item['delta']:+.3f}, z={z}; {item['label']}."]
        lines += ["", "### Рекомендации", "", *["- "+s for s in row["recommendations"]], ""]
    (Path(output)/"RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--historical-demo", action="store_true")
    parser.add_argument("--refresh-current", action="store_true")
    parser.add_argument("--download-history", choices=["nasa", "openmeteo"])
    args = parser.parse_args()
    try:
        if args.historical_demo and args.refresh_current:
            raise ValueError("Исторический пример нельзя обозначать как текущий.")
        if args.download_history == "nasa":
            from nasa_history import fetch_nasa_history
            fetch_nasa_history(args.data)
        elif args.download_history == "openmeteo":
            fetch_history(args.data)
        if args.refresh_current:
            config = read_json(ROOT/"config.json")
            key = config.get("openweather_api_key", "")
            if not isinstance(key, str) or not key or key.startswith("PUT_"):
                raise ValueError("Заполните OpenWeatherMap API key через setup_config.py.")
            fetch_current(args.data, key)
        if not args.historical_demo:
            absent = [c for c in CITIES if not (args.data/"current"/f"{c}.json").exists()]
            if absent:
                raise ValueError("Нет сохранённых ответов OpenWeatherMap. Запустите с --refresh-current "
                                 "или явно выберите --historical-demo.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        run(args.data, args.output or ROOT/"output"/stamp, args.historical_demo)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print("Ошибка:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

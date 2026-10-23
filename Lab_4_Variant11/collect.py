"""Interactive collection: navigate FIPS in Chrome, save each open card."""
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

RANGES = {"invention": (1700000,1799999), "utility_model": (222000,222999)}

def text(node):
    return node.get_text(" ", strip=True) if node else None

def parse(html, url, kind, number):
    lo, hi = RANGES[kind]
    if not lo <= number <= hi:
        raise ValueError("Номер вне варианта 11")
    soup = BeautifulSoup(html, "lxml")
    title = text(soup.find(id="B542"))
    if not title:
        raise ValueError("Не найден B542: это не поддерживаемая карточка. HTML сохранён; нужна проверка структуры.")
    body = soup.get_text(" ", strip=True)
    if not re.search(r"(?<!\d)"+str(number)+r"(?!\d)", body):
        raise ValueError("Заявленный номер не найден в тексте карточки")
    def block(name):
        return text(soup.find(id=name))
    return {
        "patent_id": f"{kind}:{number}", "patent_type": kind,
        "patent_number": number, "patent_number_full": None,
        "title": title, "status_info": {"status":None,"last_change":None},
        "application_details": {k:None for k in ["application_number","application_date","registration_date","publication_date","publication_bulletin_number"]},
        "date": None, "ipc": [], "cpc": [], "inventors": [], "authors": [],
        "owners": [], "correspondence_address": None,
        "abstract":block("Abs"), "claims":None, "description_sections":[],
        "search_report":None, "url":url,
        "bibliography_raw":block("bib"),
        "collected_at_utc":datetime.now(timezone.utc).isoformat(),
        "html_sha256":hashlib.sha256(html.encode()).hexdigest(),
        "review_required":True,
        "missing_fields_note":"Поля null и пустые массивы не извлечены: проверьте исходную карточку, это не доказательство отсутствия сведений."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('data'))
    args=p.parse_args()
    raw=args.data/'raw'; raw.mkdir(parents=True,exist_ok=True)
    records=args.data/'records'; records.mkdir(exist_ok=True)
    driver=webdriver.Chrome()
    driver.set_page_load_timeout(90)
    try:
        driver.get('https://www1.fips.ru/registers-web/')
        print('В Chrome откройте реестр и карточку своего диапазона. Не обходите ограничения сайта.')
        print('Для сохранения: invention 1700000 либо utility_model 222000; q — выход.')
        while True:
            cmd=input('Откройте карточку, затем введите тип и номер: ').strip()
            if cmd.lower()=='q':break
            try:
                parts = cmd.split()
                if len(parts) != 2:
                    raise ValueError(
                        "Введите только тип и номер, например: invention 1790000. "
                        f"Получено: {cmd!r}"
                    )
                kind, num = parts
                number = int(num)
                if kind not in RANGES:raise ValueError('Тип: invention / utility_model')
                driver.switch_to.window(driver.window_handles[-1])
                WebDriverWait(driver,30).until(lambda d:d.execute_script('return document.readyState')=='complete')
                from urllib.parse import urlparse
                host=urlparse(driver.current_url).hostname or ''
                if not (host=='fips.ru' or host.endswith('.fips.ru')):
                    raise ValueError('Ожидался официальный домен ФИПС')
                html=driver.page_source
                name=f'{kind}_{number}'
                (raw/(name+'.html')).write_text(html,encoding='utf-8')
                record=parse(html,driver.current_url,kind,number)
                (records/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                print('Сохранено:',record['title'],'— требуется проверка остальных полей')
            except (ValueError,KeyError) as e:
                print('Не сохранено:',e)
    finally:
        driver.quit()

if __name__=='__main__':main()

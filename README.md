<h1 align="center">Yandex Forms Filler</h1>

<p align="center">
  <b>Просмотр и заполнение Яндекс Форм на Windows</b><br>
  <sub>PySide6 · Selenium · Microsoft Edge / Google Chrome</sub>
</p>

<p align="center">
  <a href="https://github.com/KONTROLIK/Yandex-Forms-Filler/releases/latest">
    <img src="https://img.shields.io/github/v/release/KONTROLIK/Yandex-Forms-Filler?style=for-the-badge&amp;label=release&amp;color=2ea44f" alt="Release">
  </a>
  <a href="https://github.com/KONTROLIK/Yandex-Forms-Filler/releases">
    <img src="https://img.shields.io/github/downloads/KONTROLIK/Yandex-Forms-Filler/total?style=for-the-badge&amp;label=downloads&amp;color=2563eb" alt="Downloads">
  </a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4?style=for-the-badge&amp;logo=windows&amp;logoColor=white" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=for-the-badge&amp;logo=python&amp;logoColor=white" alt="Python 3.11+">
</p>

---

## Установка

Скачайте установщик из [последнего релиза](https://github.com/KONTROLIK/Yandex-Forms-Filler/releases/latest) и запустите его. Права администратора не нужны.

| Компонент | Требование |
|---|---|
| ОС | Windows 10/11 x64 |
| Браузер | Microsoft Edge или Google Chrome |
| Сеть | Интернет при первом запуске для загрузки драйвера |
| Python | Не требуется — runtime включён в установщик |

> Установщик не подписан, поэтому SmartScreen может показать предупреждение.

## Возможности

- Сканирование публичной Яндекс Формы по ссылке и автоматическое определение вопросов.
- Редактирование ответов с учётом типов вопросов и ограничений формы.
- Проверка заполнения перед отправкой.
- Сохранение и загрузка профилей ответов; автосохранение по URL формы.
- Пакетный режим: несколько последовательных прогонов с задержкой.
- Автоотправка, видимый или скрытый браузер, логи и снимки экрана при ошибках.
- Сохранение `akey` успешных отправок в файл ключей.

## Быстрый старт

1. Вставьте ссылку на форму и нажмите **«Сканировать»**.
2. Заполните ответы в карточках или используйте **«Все первые»** для чернового заполнения.
3. Нажмите **«Проверить»**, затем **«Заполнить»**.
4. Для отправки включите **«Отправить автоматически»**; без этого браузер останется открытым для ручной отправки.
5. Для нескольких прогонов включите автоотправку и задайте количество в поле **«Прогонов»**.

## Поддерживаемые вопросы

Короткий и длинный текст, числа, email, телефон, ИНН, URL, оплата, файлы, дата и диапазон дат, радио-кнопки, чекбоксы, выпадающие списки, подсказки, матрицы, «Да/Нет», серии вопросов и статические блоки.

Капча и внешние платёжные виджеты требуют ручного участия.

## Данные приложения

```text
%LOCALAPPDATA%\YandexFormsFiller\
├── keys.txt
├── logs\
│   ├── *.log
│   ├── *.png
│   └── *.html
└── profiles\
    └── autosave_<hash>.json
```

- `keys.txt` — `akey` успешных отправок; путь можно изменить в настройках.
- `logs\` — журналы и снимки экрана при ошибках.
- `profiles\` — автосохранённые ответы, привязанные к URL формы.

Файлы приложения хранятся локально; ответы уходят на Яндекс только при отправке формы. `keys.txt`, `logs`, `profiles`, тестовые фикстуры и артефакты сборки исключены из Git.

## Запуск из исходников

Требуется Python 3.11+.

```bat
git clone https://github.com/KONTROLIK/Yandex-Forms-Filler.git
cd Yandex-Forms-Filler
py -3 -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
run.bat
```

Проверка тестов:

```bat
python -m unittest discover -s tests -q
```

## Сборка установщика

```bat
python -m pip install pyinstaller
pyinstaller --noconfirm YandexFormsFiller.spec
iscc installer\YandexFormsFiller.iss
```

Готовый установщик появится в `installer\Output\YandexFormsFiller-Setup-<версия>.exe`. Для сборки нужен [Inno Setup 6](https://jrsoftware.org/isinfo.php); если `iscc` не добавлен в PATH, запустите `ISCC.exe` из папки установки напрямую.

## Ограничения

- Работа зависит от разметки Яндекс Форм; при её изменении могут потребоваться правки селекторов.
- Капча и платёжные формы не обходятся.
- При первом запуске на новом ПК нужен интернет для Selenium Manager.
- Автоотправка необратима: проверяйте ответы перед включением.

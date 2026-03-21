# Магазин обуви

[![Maintainability]([![Maintainability](https://qlty.sh/gh/amariott/projects/mrpo_shop/maintainability.png)](https://qlty.sh/gh/amariott/projects/mrpo_shop))](https://qlty.sh/gh/amariott/projects/mrpo_shop)

Веб-приложение для магазина обуви, выполненное на Flask + SQLite.

## Возможности

- авторизация по ролям: гость, клиент, менеджер, администратор;
- просмотр товаров из базы данных;
- поиск, фильтрация и сортировка товаров;
- добавление, редактирование и удаление товаров;
- просмотр, добавление, редактирование и удаление заказов;
- импорт данных из Excel;
- подключён линтер flake8.

## Стек

- Python
- Flask
- SQLite
- openpyxl
- HTML
- CSS

## Запуск проекта

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 init_db.py
python3 import_data.py
python3 app.py
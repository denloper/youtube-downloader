#!/usr/bin/env python3
"""CRM клиники «Семейный доктор» — локальный сервер с демо-данными."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "clinic.db"
STATIC = ROOT / "static"

app = Flask(
    __name__,
    static_folder=str(STATIC),
    static_url_path="/static",
)
app.secret_key = os.environ.get("CLINIC_SECRET", "family-doctor-crm-dev-key")
app.config["JSON_AS_ASCII"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def db() -> sqlite3.Connection:
    if "db" not in g:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def one(cur):
    item = cur.fetchone()
    return dict(item) if item else None


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return date.today().isoformat()


def ok(data=None, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


def err(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return err("Нужна авторизация", 401)
        return fn(*args, **kwargs)

    return wrapper


def current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    cur = db().execute(
        "SELECT id, email, role, full_name, specialty, phone, color, active FROM users WHERE id=?",
        (uid,),
    )
    return one(cur)


def require_roles(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return err("Нужна авторизация", 401)
            if user["role"] not in roles and user["role"] != "admin":
                return err("Недостаточно прав", 403)
            return fn(*args, **kwargs)

        return wrapper

    return deco


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  full_name TEXT NOT NULL,
  specialty TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  color TEXT DEFAULT '#3D8B4E',
  active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS rooms (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT DEFAULT 'кабинет'
);
CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  duration_min INTEGER DEFAULT 30,
  price INTEGER NOT NULL,
  code TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS patients (
  id INTEGER PRIMARY KEY,
  card_no TEXT UNIQUE NOT NULL,
  last_name TEXT NOT NULL,
  first_name TEXT NOT NULL,
  patronymic TEXT DEFAULT '',
  birth_date TEXT,
  sex TEXT,
  phone TEXT,
  email TEXT,
  address TEXT,
  insurance TEXT,
  snils TEXT,
  blood_type TEXT,
  allergies TEXT DEFAULT '',
  chronic TEXT DEFAULT '',
  surgeries TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  doctor_id INTEGER,
  status TEXT DEFAULT 'active',
  created_at TEXT,
  FOREIGN KEY(doctor_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS appointments (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER NOT NULL,
  doctor_id INTEGER NOT NULL,
  service_id INTEGER,
  room_id INTEGER,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  status TEXT DEFAULT 'scheduled',
  source TEXT DEFAULT 'регистратура',
  complaint TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  created_at TEXT,
  FOREIGN KEY(patient_id) REFERENCES patients(id),
  FOREIGN KEY(doctor_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY,
  appointment_id INTEGER,
  patient_id INTEGER NOT NULL,
  doctor_id INTEGER NOT NULL,
  complaint TEXT,
  anamnesis TEXT,
  examination TEXT,
  diagnosis TEXT,
  icd10 TEXT,
  recommendations TEXT,
  created_at TEXT,
  FOREIGN KEY(patient_id) REFERENCES patients(id),
  FOREIGN KEY(doctor_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS prescriptions (
  id INTEGER PRIMARY KEY,
  visit_id INTEGER,
  patient_id INTEGER NOT NULL,
  doctor_id INTEGER NOT NULL,
  medication TEXT NOT NULL,
  dosage TEXT,
  duration_days INTEGER,
  times_per_day INTEGER DEFAULT 1,
  instructions TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS lab_orders (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER NOT NULL,
  doctor_id INTEGER,
  test_name TEXT NOT NULL,
  category TEXT DEFAULT 'лаборатория',
  status TEXT DEFAULT 'ordered',
  ordered_at TEXT,
  result_at TEXT,
  result_json TEXT DEFAULT '[]',
  comment TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER NOT NULL,
  appointment_id INTEGER,
  number TEXT NOT NULL,
  amount INTEGER NOT NULL,
  paid INTEGER DEFAULT 0,
  status TEXT DEFAULT 'open',
  method TEXT DEFAULT '',
  created_at TEXT,
  paid_at TEXT
);
CREATE TABLE IF NOT EXISTS invoice_items (
  id INTEGER PRIMARY KEY,
  invoice_id INTEGER NOT NULL,
  service_id INTEGER,
  title TEXT NOT NULL,
  qty INTEGER DEFAULT 1,
  price INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER NOT NULL,
  sender TEXT NOT NULL,
  sender_name TEXT,
  text TEXT NOT NULL,
  created_at TEXT,
  read_flag INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inventory (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  sku TEXT,
  unit TEXT DEFAULT 'шт',
  qty INTEGER DEFAULT 0,
  min_qty INTEGER DEFAULT 5,
  price INTEGER DEFAULT 0,
  category TEXT DEFAULT 'расходники'
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  assignee_id INTEGER,
  patient_id INTEGER,
  due_at TEXT,
  status TEXT DEFAULT 'open',
  priority TEXT DEFAULT 'normal',
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY,
  patient_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  due_at TEXT,
  done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS clinic_settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


def seed_if_needed():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    n = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if n and not os.environ.get("CLINIC_RESEED"):
        conn.close()
        return
    if n:
        for table in [
            "invoice_items",
            "invoices",
            "messages",
            "reminders",
            "tasks",
            "inventory",
            "lab_orders",
            "prescriptions",
            "visits",
            "appointments",
            "patients",
            "services",
            "rooms",
            "clinic_settings",
            "users",
        ]:
            conn.execute(f"DELETE FROM {table}")

    pw = lambda raw: generate_password_hash(raw)
    users = [
        (1, "admin@clinic.local", pw("admin123"), "admin", "Соколова Елена Викторовна", "Главный врач · терапия", "+7 495 120-01-01", "#2D6E3E"),
        (2, "doctor@clinic.local", pw("doctor123"), "doctor", "Морозов Андрей Павлович", "Кардиология", "+7 495 120-01-02", "#2563eb"),
        (3, "anna@clinic.local", pw("doctor123"), "doctor", "Ким Анна Сергеевна", "Педиатрия", "+7 495 120-01-03", "#7c3aed"),
        (4, "volkov@clinic.local", pw("doctor123"), "doctor", "Волков Дмитрий Игоревич", "Неврология", "+7 495 120-01-04", "#0f766e"),
        (5, "orlova@clinic.local", pw("doctor123"), "doctor", "Орлова Мария Александровна", "Гинекология", "+7 495 120-01-05", "#db2777"),
        (6, "reception@clinic.local", pw("reception123"), "reception", "Петрова Ольга Николаевна", "Регистратура", "+7 495 120-00-00", "#ca8a04"),
        (7, "nurse@clinic.local", pw("nurse123"), "nurse", "Белова Ирина Юрьевна", "Процедурная медсестра", "+7 495 120-01-10", "#0891b2"),
        (8, "acc@clinic.local", pw("acc123"), "accountant", "Савельева Татьяна Львовна", "Бухгалтерия / касса", "+7 495 120-01-20", "#b45309"),
    ]
    conn.executemany(
        "INSERT INTO users(id,email,password_hash,role,full_name,specialty,phone,color) VALUES(?,?,?,?,?,?,?,?)",
        users,
    )

    rooms = [
        (1, "Каб. 1 · Терапия", "приём"),
        (2, "Каб. 2 · Кардиология", "приём"),
        (3, "Каб. 3 · Педиатрия", "приём"),
        (4, "Каб. 4 · Неврология", "приём"),
        (5, "Каб. 5 · Гинекология", "приём"),
        (6, "Процедурная", "манипуляции"),
        (7, "Кабинет УЗИ", "диагностика"),
        (8, "Забор анализов", "лаборатория"),
    ]
    conn.executemany("INSERT INTO rooms(id,name,kind) VALUES(?,?,?)", rooms)

    services = [
        (1, "Первичный приём терапевта", "приём", 30, 2800, "THER-1"),
        (2, "Повторный приём терапевта", "приём", 20, 1900, "THER-2"),
        (3, "Приём кардиолога", "приём", 40, 3500, "CARD-1"),
        (4, "Приём педиатра", "приём", 30, 2600, "PED-1"),
        (5, "Приём невролога", "приём", 40, 3400, "NEU-1"),
        (6, "Приём гинеколога", "приём", 30, 3200, "GYN-1"),
        (7, "ЭКГ", "диагностика", 15, 1200, "ECG-1"),
        (8, "УЗИ органов брюшной полости", "диагностика", 25, 2800, "US-ABD"),
        (9, "УЗИ сердца", "диагностика", 30, 3900, "US-HEART"),
        (10, "Общий анализ крови", "лаборатория", 10, 650, "LAB-CBC"),
        (11, "Биохимия крови", "лаборатория", 10, 1850, "LAB-BIO"),
        (12, "Липидный профиль", "лаборатория", 10, 1400, "LAB-LIP"),
        (13, "Внутримышечная инъекция", "процедура", 10, 450, "INJ-IM"),
        (14, "Капельница", "процедура", 40, 1800, "INF-1"),
        (15, "Справка / выписка", "документы", 15, 700, "DOC-1"),
    ]
    conn.executemany(
        "INSERT INTO services(id,name,category,duration_min,price,code) VALUES(?,?,?,?,?,?)",
        services,
    )

    patients = [
        (1, "MC-1001", "Иванова", "Мария", "Петровна", "1984-03-12", "female", "+7 916 441-22-10", "ivanova@mail.test", "Москва, ул. Лесная, 12", "СОГАЗ", "123-456-789 00", "A(II)+", "пенициллин", "гипертоническая болезнь 2 ст., хронический гастрит", "аппендэктомия 2012", "Контроль АД, следующая явка через месяц", 1, "active"),
        (2, "MC-1002", "Смирнов", "Игорь", "Алексеевич", "1976-11-02", "male", "+7 903 112-80-44", "smirnov@mail.test", "Москва, пр. Мира, 88", "Ингосстрах", "111-222-333 44", "O(I)+", "нет", "ИБС, стенокардия напряжения", "стентирование 2021", "Нужен липидный профиль", 2, "active"),
        (3, "MC-1003", "Кузнецова", "Алина", "Дмитриевна", "2018-06-21", "female", "+7 925 300-19-77", "kuz.parent@mail.test", "Химки, ул. Маяковского, 5", "ОМС", "555-666-777 88", "B(III)+", "белок куриного яйца", "атопический дерматит", "", "Ребёнок, сопровождает мама", 3, "active"),
        (4, "MC-1004", "Новиков", "Павел", "Сергеевич", "1991-01-30", "male", "+7 909 555-01-23", "novikov@mail.test", "Мытищи, ул. Колпакова, 3", "РЕСО", "999-000-111 22", "AB(IV)-", "йод", "мигрень без ауры", "", "Частые головные боли", 4, "active"),
        (5, "MC-1005", "Фёдорова", "Екатерина", "Ильинична", "1995-09-08", "female", "+7 985 222-67-90", "fedorova@mail.test", "Москва, ул. Арбат, 19", "АльфаСтрахование", "321-654-987 00", "A(II)-", "нет", "планирование беременности", "", "Прегравидарная подготовка", 5, "active"),
        (6, "MC-1006", "Белов", "Никита", "Олегович", "2002-04-17", "male", "+7 926 777-14-08", "belov@mail.test", "Королёв, ул. Циолковского, 2", "ОМС", "147-258-369 00", "O(I)-", "нет", "сколиоз 2 ст.", "", "Нужна ЛФК", 4, "active"),
        (7, "MC-1007", "Орлов", "Геннадий", "Васильевич", "1958-12-05", "male", "+7 915 404-33-21", "orlov@mail.test", "Москва, ул. Вавилова, 41", "СОГАЗ", "741-852-963 00", "B(III)+", "аспирин", "СД 2 типа, АГ", "холецистэктомия 2019", "Высокий риск, контроль глюкозы", 1, "watch"),
        (8, "MC-1008", "Лебедева", "София", "Романовна", "2015-02-14", "female", "+7 903 888-62-11", "leb.parent@mail.test", "Москва, ул. Академика Королёва, 9", "ОМС", "159-357-486 00", "A(II)+", "нет", "часто болеющий ребёнок", "", "Календарь прививок", 3, "active"),
        (9, "MC-1009", "Громова", "Ольга", "Николаевна", "1970-07-19", "female", "+7 916 130-44-55", "gromova@mail.test", "Реутов, ул. Ленина, 7", "ВСК", "753-951-456 00", "O(I)+", "сульфаниламиды", "остеохондроз шейного отдела", "", "Головокружения", 4, "active"),
        (10, "MC-1010", "Павлов", "Артём", "Игоревич", "1988-05-03", "male", "+7 925 616-09-40", "pavlov@mail.test", "Москва, Кутузовский пр., 30", "Ингосстрах", "852-963-741 00", "A(II)+", "нет", "повышен холестерин", "", "Динамика липидов", 2, "active"),
        (11, "MC-1011", "Ершова", "Дарья", "Валерьевна", "1999-10-26", "female", "+7 909 212-77-18", "ershova@mail.test", "Москва, ул. Тверская, 4", "ОМС", "369-258-147 00", "B(III)+", "латекс", "железодефицитная анемия", "", "Контроль ферритина", 1, "active"),
        (12, "MC-1012", "Тихонов", "Михаил", "Юрьевич", "1964-08-11", "male", "+7 903 444-28-60", "tikhonov@mail.test", "Люберцы, ул. Кирова, 15", "СОГАЗ", "258-147-369 00", "AB(IV)+", "нет", "ГЭРБ, АГ", "грыжесечение 2016", "Жалобы на изжогу", 1, "active"),
    ]
    created = "2026-03-01 10:00:00"
    conn.executemany(
        """INSERT INTO patients(id,card_no,last_name,first_name,patronymic,birth_date,sex,phone,email,address,insurance,snils,blood_type,allergies,chronic,surgeries,notes,doctor_id,status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [p + (created,) for p in patients],
    )

    today = date.today()
    monday = today - timedelta(days=today.weekday())

    def ts(day_offset, hh, mm, dur=30):
        start = datetime.combine(monday + timedelta(days=day_offset), datetime.min.time()).replace(hour=hh, minute=mm)
        end = start + timedelta(minutes=dur)
        return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")

    appts = []
    aid = 1
    plan = [
        (0, 9, 0, 1, 1, 1, 1, "completed", "Головная боль, слабость"),
        (0, 9, 40, 2, 2, 3, 2, "completed", "Давление, одышка при нагрузке"),
        (0, 10, 30, 3, 3, 4, 3, "completed", "Кашель 5 дней"),
        (0, 11, 20, 7, 1, 1, 1, "completed", "Контроль сахара"),
        (0, 13, 0, 11, 1, 2, 1, "in_progress", "Слабость, контроль ферритина"),
        (0, 13, 40, 4, 4, 5, 4, "waiting", "Мигрень, ожидает в холле"),
        (0, 14, 20, 10, 2, 3, 2, "waiting", "Контроль холестерина"),
        (0, 15, 0, 9, 4, 5, 4, "confirmed", "Головокружение"),
        (0, 16, 0, 12, 1, 1, 1, "confirmed", "Изжога, повтор"),
        (0, 16, 40, 6, 4, 5, 4, "scheduled", "Боль в спине"),
        (0, 17, 20, 5, 5, 6, 5, "scheduled", "Планирование беременности"),
        (1, 9, 0, 4, 4, 5, 4, "confirmed", "Мигрень, светобоязнь"),
        (1, 10, 0, 5, 5, 6, 5, "confirmed", "Планирование беременности"),
        (1, 11, 0, 10, 2, 3, 2, "scheduled", "Контроль холестерина"),
        (1, 12, 0, 9, 4, 5, 4, "scheduled", "Головокружение"),
        (1, 14, 0, 11, 1, 2, 1, "scheduled", "Слабость, бледность"),
        (1, 15, 0, 6, 4, 5, 4, "scheduled", "Боль в спине"),
        (2, 9, 0, 1, 1, 2, 1, "scheduled", "Повторный осмотр АД"),
        (2, 9, 30, 8, 3, 4, 3, "scheduled", "Частые ОРВИ"),
        (2, 10, 30, 12, 1, 1, 1, "scheduled", "Изжога"),
        (2, 11, 30, 2, 2, 9, 7, "scheduled", "УЗИ сердца"),
        (2, 13, 0, 5, 5, 6, 5, "scheduled", "Результаты анализов"),
        (2, 14, 0, 4, 4, 5, 4, "scheduled", "Контроль лечения"),
        (3, 9, 0, 7, 1, 1, 1, "scheduled", "Подбор терапии"),
        (3, 10, 0, 3, 3, 4, 3, "scheduled", "Вакцинация"),
        (3, 11, 0, 10, 2, 7, 2, "scheduled", "ЭКГ"),
        (3, 12, 0, 9, 4, 5, 4, "scheduled", "Шейный отдел"),
        (4, 9, 0, 1, 1, 1, 1, "scheduled", "Диспансеризация"),
        (4, 10, 0, 11, 1, 11, 8, "scheduled", "Биохимия"),
        (4, 11, 0, 6, 4, 5, 4, "scheduled", "ЛФК-план"),
        (4, 12, 0, 5, 5, 6, 5, "scheduled", "УЗИ ОМТ"),
        (4, 15, 0, 12, 1, 8, 7, "scheduled", "УЗИ ОБП"),
    ]
    weekday_today = today.weekday()
    for day, hh, mm, pid, did, sid, rid, status, complaint in plan:
        if day == weekday_today and hh < datetime.now().hour and status == "scheduled":
            status = "waiting" if hh == datetime.now().hour - 1 else "confirmed"
        start, end = ts(day, hh, mm, 30 if sid not in (3, 5, 9) else 40)
        appts.append((aid, pid, did, sid, rid, start, end, status, "сайт / регистратура", complaint, "", now_iso()))
        aid += 1
    conn.executemany(
        """INSERT INTO appointments(id,patient_id,doctor_id,service_id,room_id,start_at,end_at,status,source,complaint,notes,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        appts,
    )

    # история визитов за 2 недели — чтобы графики дашборда были живыми
    hist_id = aid
    hist = []
    for days_ago in range(1, 14):
        d = today - timedelta(days=days_ago)
        if d.weekday() >= 5:
            continue
        count = 3 + (days_ago % 4)
        for i in range(count):
            pid = (days_ago + i) % 12 + 1
            did = (i % 5) + 1
            sid = (i % 6) + 1
            start = datetime.combine(d, datetime.min.time()).replace(hour=9 + i, minute=0)
            end = start + timedelta(minutes=30)
            hist.append((
                hist_id, pid, did, sid, did, start.strftime("%Y-%m-%d %H:%M:%S"),
                end.strftime("%Y-%m-%d %H:%M:%S"), "completed", "повтор", "плановый осмотр", "",
                start.strftime("%Y-%m-%d %H:%M:%S"),
            ))
            hist_id += 1
    conn.executemany(
        """INSERT INTO appointments(id,patient_id,doctor_id,service_id,room_id,start_at,end_at,status,source,complaint,notes,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        hist,
    )
    # оплаченная история для графика выручки
    extra_inv = []
    ninv = 7
    for i, row in enumerate(hist[:18]):
        amt = 1900 + (i % 5) * 400
        day = row[5][:10]
        extra_inv.append((
            ninv, row[1], row[0], f"СЧ-{day.replace('-','')[2:]}-{i+1:02d}",
            amt, amt, "paid", "карта", row[5], row[5],
        ))
        ninv += 1
    conn.executemany(
        """INSERT INTO invoices(id,patient_id,appointment_id,number,amount,paid,status,method,created_at,paid_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        extra_inv,
    )

    visits = [
        (1, 1, 1, 1, "Головная боль, слабость 4 дня", "АД обычно 140/90, принимает эналаприл нерегулярно", "АД 148/92, ЧСС 78, язык обложен", "Гипертоническая болезнь II ст. Цефалгия напряжения", "I11.9", "Суточный мониторинг АД, эналаприл 10 мг утром, контроль через 14 дней", "2026-08-17 09:25:00"),
        (2, 2, 2, 2, "Одышка при подъёме на 2 этаж", "Стентирование ПНА 2021, аторвастатин 20 мг", "Тоны ритмичны, АД 132/84, отёков нет", "ИБС. Стенокардия напряжения II ФК", "I20.8", "Липидный профиль, УЗИ сердца, увеличить статины после результатов", "2026-08-17 10:15:00"),
        (3, 3, 3, 3, "Сухой кашель 5 дней, температура 37.2", "Атопический дерматит, аллергия на яйцо", "Зев гиперемирован, аускультация без хрипов", "ОРВИ, ринофарингит", "J00", "Обильное питьё, солевой назальный душ, контроль если лихорадка >38.5", "2026-08-17 10:55:00"),
        (4, 4, 7, 1, "Жажда, слабость, глюкоза натощак 8.1", "СД 2 типа, метформин 1000, АГ", "ИМТ 31, АД 150/90", "Сахарный диабет 2 типа, целевой HbA1c не достигнут", "E11.8", "HbA1c, микроальбумин, усилить метформин, консультация эндокринолога", "2026-08-17 11:45:00"),
    ]
    conn.executemany(
        """INSERT INTO visits(id,appointment_id,patient_id,doctor_id,complaint,anamnesis,examination,diagnosis,icd10,recommendations,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        visits,
    )

    rxs = [
        (1, 1, 1, 1, "Эналаприл", "10 мг утром", 30, 1, "Контроль АД дома, дневник"),
        (2, 2, 2, 2, "Аторвастатин", "40 мг вечером", 90, 1, "После еды, контроль АЛТ через 6 недель"),
        (3, 2, 2, 2, "Бисопролол", "2.5 мг утром", 30, 1, "Не отменять резко"),
        (4, 4, 7, 1, "Метформин", "1000 мг 2 раза в день", 30, 2, "Во время еды"),
        (5, 3, 3, 3, "Аквамарис", "по 2 впрыска 3 раза", 7, 3, "Промывание носа"),
    ]
    conn.executemany(
        """INSERT INTO prescriptions(id,visit_id,patient_id,doctor_id,medication,dosage,duration_days,times_per_day,instructions,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        [r + (now_iso(),) for r in rxs],
    )

    labs = [
        (1, 1, 1, "Общий анализ крови", "лаборатория", "ready", "2026-08-10 08:40:00", "2026-08-10 14:00:00",
         json.dumps([
             {"name": "Гемоглобин", "val": 128, "unit": "г/л", "ref": "120–150", "status": "ok"},
             {"name": "Лейкоциты", "val": 6.1, "unit": "10⁹/л", "ref": "4–9", "status": "ok"},
             {"name": "СОЭ", "val": 18, "unit": "мм/ч", "ref": "2–15", "status": "hi"},
         ], ensure_ascii=False), ""),
        (2, 2, 2, "Липидный профиль", "лаборатория", "ready", "2026-08-12 09:00:00", "2026-08-12 16:20:00",
         json.dumps([
             {"name": "Холестерин", "val": 6.8, "unit": "ммоль/л", "ref": "<5.0", "status": "hi"},
             {"name": "ЛПНП", "val": 4.4, "unit": "ммоль/л", "ref": "<3.0", "status": "hi"},
             {"name": "ЛПВП", "val": 1.1, "unit": "ммоль/л", "ref": ">1.0", "status": "ok"},
             {"name": "Триглицериды", "val": 2.1, "unit": "ммоль/л", "ref": "<1.7", "status": "hi"},
         ], ensure_ascii=False), "Рекомендовано усилить статины"),
        (3, 7, 1, "Глюкоза / HbA1c", "лаборатория", "ready", "2026-08-15 08:10:00", "2026-08-15 13:40:00",
         json.dumps([
             {"name": "Глюкоза", "val": 8.4, "unit": "ммоль/л", "ref": "3.3–6.1", "status": "hi"},
             {"name": "HbA1c", "val": 7.9, "unit": "%", "ref": "<7.0", "status": "hi"},
         ], ensure_ascii=False), ""),
        (4, 11, 1, "Ферритин + ОАК", "лаборатория", "ordered", now_iso(), None,
         "[]", "Натощак"),
        (5, 10, 2, "Липидный профиль, контроль", "лаборатория", "processing", now_iso(), None, "[]", ""),
        (6, 5, 5, "ТТГ, ферритин, фолиевая", "лаборатория", "ordered", now_iso(), None, "[]", "Прегравидарная панель"),
    ]
    conn.executemany(
        """INSERT INTO lab_orders(id,patient_id,doctor_id,test_name,category,status,ordered_at,result_at,result_json,comment)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        labs,
    )

    invoices = [
        (1, 1, 1, "СЧ-260817-01", 2800, 2800, "paid", "карта", "2026-08-17 09:05:00", "2026-08-17 09:06:00"),
        (2, 2, 2, "СЧ-260817-02", 4700, 4700, "paid", "карта", "2026-08-17 09:45:00", "2026-08-17 09:46:00"),
        (3, 3, 3, "СЧ-260817-03", 2600, 2600, "paid", "наличные", "2026-08-17 10:28:00", "2026-08-17 10:29:00"),
        (4, 7, 4, "СЧ-260817-04", 2800, 0, "open", "", "2026-08-17 11:18:00", None),
        (5, 4, 5, "СЧ-260818-01", 3400, 0, "open", "", now_iso(), None),
        (6, 10, 7, "СЧ-260818-02", 1400, 0, "open", "", now_iso(), None),
    ]
    conn.executemany(
        """INSERT INTO invoices(id,patient_id,appointment_id,number,amount,paid,status,method,created_at,paid_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        invoices,
    )
    items = [
        (1, 1, 1, "Первичный приём терапевта", 1, 2800),
        (2, 2, 3, "Приём кардиолога", 1, 3500),
        (3, 2, 7, "ЭКГ", 1, 1200),
        (4, 3, 4, "Приём педиатра", 1, 2600),
        (5, 4, 1, "Первичный приём терапевта", 1, 2800),
        (6, 5, 5, "Приём невролога", 1, 3400),
        (7, 6, 12, "Липидный профиль", 1, 1400),
    ]
    conn.executemany(
        "INSERT INTO invoice_items(id,invoice_id,service_id,title,qty,price) VALUES(?,?,?,?,?,?)",
        items,
    )

    messages = [
        (1, 1, "patient", "Иванова М.П.", "Елена Викторовна, давление утром 150/94. Продолжать ту же дозу?", "2026-08-17 07:40:00", 0),
        (2, 1, "doctor", "Соколова Е.В.", "Доброе утро. Да, 10 мг оставляем, пришлите дневник за 3 дня.", "2026-08-17 08:05:00", 1),
        (3, 2, "patient", "Смирнов И.А.", "После нагрузки колет слева. Это срочно?", "2026-08-16 21:10:00", 0),
        (4, 7, "doctor", "Соколова Е.В.", "Не забудьте анализ HbA1c — направление уже в карте.", "2026-08-16 12:00:00", 1),
        (5, 3, "patient", "Кузнецова (мама)", "Температура спала, кашель остался. Можно в сад?", "2026-08-17 11:20:00", 0),
        (6, 5, "patient", "Фёдорова Е.И.", "Можно ли перенести приём на час позже?", "2026-08-17 09:00:00", 0),
    ]
    conn.executemany(
        "INSERT INTO messages(id,patient_id,sender,sender_name,text,created_at,read_flag) VALUES(?,?,?,?,?,?,?)",
        messages,
    )

    inventory = [
        (1, "Шприц 5 мл", "SYR-5", "шт", 180, 40, 18, "расходники"),
        (2, "Перчатки нитрил M", "GLV-M", "пара", 42, 50, 22, "расходники"),
        (3, "Бинт стерильный", "BND-1", "шт", 90, 20, 35, "расходники"),
        (4, "Эналаприл 10 мг", "ENA-10", "уп", 24, 8, 280, "аптека"),
        (5, "Аторвастатин 20 мг", "ATO-20", "уп", 16, 6, 540, "аптека"),
        (6, "Метформин 1000 мг", "MET-1000", "уп", 11, 6, 390, "аптека"),
        (7, "Спирт 70%", "ALC-70", "фл", 8, 10, 120, "расходники"),
        (8, "Электроды ЭКГ", "ECG-EL", "упак", 14, 5, 650, "диагностика"),
        (9, "Катетер периферический", "CAT-22", "шт", 35, 15, 85, "расходники"),
        (10, "Гель для УЗИ", "US-GEL", "фл", 6, 4, 410, "диагностика"),
    ]
    conn.executemany(
        "INSERT INTO inventory(id,name,sku,unit,qty,min_qty,price,category) VALUES(?,?,?,?,?,?,?,?)",
        inventory,
    )

    tasks = [
        (1, "Позвонить Ивановой: дневник АД", 1, 1, (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"), "open", "high"),
        (2, "Забрать результаты липидов Павлова", 2, 10, (datetime.now() + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"), "open", "normal"),
        (3, "Подготовить справку для Кузнецовой в сад", 6, 3, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 12:00:00"), "open", "normal"),
        (4, "Заказать перчатки — остаток ниже минимума", 7, None, today_str() + " 16:00:00", "open", "high"),
        (5, "Сверка кассы за вчера", 8, None, today_str() + " 18:00:00", "done", "normal"),
        (6, "Напомнить Орлову про эндокринолога", 1, 7, (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d 10:00:00"), "open", "normal"),
    ]
    conn.executemany(
        "INSERT INTO tasks(id,title,assignee_id,patient_id,due_at,status,priority,created_at) VALUES(?,?,?,?,?,?,?,?)",
        [t + (now_iso(),) for t in tasks],
    )

    reminders = [
        (1, 1, "Приём эналаприла", today_str() + " 09:00:00", 1),
        (2, 7, "Измерить глюкозу натощак", today_str() + " 08:00:00", 0),
        (3, 2, "Контрольный визит кардиолога", (today + timedelta(days=14)).isoformat() + " 10:00:00", 0),
        (4, 5, "Сдать ТТГ", (today + timedelta(days=2)).isoformat() + " 08:30:00", 0),
    ]
    conn.executemany(
        "INSERT INTO reminders(id,patient_id,title,due_at,done) VALUES(?,?,?,?,?)",
        reminders,
    )

    settings = [
        ("clinic_name", "Семейный доктор"),
        ("clinic_legal", "ООО «Семейный доктор ИИ»"),
        ("address", "Москва, ул. Садовая, 15"),
        ("phone", "+7 495 120-00-00"),
        ("inn", "7701234567"),
        ("work_from", "08:00"),
        ("work_to", "20:00"),
        ("slot_min", "20"),
        ("currency", "₽"),
    ]
    conn.executemany("INSERT INTO clinic_settings(key,value) VALUES(?,?)", settings)
    conn.commit()
    conn.close()


PATIENT_SELECT = """
SELECT p.*, u.full_name AS doctor_name,
  (p.last_name || ' ' || p.first_name || ' ' || COALESCE(p.patronymic,'')) AS full_name
FROM patients p
LEFT JOIN users u ON u.id = p.doctor_id
"""


def patient_age(birth: str | None) -> int | None:
    if not birth:
        return None
    try:
        b = datetime.strptime(birth, "%Y-%m-%d").date()
    except ValueError:
        return None
    t = date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def enrich_patient(p: dict) -> dict:
    p["age"] = patient_age(p.get("birth_date"))
    p["full_name"] = f"{p.get('last_name','')} {p.get('first_name','')} {p.get('patronymic') or ''}".strip()
    return p


@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.post("/api/login")
def api_login():
    body = request.get_json(force=True, silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    cur = db().execute("SELECT * FROM users WHERE email=? AND active=1", (email,))
    user = one(cur)
    if not user or not check_password_hash(user["password_hash"], password):
        return err("Неверный email или пароль", 401)
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    public = {k: user[k] for k in ("id", "email", "role", "full_name", "specialty", "phone", "color")}
    return ok(public)


@app.post("/api/logout")
def api_logout():
    session.clear()
    return ok({"logged_out": True})


@app.get("/api/me")
def api_me():
    user = current_user()
    if not user:
        return err("Нужна авторизация", 401)
    return ok(user)


@app.get("/api/meta")
@login_required
def api_meta():
    doctors = rows(db().execute("SELECT id, full_name, specialty, color, role, phone, email FROM users WHERE role IN ('doctor','admin') AND active=1"))
    staff = rows(db().execute("SELECT id, full_name, specialty, color, role, phone, email FROM users WHERE active=1"))
    services = rows(db().execute("SELECT * FROM services ORDER BY category, name"))
    rooms = rows(db().execute("SELECT * FROM rooms"))
    settings = {r["key"]: r["value"] for r in rows(db().execute("SELECT * FROM clinic_settings"))}
    return ok({"doctors": doctors, "staff": staff, "services": services, "rooms": rooms, "settings": settings})


@app.get("/api/dashboard")
@login_required
def api_dashboard():
    today = today_str()
    appts_today = rows(db().execute(
        """SELECT a.*, p.last_name, p.first_name, p.patronymic, u.full_name AS doctor_name, u.color AS doctor_color,
                  s.name AS service_name, r.name AS room_name
           FROM appointments a
           JOIN patients p ON p.id=a.patient_id
           JOIN users u ON u.id=a.doctor_id
           LEFT JOIN services s ON s.id=a.service_id
           LEFT JOIN rooms r ON r.id=a.room_id
           WHERE date(a.start_at)=?
           ORDER BY a.start_at""",
        (today,),
    ))
    revenue_today = db().execute(
        "SELECT COALESCE(SUM(paid),0) AS v FROM invoices WHERE date(created_at)=? OR date(paid_at)=?",
        (today, today),
    ).fetchone()["v"]
    open_invoices = db().execute("SELECT COALESCE(SUM(amount-paid),0) AS v FROM invoices WHERE status!='paid'").fetchone()["v"]
    patients_n = db().execute("SELECT COUNT(*) AS c FROM patients").fetchone()["c"]
    waiting = db().execute("SELECT COUNT(*) AS c FROM appointments WHERE date(start_at)=? AND status IN ('waiting','in_progress')", (today,)).fetchone()["c"]
    unread = db().execute("SELECT COUNT(*) AS c FROM messages WHERE sender='patient' AND read_flag=0").fetchone()["c"]
    lab_pending = db().execute("SELECT COUNT(*) AS c FROM lab_orders WHERE status!='ready'").fetchone()["c"]
    low_stock = rows(db().execute("SELECT * FROM inventory WHERE qty < min_qty ORDER BY qty"))
    watch = rows(db().execute(PATIENT_SELECT + " WHERE p.status='watch'"))
    tasks_open = rows(db().execute(
        """SELECT t.*, u.full_name AS assignee_name,
                  (p.last_name || ' ' || p.first_name) AS patient_name
           FROM tasks t
           LEFT JOIN users u ON u.id=t.assignee_id
           LEFT JOIN patients p ON p.id=t.patient_id
           WHERE t.status='open' ORDER BY t.priority DESC, t.due_at"""
    ))

    visits_series = []
    revenue_series = []
    for i in range(13, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        vc = db().execute("SELECT COUNT(*) AS c FROM appointments WHERE date(start_at)=? AND status='completed'", (d,)).fetchone()["c"]
        rv = db().execute("SELECT COALESCE(SUM(paid),0) AS v FROM invoices WHERE date(paid_at)=?", (d,)).fetchone()["v"]
        visits_series.append({"date": d, "count": vc})
        revenue_series.append({"date": d, "amount": rv})

    by_spec = rows(db().execute(
        """SELECT u.specialty AS name, COUNT(a.id) AS value
           FROM appointments a JOIN users u ON u.id=a.doctor_id
           WHERE date(a.start_at) >= date('now','-14 day')
           GROUP BY u.specialty"""
    ))
    return ok({
        "appointments_today": appts_today,
        "kpis": {
            "patients": patients_n,
            "today": len(appts_today),
            "waiting": waiting,
            "revenue_today": revenue_today,
            "open_invoices": open_invoices,
            "unread": unread,
            "lab_pending": lab_pending,
        },
        "low_stock": low_stock,
        "watch": [enrich_patient(p) for p in watch],
        "tasks": tasks_open,
        "visits_series": visits_series,
        "revenue_series": revenue_series,
        "by_specialty": by_spec,
    })


@app.get("/api/patients")
@login_required
def api_patients():
    q = (request.args.get("q") or "").strip()
    sql = PATIENT_SELECT
    args: list = []
    if q:
        sql += """ WHERE p.last_name LIKE ? OR p.first_name LIKE ? OR p.phone LIKE ? OR p.card_no LIKE ?"""
        like = f"%{q}%"
        args = [like, like, like, like]
    sql += " ORDER BY p.last_name, p.first_name"
    items = [enrich_patient(p) for p in rows(db().execute(sql, args))]
    return ok(items)


@app.get("/api/patients/<int:pid>")
@login_required
def api_patient(pid: int):
    p = one(db().execute(PATIENT_SELECT + " WHERE p.id=?", (pid,)))
    if not p:
        return err("Пациент не найден", 404)
    enrich_patient(p)
    appts = rows(db().execute(
        """SELECT a.*, u.full_name AS doctor_name, s.name AS service_name, r.name AS room_name
           FROM appointments a
           JOIN users u ON u.id=a.doctor_id
           LEFT JOIN services s ON s.id=a.service_id
           LEFT JOIN rooms r ON r.id=a.room_id
           WHERE a.patient_id=? ORDER BY a.start_at DESC""",
        (pid,),
    ))
    visits = rows(db().execute(
        """SELECT v.*, u.full_name AS doctor_name FROM visits v
           JOIN users u ON u.id=v.doctor_id WHERE v.patient_id=? ORDER BY v.created_at DESC""",
        (pid,),
    ))
    rxs = rows(db().execute(
        """SELECT r.*, u.full_name AS doctor_name FROM prescriptions r
           JOIN users u ON u.id=r.doctor_id WHERE r.patient_id=? ORDER BY r.created_at DESC""",
        (pid,),
    ))
    labs = rows(db().execute("SELECT * FROM lab_orders WHERE patient_id=? ORDER BY ordered_at DESC", (pid,)))
    for lab in labs:
        try:
            lab["results"] = json.loads(lab.get("result_json") or "[]")
        except json.JSONDecodeError:
            lab["results"] = []
    invoices = rows(db().execute("SELECT * FROM invoices WHERE patient_id=? ORDER BY created_at DESC", (pid,)))
    msgs = rows(db().execute("SELECT * FROM messages WHERE patient_id=? ORDER BY created_at", (pid,)))
    reminders = rows(db().execute("SELECT * FROM reminders WHERE patient_id=? ORDER BY due_at", (pid,)))
    return ok({
        "patient": p,
        "appointments": appts,
        "visits": visits,
        "prescriptions": rxs,
        "labs": labs,
        "invoices": invoices,
        "messages": msgs,
        "reminders": reminders,
    })


@app.post("/api/patients")
@login_required
def api_patients_create():
    body = request.get_json(force=True, silent=True) or {}
    required = ["last_name", "first_name"]
    if any(not body.get(k) for k in required):
        return err("Укажите фамилию и имя")
    n = db().execute("SELECT COUNT(*) AS c FROM patients").fetchone()["c"] + 1
    card = body.get("card_no") or f"MC-{1000 + n}"
    db().execute(
        """INSERT INTO patients(card_no,last_name,first_name,patronymic,birth_date,sex,phone,email,address,insurance,snils,blood_type,allergies,chronic,surgeries,notes,doctor_id,status,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            card,
            body.get("last_name"),
            body.get("first_name"),
            body.get("patronymic") or "",
            body.get("birth_date"),
            body.get("sex"),
            body.get("phone"),
            body.get("email"),
            body.get("address"),
            body.get("insurance"),
            body.get("snils"),
            body.get("blood_type"),
            body.get("allergies") or "",
            body.get("chronic") or "",
            body.get("surgeries") or "",
            body.get("notes") or "",
            body.get("doctor_id") or None,
            body.get("status") or "active",
            now_iso(),
        ),
    )
    db().commit()
    pid = db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return ok({"id": pid, "card_no": card})


@app.put("/api/patients/<int:pid>")
@login_required
def api_patients_update(pid: int):
    body = request.get_json(force=True, silent=True) or {}
    fields = [
        "last_name", "first_name", "patronymic", "birth_date", "sex", "phone", "email",
        "address", "insurance", "snils", "blood_type", "allergies", "chronic", "surgeries",
        "notes", "doctor_id", "status",
    ]
    sets, args = [], []
    for f in fields:
        if f in body:
            sets.append(f"{f}=?")
            args.append(body[f] if body[f] != "" else None)
    if not sets:
        return err("Нет изменений")
    args.append(pid)
    db().execute(f"UPDATE patients SET {', '.join(sets)} WHERE id=?", args)
    db().commit()
    return ok({"id": pid})


@app.get("/api/appointments")
@login_required
def api_appointments():
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    doctor_id = request.args.get("doctor_id")
    sql = """SELECT a.*, p.last_name, p.first_name, p.patronymic, p.phone,
                    u.full_name AS doctor_name, u.color AS doctor_color, u.specialty,
                    s.name AS service_name, s.duration_min, r.name AS room_name
             FROM appointments a
             JOIN patients p ON p.id=a.patient_id
             JOIN users u ON u.id=a.doctor_id
             LEFT JOIN services s ON s.id=a.service_id
             LEFT JOIN rooms r ON r.id=a.room_id
             WHERE 1=1"""
    args: list = []
    if date_from:
        sql += " AND date(a.start_at) >= ?"
        args.append(date_from)
    if date_to:
        sql += " AND date(a.start_at) <= ?"
        args.append(date_to)
    if doctor_id:
        sql += " AND a.doctor_id=?"
        args.append(doctor_id)
    sql += " ORDER BY a.start_at"
    return ok(rows(db().execute(sql, args)))


@app.post("/api/appointments")
@login_required
def api_appointments_create():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("patient_id") or not body.get("doctor_id") or not body.get("start_at"):
        return err("Нужны пациент, врач и время")
    start = body["start_at"]
    dur = int(body.get("duration_min") or 30)
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%dT%H:%M")
        except ValueError:
            return err("Некорректная дата")
    end_dt = start_dt + timedelta(minutes=dur)
    clash = one(db().execute(
        """SELECT id FROM appointments
           WHERE doctor_id=? AND status NOT IN ('cancelled','no_show')
             AND start_at < ? AND end_at > ?""",
        (body["doctor_id"], end_dt.strftime("%Y-%m-%d %H:%M:%S"), start_dt.strftime("%Y-%m-%d %H:%M:%S")),
    ))
    if clash:
        return err("У врача уже есть запись на это время")
    db().execute(
        """INSERT INTO appointments(patient_id,doctor_id,service_id,room_id,start_at,end_at,status,source,complaint,notes,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            body["patient_id"],
            body["doctor_id"],
            body.get("service_id"),
            body.get("room_id"),
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            body.get("status") or "scheduled",
            body.get("source") or "регистратура",
            body.get("complaint") or "",
            body.get("notes") or "",
            now_iso(),
        ),
    )
    db().commit()
    aid = db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    svc = one(db().execute("SELECT * FROM services WHERE id=?", (body.get("service_id"),))) if body.get("service_id") else None
    if svc and body.get("create_invoice"):
        n = db().execute("SELECT COUNT(*) AS c FROM invoices").fetchone()["c"] + 1
        number = f"СЧ-{date.today().strftime('%y%m%d')}-{n:02d}"
        db().execute(
            """INSERT INTO invoices(patient_id,appointment_id,number,amount,paid,status,method,created_at)
               VALUES(?,?,?,?,0,'open','',?)""",
            (body["patient_id"], aid, number, svc["price"], now_iso()),
        )
        iid = db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        db().execute(
            "INSERT INTO invoice_items(invoice_id,service_id,title,qty,price) VALUES(?,?,?,?,?)",
            (iid, svc["id"], svc["name"], 1, svc["price"]),
        )
        db().commit()
    return ok({"id": aid})


@app.put("/api/appointments/<int:aid>")
@login_required
def api_appointments_update(aid: int):
    body = request.get_json(force=True, silent=True) or {}
    fields = ["status", "notes", "complaint", "room_id", "doctor_id", "service_id", "start_at", "end_at"]
    sets, args = [], []
    for f in fields:
        if f in body:
            sets.append(f"{f}=?")
            args.append(body[f])
    if not sets:
        return err("Нет изменений")
    args.append(aid)
    db().execute(f"UPDATE appointments SET {', '.join(sets)} WHERE id=?", args)
    db().commit()
    appt = one(db().execute("SELECT * FROM appointments WHERE id=?", (aid,)))
    if body.get("status") == "completed" and appt:
        exists = one(db().execute("SELECT id FROM visits WHERE appointment_id=?", (aid,)))
        if not exists:
            db().execute(
                """INSERT INTO visits(appointment_id,patient_id,doctor_id,complaint,created_at)
                   VALUES(?,?,?,?,?)""",
                (aid, appt["patient_id"], appt["doctor_id"], appt.get("complaint") or "", now_iso()),
            )
            db().commit()
    return ok({"id": aid})


@app.get("/api/queue")
@login_required
def api_queue():
    today = today_str()
    items = rows(db().execute(
        """SELECT a.*, p.last_name, p.first_name, p.patronymic, p.phone,
                  u.full_name AS doctor_name, s.name AS service_name
           FROM appointments a
           JOIN patients p ON p.id=a.patient_id
           JOIN users u ON u.id=a.doctor_id
           LEFT JOIN services s ON s.id=a.service_id
           WHERE date(a.start_at)=? AND a.status IN ('scheduled','confirmed','waiting','in_progress')
           ORDER BY CASE a.status WHEN 'in_progress' THEN 0 WHEN 'waiting' THEN 1 WHEN 'confirmed' THEN 2 ELSE 3 END, a.start_at""",
        (today,),
    ))
    return ok(items)


@app.post("/api/visits")
@login_required
def api_visits_create():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("patient_id") or not body.get("doctor_id"):
        return err("Нужны пациент и врач")
    db().execute(
        """INSERT INTO visits(appointment_id,patient_id,doctor_id,complaint,anamnesis,examination,diagnosis,icd10,recommendations,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            body.get("appointment_id"),
            body["patient_id"],
            body["doctor_id"],
            body.get("complaint") or "",
            body.get("anamnesis") or "",
            body.get("examination") or "",
            body.get("diagnosis") or "",
            body.get("icd10") or "",
            body.get("recommendations") or "",
            now_iso(),
        ),
    )
    db().commit()
    return ok({"id": db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]})


@app.put("/api/visits/<int:vid>")
@login_required
def api_visits_update(vid: int):
    body = request.get_json(force=True, silent=True) or {}
    fields = ["complaint", "anamnesis", "examination", "diagnosis", "icd10", "recommendations"]
    sets, args = [], []
    for f in fields:
        if f in body:
            sets.append(f"{f}=?")
            args.append(body[f])
    if not sets:
        return err("Нет изменений")
    args.append(vid)
    db().execute(f"UPDATE visits SET {', '.join(sets)} WHERE id=?", args)
    db().commit()
    return ok({"id": vid})


@app.get("/api/visits")
@login_required
def api_visits():
    items = rows(db().execute(
        """SELECT v.*, p.last_name, p.first_name, u.full_name AS doctor_name
           FROM visits v JOIN patients p ON p.id=v.patient_id
           JOIN users u ON u.id=v.doctor_id
           ORDER BY v.created_at DESC LIMIT 200"""
    ))
    return ok(items)


@app.post("/api/prescriptions")
@login_required
def api_rx_create():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("patient_id") or not body.get("medication"):
        return err("Нужны пациент и препарат")
    user = current_user()
    db().execute(
        """INSERT INTO prescriptions(visit_id,patient_id,doctor_id,medication,dosage,duration_days,times_per_day,instructions,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            body.get("visit_id"),
            body["patient_id"],
            body.get("doctor_id") or user["id"],
            body["medication"],
            body.get("dosage") or "",
            body.get("duration_days") or 7,
            body.get("times_per_day") or 1,
            body.get("instructions") or "",
            now_iso(),
        ),
    )
    db().commit()
    return ok({"id": db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]})


@app.get("/api/lab")
@login_required
def api_lab():
    items = rows(db().execute(
        """SELECT l.*, p.last_name, p.first_name, u.full_name AS doctor_name
           FROM lab_orders l JOIN patients p ON p.id=l.patient_id
           LEFT JOIN users u ON u.id=l.doctor_id
           ORDER BY l.ordered_at DESC"""
    ))
    for lab in items:
        try:
            lab["results"] = json.loads(lab.get("result_json") or "[]")
        except json.JSONDecodeError:
            lab["results"] = []
    return ok(items)


@app.post("/api/lab")
@login_required
def api_lab_create():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("patient_id") or not body.get("test_name"):
        return err("Нужны пациент и исследование")
    user = current_user()
    db().execute(
        """INSERT INTO lab_orders(patient_id,doctor_id,test_name,category,status,ordered_at,result_json,comment)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            body["patient_id"],
            body.get("doctor_id") or user["id"],
            body["test_name"],
            body.get("category") or "лаборатория",
            "ordered",
            now_iso(),
            json.dumps(body.get("results") or [], ensure_ascii=False),
            body.get("comment") or "",
        ),
    )
    db().commit()
    return ok({"id": db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]})


@app.put("/api/lab/<int:lid>")
@login_required
def api_lab_update(lid: int):
    body = request.get_json(force=True, silent=True) or {}
    sets, args = [], []
    if "status" in body:
        sets.append("status=?")
        args.append(body["status"])
        if body["status"] == "ready":
            sets.append("result_at=?")
            args.append(now_iso())
    if "results" in body:
        sets.append("result_json=?")
        args.append(json.dumps(body["results"], ensure_ascii=False))
    if "comment" in body:
        sets.append("comment=?")
        args.append(body["comment"])
    if not sets:
        return err("Нет изменений")
    args.append(lid)
    db().execute(f"UPDATE lab_orders SET {', '.join(sets)} WHERE id=?", args)
    db().commit()
    return ok({"id": lid})


@app.get("/api/invoices")
@login_required
def api_invoices():
    items = rows(db().execute(
        """SELECT i.*, p.last_name, p.first_name
           FROM invoices i JOIN patients p ON p.id=i.patient_id
           ORDER BY i.created_at DESC"""
    ))
    for inv in items:
        inv["items"] = rows(db().execute("SELECT * FROM invoice_items WHERE invoice_id=?", (inv["id"],)))
    return ok(items)


@app.post("/api/invoices")
@login_required
def api_invoices_create():
    body = request.get_json(force=True, silent=True) or {}
    items = body.get("items") or []
    if not body.get("patient_id") or not items:
        return err("Нужны пациент и позиции")
    amount = sum(int(x.get("price") or 0) * int(x.get("qty") or 1) for x in items)
    n = db().execute("SELECT COUNT(*) AS c FROM invoices").fetchone()["c"] + 1
    number = body.get("number") or f"СЧ-{date.today().strftime('%y%m%d')}-{n:02d}"
    db().execute(
        """INSERT INTO invoices(patient_id,appointment_id,number,amount,paid,status,method,created_at)
           VALUES(?,?,?,?,0,'open','',?)""",
        (body["patient_id"], body.get("appointment_id"), number, amount, now_iso()),
    )
    iid = db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    for x in items:
        db().execute(
            "INSERT INTO invoice_items(invoice_id,service_id,title,qty,price) VALUES(?,?,?,?,?)",
            (iid, x.get("service_id"), x.get("title") or "Услуга", x.get("qty") or 1, x.get("price") or 0),
        )
    db().commit()
    return ok({"id": iid, "number": number, "amount": amount})


@app.post("/api/invoices/<int:iid>/pay")
@login_required
def api_invoices_pay(iid: int):
    body = request.get_json(force=True, silent=True) or {}
    inv = one(db().execute("SELECT * FROM invoices WHERE id=?", (iid,)))
    if not inv:
        return err("Счёт не найден", 404)
    method = body.get("method") or "карта"
    db().execute(
        "UPDATE invoices SET paid=amount, status='paid', method=?, paid_at=? WHERE id=?",
        (method, now_iso(), iid),
    )
    db().commit()
    return ok({"id": iid})


@app.get("/api/messages")
@login_required
def api_messages():
    pid = request.args.get("patient_id")
    if pid:
        items = rows(db().execute("SELECT * FROM messages WHERE patient_id=? ORDER BY created_at", (pid,)))
        db().execute("UPDATE messages SET read_flag=1 WHERE patient_id=? AND sender='patient'", (pid,))
        db().commit()
        return ok(items)
    threads = rows(db().execute(
        """SELECT m.patient_id, p.last_name, p.first_name, p.patronymic,
                  MAX(m.created_at) AS last_at,
                  SUM(CASE WHEN m.sender='patient' AND m.read_flag=0 THEN 1 ELSE 0 END) AS unread
           FROM messages m JOIN patients p ON p.id=m.patient_id
           GROUP BY m.patient_id
           ORDER BY last_at DESC"""
    ))
    last_map = {}
    for t in threads:
        last = one(db().execute(
            "SELECT text, sender, sender_name FROM messages WHERE patient_id=? ORDER BY created_at DESC LIMIT 1",
            (t["patient_id"],),
        ))
        last_map[t["patient_id"]] = last
        t["last"] = last
    return ok(threads)


@app.post("/api/messages")
@login_required
def api_messages_send():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("patient_id") or not body.get("text"):
        return err("Нужны пациент и текст")
    user = current_user()
    sender = body.get("sender") or "doctor"
    db().execute(
        "INSERT INTO messages(patient_id,sender,sender_name,text,created_at,read_flag) VALUES(?,?,?,?,?,?)",
        (body["patient_id"], sender, user["full_name"], body["text"].strip(), now_iso(), 1 if sender != "patient" else 0),
    )
    db().commit()
    return ok({"id": db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]})


@app.get("/api/inventory")
@login_required
def api_inventory():
    return ok(rows(db().execute("SELECT * FROM inventory ORDER BY category, name")))


@app.post("/api/inventory")
@login_required
def api_inventory_create():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("name"):
        return err("Укажите название")
    db().execute(
        "INSERT INTO inventory(name,sku,unit,qty,min_qty,price,category) VALUES(?,?,?,?,?,?,?)",
        (
            body["name"],
            body.get("sku") or "",
            body.get("unit") or "шт",
            int(body.get("qty") or 0),
            int(body.get("min_qty") or 5),
            int(body.get("price") or 0),
            body.get("category") or "расходники",
        ),
    )
    db().commit()
    return ok({"id": db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]})


@app.put("/api/inventory/<int:iid>")
@login_required
def api_inventory_update(iid: int):
    body = request.get_json(force=True, silent=True) or {}
    fields = ["name", "sku", "unit", "qty", "min_qty", "price", "category"]
    sets, args = [], []
    for f in fields:
        if f in body:
            sets.append(f"{f}=?")
            args.append(body[f])
    if not sets:
        return err("Нет изменений")
    args.append(iid)
    db().execute(f"UPDATE inventory SET {', '.join(sets)} WHERE id=?", args)
    db().commit()
    return ok({"id": iid})


@app.get("/api/tasks")
@login_required
def api_tasks():
    items = rows(db().execute(
        """SELECT t.*, u.full_name AS assignee_name,
                  (p.last_name || ' ' || p.first_name) AS patient_name
           FROM tasks t
           LEFT JOIN users u ON u.id=t.assignee_id
           LEFT JOIN patients p ON p.id=t.patient_id
           ORDER BY CASE t.status WHEN 'open' THEN 0 ELSE 1 END, t.due_at"""
    ))
    return ok(items)


@app.post("/api/tasks")
@login_required
def api_tasks_create():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("title"):
        return err("Нужен заголовок")
    db().execute(
        "INSERT INTO tasks(title,assignee_id,patient_id,due_at,status,priority,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            body["title"],
            body.get("assignee_id"),
            body.get("patient_id"),
            body.get("due_at"),
            "open",
            body.get("priority") or "normal",
            now_iso(),
        ),
    )
    db().commit()
    return ok({"id": db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]})


@app.put("/api/tasks/<int:tid>")
@login_required
def api_tasks_update(tid: int):
    body = request.get_json(force=True, silent=True) or {}
    fields = ["title", "status", "priority", "due_at", "assignee_id"]
    sets, args = [], []
    for f in fields:
        if f in body:
            sets.append(f"{f}=?")
            args.append(body[f])
    if not sets:
        return err("Нет изменений")
    args.append(tid)
    db().execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", args)
    db().commit()
    return ok({"id": tid})


@app.post("/api/services")
@require_roles("admin", "accountant", "reception")
def api_services_create():
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("name") or body.get("price") is None:
        return err("Нужны название и цена")
    db().execute(
        "INSERT INTO services(name,category,duration_min,price,code) VALUES(?,?,?,?,?)",
        (
            body["name"],
            body.get("category") or "приём",
            int(body.get("duration_min") or 30),
            int(body["price"]),
            body.get("code") or "",
        ),
    )
    db().commit()
    return ok({"id": db().execute("SELECT last_insert_rowid() AS id").fetchone()["id"]})


@app.put("/api/settings")
@require_roles("admin")
def api_settings_update():
    body = request.get_json(force=True, silent=True) or {}
    for k, v in body.items():
        db().execute(
            "INSERT INTO clinic_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v)),
        )
    db().commit()
    return ok(True)


@app.get("/api/reports")
@login_required
def api_reports():
    by_doctor = rows(db().execute(
        """SELECT u.full_name AS name, u.specialty,
                  COUNT(a.id) AS visits,
                  SUM(CASE WHEN a.status='completed' THEN 1 ELSE 0 END) AS done,
                  SUM(CASE WHEN a.status='no_show' THEN 1 ELSE 0 END) AS no_show
           FROM users u
           LEFT JOIN appointments a ON a.doctor_id=u.id AND date(a.start_at) >= date('now','-30 day')
           WHERE u.role IN ('doctor','admin')
           GROUP BY u.id
           ORDER BY visits DESC"""
    ))
    by_service = rows(db().execute(
        """SELECT s.name, s.category, COUNT(a.id) AS cnt, COALESCE(SUM(s.price),0) AS amount
           FROM appointments a JOIN services s ON s.id=a.service_id
           WHERE date(a.start_at) >= date('now','-30 day') AND a.status!='cancelled'
           GROUP BY s.id ORDER BY cnt DESC"""
    ))
    cash = rows(db().execute(
        """SELECT date(paid_at) AS day, method, SUM(paid) AS amount
           FROM invoices WHERE status='paid' AND paid_at IS NOT NULL
           GROUP BY date(paid_at), method ORDER BY day DESC LIMIT 30"""
    ))
    funnel = rows(db().execute(
        """SELECT status, COUNT(*) AS cnt FROM appointments
           WHERE date(start_at) >= date('now','-30 day') GROUP BY status"""
    ))
    return ok({"by_doctor": by_doctor, "by_service": by_service, "cash": cash, "funnel": funnel})


@app.get("/health")
def health():
    return jsonify({"ok": True, "app": "clinic-crm"})


def main():
    seed_if_needed()
    port = int(os.environ.get("PORT", "5050"))
    print("CRM клиники «Семейный доктор»")
    print(f"Откройте http://127.0.0.1:{port}")
    print("Демо-входы:")
    print("  admin@clinic.local       / admin123       — главный врач")
    print("  doctor@clinic.local      / doctor123      — кардиолог")
    print("  reception@clinic.local   / reception123   — регистратура")
    print("  nurse@clinic.local       / nurse123       — медсестра")
    print("  acc@clinic.local         / acc123         — касса")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    seed_if_needed()
    main()
else:
    seed_if_needed()

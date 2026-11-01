"""Управление сервером из консоли.

    python -m server.manage init
    python -m server.manage create-admin admin
    python -m server.manage make-keys 5 --days 30 --devices 1 --plan "Стандарт"
    python -m server.manage public-key        # вставить в photogrid/license_pub.pem
    python -m server.manage stats
    python -m server.manage set maintenance 1

Каталог данных: переменная окружения PE_DATA_DIR (по умолчанию ~/photoenjoyer_data).
"""
import argparse
import getpass
import os
import sys

from . import db, security
from .app import create_app


def _open(app):
    return db.connect(app.db_path)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="server.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="создать базу и ключ подписи")
    p = sub.add_parser("create-admin", help="создать администратора")
    p.add_argument("username")
    p.add_argument("--password")
    p = sub.add_parser("make-keys", help="выпустить ключи лицензий")
    p.add_argument("count", type=int)
    p.add_argument("--days", type=int, default=30, help="срок после активации, 0 = бессрочно")
    p.add_argument("--devices", type=int, default=1)
    p.add_argument("--plan", default="Стандарт")
    sub.add_parser("public-key", help="напечатать открытый ключ для программы")
    sub.add_parser("stats", help="краткая статистика")
    p = sub.add_parser("set", help="изменить настройку сервера")
    p.add_argument("key")
    p.add_argument("value")
    args = ap.parse_args(argv)

    app = create_app()
    con = _open(app)
    if args.cmd == "init":
        print("Каталог данных:", app.data_dir)
        print("База:", app.db_path)
        print("Открытый ключ (скопируйте в photogrid/license_pub.pem):\n")
        print(security.public_pem(app.priv).decode())
    elif args.cmd == "create-admin":
        pw = args.password or getpass.getpass("Пароль (мин. 8 символов): ")
        if len(pw) < 8:
            sys.exit("Пароль слишком короткий")
        if con.execute("SELECT 1 FROM users WHERE username=?", (args.username,)).fetchone():
            sys.exit("Такой логин уже есть")
        app.create_user(con, args.username, pw, role="admin", max_devices=10)
        print("Администратор создан:", args.username)
    elif args.cmd == "make-keys":
        for _ in range(args.count):
            k = security.new_license_key()
            con.execute("INSERT INTO license_keys(key, plan, days, max_devices, created_at) "
                        "VALUES(?,?,?,?,?)", (k, args.plan, args.days, args.devices, db.now()))
            print(k)
        con.commit()
    elif args.cmd == "public-key":
        print(security.public_pem(app.priv).decode())
    elif args.cmd == "stats":
        q = lambda s: con.execute(s).fetchone()[0]
        print("пользователей:", q("SELECT COUNT(*) FROM users WHERE role='user'"))
        print("ключей свободно:", q("SELECT COUNT(*) FROM license_keys WHERE used_by IS NULL AND revoked=0"))
        print("событий:", q("SELECT COUNT(*) FROM events"))
    elif args.cmd == "set":
        if args.key not in db.DEFAULT_SETTINGS:
            sys.exit("Допустимые ключи: " + ", ".join(db.DEFAULT_SETTINGS))
        db.set_setting(con, args.key, args.value)
        con.commit()
        print("OK")
    con.close()


if __name__ == "__main__":
    main()

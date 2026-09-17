"""Проверяет подпись манифеста локально. Запуск: python tools/verify_manifest.py"""
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


def main():
    manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "manifest.json")
    pubkey_path = Path("photogrid/public_key.pem")

    if not manifest_path.exists():
        print(f"❌ {manifest_path} не найден")
        return
    if not pubkey_path.exists():
        print(f"❌ {pubkey_path} не найден")
        return

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    sig = data.pop("signature", None)
    if not sig:
        print("❌ В манифесте нет поля 'signature'")
        return

    canonical = json.dumps(data, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":")).encode("utf-8")

    pub = serialization.load_pem_public_key(pubkey_path.read_bytes())
    try:
        pub.verify(base64.b64decode(sig), canonical)
        print(f"✓ Подпись верна (версия {data.get('version')})")
    except InvalidSignature:
        print(f"❌ ПОДПИСЬ НЕВЕРНА для версии {data.get('version')}")
        print("   Публичный ключ в проекте НЕ соответствует приватному,")
        print("   которым подписан манифест. Нужно пересоздать пару.")


if __name__ == "__main__":
    main()
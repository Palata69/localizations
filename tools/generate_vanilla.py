#!/usr/bin/env python3
"""
Генерирует localizations/ru/vanilla.yml — русские названия ванильных предметов, блоков, эффектов,
зачарований и существ из официального ru_ru.json Mojang.

Ключи — в той же схеме, что строит код (LocaleUtil в lite-api): ключ перевода Minecraft,
точки заменены на «_»; у существ спереди добавлено «entity_».

    item.minecraft.diamond_sword        -> item_minecraft_diamond_sword
    block.minecraft.stone               -> block_minecraft_stone
    effect.minecraft.speed              -> effect_minecraft_speed
    enchantment.minecraft.sharpness     -> enchantment_minecraft_sharpness
    entity.minecraft.zombie             -> entity_entity_minecraft_zombie
    effect.duration.infinite            -> potion_infinity

Версия Minecraft берётся из core/gradle/libs.versions.toml (paper = "26.3.build..." -> 26.3);
если такой версии нет в манифесте Mojang — последняя release. Можно задать явно: --version 26.3

Запуск (только стандартная библиотека Python 3):

    python localizations/tools/generate_vanilla.py
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
RESOURCES_URL = "https://resources.download.minecraft.net/{prefix}/{hash}"
LANG_OBJECT = "minecraft/lang/ru_ru.json"

ROOT = Path(__file__).resolve().parents[2]
VERSIONS_TOML = ROOT / "core" / "gradle" / "libs.versions.toml"
OUTPUT = ROOT / "localizations" / "ru" / "vanilla.yml"

# префикс ключа Mojang -> префикс ключа в локализации (после замены «.» на «_»)
PREFIXES = {
    "item.minecraft.": "",
    "block.minecraft.": "",
    "effect.minecraft.": "",
    "enchantment.minecraft.": "",
    "entity.minecraft.": "entity_",
}

# ключи, которые код запрашивает под своим именем
EXTRA = {
    "potion_infinity": "effect.duration.infinite",
}


def fetch(url, sha1=None):
    request = urllib.request.Request(url, headers={"User-Agent": "localization-generator"})

    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()

    if sha1 is not None and hashlib.sha1(data).hexdigest() != sha1:
        raise RuntimeError(f"не совпал sha1 у {url}")

    return data


def server_version():
    if not VERSIONS_TOML.is_file():
        return None

    match = re.search(r'^\s*paper\s*=\s*"([^"]+)"', VERSIONS_TOML.read_text(encoding="utf-8"), re.MULTILINE)

    if match is None:
        return None

    # 26.3.build.253-stable -> 26.3; 1.21.11-R0.1-SNAPSHOT -> 1.21.11
    return re.split(r"\.build|-", match.group(1))[0]


def pick_version(manifest, wanted):
    versions = {entry["id"]: entry for entry in manifest["versions"]}

    if wanted and wanted in versions:
        return versions[wanted]

    latest = manifest["latest"]["release"]

    if wanted:
        print(f"версии {wanted} нет в манифесте, беру последнюю release: {latest}", file=sys.stderr)

    return versions[latest]


def escape(text):
    # разметка: буквальные \ < { -> \\ \< \{
    text = text.replace("\\", "\\\\").replace("<", "\\<").replace("{", "\\{")
    # YAML в двойных кавычках
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def convert(lang):
    result = {}
    skipped = []

    for mojang_key, value in lang.items():
        for prefix, extra in PREFIXES.items():
            if mojang_key.startswith(prefix):
                key = extra + mojang_key.replace(".", "_")

                if key != key.lower():
                    skipped.append(mojang_key)
                elif key in result:
                    raise RuntimeError(f"два ключа Mojang дают один и тот же ключ {key}")
                else:
                    result[key] = value

                break

    for key, mojang_key in EXTRA.items():
        if mojang_key in lang:
            result[key] = lang[mojang_key]
        else:
            skipped.append(mojang_key)

    return result, skipped


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", help="версия Minecraft (по умолчанию — из libs.versions.toml)")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="куда записать (по умолчанию ru/vanilla.yml)")
    args = parser.parse_args()

    manifest = json.loads(fetch(MANIFEST_URL))
    version = pick_version(manifest, args.version or server_version())

    version_json = json.loads(fetch(version["url"], version.get("sha1")))
    asset_index_ref = version_json["assetIndex"]
    asset_index = json.loads(fetch(asset_index_ref["url"], asset_index_ref.get("sha1")))

    lang_object = asset_index["objects"].get(LANG_OBJECT)

    if lang_object is None:
        raise RuntimeError(f"в assetIndex {asset_index_ref['id']} нет {LANG_OBJECT}")

    lang_hash = lang_object["hash"]
    lang = json.loads(fetch(RESOURCES_URL.format(prefix=lang_hash[:2], hash=lang_hash), lang_hash).decode("utf-8"))

    messages, skipped = convert(lang)

    lines = [
        "# Сгенерировано скриптом localizations/tools/generate_vanilla.py — не править руками.",
        f"# Версия Minecraft: {version['id']} (ru_ru.json, sha1 {lang_hash})",
        "# Названия предметов, блоков, эффектов, зачарований и существ для LocaleUtil.",
        "",
    ]

    for key in sorted(messages):
        lines.append(f'{key}: "{escape(messages[key])}"')

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"Minecraft {version['id']}: {len(messages)} ключей -> {args.output}")

    if skipped:
        print(f"пропущено {len(skipped)}: {', '.join(skipped)}", file=sys.stderr)


if __name__ == "__main__":
    main()

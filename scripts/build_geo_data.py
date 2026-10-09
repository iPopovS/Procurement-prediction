"""Rebuild the bundled geo files from Natural Earth (public domain).

Usage (dev machine, needs ``pip install shapely``):

    B=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson
    curl -o /tmp/admin1_50m.geojson    $B/ne_50m_admin_1_states_provinces.geojson
    curl -o /tmp/countries_50m.geojson $B/ne_50m_admin_0_countries.geojson
    python scripts/build_geo_data.py /tmp/admin1_50m.geojson /tmp/countries_50m.geojson

Outputs (committed to the repo, so the app has NO runtime dependency on any geo service):
    app/data/regions.json              region code -> names + representative point (lat/lon)
    app/static/data/regions.geojson    Russian region polygons (code, name_en, name_ru)
    app/static/data/countries.geojson  world country polygons

``region`` in the GosPlan purchase response is the two-digit subject code of the Russian
Federation as used by FIAS/GAR and vehicle plates (verified on one record: ``25`` ->
Primorsky Krai, matching the delivery address). Natural Earth polygons are matched by
their English ``name`` field; ``iso_3166_2`` in that file is NOT reliable (it swaps
Moscow city and Moscow Oblast), so it is not used.

To use different borders, replace the two GeoJSON files in app/static/data/ (keep the
``code`` property on regions) and regions.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]

# code: (English name, Russian name, Natural Earth `name`)
REGIONS = {
    "01": ("Republic of Adygea", "Республика Адыгея", "Adygey"),
    "02": ("Republic of Bashkortostan", "Республика Башкортостан", "Bashkortostan"),
    "03": ("Republic of Buryatia", "Республика Бурятия", "Buryat"),
    "04": ("Altai Republic", "Республика Алтай", "Gorno-Altay"),
    "05": ("Republic of Dagestan", "Республика Дагестан", "Dagestan"),
    "06": ("Republic of Ingushetia", "Республика Ингушетия", "Ingush"),
    "07": ("Kabardino-Balkar Republic", "Кабардино-Балкарская Республика", "Kabardin-Balkar"),
    "08": ("Republic of Kalmykia", "Республика Калмыкия", "Kalmyk"),
    "09": ("Karachay-Cherkess Republic", "Карачаево-Черкесская Республика", "Karachay-Cherkess"),
    "10": ("Republic of Karelia", "Республика Карелия", "Karelia"),
    "11": ("Komi Republic", "Республика Коми", "Komi"),
    "12": ("Mari El Republic", "Республика Марий Эл", "Mariy-El"),
    "13": ("Republic of Mordovia", "Республика Мордовия", "Mordovia"),
    "14": ("Sakha Republic (Yakutia)", "Республика Саха (Якутия)", "Sakha (Yakutia)"),
    "15": ("North Ossetia-Alania", "Республика Северная Осетия - Алания", "North Ossetia"),
    "16": ("Republic of Tatarstan", "Республика Татарстан", "Tatarstan"),
    "17": ("Tuva Republic", "Республика Тыва", "Tuva"),
    "18": ("Udmurt Republic", "Удмуртская Республика", "Udmurt"),
    "19": ("Republic of Khakassia", "Республика Хакасия", "Khakass"),
    "20": ("Chechen Republic", "Чеченская Республика", "Chechnya"),
    "21": ("Chuvash Republic", "Чувашская Республика", "Chuvash"),
    "22": ("Altai Krai", "Алтайский край", "Altay"),
    "23": ("Krasnodar Krai", "Краснодарский край", "Krasnodar"),
    "24": ("Krasnoyarsk Krai", "Красноярский край", "Krasnoyarsk"),
    "25": ("Primorsky Krai", "Приморский край", "Primor'ye"),
    "26": ("Stavropol Krai", "Ставропольский край", "Stavropol'"),
    "27": ("Khabarovsk Krai", "Хабаровский край", "Khabarovsk"),
    "28": ("Amur Oblast", "Амурская область", "Amur"),
    "29": ("Arkhangelsk Oblast", "Архангельская область", "Arkhangel'sk"),
    "30": ("Astrakhan Oblast", "Астраханская область", "Astrakhan'"),
    "31": ("Belgorod Oblast", "Белгородская область", "Belgorod"),
    "32": ("Bryansk Oblast", "Брянская область", "Bryansk"),
    "33": ("Vladimir Oblast", "Владимирская область", "Vladimir"),
    "34": ("Volgograd Oblast", "Волгоградская область", "Volgograd"),
    "35": ("Vologda Oblast", "Вологодская область", "Vologda"),
    "36": ("Voronezh Oblast", "Воронежская область", "Voronezh"),
    "37": ("Ivanovo Oblast", "Ивановская область", "Ivanovo"),
    "38": ("Irkutsk Oblast", "Иркутская область", "Irkutsk"),
    "39": ("Kaliningrad Oblast", "Калининградская область", "Kaliningrad"),
    "40": ("Kaluga Oblast", "Калужская область", "Kaluga"),
    "41": ("Kamchatka Krai", "Камчатский край", "Kamchatka"),
    "42": ("Kemerovo Oblast", "Кемеровская область", "Kemerovo"),
    "43": ("Kirov Oblast", "Кировская область", "Kirov"),
    "44": ("Kostroma Oblast", "Костромская область", "Kostroma"),
    "45": ("Kurgan Oblast", "Курганская область", "Kurgan"),
    "46": ("Kursk Oblast", "Курская область", "Kursk"),
    "47": ("Leningrad Oblast", "Ленинградская область", "Leningrad"),
    "48": ("Lipetsk Oblast", "Липецкая область", "Lipetsk"),
    "49": ("Magadan Oblast", "Магаданская область", "Maga Buryatdan"),
    "50": ("Moscow Oblast", "Московская область", "Moskovskaya"),
    "51": ("Murmansk Oblast", "Мурманская область", "Murmansk"),
    "52": ("Nizhny Novgorod Oblast", "Нижегородская область", "Nizhegorod"),
    "53": ("Novgorod Oblast", "Новгородская область", "Novgorod"),
    "54": ("Novosibirsk Oblast", "Новосибирская область", "Novosibirsk"),
    "55": ("Omsk Oblast", "Омская область", "Omsk"),
    "56": ("Orenburg Oblast", "Оренбургская область", "Orenburg"),
    "57": ("Oryol Oblast", "Орловская область", "Orel"),
    "58": ("Penza Oblast", "Пензенская область", "Penza"),
    "59": ("Perm Krai", "Пермский край", "Perm'"),
    "60": ("Pskov Oblast", "Псковская область", "Pskov"),
    "61": ("Rostov Oblast", "Ростовская область", "Rostov"),
    "62": ("Ryazan Oblast", "Рязанская область", "Ryazan'"),
    "63": ("Samara Oblast", "Самарская область", "Samara"),
    "64": ("Saratov Oblast", "Саратовская область", "Saratov"),
    "65": ("Sakhalin Oblast", "Сахалинская область", "Sakhalin"),
    "66": ("Sverdlovsk Oblast", "Свердловская область", "Sverdlovsk"),
    "67": ("Smolensk Oblast", "Смоленская область", "Smolensk"),
    "68": ("Tambov Oblast", "Тамбовская область", "Tambov"),
    "69": ("Tver Oblast", "Тверская область", "Tver'"),
    "70": ("Tomsk Oblast", "Томская область", "Tomsk"),
    "71": ("Tula Oblast", "Тульская область", "Tula"),
    "72": ("Tyumen Oblast", "Тюменская область", "Tyumen'"),
    "73": ("Ulyanovsk Oblast", "Ульяновская область", "Ul'yanovsk"),
    "74": ("Chelyabinsk Oblast", "Челябинская область", "Chelyabinsk"),
    "75": ("Zabaykalsky Krai", "Забайкальский край", "Chita"),
    "76": ("Yaroslavl Oblast", "Ярославская область", "Yaroslavl'"),
    "77": ("Moscow", "Москва", "Moskva"),
    "78": ("Saint Petersburg", "Санкт-Петербург", "City of St. Petersburg"),
    "79": ("Jewish Autonomous Oblast", "Еврейская автономная область", "Yevrey"),
    "83": ("Nenets Autonomous Okrug", "Ненецкий автономный округ", "Nenets"),
    "86": ("Khanty-Mansi Autonomous Okrug", "Ханты-Мансийский автономный округ", "Khanty-Mansiy"),
    "87": ("Chukotka Autonomous Okrug", "Чукотский автономный округ", "Chukchi Autonomous Okrug"),
    "89": ("Yamalo-Nenets Autonomous Okrug", "Ямало-Ненецкий автономный округ", "Yamal-Nenets"),
    # Crimea / Sevastopol: the two-digit code is not verified against real data (91/92 are the
    # FIAS/GAR codes, 82 the vehicle-plate code). Unknown codes are never guessed: a record
    # with a code missing from this table simply has no map location.
    "91": ("Republic of Crimea", "Республика Крым", "Crimea"),
    "92": ("Sevastopol", "Севастополь", "Sevastopol"),
}
ALIASES = {"82": "91"}  # alternative code -> canonical code (see note above)

PRECISION = 2  # decimal degrees kept in the output (~1 km)

# City-regions: the polygon centroid is skewed by suburban territories (e.g. "New Moscow"),
# so the marker is pinned to the city centre instead.
ANCHOR_OVERRIDES = {
    "77": (55.751, 37.618),  # Moscow
    "78": (59.934, 30.335),  # Saint Petersburg
    "92": (44.616, 33.525),  # Sevastopol
}


def round_coords(obj, nd=PRECISION):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(c, nd) for c in obj]
        return [round_coords(o, nd) for o in obj]
    return obj


def simplified(geom, tol):
    g = geom.simplify(tol, preserve_topology=True)
    if g.is_empty:
        g = geom
    m = mapping(g)
    return {"type": m["type"], "coordinates": round_coords(m["coordinates"])}


def anchor_point(geom):
    """Representative point of the largest polygon (always inside the region)."""
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    p = geom.representative_point()
    c = geom.centroid
    pt = c if geom.contains(c) else p  # prefer the true centroid when it lies inside
    return round(pt.y, 3), round(pt.x, 3)


def main(admin1_path: str, countries_path: str) -> None:
    admin1 = json.loads(Path(admin1_path).read_text(encoding="utf-8"))
    by_name = {
        f["properties"]["name"]: f
        for f in admin1["features"]
        if f["properties"].get("adm0_a3") == "RUS"
    }
    feats, table = [], {}
    for code, (en, ru, ne) in REGIONS.items():
        f = by_name.get(ne)
        if f is None:
            print(f"WARNING: no Natural Earth feature named {ne!r} for region {code}", file=sys.stderr)
            continue
        geom = shape(f["geometry"])
        lat, lon = ANCHOR_OVERRIDES.get(code) or anchor_point(geom)
        table[code] = {"name_en": en, "name_ru": ru, "lat": lat, "lon": lon}
        feats.append(
            {
                "type": "Feature",
                "properties": {"code": code, "name_en": en, "name_ru": ru},
                "geometry": simplified(geom, 0.03),
            }
        )
    for alias, canon in ALIASES.items():
        if canon in table:
            table[alias] = dict(table[canon], alias_of=canon)

    (ROOT / "app/data").mkdir(parents=True, exist_ok=True)
    (ROOT / "app/static/data").mkdir(parents=True, exist_ok=True)
    (ROOT / "app/data/regions.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )
    (ROOT / "app/static/data/regions.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    countries = json.loads(Path(countries_path).read_text(encoding="utf-8"))
    cfeats = []
    for f in countries["features"]:
        p = f["properties"]
        name = p.get("NAME") or p.get("name") or p.get("ADMIN")
        cfeats.append(
            {
                "type": "Feature",
                "properties": {"name": name, "iso_a3": p.get("ADM0_A3") or p.get("adm0_a3")},
                "geometry": simplified(shape(f["geometry"]), 0.05),
            }
        )
    (ROOT / "app/static/data/countries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": cfeats}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"regions: {len(table)} codes, {len(feats)} polygons; countries: {len(cfeats)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

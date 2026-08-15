#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取阿里 DataV GeoAtlas 的 GeoJSON 边界数据，生成 shared/geo-data.js。

产出五份 ECharts registerMap 可用的数据集：
  - china              全国（含各省界，100000_full 原样）
  - yangtzeDelta       长三角（江苏、浙江、安徽、上海 四个省级 feature）
  - yangtzeDeltaCities 长三角地级市（苏13市 + 浙11市 + 皖16市 + 上海整体，properties.prov 标省份）
  - jiangsu            江苏省（13 个地级市，320000_full 原样）
  - jiangsuBlocks      江苏三大板块（苏南 / 苏中 / 苏北，13 市合并）

用法：
  python3 tools/fetch_geo.py            # 抓取远端数据并生成
  python3 tools/fetch_geo.py --cache DIR  # 优先使用 DIR 下缓存的原始 json

依赖：shapely（合并板块用；缺失时自动降级为 13 市 features + block 字段）。
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request

BASE = "https://geo.datav.aliyun.com/areas_v3/bound/geojson?code={code}"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JS = os.path.join(ROOT, "shared", "geo-data.js")

YANGTZE_DELTA = ["江苏省", "浙江省", "安徽省", "上海市"]

BLOCKS = {
    "苏南": ["南京市", "镇江市", "常州市", "无锡市", "苏州市"],
    "苏中": ["扬州市", "泰州市", "南通市"],
    "苏北": ["徐州市", "连云港市", "宿迁市", "淮安市", "盐城市"],
}

KEEP_PROPS = ("name", "adcode", "center", "centroid", "block", "prov")

COORD_PRECISION = 4

# 江苏 13 个设区市的行政区划代码，用于抓各自的县区级边界（jiangsuCounties）
JIANGSU_CITY_CODES = [
    ("南京", 320100), ("无锡", 320200), ("徐州", 320300), ("常州", 320400),
    ("苏州", 320500), ("南通", 320600), ("连云港", 320700), ("淮安", 320800),
    ("盐城", 320900), ("扬州", 321000), ("镇江", 321100), ("泰州", 321200),
    ("宿迁", 321300),
]

# 县区级要素数量大（13 市约 95 个），原始约 650 KB。页面是把 GeoJSON **内联**进 HTML 的，
# 故这里额外做一道拓扑保持的简化；0.0012° 约合 100 m，在 600 px 宽的市域图上不可见。
COUNTY_SIMPLIFY = 0.0012


def fetch(code, cache_dir=None):
    """抓取一份 GeoJSON；cache_dir 中已有同名文件时直接读取。"""
    fname = "{}.json".format(code)
    if cache_dir:
        path = os.path.join(cache_dir, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    url = BASE.format(code=code)
    print("fetching", url)
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, fname), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    return data


def round_coords(obj):
    """递归把坐标数值四舍五入到 4 位小数。"""
    if isinstance(obj, float):
        return round(obj, COORD_PRECISION)
    if isinstance(obj, list):
        return [round_coords(x) for x in obj]
    return obj


def clean_feature(feat):
    """只保留必要 properties，并压缩坐标精度。"""
    props = {k: feat["properties"][k] for k in KEEP_PROPS if k in feat["properties"]}
    return {
        "type": "Feature",
        "properties": round_coords(props),
        "geometry": {
            "type": feat["geometry"]["type"],
            "coordinates": round_coords(feat["geometry"]["coordinates"]),
        },
    }


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def county_kind(name):
    """按名称后缀判层级：市辖区 / 县级市 / 县。页面据此把「市本级及市辖区」合并着色。"""
    if name.endswith("区"):
        return "区"
    if name.endswith("市"):
        return "县级市"
    return "县"


def fetch_counties(cache_dir):
    """13 个设区市各自的县区级边界，合成一个扁平 FeatureCollection，
    每个要素带 city（所属设区市简称）与 kind（区/县级市/县）两个附加属性。"""
    try:
        from shapely.geometry import shape, mapping
        simplify = True
    except ImportError:
        print("WARN: shapely 不可用，jiangsuCounties 不做几何简化（体积约为简化后的 2 倍）", file=sys.stderr)
        simplify = False
    feats = []
    for city, code in JIANGSU_CITY_CODES:
        raw = fetch("%d_full" % code, cache_dir)
        for f in raw["features"]:
            if simplify:
                g = shape(f["geometry"]).simplify(COUNTY_SIMPLIFY, preserve_topology=True)
                f = {"type": "Feature", "properties": f["properties"], "geometry": mapping(g)}
            cf = clean_feature(f)
            cf["properties"]["city"] = city
            cf["properties"]["kind"] = county_kind(cf["properties"]["name"])
            feats.append(cf)
    return fc(feats)


def merge_blocks(jiangsu):
    """把江苏 13 市合并成 苏南/苏中/苏北 三个板块 feature（依赖 shapely）。

    shapely 不可用时返回 None（调用方降级处理）。
    """
    try:
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union
    except ImportError:
        return None

    by_name = {f["properties"]["name"]: f for f in jiangsu["features"]}
    features = []
    for block, cities in BLOCKS.items():
        geoms = []
        for city in cities:
            feat = by_name[city]
            geoms.append(shape(feat["geometry"]).buffer(0))  # buffer(0) 修复无效多边形
        merged = unary_union(geoms)
        merged = merged.simplify(0.001, preserve_topology=True)  # 去除接缝碎片
        # 板块中心点取合并后几何的代表点，供 label / 数据标注用
        centroid = merged.centroid
        features.append({
            "type": "Feature",
            "properties": {
                "name": block,
                "centroid": [round(centroid.x, COORD_PRECISION),
                             round(centroid.y, COORD_PRECISION)],
            },
            "geometry": round_coords(mapping(merged)),
        })
    return fc(features)


def blocks_fallback(jiangsu):
    """降级方案：13 市 features 原样，properties 加 block 字段。"""
    features = []
    city_block = {c: b for b, cities in BLOCKS.items() for c in cities}
    for feat in jiangsu["features"]:
        f2 = json.loads(json.dumps(feat, ensure_ascii=False))
        f2["properties"]["block"] = city_block.get(f2["properties"]["name"], "")
        features.append(f2)
    return fc(features)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=None, help="原始 GeoJSON 缓存目录")
    args = ap.parse_args()

    china_raw = fetch("100000_full", args.cache)
    jiangsu_raw = fetch("320000_full", args.cache)
    zhejiang_raw = fetch("330000_full", args.cache)
    anhui_raw = fetch("340000_full", args.cache)

    china = fc([clean_feature(f) for f in china_raw["features"]])
    yangtze = fc([clean_feature(f) for f in china_raw["features"]
                  if f["properties"]["name"] in YANGTZE_DELTA])
    jiangsu = fc([clean_feature(f) for f in jiangsu_raw["features"]])

    # 长三角地级市：三省地市 + 上海整体（沪为直辖市，市级 = 全市）
    delta_cities = []
    for prov, raw in (("江苏省", jiangsu_raw), ("浙江省", zhejiang_raw), ("安徽省", anhui_raw)):
        for f in raw["features"]:
            cf = clean_feature(f)
            cf["properties"]["prov"] = prov
            delta_cities.append(cf)
    for f in china_raw["features"]:
        if f["properties"]["name"] == "上海市":
            cf = clean_feature(f)
            cf["properties"]["prov"] = "上海市"
            delta_cities.append(cf)
    delta_cities = fc(delta_cities)

    blocks = merge_blocks(jiangsu)
    degraded = blocks is None
    if degraded:
        print("WARN: shapely 不可用，jiangsuBlocks 降级为 13 市 + block 字段", file=sys.stderr)
        blocks = blocks_fallback(jiangsu)

    today = datetime.date.today().isoformat()
    datasets = [
        ("china", china),
        ("yangtzeDelta", yangtze),
        ("yangtzeDeltaCities", delta_cities),
        ("jiangsu", jiangsu),
        ("jiangsuBlocks", blocks),
        ("jiangsuCounties", fetch_counties(args.cache)),
    ]

    os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("/* 自动生成：tools/fetch_geo.py（数据源：阿里 DataV GeoAtlas，抓取日期 %s） */\n" % today)
        f.write("const GEO_DATA = {\n")
        for i, (key, data) in enumerate(datasets):
            comma = "," if i < len(datasets) - 1 else ""
            f.write("  %s: %s%s\n" % (
                key,
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                comma,
            ))
        f.write("};\n")

    size = os.path.getsize(OUT_JS)
    print("written:", OUT_JS, "(%.1f KB)" % (size / 1024))
    for key, data in datasets:
        print("  %-14s features=%d" % (key, len(data["features"])))
    if degraded:
        print("  jiangsuBlocks: 降级方案（13 市 + block 字段）")


if __name__ == "__main__":
    main()

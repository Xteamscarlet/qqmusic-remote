# -*- coding: utf-8 -*-
"""配置加载模块：读取 config.yaml（不存在则回落到 config.example.yaml）。"""
import os

import yaml

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_BASE_DIR, "config.yaml")
EXAMPLE_PATH = os.path.join(_BASE_DIR, "config.example.yaml")


def load_config():
    """加载配置；优先 config.yaml，缺失时退回模板并给出提示。"""
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else EXAMPLE_PATH
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if path == EXAMPLE_PATH:
        print("[提示] 未找到 config.yaml，正在使用模板配置；建议复制 config.example.yaml 为 config.yaml")
    return cfg


def save_config(cfg):
    """把更新后的配置写回 config.yaml（校准向导使用）。"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

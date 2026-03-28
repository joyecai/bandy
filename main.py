#!/usr/bin/env python3
"""Bandy 语音助手 - 入口脚本"""
import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import warnings
warnings.filterwarnings('ignore')

from bandy.output import cleanup_old_output
from bandy.assistant import VoiceAssistant


def main():
    cleanup_old_output()
    VoiceAssistant().start()


if __name__ == "__main__":
    main()

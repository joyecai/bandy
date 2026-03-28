#!/bin/zsh
# Bandy 语音助手 — 权限检查与授权引导
# 运行: chmod +x setup_permissions.sh && ./setup_permissions.sh

set -e

PYTHON="/usr/bin/python3"
PYTHON_APP="/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app"
PYTHON_BID="com.apple.python3"
IMAGESNAP="/opt/homebrew/bin/imagesnap"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo "========================================"
echo "  Bandy 语音助手 — 权限检查"
echo "========================================"
echo ""

# ─── 1. 麦克风权限 ───
echo "${YELLOW}[1/4] 麦克风权限 (Microphone)${NC}"
echo "  所需程序: Python.app ($PYTHON_BID)"
echo "  用途: PyAudio 录音、语音识别"
echo ""
echo "  正在测试麦克风访问..."
MIC_OK=0
$PYTHON -c "
import pyaudio, sys
pa = pyaudio.PyAudio()
try:
    s = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                input=True, frames_per_buffer=480, input_device_index=1)
    s.read(480, exception_on_overflow=False)
    s.stop_stream(); s.close()
    print('  ✅ 麦克风权限正常')
except Exception as e:
    print(f'  ❌ 麦克风访问失败: {e}')
    sys.exit(1)
finally:
    pa.terminate()
" 2>/dev/null && MIC_OK=1

if [ $MIC_OK -eq 0 ]; then
    echo ""
    echo "  ${RED}需要手动授权麦克风:${NC}"
    echo "  系统设置 → 隐私与安全性 → 麦克风 → 开启 Python"
    echo "  正在打开设置页面..."
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
    echo "  授权后按回车继续..."
    read -r
fi

# ─── 2. 摄像头权限 ───
echo ""
echo "${YELLOW}[2/4] 摄像头权限 (Camera)${NC}"
echo "  所需程序: imagesnap"
echo "  用途: 视觉识别抓帧"
echo ""
echo "  正在测试摄像头访问..."
CAM_OK=0
TMPFILE=$(mktemp /tmp/bandy_cam_test.XXXXXX.jpg)
if $IMAGESNAP -w 0.5 "$TMPFILE" 2>/dev/null && [ -s "$TMPFILE" ]; then
    echo "  ${GREEN}✅ 摄像头权限正常${NC}"
    CAM_OK=1
else
    echo "  ${RED}❌ 摄像头访问失败${NC}"
fi
rm -f "$TMPFILE"

if [ $CAM_OK -eq 0 ]; then
    echo ""
    echo "  ${RED}需要手动授权摄像头:${NC}"
    echo "  系统设置 → 隐私与安全性 → 摄像头 → 开启 imagesnap / Terminal"
    echo "  正在打开设置页面..."
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"
    echo "  授权后按回车继续..."
    read -r
fi

# ─── 3. 辅助功能权限 ───
echo ""
echo "${YELLOW}[3/4] 辅助功能 (Accessibility)${NC}"
echo "  所需程序: osascript (通过终端执行)"
echo "  用途: AppleScript 控制应用 (打开/关闭 Insta360 Link Controller)"
echo ""
echo "  正在测试辅助功能..."
ACC_OK=0
if osascript -e 'tell application "System Events" to return name of first process' 2>/dev/null | grep -q .; then
    echo "  ${GREEN}✅ 辅助功能权限正常${NC}"
    ACC_OK=1
else
    echo "  ${RED}❌ 辅助功能访问受限${NC}"
fi

if [ $ACC_OK -eq 0 ]; then
    echo ""
    echo "  ${RED}需要手动授权辅助功能:${NC}"
    echo "  系统设置 → 隐私与安全性 → 辅助功能 → 开启 Terminal / Cursor"
    echo "  正在打开设置页面..."
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    echo "  授权后按回车继续..."
    read -r
fi

# ─── 4. 自动化权限 ───
echo ""
echo "${YELLOW}[4/4] 自动化 (Automation)${NC}"
echo "  用途: osascript 控制其他应用"
echo ""
echo "  正在测试自动化..."
AUTO_OK=0
if osascript -e 'tell application "System Events" to return (count of processes)' 2>/dev/null | grep -qE '[0-9]+'; then
    echo "  ${GREEN}✅ 自动化权限正常${NC}"
    AUTO_OK=1
else
    echo "  ${RED}❌ 自动化权限受限${NC}"
fi

if [ $AUTO_OK -eq 0 ]; then
    echo ""
    echo "  ${RED}需要手动授权:${NC}"
    echo "  系统设置 → 隐私与安全性 → 自动化 → 开启 Terminal → System Events"
    echo "  正在打开设置页面..."
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
    echo "  授权后按回车继续..."
    read -r
fi

# ─── 总结 ───
echo ""
echo "========================================"
echo "  权限检查完成"
echo "========================================"
TOTAL=0
[ $MIC_OK -eq 1 ] && echo "  ${GREEN}✅ 麦克风${NC}" && TOTAL=$((TOTAL+1)) || echo "  ${RED}❌ 麦克风${NC}"
[ $CAM_OK -eq 1 ] && echo "  ${GREEN}✅ 摄像头${NC}" && TOTAL=$((TOTAL+1)) || echo "  ${RED}❌ 摄像头${NC}"
[ $ACC_OK -eq 1 ] && echo "  ${GREEN}✅ 辅助功能${NC}" && TOTAL=$((TOTAL+1)) || echo "  ${RED}❌ 辅助功能${NC}"
[ $AUTO_OK -eq 1 ] && echo "  ${GREEN}✅ 自动化${NC}" && TOTAL=$((TOTAL+1)) || echo "  ${RED}❌ 自动化${NC}"
echo ""
if [ $TOTAL -eq 4 ]; then
    echo "  ${GREEN}所有权限就绪，Bandy 可以正常运行!${NC}"
else
    echo "  ${YELLOW}部分权限未就绪，请按上述步骤授权后重新运行此脚本${NC}"
fi
echo ""

# ─── 确保 LaunchAgent 已注册 ───
echo "检查开机自启动..."
PLIST="$HOME/Library/LaunchAgents/com.openclaw.voiceassistant.plist"
if [ -f "$PLIST" ]; then
    echo "  ${GREEN}✅ LaunchAgent 已配置${NC}: $PLIST"
    if launchctl list | grep -q com.openclaw.voiceassistant; then
        echo "  ${GREEN}✅ 服务已加载运行中${NC}"
    else
        echo "  ${YELLOW}⚠️ 服务未加载，正在加载...${NC}"
        launchctl bootstrap gui/$(id -u) "$PLIST" 2>/dev/null || true
        echo "  已加载"
    fi
else
    echo "  ${RED}❌ LaunchAgent 未配置${NC}"
fi
echo ""

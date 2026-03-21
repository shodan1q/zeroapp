"""Device manager for checking emulators and running Flutter apps."""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

ENV = {**os.environ, "NO_PROXY": "127.0.0.1,localhost"}


async def check_devices() -> dict:
    """Check which emulators/simulators are running."""
    result = {"android": False, "ios": False, "ohos": False,
              "android_device": None, "ios_device": None, "ohos_device": None}

    # Check Android emulator
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", "devices",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().strip().split("\n")[1:]  # skip header
        for line in lines:
            if "device" in line and "offline" not in line:
                result["android"] = True
                result["android_device"] = line.split("\t")[0]
                break
    except Exception:
        pass

    # Check iOS simulator
    try:
        proc = await asyncio.create_subprocess_exec(
            "xcrun", "simctl", "list", "devices", "booted",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        for line in output.split("\n"):
            if "Booted" in line:
                result["ios"] = True
                # Extract device ID from parentheses
                import re
                match = re.search(r'\(([A-F0-9-]+)\)', line)
                if match:
                    result["ios_device"] = match.group(1)
                break
    except Exception:
        pass

    # Check HarmonyOS emulator
    try:
        hdc = "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc"
        proc = await asyncio.create_subprocess_exec(
            hdc, "list", "targets",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        if output and "[Empty]" not in output:
            result["ohos"] = True
            result["ohos_device"] = output.split("\n")[0].strip()
    except Exception:
        pass

    return result


async def run_on_device(app_dir: str, platform: str) -> dict:
    """Build and run a Flutter app on the specified platform's emulator/simulator."""
    from pathlib import Path
    app_path = Path(app_dir)
    if not app_path.exists():
        return {"status": "error", "message": f"目录不存在: {app_dir}"}

    devices = await check_devices()

    if platform == "android":
        if not devices["android"]:
            return {"status": "error", "message": "Android 模拟器未启动。请先启动 Android 模拟器。"}
        device_id = devices["android_device"]

        # Build APK
        proc = await asyncio.create_subprocess_exec(
            "flutter", "build", "apk", "--debug",
            cwd=str(app_path), env=ENV,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return {"status": "error", "message": f"APK 构建失败: {stderr.decode()[-500:]}"}

        # Install and launch
        apk = app_path / "build/app/outputs/flutter-apk/app-debug.apk"
        if not apk.exists():
            return {"status": "error", "message": "APK 文件未找到"}

        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", device_id, "install", "-r", str(apk),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
        )
        await proc.wait()

        # Get package name from app_dir name
        pkg = f"com.autodev.{app_path.name}"
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", device_id, "shell", "am", "start", "-n", f"{pkg}/.MainActivity",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
        )
        await proc.wait()

        return {"status": "success", "message": f"已在 Android 模拟器上启动 ({device_id})"}

    elif platform == "ios":
        if not devices["ios"]:
            return {"status": "error", "message": "iOS 模拟器未启动。请先启动 iOS 模拟器。"}
        device_id = devices["ios_device"]

        # Build for simulator
        proc = await asyncio.create_subprocess_exec(
            "flutter", "build", "ios", "--debug", "--simulator",
            cwd=str(app_path), env=ENV,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return {"status": "error", "message": f"iOS 构建失败: {stderr.decode()[-500:]}"}

        # Install and launch
        runner_app = app_path / "build/ios/iphonesimulator/Runner.app"
        if not runner_app.exists():
            return {"status": "error", "message": "Runner.app 未找到"}

        await asyncio.create_subprocess_exec(
            "xcrun", "simctl", "install", device_id, str(runner_app),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
        )

        bundle_id = f"com.autodev.{app_path.name}"
        # Try common bundle ID patterns
        proc = await asyncio.create_subprocess_exec(
            "xcrun", "simctl", "launch", device_id, bundle_id,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
        )
        await proc.wait()

        return {"status": "success", "message": f"已在 iOS 模拟器上启动 ({device_id})"}

    elif platform == "ohos":
        if not devices["ohos"]:
            return {"status": "error", "message": "HarmonyOS 模拟器未启动。请先通过 DevEco Studio 启动模拟器。"}

        return {"status": "error", "message": "HarmonyOS 运行需要 Flutter OHOS 版本构建，暂未自动化。请手动构建。"}

    return {"status": "error", "message": f"未知平台: {platform}"}

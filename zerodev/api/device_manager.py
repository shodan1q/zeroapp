"""Device manager for checking emulators and running Flutter apps."""

import asyncio
import logging
import os
import re

from zerodev.api.events import emit_stage_change

logger = logging.getLogger(__name__)

ENV = {**os.environ, "NO_PROXY": "127.0.0.1,localhost"}

# Track running builds
_running_builds: dict[str, str] = {}  # app_id -> status


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
        lines = stdout.decode().strip().split("\n")[1:]
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


async def start_run_on_device(app_dir: str, platform: str) -> dict:
    """Check device availability, then launch build in background. Returns immediately."""
    from pathlib import Path
    app_path = Path(app_dir)
    if not app_path.exists():
        return {"status": "error", "message": f"目录不存在: {app_dir}"}

    devices = await check_devices()

    platform_names = {"android": "Android", "ios": "iOS", "ohos": "HarmonyOS"}
    platform_label = platform_names.get(platform, platform)

    if platform == "android" and not devices["android"]:
        return {"status": "error", "message": "Android 模拟器未启动。请先启动 Android 模拟器。"}
    if platform == "ios" and not devices["ios"]:
        return {"status": "error", "message": "iOS 模拟器未启动。请先启动 iOS 模拟器。"}
    if platform == "ohos" and not devices["ohos"]:
        return {"status": "error", "message": "HarmonyOS 模拟器未启动。请先通过 DevEco Studio 启动模拟器。"}
    if platform == "ohos":
        return {"status": "error", "message": "HarmonyOS 运行需要 Flutter OHOS 版本构建，暂未自动化。"}

    build_key = f"{app_path.name}_{platform}"
    if build_key in _running_builds:
        return {"status": "error", "message": f"{platform_label} 构建已在进行中"}

    # Launch build in background
    _running_builds[build_key] = "building"
    asyncio.create_task(_run_build_background(app_path, platform, devices, build_key))

    return {"status": "building", "message": f"已开始 {platform_label} 构建，完成后自动部署。请查看活动日志。"}


async def _run_build_background(app_path, platform: str, devices: dict, build_key: str):
    """Build and deploy in background, emitting events via WebSocket."""
    app_name = app_path.name
    platform_names = {"android": "Android", "ios": "iOS", "ohos": "HarmonyOS"}
    label = platform_names.get(platform, platform)

    try:
        if platform == "android":
            await _build_and_run_android(app_path, devices["android_device"], app_name, label)
        elif platform == "ios":
            await _build_and_run_ios(app_path, devices["ios_device"], app_name, label)
    except Exception as e:
        logger.exception("Build failed for %s on %s", app_name, platform)
        try:
            await emit_stage_change("build", app_name, "failed",
                                    {"message": f"{label} 构建失败: {str(e)[:200]}"})
        except Exception:
            pass
    finally:
        _running_builds.pop(build_key, None)


async def _build_and_run_android(app_path, device_id: str, app_name: str, label: str):
    """Build APK and deploy to Android emulator."""
    try:
        await emit_stage_change("build", app_name, "active",
                                {"message": f"正在构建 {app_name} {label} APK..."})
    except Exception:
        pass

    proc = await asyncio.create_subprocess_exec(
        "flutter", "build", "apk", "--debug",
        cwd=str(app_path), env=ENV,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode()[-300:]
        try:
            await emit_stage_change("build", app_name, "failed",
                                    {"message": f"{label} APK 构建失败: {err}"})
        except Exception:
            pass
        return

    apk = app_path / "build/app/outputs/flutter-apk/app-debug.apk"
    if not apk.exists():
        try:
            await emit_stage_change("build", app_name, "failed",
                                    {"message": f"{label} APK 文件未找到"})
        except Exception:
            pass
        return

    try:
        await emit_stage_change("build", app_name, "active",
                                {"message": f"正在安装到 {label} 模拟器..."})
    except Exception:
        pass

    proc = await asyncio.create_subprocess_exec(
        "adb", "-s", device_id, "install", "-r", str(apk),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
    )
    await proc.wait()

    pkg = f"com.zerodev.{app_name}"
    proc = await asyncio.create_subprocess_exec(
        "adb", "-s", device_id, "shell", "am", "start", "-n", f"{pkg}/.MainActivity",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
    )
    await proc.wait()

    try:
        await emit_stage_change("build", app_name, "completed",
                                {"message": f"{app_name} 已在 {label} 模拟器上启动"})
    except Exception:
        pass


async def _build_and_run_ios(app_path, device_id: str, app_name: str, label: str):
    """Build and deploy to iOS simulator."""
    try:
        await emit_stage_change("build", app_name, "active",
                                {"message": f"正在构建 {app_name} {label}..."})
    except Exception:
        pass

    proc = await asyncio.create_subprocess_exec(
        "flutter", "build", "ios", "--debug", "--simulator",
        cwd=str(app_path), env=ENV,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode()[-300:]
        try:
            await emit_stage_change("build", app_name, "failed",
                                    {"message": f"{label} 构建失败: {err}"})
        except Exception:
            pass
        return

    runner_app = app_path / "build/ios/iphonesimulator/Runner.app"
    if not runner_app.exists():
        try:
            await emit_stage_change("build", app_name, "failed",
                                    {"message": "Runner.app 未找到"})
        except Exception:
            pass
        return

    try:
        await emit_stage_change("build", app_name, "active",
                                {"message": f"正在安装到 {label} 模拟器..."})
    except Exception:
        pass

    await asyncio.create_subprocess_exec(
        "xcrun", "simctl", "install", device_id, str(runner_app),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
    )

    bundle_id = f"com.zerodev.{app_name}"
    proc = await asyncio.create_subprocess_exec(
        "xcrun", "simctl", "launch", device_id, bundle_id,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=ENV,
    )
    await proc.wait()

    try:
        await emit_stage_change("build", app_name, "completed",
                                {"message": f"{app_name} 已在 {label} 模拟器上启动"})
    except Exception:
        pass

"""Tests for ORM model definitions (import check)."""

from zerodev.models.demand import Demand, DemandStatus
from zerodev.models.app_registry import AppRegistry, AppStatus
from zerodev.models.build_log import BuildLog, BuildStep, BuildStatus


def test_demand_status_enum():
    assert DemandStatus.PENDING.value == "pending"
    assert DemandStatus.PUBLISHED.value == "published"


def test_app_status_enum():
    assert AppStatus.DRAFT.value == "draft"
    assert AppStatus.LIVE.value == "live"


def test_build_step_enum():
    assert BuildStep.CODE_GEN.value == "code_gen"
    assert BuildStep.BUILD_APK.value == "build_apk"


def test_build_status_enum():
    assert BuildStatus.SUCCESS.value == "success"
    assert BuildStatus.FAILED.value == "failed"

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BUG-166 回归：golden 基准按渲染环境隔离。

跨平台 golden PNG 字节差曾让 macOS 上的全量回归恒有 4 项失败：Windows 上重建的
基准与 macOS 渲染的同页同框 PNG 只在个别行差几个字节（栅格化舍入随平台与 CPU
架构变化），而基准只存字节数与 sha256。修复后的契约：

- 基准按渲染环境（平台、CPU 架构、PyMuPDF 与 MuPDF 版本）分文件保存；不含
  MuPDF 的旧环境键基准保留不覆盖，仅在平台/架构/PyMuPDF 相同时兼容回退，
  旧版无后缀基准也只作回退；
- 严格检查不变：PNG 尺寸与 sha256 必须相等，条目与 final_bbox 照比；
- 回退到旧版基准且 PNG 字节不一致时，失败信息要指明当前渲染环境与处理办法；
- 基准文件名里的环境标识必须与文件内记录一致；
- 本环境基准比别的环境的基准旧、而当前产物与那份更新的基准几何一致时，提示
  本环境基准可能过期（仍然判失败，不自动放行）；
- --update-golden 只写本环境基准文件，并报告它与其他基准、与上一版本环境基准的差异。
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_extraction_golden as golden  # noqa: E402

ENV_KEY = golden.render_environment_key()
_ENV = golden.render_environment()
OLD_ENV_KEY = f"{_ENV['platform']}-{_ENV['machine']}-pymupdf{_ENV['pymupdf']}"
OTHER_KEY = "other-os-x86_64-pymupdf0.0.0-mupdf0.0.0"
BBOX = [10.0, 20.0, 110.0, 220.0]
BBOX_OLD = [10.0, 20.0, 110.0, 220.0]
BBOX_NEW = [10.0, 20.0, 110.0, 224.0]
PNG = b"\x89PNG\r\n\x1a\n" + b"same-page-same-clip" * 4


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _item(**overrides):
    item = {
        "type": "figure", "id": "1", "page": 1, "continued": False, "file": "Figure_1.png",
        "caption": "Figure 1: sample", "final_bbox": list(BBOX),
        "golden_file_size_bytes": len(PNG), "golden_file_sha256": _sha(PNG),
    }
    item.update(overrides)
    return item


def _golden(items, environment_key=None):
    meta = {"pdf": "paper.pdf", "pages": 1, "preset": "robust"}
    if environment_key is not None:
        meta["render_environment"] = {"key": environment_key}
    return {"version": "2.0", "meta": meta, "items": items}


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class _Rig:
    """临时 tests/results：一份当前产物，加若干批次里的基准。"""

    def __init__(self, tmp_path, monkeypatch):
        self.results = tmp_path / "results"
        self.images_dir = self.results / "20261124-001" / "paper" / "images"
        self.update_batch = self.results / "20261125-001"
        monkeypatch.setattr(golden, "RESULTS_DIR", self.results)
        spec = golden.GoldenSpec("paper.pdf", 1, 0, expected_ids={"figures": {"1"}, "tables": set()})
        monkeypatch.setattr(golden, "CORE_REGRESSION_SET", [spec])
        monkeypatch.setattr(golden, "ensure_extracted_index", lambda *_a, **_k: (True, ""))
        monkeypatch.setattr(golden, "_compute_batch_dir", lambda: self.update_batch)
        monkeypatch.setattr(
            golden, "_resolve_golden_paths",
            lambda _spec: (
                tmp_path / "paper.pdf", self.images_dir, self.images_dir / "index.json",
                golden._find_golden_index("paper") or (self.images_dir / golden.LEGACY_GOLDEN_FILENAME),
            ),
        )

    def current(self, items, png: bytes = PNG) -> None:
        index_items = [{k: v for k, v in it.items() if not k.startswith("golden_")} for it in items]
        _write_json(
            self.images_dir / "index.json",
            {"version": "2.0", "meta": {"pdf": "paper.pdf", "pages": 1}, "items": index_items},
        )
        self.images_dir.mkdir(parents=True, exist_ok=True)
        (self.images_dir / "Figure_1.png").write_bytes(png)

    def baseline(self, batch: str, payload, key=None) -> Path:
        name = golden.LEGACY_GOLDEN_FILENAME if not key else golden.golden_filename_for(key)
        path = self.results / batch / "paper" / "images" / name
        _write_json(path, payload)
        return path

    def run(self, **kwargs):
        return golden.run_golden_tests(**kwargs)


# ---------------------------------------------------------------------------
# 渲染环境标识与基准命名
# ---------------------------------------------------------------------------

def test_render_environment_key_names_platform_arch_and_pymupdf() -> None:
    env = golden.render_environment()
    assert env["platform"] == sys.platform
    assert env["pymupdf"] and env["mupdf"]
    assert golden.render_environment_key(env) == (
        f"{sys.platform}-{env['machine']}-pymupdf{env['pymupdf']}-mupdf{env['mupdf']}"
    )
    assert golden.legacy_render_environment_key(env) == OLD_ENV_KEY
    assert golden.render_environment_key(env) != OLD_ENV_KEY
    assert golden.golden_filename_for("a-b-c") == "golden_index.a-b-c.json"
    assert golden.golden_filename_for("a-b-c") != golden.LEGACY_GOLDEN_FILENAME


# ---------------------------------------------------------------------------
# 基准选择：本环境优先，旧版回退，别的环境不借用
# ---------------------------------------------------------------------------

def test_environment_baseline_is_preferred_over_legacy(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    legacy = rig.baseline("20260101-001", _golden([_item()]))
    env_file = rig.baseline("20260102-001", _golden([_item()], ENV_KEY), key=ENV_KEY)
    # 之后又出现一份更新的旧版基准：本环境基准仍然优先
    newer_legacy = rig.baseline("20260103-001", _golden([_item()]))
    assert golden._find_golden_index("paper") == env_file
    assert legacy.exists() and newer_legacy.exists()


def test_falls_back_to_legacy_baseline_when_environment_has_none(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    legacy = rig.baseline("20260101-001", _golden([_item()]))
    assert golden._find_golden_index("paper") == legacy


def test_pre_mupdf_environment_baseline_remains_compatible(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    old_env = rig.baseline("20260101-001", _golden([_item()], OLD_ENV_KEY), key=OLD_ENV_KEY)
    assert golden._find_golden_index("paper") == old_env
    rig.current([_item()])
    passed, failed, results = rig.run()
    assert (passed, failed) == (1, 0), results[0].messages
    assert not (rig.images_dir / golden.golden_filename_for(ENV_KEY)).exists()


def test_legacy_key_rejects_known_mupdf_conflict(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    data = _golden([_item()], OLD_ENV_KEY)
    data["meta"]["render_environment"]["mupdf"] = "foreign-version"
    rig.baseline("20260101-001", data, key=OLD_ENV_KEY)
    rig.current([_item()])

    passed, failed, results = rig.run()

    assert (passed, failed) == (0, 1)
    assert "mupdf" in results[0].messages[0]


def test_conflicting_legacy_key_falls_through_to_unsuffixed_baseline(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    conflict = _golden([_item()], OLD_ENV_KEY)
    conflict["meta"]["render_environment"]["mupdf"] = "foreign-version"
    conflicting_path = rig.baseline("20260102-001", conflict, key=OLD_ENV_KEY)
    legacy = rig.baseline("20260101-001", _golden([_item()]))
    rig.current([_item()])

    assert golden._find_golden_index("paper") == legacy
    passed, failed, results = rig.run()

    assert (passed, failed) == (1, 0), results[0].messages
    assert conflicting_path.exists()


def test_cached_extraction_requires_matching_render_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(golden, "RESULTS_DIR", tmp_path)
    monkeypatch.delenv(golden.REEXTRACT_ENV, raising=False)

    def create_index(batch):
        directory = tmp_path / batch / "paper" / "images"
        _write_json(directory / "index.json", {"items": []})
        return directory

    local = create_index("20260101-001")
    golden._write_code_fingerprint(local.parent)
    foreign = create_index("20260102-001")
    with monkeypatch.context() as changed:
        changed.setattr(golden, "render_environment", lambda: {**_ENV, "mupdf": "foreign-version"})
        golden._write_code_fingerprint(foreign.parent)
    unknown = create_index("20260103-001")
    _write_json(unknown.parent / golden.FINGERPRINT_FILENAME, {
        "skills_scripts_sha256": golden._current_code_fingerprint(),
    })

    assert golden._find_existing_index("paper") == (local, local / "index.json")
    monkeypatch.setenv(golden.REEXTRACT_ENV, "1")
    assert golden._find_existing_index("paper") is None


def test_other_environment_baseline_is_never_borrowed(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20260101-001", _golden([_item()], OTHER_KEY), key=OTHER_KEY)
    assert golden._find_golden_index("paper") is None
    rig.current([_item()])
    passed, failed, results = rig.run()
    assert (passed, failed) == (0, 1)
    assert "基准缺失" in results[0].messages[0]


def test_variants_list_every_environment_once_with_newest_batch(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    old_env = rig.baseline("20260101-001", _golden([_item()], ENV_KEY), key=ENV_KEY)
    new_env = rig.baseline("20260103-001", _golden([_item()], ENV_KEY), key=ENV_KEY)
    legacy = rig.baseline("20260102-001", _golden([_item()]))
    other = rig.baseline("20260102-002", _golden([_item()], OTHER_KEY), key=OTHER_KEY)
    variants = golden._find_golden_variants("paper")
    assert variants == {"": legacy, ENV_KEY: new_env, OTHER_KEY: other}
    assert old_env.exists()


# ---------------------------------------------------------------------------
# 更新基准：只写本环境文件，旧基准原样保留，并报告差异
# ---------------------------------------------------------------------------

def test_update_golden_writes_environment_file_and_keeps_legacy_untouched(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    legacy = rig.baseline("20261024-006", _golden([_item()]))
    before = legacy.read_bytes()
    rig.current([_item()])

    passed, failed, results = rig.run(update_golden=True)

    assert (passed, failed) == (1, 0), results[0].messages
    written = rig.update_batch / "paper" / "images" / golden.golden_filename_for(ENV_KEY)
    assert written.exists()
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["meta"]["render_environment"]["key"] == ENV_KEY
    assert data["meta"]["render_environment"]["platform"] == sys.platform
    assert data["items"][0]["golden_file_sha256"] == _sha(PNG)
    assert legacy.read_bytes() == before
    assert not (written.parent / golden.LEGACY_GOLDEN_FILENAME).exists()
    assert not golden.golden_is_self_comparison(rig.images_dir / "index.json", written)


def test_update_golden_reports_differences_against_other_and_previous_baselines(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20261024-006", _golden([_item()]))                                  # 旧版：几何相同
    rig.baseline("20261120-001", _golden([_item(final_bbox=BBOX_OLD)], ENV_KEY), key=ENV_KEY)  # 本环境上一版：几何不同
    rig.baseline("20261121-001", _golden([_item()], OTHER_KEY), key=OTHER_KEY)       # 别的环境：几何相同
    rig.current([_item(final_bbox=BBOX_NEW)])

    passed, failed, results = rig.run(update_golden=True)

    assert (passed, failed) == (1, 0)
    text = "\n".join(results[0].messages)
    assert "与旧版基准（批次 20261024-006）对比：条目差异 0、final_bbox 差异 1、PNG 字节差异 0" in text
    assert "与本环境上一版基准（批次 20261120-001）对比：条目差异 0、final_bbox 差异 1、PNG 字节差异 0" in text
    assert f"与 {OTHER_KEY} 环境基准（批次 20261121-001）对比：条目差异 0、final_bbox 差异 1、PNG 字节差异 0" in text


def test_baseline_diff_counts_sub_tolerance_bbox_change_without_failing_comparison() -> None:
    reference = _golden([_item()])
    changed = _golden([_item(final_bbox=[10.0, 20.0, 110.0, 220.1])])
    diff = golden.diff_golden_baselines(reference, changed)
    assert diff["final_bbox"] == 1
    assert golden._compare_bbox(BBOX, [10.0, 20.0, 110.0, 220.1], "") is None


# ---------------------------------------------------------------------------
# 比较：严格检查不变，失败信息可行动
# ---------------------------------------------------------------------------

def test_legacy_baseline_png_mismatch_fails_and_names_the_environment(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    # 模拟另一平台渲染的同页同框 PNG：只差一个字节
    rig.baseline(
        "20261024-006",
        _golden([_item(golden_file_size_bytes=len(PNG) + 1, golden_file_sha256=_sha(PNG + b"\0"))]),
    )
    rig.current([_item()])

    passed, failed, results = rig.run()

    assert (passed, failed) == (0, 1)  # 严格检查不变：换环境不是放宽理由
    text = "\n".join(results[0].messages)
    assert "PNG 尺寸不一致" in text
    assert ENV_KEY in text and "--update-golden" in text


def test_same_environment_png_mismatch_is_a_plain_failure(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20261124-005", _golden([_item(golden_file_sha256=_sha(PNG[:-1] + b"x"))], ENV_KEY), key=ENV_KEY)
    rig.current([_item()])

    passed, failed, results = rig.run()

    assert (passed, failed) == (0, 1)
    text = "\n".join(results[0].messages)
    assert "PNG sha256 不一致" in text
    assert "旧版基准" not in text  # 本环境基准的 PNG 差异是真实变化，不归因于跨环境


def test_geometry_change_fails_against_legacy_baseline_too(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20261024-006", _golden([_item(final_bbox=BBOX_NEW)]))
    rig.current([_item()])  # 当前框位与基准差 4pt

    passed, failed, results = rig.run()

    assert failed == 1
    assert any("final_bbox 偏移超过" in m for m in results[0].messages)


def test_environment_file_with_foreign_recorded_key_is_rejected(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    # 文件名是本环境，文件内却记录着别的环境：基准被改名或混入
    rig.baseline("20261124-005", _golden([_item()], OTHER_KEY), key=ENV_KEY)
    rig.current([_item()])

    passed, failed, results = rig.run()

    assert (passed, failed) == (0, 1)
    assert "渲染环境标识不一致" in results[0].messages[0]


def test_legacy_filename_with_environment_record_is_rejected(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20261124-005", _golden([_item()], OTHER_KEY))
    rig.current([_item()])

    passed, failed, results = rig.run()

    assert (passed, failed) == (0, 1)
    assert "渲染环境标识不一致" in results[0].messages[0]
    assert "旧版无后缀文件名" in results[0].messages[0]


# ---------------------------------------------------------------------------
# 多环境并存：本环境基准过期时给出诊断，但不自动放行
# ---------------------------------------------------------------------------

def test_stale_environment_baseline_is_flagged_when_output_matches_newer_baseline(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20261124-005", _golden([_item(final_bbox=BBOX_OLD)], ENV_KEY), key=ENV_KEY)
    rig.baseline("20261201-002", _golden([_item(final_bbox=BBOX_NEW)], OTHER_KEY), key=OTHER_KEY)
    rig.current([_item(final_bbox=BBOX_NEW)])

    passed, failed, results = rig.run()

    assert failed == 1  # 本环境基准没有更新，仍然判失败
    text = "\n".join(results[0].messages)
    assert "可能过期" in text and "20261201-002" in text


def test_no_stale_hint_when_this_environment_baseline_is_the_newest(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20261201-002", _golden([_item(final_bbox=BBOX_NEW)], ENV_KEY), key=ENV_KEY)
    rig.baseline("20261124-005", _golden([_item(final_bbox=BBOX_OLD)], OTHER_KEY), key=OTHER_KEY)
    rig.current([_item(final_bbox=BBOX_NEW)])

    passed, failed, results = rig.run()

    assert (passed, failed) == (1, 0), results[0].messages


def test_no_stale_hint_when_output_matches_neither_baseline(tmp_path, monkeypatch) -> None:
    rig = _Rig(tmp_path, monkeypatch)
    rig.baseline("20261124-005", _golden([_item(final_bbox=BBOX_OLD)], ENV_KEY), key=ENV_KEY)
    rig.baseline("20261201-002", _golden([_item(final_bbox=BBOX_NEW)], OTHER_KEY), key=OTHER_KEY)
    rig.current([_item(final_bbox=[1.0, 2.0, 3.0, 4.0])])  # 真实回归：与两份基准都不同

    passed, failed, results = rig.run()

    assert failed == 1
    assert "可能过期" not in "\n".join(results[0].messages)

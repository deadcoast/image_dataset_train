"""Package disaster recovery protects originals, resources, and interrupted attempts."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile

import pytest

from image_dataset_train import repair_package as repair


def wheel_at(root, entries):
    wheel = root / "repair.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, raw in entries:
            if isinstance(name, str) and "\\" in name:
                member = zipfile.ZipInfo("placeholder")
                member.filename = name
                name = member
            archive.writestr(name, raw)
    return wheel


@pytest.fixture
def installed(tmp_path, monkeypatch):
    site, home = tmp_path / "site-packages", tmp_path / "app"
    package = site / repair.PACKAGE
    package.mkdir(parents=True)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    return site, package, home


def receipts(home):
    return list((home / "recovery/application").glob("*/repair.json"))


def test_resources_and_python_are_restored_with_verified_originals(installed, tmp_path):
    site, package, home = installed
    expected = {
        "bootstrap.py": b"# restored\n",
        "qa_report.html": b"<html>restored</html>",
        "qa_report.js": b"const restored = true;",
        "trainer-requirements.txt": b"package==1\n",
        "trainer-requirements.in": b"package\n",
        "nested/theme.css": b"body {}",
    }
    for name in list(expected)[:4]:
        (package / name).write_bytes(b"original " + name.encode())
    (package / "unmanaged.txt").write_bytes(b"keep me")
    launcher = site / "trainime.exe"
    launcher.write_bytes(b"running launcher")
    wheel = wheel_at(tmp_path, [(f"{repair.PACKAGE}/{k}", v) for k, v in expected.items()])
    assert repair.restore(wheel, site) == 6
    for name, raw in expected.items():
        assert (package / name).read_bytes() == raw
    assert launcher.read_bytes() == b"running launcher"
    assert (package / "unmanaged.txt").read_bytes() == b"keep me"
    receipt_path = receipts(home)[0]
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "completed" and receipt["restored"] == 6
    assert receipt["wheel_sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    for item in receipt["files"]:
        assert item["status"] == "restored"
        if item["backup"]:
            raw = (receipt_path.parent / item["backup"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == item["before_sha256"]
    journal = [
        json.loads(line)
        for line in (receipt_path.parent / "journal.jsonl").read_text().splitlines()
    ]
    assert sum(row["event"] == "backup_verified" for row in journal) == 4
    assert repair.restore(wheel, site) == 0
    assert receipts(home) == [receipt_path]


@pytest.mark.parametrize(
    "invalid",
    [
        "../escape.py",
        "part/../../escape.py",
        "data:stream",
        "CON.txt",
        "space .txt/../x",
        "bad./x",
        "part//x",
        "part/./x",
        "sub\\escape.py",
    ],
)
def test_invalid_late_member_rejected_before_any_mutation(installed, tmp_path, invalid):
    site, package, home = installed
    (package / "bootstrap.py").write_bytes(b"old")
    wheel = wheel_at(
        tmp_path,
        [(f"{repair.PACKAGE}/bootstrap.py", b"new"), (f"{repair.PACKAGE}/{invalid}", b"invalid")],
    )
    with pytest.raises(ValueError, match="Invalid application"):
        repair.restore(wheel, site)
    assert (package / "bootstrap.py").read_bytes() == b"old"
    assert not home.exists()


def test_case_alias_and_zip_links_are_rejected(installed, tmp_path):
    site, _, home = installed
    for extra in [f"{repair.PACKAGE}/BOOTSTRAP.py", zipfile.ZipInfo(f"{repair.PACKAGE}/linked")]:
        if isinstance(extra, zipfile.ZipInfo):
            extra.create_system = 3
            extra.external_attr = (stat.S_IFLNK | 0o777) << 16
        wheel = wheel_at(tmp_path, [(f"{repair.PACKAGE}/bootstrap.py", b"new"), (extra, b"target")])
        with pytest.raises(ValueError, match="Duplicate|Invalid"):
            repair.restore(wheel, site)
        assert not home.exists()


def test_late_archive_read_failure_cannot_partially_restore(installed, tmp_path, monkeypatch):
    site, package, home = installed
    (package / "bootstrap.py").write_bytes(b"old")
    wheel = wheel_at(
        tmp_path,
        [
            (f"{repair.PACKAGE}/bootstrap.py", b"new"),
            (f"{repair.PACKAGE}/qa_report.js", b"new resource"),
        ],
    )
    read = zipfile.ZipFile.read

    def corrupt(archive, member, *args, **kwargs):
        if member.filename.endswith(".js"):
            raise zipfile.BadZipFile("CRC failure")
        return read(archive, member, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", corrupt)
    with pytest.raises(zipfile.BadZipFile, match="CRC failure"):
        repair.restore(wheel, site)
    assert (package / "bootstrap.py").read_bytes() == b"old"
    assert not home.exists()


def test_failed_backup_or_changed_file_is_never_replaced(installed, tmp_path, monkeypatch):
    site, package, home = installed
    target = package / "bootstrap.py"
    target.write_bytes(b"old")
    wheel = wheel_at(tmp_path, [(f"{repair.PACKAGE}/bootstrap.py", b"new")])
    original = repair._write_backup

    def fail(path, raw):
        raise OSError("disk full")

    monkeypatch.setattr(repair, "_write_backup", fail)
    with pytest.raises(OSError, match="disk full"):
        repair.restore(wheel, site)
    assert target.read_bytes() == b"old"
    assert json.loads(receipts(home)[0].read_text())["status"] == "failed"

    def race(path, raw):
        original(path, raw)
        target.write_bytes(b"newer external edit")

    monkeypatch.setattr(repair, "_write_backup", race)
    with pytest.raises(ValueError, match="changed during backup"):
        repair.restore(wheel, site)
    assert target.read_bytes() == b"newer external edit"
    assert not list(package.glob(".repair-*"))


def test_interrupt_after_replace_retries_without_losing_backup(installed, tmp_path, monkeypatch):
    site, package, home = installed
    target = package / "bootstrap.py"
    target.write_bytes(b"old")
    wheel = wheel_at(
        tmp_path,
        [
            (f"{repair.PACKAGE}/bootstrap.py", b"new"),
            (f"{repair.PACKAGE}/qa_report.js", b"resource"),
        ],
    )
    publish = repair._publish

    def interrupt(*args, **kwargs):
        publish(*args, **kwargs)
        raise KeyboardInterrupt()

    monkeypatch.setattr(repair, "_publish", interrupt)
    with pytest.raises(KeyboardInterrupt):
        repair.restore(wheel, site)
    first = receipts(home)[0]
    assert json.loads(first.read_text())["status"] == "interrupted"
    assert (first.parent / repair.PACKAGE / "bootstrap.py").read_bytes() == b"old"
    assert target.read_bytes() == b"new"
    monkeypatch.setattr(repair, "_publish", publish)
    assert repair.restore(wheel, site) == 1
    assert (package / "qa_report.js").read_bytes() == b"resource"
    assert (first.parent / repair.PACKAGE / "bootstrap.py").read_bytes() == b"old"


def test_missing_target_publication_keeps_a_raced_new_file(installed, tmp_path, monkeypatch):
    site, package, _ = installed
    wheel = wheel_at(tmp_path, [(f"{repair.PACKAGE}/bootstrap.py", b"new")])
    publish = repair._publish

    def race(temporary, target, **kwargs):
        target.write_bytes(b"external file")
        publish(temporary, target, **kwargs)

    monkeypatch.setattr(repair, "_publish", race)
    with pytest.raises(FileExistsError):
        repair.restore(wheel, site)
    assert (package / "bootstrap.py").read_bytes() == b"external file"


def test_blocked_resource_path_is_preflighted(installed, tmp_path):
    site, package, home = installed
    (package / "bootstrap.py").write_bytes(b"old")
    (package / "qa_report.js").mkdir()
    wheel = wheel_at(
        tmp_path,
        [
            (f"{repair.PACKAGE}/bootstrap.py", b"new"),
            (f"{repair.PACKAGE}/qa_report.js", b"new resource"),
        ],
    )
    with pytest.raises(ValueError, match="not a regular file"):
        repair.restore(wheel, site)
    assert (package / "bootstrap.py").read_bytes() == b"old" and not home.exists()


def test_linked_parent_is_preflighted(installed, tmp_path):
    site, package, home = installed
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (package / "nested").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating links requires Windows developer mode or privilege")
    wheel = wheel_at(
        tmp_path,
        [
            (f"{repair.PACKAGE}/bootstrap.py", b"new"),
            (f"{repair.PACKAGE}/nested/resource.js", b"new resource"),
        ],
    )
    with pytest.raises(ValueError, match="Linked"):
        repair.restore(wheel, site)
    assert not list(outside.iterdir()) and not home.exists()


def test_doctor_detects_resources_with_healthy_native_runtime(installed, tmp_path, monkeypatch):
    from image_dataset_train import doctor

    site, package, home = installed
    home.mkdir()
    wheel = wheel_at(
        tmp_path,
        [
            (f"{repair.PACKAGE}/bootstrap.py", b"good"),
            (f"{repair.PACKAGE}/qa_report.js", b"script"),
        ],
    )
    (package / "bootstrap.py").write_bytes(b"good")
    (package / "unowned.txt").write_bytes(b"untouched")
    (home / "install.json").write_text(
        json.dumps(
            {"wheel": str(wheel), "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
        )
    )
    monkeypatch.setattr(doctor, "__file__", str(package / "doctor.py"))
    monkeypatch.setattr(doctor, "runtime_probe", lambda: (True, "native probe passed"))
    checks = doctor.check_all(home)
    assert next(c for c in checks if c.name == "runtime").status == "ok"
    assert next(c for c in checks if c.name == "package").status == "error"
    assert not receipts(home)
    monkeypatch.setattr(doctor, "repair_runtime", lambda _: repair.restore(wheel, site))
    assert doctor._package_check(home, True).status == "fixed"
    assert doctor._package_check(home, False).status == "ok"
    assert (package / "unowned.txt").read_bytes() == b"untouched"


def test_doctor_rejects_tampered_repair_wheel_and_skips_checkout(installed, tmp_path, monkeypatch):
    from image_dataset_train import doctor

    _, package, home = installed
    home.mkdir()
    wheel = wheel_at(tmp_path, [(f"{repair.PACKAGE}/bootstrap.py", b"good")])
    (home / "install.json").write_text(json.dumps({"wheel": str(wheel), "wheel_sha256": "0" * 64}))
    monkeypatch.setattr(doctor, "__file__", str(package / "doctor.py"))
    monkeypatch.setattr(doctor, "repair_runtime", lambda _: pytest.fail("untrusted wheel repair"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        doctor._package_check(home, True)
    monkeypatch.setattr(doctor, "__file__", str(tmp_path / "src/image_dataset_train/doctor.py"))
    result = doctor._package_check(home, True)
    assert result.status == "warning" and "editable" in result.detail


@pytest.mark.parametrize("in_archive", [False, True])
def test_parent_file_conflicts_are_preflighted(installed, tmp_path, in_archive):
    site, package, home = installed
    (package / "bootstrap.py").write_bytes(b"old")
    entries = [
        (f"{repair.PACKAGE}/bootstrap.py", b"new"),
        (f"{repair.PACKAGE}/nested/asset.js", b"resource"),
    ]
    if in_archive:
        entries.append((f"{repair.PACKAGE}/nested", b"file blocking directory"))
    else:
        (package / "nested").write_bytes(b"existing unrelated file")
    wheel = wheel_at(tmp_path, entries)
    with pytest.raises(ValueError, match="directory"):
        repair.restore(wheel, site)
    assert (package / "bootstrap.py").read_bytes() == b"old"
    assert not home.exists()

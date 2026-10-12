from __future__ import annotations

import json

import pytest
from test_terror_fix import collision
from test_trainime import ScriptedTerminal, local_model, snapshot

from image_dataset_train import doctor, terror
from image_dataset_train.diagnostics import diagnose
from image_dataset_train.operations import Item, Result, run_directory
from image_dataset_train.preferences import Preferences
from image_dataset_train.repairs import RepairResult
from image_dataset_train.terror import ErrorRule, FixRule, RepairRegistry
from image_dataset_train.trainime import App, command_text, main


@pytest.fixture
def registry(monkeypatch):
    registry = RepairRegistry()
    registry.errors.update(terror.REGISTRY.errors)
    registry.fixes.update(terror.REGISTRY.fixes)
    monkeypatch.setattr(terror, "REGISTRY", registry)
    calls = []

    def add(number, error_number):
        filename = f"fixture-{number}.marker"

        def detect(source, home):
            path = source / filename
            return path.is_file() and path.read_text() == "broken"

        def apply(source, home, *, dryrun, progress):
            calls.append((number, dryrun))
            if not dryrun:
                (source / filename).write_text("fixed")
            return RepairResult(
                actions=[{"description": f"Repair fixture {number}"}],
                metrics={"fixtures repaired": int(not dryrun)},
            )

        registry.register(
            FixRule(number, f"Repair fixture {number}.", detect, apply),
            ErrorRule(error_number, f"Fixture {error_number} needs repair.", (number,)),
        )

    add(2, 20)
    add(10, 2)  # Error and fix IDs are separate; never derive one by swapping prefixes.
    return registry, calls


@pytest.mark.parametrize("selector", [1, "1", "001", "tf1", "TF001", "te1", "TE001"])
def test_numeric_and_prefixed_selectors_normalize(selector, registry):
    assert terror.normalize_selector(selector) == "tf001"


def test_selection_is_numeric_deduplicated_and_resolves_error_mapping(registry):
    registry, _ = registry
    assert [r.number for r in registry.select(["10,2", "tf002", "te002"])] == [2, 10]
    assert terror.normalize_selector("te002") == "tf010"
    assert [r.number for r in registry.select(True)] == [1, 2, 10]
    assert terror.normalize_selector(True) == "all"
    assert terror.normalize_selector(["2", "all"]) == "all"
    assert terror.normalize_selector("2, all ") == "all"


def test_error_can_map_to_multiple_fixes_and_ids_are_not_limited_to_three_digits(registry):
    registry, _ = registry
    registry.register(
        FixRule(1000, "Test registration.", lambda *a: False, lambda *a: None),
        ErrorRule(30, "Two registered repairs needed.", (2, 10)),
    )
    assert [r.number for r in registry.select("1000,te030")] == [2, 10, 1000]
    assert terror.normalize_selector("te030") == "tf002,tf010"
    assert diagnose("[te030] fixture").fix_code == "tf002,tf010"


def test_registration_rejects_missing_handlers_without_partial_registration(registry):
    registry, _ = registry
    with pytest.raises(ValueError, match="unregistered fix"):
        registry.register(
            FixRule(3, "Invalid mapping.", lambda *a: False, lambda *a: None),
            ErrorRule(3, "Invalid mapping.", (99,)),
        )
    assert 3 not in registry.fixes and 3 not in registry.errors


@pytest.mark.parametrize("selector", ["0", "-1", "tf000", "te999", "999", "one", "1,,2"])
def test_invalid_or_unregistered_codes_are_rejected(selector, registry):
    with pytest.raises(ValueError):
        terror.normalize_selector(selector)


def test_all_dispatches_multiple_detected_handlers_and_skips_unmatched(tmp_path, registry):
    source, home = collision(tmp_path)
    (source / "fixture-2.marker").write_text("broken")
    result = run_directory("fix", source, home, fix=True)
    assert result.exit_code == 0
    assert [r.fix_code for r in result.repairs.runs] == ["tf001", "tf002"]
    assert registry[1] == [(2, False)]
    assert (source / "fixture-2.marker").read_text() == "fixed"
    assert not run_directory("fix", source, home, fix=True).repairs.runs


def test_explicit_code_does_not_run_other_detected_fixes(tmp_path, registry):
    source, home = collision(tmp_path)
    (source / "fixture-2.marker").write_text("broken")
    (source / "fixture-10.marker").write_text("broken")
    before = snapshot(source)
    result = run_directory("fix", source, home, fix="te002")
    assert result.exit_code == 0
    assert [r.fix_code for r in result.repairs.runs] == ["tf010"]
    assert registry[1] == [(10, False)]
    assert (source / "fixture-2.marker").read_text() == "broken"
    assert snapshot(source)["arbitrary_42.jpg"] == before["arbitrary_42.jpg"]


def test_all_selection_validation_precedes_any_handler_or_write(tmp_path, registry):
    source, home = collision(tmp_path)
    (source / "fixture-2.marker").write_text("broken")
    before = snapshot(source)
    with pytest.raises(ValueError, match="Unknown fix"):
        run_directory("fix", source, home, fix="2,999")
    assert not registry[1] and snapshot(source) == before and not home.exists()


@pytest.mark.parametrize(
    "arguments", [["--fix"], ["--fix", "all"], ["--fix", "2,10"], ["--fix", "2", "--fix", "10"]]
)
def test_cli_accepts_multiple_registered_handlers_without_parser_edits(
    tmp_path, monkeypatch, registry, arguments, capsys
):
    source, home = tmp_path / "images", tmp_path / "app"
    source.mkdir()
    for n in (2, 10):
        (source / f"fixture-{n}.marker").write_text("broken")
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert main(["fix", str(source), *arguments]) == 0
    assert registry[1] == [(2, False), (10, False)]
    output = capsys.readouterr().out
    assert "[tf002]" in output and "[tf010]" in output and "[tf001]" not in output


def test_bare_fix_does_not_swallow_following_subcommand_or_path(tmp_path, monkeypatch):
    source, home = collision(tmp_path)
    local_model(home)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    assert main(["--fix", "tag", str(source), "--dryrun"]) == 0
    assert main(["tag", "--fix", str(source), "--dryrun"]) == 0


@pytest.mark.parametrize("code", ["0", "-1", "999", "tf999", "1,,2"])
def test_cli_rejects_invalid_selection_before_changes(tmp_path, monkeypatch, code):
    source, home = collision(tmp_path)
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    before = snapshot(source)
    with pytest.raises(SystemExit) as exc:
        main(["fix", str(source), "--fix", code])
    assert exc.value.code == 2
    assert snapshot(source) == before and not home.exists()


def test_argument_normalization_preserves_literal_paths_after_terminator():
    assert terror.normalize_fix_argv(["fix", "--", "--fix"]) == ["fix", "--", "--fix"]


def test_doctor_uses_registry_and_honors_multiple_codes_and_dryrun(
    tmp_path, monkeypatch, registry, capsys
):
    source, home = tmp_path / "images", tmp_path / "app"
    source.mkdir()
    for n in (2, 10):
        (source / f"fixture-{n}.marker").write_text("broken")
    monkeypatch.setenv("TRAINIME_HOME", str(home))
    before = snapshot(source)
    args = ["doctor", "--path", str(source), "--fix", "2,te002", "--json"]
    assert doctor.main([*args, "--dryrun"]) == 0
    output = capsys.readouterr().out
    assert "[tf002]" in output and "[tf010]" in output
    assert snapshot(source) == before and not home.exists()
    assert doctor.main(args) == 0
    checks = json.loads(capsys.readouterr().out)["checks"]
    assert checks[0]["status"] == "fixed" and "[tf010]" in checks[0]["detail"]


def test_menu_derives_repair_choices_from_registered_errors(tmp_path, registry):
    source, home = tmp_path / "images", tmp_path / "app"
    source.mkdir()
    terminal = ScriptedTerminal(["1", str(source), "", "y", "q"])
    calls = []

    def worker(action, source, home, dryrun, **options):
        calls.append(options)
        items = (
            [] if options else [Item("example.png", "example.txt", "blocked", error_code="te002")]
        )
        return Result(action, source, dryrun, items)

    assert App(Preferences(home), terminal, worker).run() == 0
    assert "Apply tf010? --fix [y/N]: " in terminal.prompts
    assert calls == [{}, {"fix": "tf010"}]


def test_menu_offers_every_pending_fix_from_the_registry(tmp_path, registry):
    source, home = tmp_path / "images", tmp_path / "app"
    source.mkdir()
    terminal = ScriptedTerminal(["1", str(source), "", "y", "q"])
    calls = []

    def worker(action, source, home, dryrun, **options):
        calls.append(options)
        errors = [] if options else ["[tf002,tf010] Interrupted repairs need to finish."]
        return Result(action, source, dryrun, [], errors=errors)

    assert App(Preferences(home), terminal, worker).run() == 0
    assert "Apply tf002,tf010? --fix [y/N]: " in terminal.prompts
    assert calls == [{}, {"fix": "tf002,tf010"}]
    assert diagnose("[tf002,tf010] Interrupted repairs.").fix_code == "tf002,tf010"


def test_unselected_pending_fix_blocks_tagging_until_resumed(tmp_path, registry):
    source, home = tmp_path / "images", tmp_path / "app"
    source.mkdir()
    (source / "fixture-2.marker").write_text("broken")
    registry, calls = registry
    old = registry.fixes[2]
    registry.fixes[2] = FixRule(2, old.description, old.detect, old.apply, old.detect)
    result = run_directory("tag", source, home, fix="10")
    assert result.exit_code == 1 and not calls
    assert "--fix tf002" in result.errors[0]
    assert run_directory("tag", source, home, fix="te020").exit_code == 0
    assert calls == [(2, False)]


def test_commands_keep_all_or_the_actual_selection(tmp_path, registry):
    assert command_text("tag", tmp_path, False, True).endswith(" --fix")
    assert command_text("tag", tmp_path, True, "2,te002").endswith(" --fix tf002,tf010 --dryrun")


def test_dispatch_failure_stops_later_mutations_and_reports_the_actual_code(tmp_path, registry):
    source, home = tmp_path / "images", tmp_path / "app"
    source.mkdir()
    for n in (2, 10):
        (source / f"fixture-{n}.marker").write_text("broken")
    old = registry[0].fixes[2]

    def fail(*args, **kwargs):
        raise OSError("fixture repair failure")

    registry[0].fixes[2] = FixRule(2, old.description, old.detect, fail)
    result = run_directory("fix", source, home, fix="2,10")
    assert result.exit_code == 1 and result.repairs.runs[0].fix_code == "tf002"
    assert "[tf002]" in result.errors[0] and not registry[1]
    assert (source / "fixture-10.marker").read_text() == "broken"

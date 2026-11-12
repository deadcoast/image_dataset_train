"""Keep diagnosis and recovery reachable when optional/native imports fail."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence

from image_dataset_train.diagnostics import EventLog, app_home, failure_text


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if arguments and arguments[0] in {"doctor", "logs"}:
            from image_dataset_train.doctor import main as doctor_main

            return doctor_main(arguments)
        from image_dataset_train.trainime import main as ui_main

        return ui_main(arguments)
    except KeyboardInterrupt:
        print("Cancelled. Completed files and recovery copies are kept.", file=sys.stderr)
        return 130
    except Exception as exc:
        log = EventLog(
            app_home(), enabled=not any(a in {"--dryrun", "--dry-run"} for a in arguments)
        )
        print(failure_text(exc, log, action="startup"), file=sys.stderr)
        return 2


def dataset_main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Receipt navigation remains available when UI/native dependencies cannot load.
    if arguments and arguments[0] == "recovery":
        try:
            from image_dataset_train.recovery_catalog_cli import main as recovery_main

            return recovery_main(arguments[1:])
        except KeyboardInterrupt:
            print("Recovery inspection cancelled; saved evidence is unchanged.", file=sys.stderr)
            return 130
        except Exception as exc:
            if "--json" in arguments:
                print(
                    json.dumps(
                        {
                            "status": "failed",
                            "error": {"type": type(exc).__name__, "message": str(exc)},
                        }
                    )
                )
            else:
                print(
                    f"Recovery navigation unavailable: {exc}. Run trainime doctor --dryrun.",
                    file=sys.stderr,
                )
            return 2
    try:
        from image_dataset_train.cli import main as technical_main

        return technical_main(arguments)
    except KeyboardInterrupt:
        print("Cancelled. Rerun the same stage to resume from verified cache.", file=sys.stderr)
        return 130
    except Exception as exc:
        log = EventLog(
            app_home(), enabled=not any(a in {"--dryrun", "--dry-run"} for a in arguments)
        )
        print(failure_text(exc, log, action="dataset"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

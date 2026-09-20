"""Global options must survive being written before the subcommand.

argparse re-registers a parent's options on each subparser, so the
subparser's defaults overwrite anything parsed ahead of the subcommand
unless those defaults are suppressed.
"""

import pytest

from cme_fedwatch.cli import build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["--json", "next"],
        ["next", "--json"],
        ["--json", "all"],
        ["--json", "history"],
    ],
)
def test_json_is_honoured_on_either_side_of_the_subcommand(argv):
    args = build_parser().parse_args(argv)
    assert getattr(args, "json", False) is True


def test_date_is_honoured_before_the_subcommand():
    args = build_parser().parse_args(["--date", "2026-09-17", "next"])
    assert getattr(args, "date", None) == "2026-09-17"


def test_rate_is_honoured_before_the_subcommand():
    args = build_parser().parse_args(["--rate", "4.33", "all"])
    assert getattr(args, "rate", None) == pytest.approx(4.33)


def test_history_rejects_a_trade_date_it_cannot_honour(capsys):
    # --date is inherited from the shared parent but history walks back from
    # today and never reads it. Accepting it silently implied a filter that
    # was not applied.
    from cme_fedwatch.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["history", "--date", "2026-09-15"])
    assert exc.value.code != 0
    assert "--date" in capsys.readouterr().err


def test_an_unknown_meeting_is_an_error_not_an_empty_success(capsys, offline):
    from cme_fedwatch.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--meeting", "2026-10-29"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "2026-10-29" in err
    assert "2026-10-28" in err

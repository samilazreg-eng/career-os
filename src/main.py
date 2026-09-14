# main.py

import subprocess
import sys
from pathlib import Path

from career import Career
from git import GitError
from workingtree import WorkingTreeError
from error import CareerError, DiagnosticKind
from workspace import WorkspaceError


HELP = """usage: career [-h | --help] <command> [<args>]

These are common Career commands used in various situations:

work on the current change
   add        Add a resource to the current Career position

examine the history and state
   diff       Show changes between HEAD and current resources
   status     Show the current Career repository status

grow the history
   commit     Record staged changes to the Career repository

work on the Career structure
   thread     Start, switch or finish a thread

See 'career <command> -h' for command-specific help.
"""

def _exit_code(kind: DiagnosticKind) -> int:
    match kind:
        case DiagnosticKind.USAGE:
            return 129

        case DiagnosticKind.ERROR:
            return 1

        case DiagnosticKind.FATAL:
            return 128

        case DiagnosticKind.BUG:
            return 128

        case _:
            return 1


def output(result: subprocess.CompletedProcess[str]) -> int:
    """
    @brief Forward a Career command result to the terminal.

    @param result Command execution result.

    @return Native command return code.
    """
    if result.stdout:
        sys.stdout.write(result.stdout)

    if result.stderr:
        sys.stderr.write(result.stderr)

    return result.returncode

def command_init(career: Career, args: list[str]) -> int:
    """
    @brief Execute career init.
    """
    if args == ["-h"] or args == ["--help"]:
        print("usage: career init")
        return 0

    if args:
        print("usage: career init", file=sys.stderr)
        return 129

    return output(career.init())

def command_add(career: Career, args: list[str]) -> int:
    """
    @brief Execute career add.

    @param career Career OS façade.
    @param args Command arguments.

    @return Command exit code.
    """
    if args == ["-h"] or args == ["--help"]:
        print("usage: career add <path>")
        return 0

    if len(args) != 1:
        print("usage: career add <path>", file=sys.stderr)
        return 129

    resource_dir = Path(args[0]).resolve()

    return output(
        career.add(resource_dir)
    )


def command_commit(career: Career, args: list[str]) -> int:
    """
    @brief Execute career commit.

    @param career Career OS façade.
    @param args Command arguments.

    @return Command exit code.
    """
    if args == ["-h"] or args == ["--help"]:
        print("usage: career commit -m <message>")
        return 0

    if len(args) != 2 or args[0] != "-m":
        print(
            "usage: career commit -m <message>",
            file=sys.stderr,
        )
        return 129

    return output(
        career.commit(args[1])
    )


def command_status(career: Career, args: list[str]) -> int:
    """
    @brief Execute career status.
    """
    if args == ["-h"] or args == ["--help"]:
        print("usage: career status")
        return 0

    if args:
        print("usage: career status", file=sys.stderr)
        return 129

    return output(career.status())


def command_diff(career: Career, args: list[str]) -> int:
    """
    @brief Execute career diff.
    """
    if args == ["-h"] or args == ["--help"]:
        print("usage: career diff")
        return 0

    if args:
        print("usage: career diff", file=sys.stderr)
        return 129

    return output(career.diff())


def command_thread(career: Career, args: list[str]) -> int:
    """
    @brief Execute career thread commands.
    """
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: career thread <command> [<args>]\n"
            "\n"
            "Commands:\n"
            "   start <id>     Start a thread\n"
            "   switch <id>    Switch to a thread\n"
            "   finish         Finish the current thread"
        )
        return 0 if args else 129

    command = args[0]
    command_args = args[1:]

    if command == "start":
        if len(command_args) != 1:
            print(
                "usage: career thread start <id>",
                file=sys.stderr,
            )
            return 129

        return output(
            career.start_thread(command_args[0])
        )

    if command == "switch":
        if len(command_args) != 1:
            print(
                "usage: career thread switch <id>",
                file=sys.stderr,
            )
            return 129

        result = career.switch_thread(
            command_args[0]
        )

        return output(result)

    if command == "finish":
        if command_args:
            print(
                "usage: career thread finish",
                file=sys.stderr,
            )
            return 129

        return output(
            career.finish_thread()
        )

    print(
        f"career: '{command}' is not a thread command. "
        "See 'career thread --help'.",
        file=sys.stderr,
    )
    return 1

def command_mission(
    career: Career,
    args: list[str],
) -> int:
    """
    @brief Execute career mission commands.

    @param career Career OS façade.
    @param args Mission command arguments.

    @return Command exit code.
    """
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: career mission <command> [<args>]\n"
            "\n"
            "Commands:\n"
            "   start <id>     Start a new mission\n"
            "   switch <id>    Switch to an existing mission\n"
            "   finish         Finish the current mission"
        )
        return 0 if args else 129

    command = args[0]
    command_args = args[1:]

    if command == "start":
        if len(command_args) != 1:
            print(
                "usage: career mission start <id>",
                file=sys.stderr,
            )
            return 129

        return output(
            career.start_mission(command_args[0])
        )

    if command == "switch":
        if len(command_args) != 1:
            print(
                "usage: career mission switch <id>",
                file=sys.stderr,
            )
            return 129

        return output(
            career.switch_mission(command_args[0])
        )

    if command == "finish":
        if command_args:
            print(
                "usage: career mission finish",
                file=sys.stderr,
            )
            return 129

        return output(
            career.finish_mission()
        )

    print(
        f"career: '{command}' is not a mission command. "
        "See 'career mission --help'.",
        file=sys.stderr,
    )
    return 1

def command_context(
    career: Career,
    args: list[str],
) -> int:
    """
    @brief Execute career context commands.

    @param career Career OS façade.
    @param args Context command arguments.

    @return Command exit code.
    """
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: career context <command> [<args>]\n"
            "\n"
            "Commands:\n"
            "   start <id>     Start a new context\n"
            "   switch <id>    Switch to an existing context\n"
            "   finish         Finish the current context"
        )
        return 0 if args else 129

    command = args[0]
    command_args = args[1:]

    if command == "start":
        if len(command_args) != 1:
            print(
                "usage: career context start <id>",
                file=sys.stderr,
            )
            return 129

        return output(
            career.start_context(command_args[0])
        )

    if command == "switch":
        if len(command_args) != 1:
            print(
                "usage: career context switch <id>",
                file=sys.stderr,
            )
            return 129

        return output(
            career.switch_context(command_args[0])
        )

    if command == "finish":
        if command_args:
            print(
                "usage: career context finish",
                file=sys.stderr,
            )
            return 129

        return output(
            career.finish_context()
        )

    print(
        f"career: '{command}' is not a context command. "
        "See 'career context --help'.",
        file=sys.stderr,
    )
    return 1

def dispatch() -> int:
    """
    @brief Parse command-line arguments and dispatch the requested command.

    @return Command exit code.
    """
    args = sys.argv[1:]

    if not args:
        print(HELP, file=sys.stderr)
        return 1

    if args[0] in ("-h", "--help"):
        print(HELP)
        return 0

    command = args[0]
    command_args = args[1:]

    career = Career()

    if command == "init":
        return command_init(career, command_args)

    if command == "add":
        return command_add(career, command_args)

    if command == "commit":
        return command_commit(career, command_args)

    if command == "status":
        return command_status(career, command_args)

    if command == "diff":
        return command_diff(career, command_args)

    if command == "thread":
        return command_thread(career, command_args)

    if command == "mission":
        return command_mission(career, command_args)

    if command == "context":
        return command_context(career, command_args)

    print(
        f"career: '{command}' is not a career command. "
        "See 'career --help'.",
        file=sys.stderr,
    )

    return 1

def main() -> int:
    """
    @brief Career OS command-line entry point.

    @return Process exit code.
    """
    try:
        return dispatch()

    except CareerError as error:
        print(error, file=sys.stderr)
        return error.returncode

if __name__ == "__main__":
    raise SystemExit(main())
# Shell scripts

- Use the interpreter required by the script. Start with an appropriate shebang and use portable POSIX syntax for `sh`; use Bash features only in scripts executed with Bash.
- Indent consistently with the repository style. Quote variable expansions and command substitutions unless intentional splitting is documented. Use arrays in Bash for argument lists.
- Pass arguments as separate words; avoid `eval` and constructing shell commands from untrusted strings. Use `--` where supported before path operands that may start with `-`.
- Check command failures deliberately. `set -e` is not a substitute for understanding pipelines, conditions, and cleanup; use `pipefail` only in shells that support it.
- Use `mktemp` and `trap` for temporary resources, and clean up on normal exit and signals. Avoid fixed temporary filenames.
- Keep functions small, use local variables where the shell supports them, and send diagnostics to stderr. Make exit codes meaningful.
- Avoid parsing human-oriented output when a stable machine-readable format or direct API exists. Prefer standard tools or document nonportable dependencies.
- Test with the actual interpreter, including paths with spaces, empty input, failure cases, and cleanup. Run `shellcheck` and `shfmt` when configured.

# Login shell setup (sh, Bash).

. "$HOME/.config/shell/env.sh"

if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
  . "$HOME/.bashrc"
fi

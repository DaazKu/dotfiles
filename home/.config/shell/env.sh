# Shared environment for login and interactive Bash and Zsh shells.
# Safe to source more than once.

# path_prepend DIR: move DIR to the front of PATH, once. Skips missing dirs.
path_prepend() {
  [ -d "$1" ] || return 0
  _path=":$PATH:"
  while :; do
    case $_path in
      *":$1:"*) _path="${_path%%":$1:"*}:${_path#*":$1:"}" ;;
      *) break ;;
    esac
  done
  _path=${_path#:}
  _path=${_path%:}
  PATH="$1${_path:+:$_path}"
  export PATH
  unset _path
}

# Homebrew on Apple Silicon is not on the default PATH.
path_prepend /opt/homebrew/sbin
path_prepend /opt/homebrew/bin

# Last, so personal commands (including the gh wrapper) win.
path_prepend "$HOME/bin"
path_prepend "$HOME/.local/bin"

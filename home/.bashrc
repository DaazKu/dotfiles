# Bash setup. Local additions go in ~/.config/bash/conf.d/*.sh.

. "$HOME/.config/shell/env.sh"

# Everything below is for interactive shells only.
case $- in
  *i*) ;;
  *) return ;;
esac

HISTCONTROL=ignoreboth
HISTSIZE=10000
HISTFILESIZE=20000
shopt -s histappend checkwinsize

if ! shopt -oq posix && [ -f /usr/share/bash-completion/bash_completion ]; then
  . /usr/share/bash-completion/bash_completion
fi

. "$HOME/.config/shell/interactive.sh"

for _snippet in "$HOME"/.config/bash/conf.d/*.sh; do
  [ -f "$_snippet" ] && . "$_snippet"
done
unset _snippet

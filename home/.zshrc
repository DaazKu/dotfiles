# Zsh setup. Local additions go in ~/.config/zsh/conf.d/*.zsh.

. "$HOME/.config/shell/env.sh"

if [[ -d /opt/homebrew/share/zsh/site-functions ]]; then
  fpath=(/opt/homebrew/share/zsh/site-functions $fpath)
fi
autoload -Uz compinit && compinit

. "$HOME/.config/shell/interactive.sh"

for _snippet in "$HOME"/.config/zsh/conf.d/*.zsh(N); do
  . "$_snippet"
done
unset _snippet

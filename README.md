# dotfiles

Shell, Git and `gh` configuration for macOS (Zsh) and Ubuntu (Bash).

Everything under `home/` is linked into `$HOME`, one symlink per file. Machine-local settings, identities and tokens live next to those links as ordinary files and are never committed.

## Requirements

- Python 3 (standard library only) to run the installer.
- Git, gh, tmux and herdr for the full setup. `./install` reports which are missing; `./install --packages` installs them.
- macOS: Zsh (the default shell) and [Homebrew](https://brew.sh) for `--packages`.
- Ubuntu: Bash and apt for `--packages`, which uses `sudo` unless run as root.

## Install

```sh
git clone https://github.com/DaazKu/dotfiles.git ~/projects/dotfiles
cd ~/projects/dotfiles
./install --dry-run   # show what would be linked
./install             # link the files and report missing tools
```

The links point into the clone, so keep it where it is. It also creates a starter `~/.gitconfig` if you have none (see [Git](#git)). Open a new shell afterwards.

### Conflicts

`./install` checks every destination before changing anything. If one is already a real file, a directory or a symlink to somewhere else, it lists them all and changes nothing. A fresh Ubuntu user already has `~/.bashrc` and `~/.profile`, for example. Move each conflict aside, copy anything you still want into a local file (see below), and run `./install` again:

```sh
mv ~/.bashrc ~/.bashrc.before-dotfiles
```

Links that already point to the right file are left alone.

### Update

```sh
git pull
./install
```

New files get linked; existing links already follow the clone. If a file is removed from the repository, its link in `$HOME` is left dangling: delete it by hand.

### Tools

```sh
./install --packages            # link, then install or upgrade tools
./install --packages --dry-run  # show the commands only
```

Package managers may also upgrade already-installed tools.

- macOS: `brew install git gh tmux herdr`. Homebrew must already be installed.
- Ubuntu: `apt-get install curl git gh tmux`, then herdr through its [official installer](https://herdr.dev/tui/docs/install/) (`curl -fsSL https://herdr.dev/install.sh | sh`), because apt has no herdr package. It installs to `~/.local/bin`, which these shells put on `PATH`.

An herdr that is already installed is kept, and herdr's configuration is never touched.

## Shells

| File | Loaded by |
| --- | --- |
| `~/.config/shell/env.sh` | every login and interactive shell: `PATH` and the `path_prepend` helper |
| `~/.config/shell/interactive.sh` | interactive shells: shared aliases |
| `~/.profile` | Bash and sh login shells: `env.sh`, then `~/.bashrc` for Bash |
| `~/.bashrc` | Bash: `env.sh`, then for interactive shells history, completion, `interactive.sh` and `~/.config/bash/conf.d/*.sh` |
| `~/.zprofile` | Zsh login shells: `env.sh` |
| `~/.zshrc` | interactive Zsh: `env.sh`, completion, `interactive.sh` and `~/.config/zsh/conf.d/*.zsh` |

`PATH` starts with `~/.local/bin`, then `~/bin`, then Homebrew's directories when present. `path_prepend DIR` moves a directory to the front without duplicating it, so nested and login shells keep a clean `PATH`.

If `~/.bash_profile` or `~/.bash_login` exists, Bash login shells read it instead of `~/.profile`. Merge it into `conf.d` and remove it.

### Local shell additions

Put machine-local settings in `conf.d` snippets. They load in name order after the shared setup, so `path_prepend` and the aliases are available. Examples: [`examples/.config/bash/conf.d/`](examples/.config/bash/conf.d/), [`examples/.config/zsh/conf.d/`](examples/.config/zsh/conf.d/).

```sh
mkdir -p ~/.config/bash/conf.d
cat > ~/.config/bash/conf.d/50-go.sh <<'EOF'
path_prepend "$HOME/go/bin"
EOF
```

## Git

`~/.config/git/config` (linked) holds the shared defaults. `~/.gitconfig` is local: Git reads it afterwards, so it overrides the defaults, and `git config --global` writes there. `./install` creates a starter `~/.gitconfig` with only comments when none exists, and never edits an existing one. If an existing `~/.gitconfig` resolves into this clone, `./install` warns, because `git config --global` would then change repository files; replace it with a local file.

`~/.gitconfig` is also the include manifest. Git includes take explicit file names, not directories, so list each fragment in `~/.config/git/conf.d/`. A listed file that does not exist is ignored.

Identities are local fragments selected by checkout directory with `includeIf "gitdir:..."`. Start from the examples, which use fictional identities:

```sh
mkdir -p ~/.config/git/conf.d
cat examples/.gitconfig >> ~/.gitconfig
cp -n examples/.config/git/conf.d/*.gitconfig ~/.config/git/conf.d/
# Edit the names, emails and directories, then check:
git -C ~/work/some-repo config --show-origin --get user.name
```

Do not set `user.name` or `user.email` with `git config --global`: the value is appended after the includes and overrides every directory identity. Other global writes, such as the credential helper from `gh auth setup-git`, are fine.

## gh tokens

`~/.local/bin/gh` is a small wrapper that runs the next real `gh` on `PATH`:

1. If `GH_TOKEN` or `GITHUB_TOKEN` is set, it is used unchanged.
2. Otherwise the effective Git `user.name` in the current directory is looked up, matching exactly, in `~/.config/gh-wrapper/identities`. A match runs `gh` with `GH_TOKEN` read from that identity's token file.
3. With no identity or no match, `gh` uses its own authentication, including credentials saved by `gh auth login`.

If the mapped token file is missing, unreadable or empty, the wrapper prints a warning and continues as in step 3. It never chooses a token from the repository owner or remote.

```sh
mkdir -p ~/.config/gh-wrapper ~/.config/github-tokens
cp -n examples/.config/gh-wrapper/identities ~/.config/gh-wrapper/
# Edit the user.name values and token paths, then store each token:
(umask 077 && cat > ~/.config/github-tokens/personal)   # paste the token, then Ctrl-D
```

The mapping uses Git's config syntax:

```ini
[identity "alex-example"]
	tokenFile = ~/.config/github-tokens/personal
```

## Diagnostics

```sh
GH_WRAPPER_DEBUG=1 gh auth status
```

prints which `gh` runs, the Git identity, whether the mapping file loaded, and where the token came from, without printing the token. Normal calls print nothing extra.

For Git, `git config --show-origin --get user.name` shows which file set a value.

## Tests

```sh
cd tests && python3 -m unittest -v
```

The tests use throwaway homes, the real Bash, Zsh and Git, and a fake `gh`. Zsh tests are skipped when Zsh is not installed, except in CI. CI runs them on Ubuntu and macOS, then does a real `./install --packages` into a throwaway home.

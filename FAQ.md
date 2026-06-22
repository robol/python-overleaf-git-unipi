# FAQ

## How do I install or update `git-overleaf`?

Run the installer:

```sh
curl https://raw.githubusercontent.com/robol/python-overleaf-git-unipi/refs/heads/main/install.sh | bash
```

You can run the same command again later to update the local installation.

## How do I uninstall `git-overleaf`?

Remove the installation directory:

```sh
rm -rf ~/.local/share/python-overleaf-git-unipi
```

Then edit `~/.profile` and remove the lines added by the installer:

```sh
# Add git-overleaf to PATH.
export PATH="$HOME/.local/share/python-overleaf-git-unipi/bin:$PATH"
```

Open a new shell, or remove the directory from `PATH` in the current shell before continuing.

## What if my `.bash_profile` does not source `.profile`?

The installer adds `git-overleaf` to `PATH` in `~/.profile`. Some Bash login shells read `~/.bash_profile` instead and do not load `~/.profile` automatically.

If `git overleaf` is not found after restarting your shell, add this to `~/.bash_profile`:

```sh
if [ -f ~/.profile ]; then
    . ~/.profile
fi
```

Then open a new shell, or run:

```sh
. ~/.profile
```

## How do I clone an Overleaf project?

Use the project URL from Overleaf:

```sh
git overleaf clone https://overleaf.unipi.it/project/<project-id>
```

To choose the local directory name:

```sh
git overleaf clone https://overleaf.unipi.it/project/<project-id> my-paper
```

## Why do `git overleaf pull` and `git overleaf push` require a clean tree?

The tool synchronizes the local git repository with the Overleaf project. A clean tree avoids mixing local uncommitted changes or untracked files with files coming from Overleaf.

Check the current state with:

```sh
git status
```

Commit or stash changes you want to keep before running:

```sh
git overleaf pull
git overleaf push
```

## How do I remove untracked files before pull or push?

Preview what would be deleted:

```sh
git clean -fdn
```

Then remove untracked files and directories:

```sh
git clean -fd
```

Be careful: `git clean -fd` permanently deletes untracked local files and directories.

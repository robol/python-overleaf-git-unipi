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

Then edit your shell startup file and remove the lines added by the installer. This is normally `~/.zshrc` on macOS, `~/.profile` on Linux with Bash, or `~/.bash_profile` on macOS with Bash:

```sh
# Add git-overleaf to PATH.
export PATH="$HOME/.local/share/python-overleaf-git-unipi/bin:$PATH"
```

Open a new shell, or remove the directory from `PATH` in the current shell before continuing.

## Where does the installer add `git-overleaf` to `PATH`?

The installer uses `~/.zshrc` for Zsh, `~/.bash_profile` for Bash on macOS, and `~/.profile` for Bash on other systems. Set the `PROFILE` environment variable to use a different file.

For example:

```sh
curl https://raw.githubusercontent.com/robol/python-overleaf-git-unipi/refs/heads/main/install.sh |
    PROFILE="$HOME/.profile" bash
```

If you use another shell, add the installation directory to its PATH configuration:

```sh
export PATH="$HOME/.local/share/python-overleaf-git-unipi/bin:$PATH"
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

## What is the relation between this project and python-sharelatex, or overleaf-sync?

This project has been pieced together by a fork of [python-sharelatex](https://gitlab.inria.fr/sed-rennes/sharelatex), 
and [overleaf-sync](https://github.com/moritzgloeckl/overleaf-sync). The latter has been used only for the browser 
login form, to automate the cookie authentication method. The license of this project is GPL-3, which is compatible
with both licenses of these two projects. 
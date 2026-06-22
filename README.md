Python-overleaf-git-unipi is a small project derived from [Python-sharelatex](https://gitlab.inria.fr/sed-rennes/sharelatex).

## Installation

The recommended way to install or update `git-overleaf` is to run the installer directly from GitHub:

```sh
curl https://raw.githubusercontent.com/robol/python-overleaf-git-unipi/refs/heads/main/install.sh | bash
```

The script creates a virtual environment under `~/.local/share/python-overleaf-git-unipi`, installs the package there, and adds `git-overleaf` to your PATH through `~/.profile`.
The script can be run multiple times to update the `git-overleaf` module.

## Quick usage

Clone an Overleaf project by passing its project URL:

```sh
git overleaf clone https://www.overleaf.com/project/<project-id>
```

You can also choose the local directory name:

```sh
git overleaf clone https://www.overleaf.com/project/<project-id> my-paper
```

Inside the cloned project directory, pull changes from Overleaf with:

```sh
git overleaf pull
```

Push committed local changes back to Overleaf with:

```sh
git overleaf push
```

Before running `git overleaf pull` or `git overleaf push`, the git working tree must be clean: there must be no uncommitted changes and no untracked files. Check with:

```sh
git status
```

Commit or stash changes you want to keep before synchronizing. The pull and push commands will
only run with a clean tree, that you can always obtain by running.

```sh
git clean -fd
```

Be careful: `git clean -fd` permanently deletes untracked local files and directories. Run `git clean -fdn` first to preview what would be deleted.

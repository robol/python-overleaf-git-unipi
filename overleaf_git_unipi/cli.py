import datetime
import json
import getpass
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from functools import wraps
from pathlib import Path
from typing import (
    AbstractSet,
    Any,
    Callable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    cast,
)
from zipfile import ZipFile

import click
import keyring
from git import Repo
from git.config import cp

from overleaf_git_unipi import (
    AUTH_DICT,
    OverleafCookieAuthenticator,
    ProjectData,
    SyncClient,
    UpdateDatum,
    get_authenticator_class,
    set_logger,
    walk_folders,
    walk_project_data,
)

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore

URL_MALFORMED_ERROR_MESSAGE = "project_url is not well formed or missing"
URL_SEEMS_TO_BE_ANONYMOUS_URL = """, project_url seems to be an anonymous URL:
 check in a browser to get the true project URL"""
AUTHENTICATION_FAILED = "Unable to authenticate, exiting"

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

set_logger(logger)


class RemoteItem(TypedDict):
    """
    Remote items.
    """

    type: str
    folder_path: str
    name: str
    _id: str
    created: str


class SharelatexError(Exception):
    """
    ShareLaTeX error.
    """

    def info(self) -> str:
        """
        Info.
        """
        return ""


class RepoNotCleanError(SharelatexError):
    """
    The repo is not clean.
    """

    def info(self) -> str:
        """
        the constant is used to check the error in the test
        a better version would be to give the list of files explicitly here
        for now we print the output of `git status` just before raising
        this exception.
        """
        return (
            f"\n---\n{MESSAGE_REPO_ISNT_CLEAN}. "
            "There mustn't be any untracked/uncommitted files here."
        )


def set_log_level(verbose: int = 0) -> None:
    """set log level from integer value"""
    if verbose is None:
        verbose = 0
    log_levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)
    logger.setLevel(log_levels[verbose])


SLATEX_SECTION = "overleaf"
SYNC_BRANCH = "__remote__overleaf_git_unipi__"


def _commit_message(action: str) -> str:
    commit_message_base = "python-overleaf-git-unipi: "
    return commit_message_base + action


COMMIT_MESSAGE_PUSH: str = _commit_message("push")
COMMIT_MESSAGE_CLONE: str = _commit_message("clone")
COMMIT_MESSAGE_PREPULL: str = _commit_message("pre pull")
COMMIT_MESSAGE_UPLOAD: str = _commit_message("upload")
COMMIT_MESSAGES: AbstractSet[str] = frozenset(
    [
        COMMIT_MESSAGE_PUSH,
        COMMIT_MESSAGE_CLONE,
        COMMIT_MESSAGE_PREPULL,
        COMMIT_MESSAGE_UPLOAD,
    ]
)

MESSAGE_REPO_ISNT_CLEAN = "The repo isn't clean"

PROMPT_BASE_URL = "Base url: "
PROMPT_PROJECT_ID = "Project id: "
PROMPT_AUTH_TYPE = """Authentication type
(*cookie*)
"""
DEFAULT_AUTH_TYPE = "cookie"
PROMPT_USERNAME = "Username: "
PROMPT_PASSWORD = "Password: "
PROMPT_CONFIRM = "Do you want to save your password in your OS keyring system (y/n) ?"
PROMPT_COOKIE = "Paste the value of overleaf.sid: "
MAX_NUMBER_ATTEMPTS = 3


class RateLimiter:
    """Ensure not overpass the max_rate events by seconds by sleep an amount
    of time if necessary"""

    def event_inc_passthrough(self) -> None:
        """
        event_inc_passthrough
        """
        self.n_events += 1

    def event_inc(self, wait_interval: float = 0.1) -> None:
        """
        event_inc
        """
        t1 = time.time()
        self.n_events += 1
        while self.n_events / (t1 - self.t0) > self.max_rate:
            time.sleep(wait_interval)
            t1 = time.time()

    def __init__(self, max_rate: float) -> None:
        self.max_rate = max_rate
        self.n_events = 0
        self.t0 = time.time()

        # if self.max_rate <= 0.0:
        #     # TODO: PS -> Is this correct? Assigning method to method?
        #     self.event_inc = self.event_inc_passthrough


class Config:
    """Handle gitconfig read/write operations in a transparent way."""

    def __init__(self, repo: Repo):
        self.repo = repo
        self.keyring = keyring.get_keyring()

    def get_password(self, service: str, username: str) -> Optional[str]:
        """
        get_password
        """
        return cast(Optional[str], self.keyring.get_password(service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        """
        set_password
        """
        self.keyring.set_password(service, username, password)

    def delete_password(self, service: str, username: str) -> None:
        """
        delete_password
        """
        self.keyring.delete_password(service, username)

    def set_value(
        self,
        section: str,
        key: str,
        value: Union[str, bool],
        config_level: str = "repository",
    ) -> None:
        """Set a config value in a specific section.

        Note:
            If the section doesn't exist it is created.

        Args:
            section (str): the section name
            key (str): the key to set
            value (str): the value to set
        """
        with self.repo.config_writer(config_level) as c:
            try:
                c.set_value(section, key, value)
            except cp.NoSectionError as e:
                # No section is found, we create a new one
                logger.debug(e)
                c.set_value(section, "init", "")
            except Exception as e:
                raise e
            finally:
                c.release()

    def get_value(
        self,
        section: str,
        key: str,
        default: Optional[str] = None,
        config_level: Optional[str] = None,
    ) -> Union[int, str, float]:
        """Get a config value in a specific section of the config.

                Note: this returns the associated value if found.
                      Otherwise, it returns the default value.

                Args:
                    section (str): the section name: str
                    key (str): the key to set
                    default (str): the default value to apply
                    config_level (str): the config level to look for
                    see:
        https://gitpython.readthedocs.io/en/stable/reference.html#git.repo.base.Repo.config_level

        """
        with self.repo.config_reader(config_level) as c:
            try:
                value = c.get_value(section, key)
            except cp.NoSectionError as e:
                logger.debug(e)
                value = default
            except cp.NoOptionError as e:
                logger.debug(e)
                value = default
            except Exception as e:
                raise e
            finally:
                return value  # type: ignore


def get_clean_repo(path: Optional[Path] = None) -> Repo:
    """Create the git.repo object from a directory.

    Note:

        This initializes the git repository and fails if the repo isn't clean.
        This is run prior to many operations to make sure there isn't any
        untracked/uncommitted files in the repo.

    Args:
        path (str): the path of the repository in the local file system.

    Returns:
        a git.Repo data-structure.

    Raises:
        Exception if the repo isn't clean
    """
    repo = Repo.init(path=path)
    # Fail if the repo is clean
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True):
        logger.error(repo.git.status())
        raise RepoNotCleanError()
    return repo


def refresh_project_information(
    repo: Repo,
    base_url: Optional[str] = None,
    project_id: Optional[str] = None,
    https_cert_check: Optional[bool] = None,
) -> Tuple[str, str, bool]:
    """Get and/or set the project information in/from the git config.

    If the information is set in the config it is retrieved, otherwise it is set.

    Args:
        repo (git.Repo): The repo object to read the config from
        base_url (str): the base_url to consider
        project_id (str): the project_id to consider
        https_cert_check (bool): Check the cert.
    Returns:
        tuple (base_url, project_id) after the refresh occurs.
    """
    config = Config(repo)
    if base_url is None:
        u = config.get_value(SLATEX_SECTION, "baseUrl")
        if u is not None:
            base_url = cast(str, u)
        else:
            base_url = input(PROMPT_BASE_URL)
            config.set_value(SLATEX_SECTION, "baseUrl", base_url)
    else:
        config.set_value(SLATEX_SECTION, "baseUrl", base_url)
    if project_id is None:
        p = config.get_value(SLATEX_SECTION, "projectId")
        if p is not None:
            project_id = cast(str, p)
        else:
            project_id = input(PROMPT_PROJECT_ID)
        config.set_value(SLATEX_SECTION, "projectId", project_id)
    else:
        config.set_value(SLATEX_SECTION, "projectId", project_id)
    if https_cert_check is None:
        c = cast(bool, config.get_value(SLATEX_SECTION, "httpsCertCheck"))
        if c is not None:
            https_cert_check = c
        else:
            https_cert_check = True
            config.set_value(SLATEX_SECTION, "httpsCertCheck", https_cert_check)
    else:
        config.set_value(SLATEX_SECTION, "httpsCertCheck", https_cert_check)

    return (
        base_url,
        project_id,
        https_cert_check,
    )


def _get_browser_executable() -> Optional[str]:
    for executable in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
        "microsoft-edge",
        "msedge",
        "brave-browser",
        "brave",
    ):
        path = shutil.which(executable)
        if path is not None:
            return path
    return None


def _read_json_url(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_devtools_port(user_data_dir: str) -> int:
    devtools_file = Path(user_data_dir) / "DevToolsActivePort"
    deadline = time.time() + 10

    while time.time() < deadline:
        if devtools_file.is_file():
            lines = devtools_file.read_text().splitlines()
            if lines:
                return int(lines[0])
        time.sleep(0.1)

    raise RuntimeError("Timed out while waiting for the browser debugging port.")


def _get_project_url(base_url: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", "project")


def _is_project_url(base_url: str, current_url: str) -> bool:
    project_url = _get_project_url(base_url)
    normalized_project_url = project_url.rstrip("/")
    normalized_current_url = current_url.rstrip("/")
    return (
        normalized_current_url == normalized_project_url
        or normalized_current_url.startswith(normalized_project_url + "/")
    )


def _get_devtools_page(port: int) -> Tuple[str, str]:
    targets = _read_json_url(f"http://127.0.0.1:{port}/json/list")
    for target in targets:
        if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
            return cast(str, target["webSocketDebuggerUrl"]), cast(str, target["url"])

    raise RuntimeError("Unable to find a browser page to inspect.")


def _get_cookie_from_devtools(port: int, base_url: str) -> Tuple[Optional[str], str]:
    try:
        import websocket
    except ImportError:
        logger.info("Unable to inspect browser cookies: websocket-client is missing.")
        return None, ""

    try:
        ws_url, current_url = _get_devtools_page(port)
        socket = websocket.create_connection(
            ws_url,
            timeout=2,
            suppress_origin=True,
        )
    except Exception as e:
        logger.debug(f"Unable to connect to browser devtools: {e}")
        return None, ""

    try:
        commands = [
            {"id": 1, "method": "Network.enable"},
            {"id": 2, "method": "Network.getAllCookies"},
            {
                "id": 3,
                "method": "Network.getCookies",
                "params": {"urls": [base_url]},
            },
            {"id": 4, "method": "Storage.getCookies"},
        ]
        pending = {command["id"] for command in commands}

        for command in commands:
            socket.send(json.dumps(command))

        while pending:
            message = json.loads(socket.recv())
            message_id = message.get("id")
            if message_id not in pending:
                continue

            pending.remove(message_id)
            if "error" in message:
                logger.debug(f"Browser cookie command failed: {message['error']}")
                continue

            for cookie in message.get("result", {}).get("cookies", []):
                if cookie.get("name") == "overleaf.sid":
                    return cast(str, cookie.get("value")), current_url

        return None, current_url
    except Exception as e:
        logger.debug(f"Unable to read browser cookies from devtools: {e}")
        return None, current_url
    finally:
        socket.close()


def _capture_cookie_from_browser(base_url: str) -> Optional[str]:
    browser = _get_browser_executable()
    if browser is None:
        return None

    with tempfile.TemporaryDirectory(
        prefix="python-overleaf-git-unipi-browser-",
        ignore_cleanup_errors=True,
    ) as user_data:
        try:
            process = subprocess.Popen(
                [
                    browser,
                    "--new-window",
                    "--no-first-run",
                    "--remote-debugging-port=0",
                    "--remote-allow-origins=*",
                    f"--user-data-dir={user_data}",
                    base_url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            logger.debug(f"Unable to launch browser {browser}: {e}")
            return None

        try:
            port = _wait_for_devtools_port(user_data)
            click.echo(
                "Browser window opened. Log in there; waiting for the project page..."
            )
            deadline = time.time() + 180

            while time.time() < deadline:
                cookie, current_url = _get_cookie_from_devtools(port, base_url)
                if cookie and _is_project_url(base_url, current_url):
                    return cookie
                time.sleep(1)
        except Exception as e:
            logger.debug(f"Unable to capture cookie from browser: {e}")
            return None
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    return None


def _prompt_for_cookie(base_url: str) -> str:
    cookie = _capture_cookie_from_browser(base_url)
    if cookie:
        return cookie

    click.echo("Could not capture overleaf.sid from a browser window.")

    return getpass.getpass(PROMPT_COOKIE)


class BrowserCookieAuthenticator(OverleafCookieAuthenticator):
    def authenticate(
        self,
        base_url: str,
        username: str,
        password: str,
        verify: bool = True,
        login_path: str = "/login",
    ) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
        if not password:
            password = _prompt_for_cookie(base_url)
        return super().authenticate(base_url, username, password, verify, login_path)


def refresh_account_information(
    repo: Repo,
    auth_type: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    save_password: Optional[bool] = None,
    ignore_saved_user_info: Optional[bool] = False,
) -> Tuple[str, str, str]:
    """Get and/or set the account information in/from the git config.

    If the information is set in the config it is retrieved, otherwise it is set.
    Note that no further encryption of the password is offered here.

    Args:
        repo (git.Repo): The repo object to read the config from
        username (str): The username to consider
        password (str): The password to consider
        save_password (boolean): True for save user account information (in OS
                                 keyring system) if needed
        ignore_saved_user_info (boolean): True for ignore user account information (in
                                 OS keyring system) if present
    Returns:
        tuple (login_path, username, password) after the refresh occurs.
    """

    config = Config(repo)
    base_url = config.get_value(SLATEX_SECTION, "baseUrl")

    auth_type = "cookie"
    config.set_value(SLATEX_SECTION, "authType", auth_type)

    if username is None:
        username = ""
    config.set_value(SLATEX_SECTION, "username", username)

    if password is None and not ignore_saved_user_info:
        password = config.get_password(base_url, username)  # type: ignore

    if password is None:
        password = ""

    if save_password and password:
        config.set_password(base_url, username, password)  # type: ignore

    return auth_type, username, password


def exit_on_error(
    f: Callable[..., Any], msg: str, clean_up: Optional[Callable[[], None]] = None
) -> Any:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return f(*args, **kwargs)
        except Exception:
            logger.error(msg)
            if clean_up is not None:
                clean_up()
            sys.exit(1)

    return wrapped


def getClient(
    repo: Repo,
    base_url: str,
    auth_type: str,
    username: str,
    password: str,
    verify: bool,
    save_password: Optional[bool] = None,
) -> SyncClient:
    logger.debug(f"try to open session on {base_url} with {username}")
    client = None

    if auth_type == "cookie":
        authenticator = BrowserCookieAuthenticator()
    else:
        authenticator = get_authenticator_class(auth_type)()
    for i in range(MAX_NUMBER_ATTEMPTS):
        try:
            client = SyncClient(
                base_url=base_url,
                username=username,
                password=password,
                verify=verify,
                authenticator=authenticator,
            )
        except Exception as inst:
            client = None
            logger.warning(f"{inst}  : attempt # {i + 1} ")
            auth_type, username, password = refresh_account_information(
                repo,
                auth_type,
                save_password=save_password,
                ignore_saved_user_info=True,
            )
    if client is None:
        raise Exception("maximum number of authentication attempts is reached")
    return client


def update_ref(
    repo: Repo, message: str = "update_ref", git_branch: str = SYNC_BRANCH
) -> None:
    """Makes the remote pointer to point on the latest revision we have.

    This is called after a successful clone, push, new. In short when we
    are sure the remote and the local are in sync.
    """
    git = repo.git

    git.add(".")
    # with this we can have two consecutive commit with the same content
    repo.index.commit(f"{message}")
    sync_branch = repo.create_head(git_branch, force=True)
    sync_branch.commit = "HEAD"


def handle_exception(*exceptions: Type[SharelatexError]) -> Callable:
    """Decorator to handle the cli exceptions.

    Decorated
    """

    def wrapper(f: Any) -> Callable:
        """
        Wrapper.
        """

        @wraps(f)
        def inner(*args: Any, **kwargs: Any) -> Any:
            """
            inner.
            """
            try:
                r = f(*args, **kwargs)
            except exceptions as e:
                print(e.info())
                sys.exit(1)
            return r

        return inner

    return wrapper


@click.group()
def cli() -> None:
    pass


_GIT_BRANCH_OPTION = click.option(
    "--git-branch",
    "-b",
    default=SYNC_BRANCH,
    help=f"The name of a branch. We will commit the changes from Sharelatex "
    f"on this branch.\n\n Default: {SYNC_BRANCH}",
)


def log_options(function: Callable) -> Callable:
    """
    The log options.
    """
    function = click.option("-s", "--silent", "verbose", flag_value=0)(function)
    function = click.option("--debug", "-d", "verbose", flag_value=3)(function)
    function = click.option(
        "-v",
        "--verbose",
        count=True,
        default=2,
        help="verbose level (can be: -v, -vv, -vvv)",
    )(function)
    return function


def authentication_options(function: Callable) -> Callable:
    """
    authentication_options
    """
    function = click.option(
        "--auth_type",
        "-a",
        default=None,
        help="""Authentication type.""",
        type=click.Choice(list(AUTH_DICT.keys())),
    )(function)

    function = click.option(
        "--username",
        "-u",
        default=None,
        help="""Username for sharelatex server account, if username is not provided,
 it will be asked online""",
    )(function)
    function = click.option(
        "--password",
        "-p",
        default=None,
        help="""User password for sharelatex server, if password is not provided,
 it will be asked online""",
    )(function)
    function = click.option(
        "--save-password/--no-save-password",
        default=None,
        help="""Save user account information (in OS keyring system)""",
    )(function)
    function = click.option(
        "--ignore-saved-user-info",
        default=False,
        help="""Forget user account information already saved (in OS keyring system)""",
    )(function)

    return function


@cli.command(help="test log levels")
@log_options
def test(verbose: int) -> None:
    set_log_level(verbose)
    logger.debug("debug")
    logger.info("info")
    logger.error("error")
    logger.warning("warning")
    print("print")


def _sync_deleted_items(
    working_path: Path,
    remote_items: Sequence[RemoteItem],
    objects: Sequence[Path],
) -> None:
    remote_path = [Path(fd["folder_path"]).joinpath(fd["name"]) for fd in remote_items]
    for blob_path in objects:
        p_relative = blob_path.relative_to(working_path)
        # check the path and all of its parents dir
        if p_relative not in remote_path:
            logger.debug(f"delete {blob_path}")
            if blob_path.is_dir():
                blob_path.rmdir()
            else:
                Path.unlink(blob_path)


def _get_datetime_from_git(
    repo: Repo, branch: str, files: Sequence[Path], working_path: Path
) -> Mapping[str, datetime.datetime]:
    datetimes_dict = {}
    for p in files:
        commits = repo.iter_commits(branch)
        p_relative = p.relative_to(working_path)
        if not str(p_relative).startswith(".git"):
            if p not in datetimes_dict:
                for c in commits:
                    re = repo.git.show("--pretty=", "--name-only", c.hexsha)
                    if re != "":
                        commit_file_list = re.split("\n")
                        for cf in commit_file_list:
                            if cf not in datetimes_dict:
                                datetimes_dict[cf] = c.authored_datetime
                        if p in datetimes_dict:
                            break
    return datetimes_dict


def remote_last_update_time(
    update_data: UpdateDatum, relative_path: str, doc_id: str
) -> Optional[int]:
    # iterate over all the updates
    if update_data["updates"]:
        # keep track of all updates
        updates = []
        # check if have a new updates data structure
        if "pathnames" in update_data["updates"][0]:
            for update in update_data["updates"]:
                if relative_path in update["pathnames"]:
                    # the file content has been updated
                    updates.append(update["meta"]["end_ts"])
                else:
                    # creation, removal, rename case
                    for op in update["project_ops"]:
                        for v in op.values():
                            if type(v) is dict:
                                if "pathname" in v:
                                    if relative_path == v["pathname"]:
                                        updates.append(update["meta"]["end_ts"])
        else:
            # FIXME(msimonin): dead code ? (since overleaf 5.2.1 ?)
            updates = [
                update["meta"]["end_ts"]
                for update in update_data["updates"]
                if doc_id in update["docs"]
            ]

    # FIXME(msimonin): can be set to the infinity (or the judgement day)
    remote_time = None
    if len(updates) > 0:
        remote_time = updates[0]
    return remote_time


def _sync_remote(
    client: SyncClient,
    project_id: str,
    working_path: Path,
    remote_items: Sequence[RemoteItem],
    update_data: UpdateDatum,
    datetimes_dict: Mapping[str, datetime.datetime],
) -> None:
    logger.debug("check if remote documents and files are newer that locals")
    remote_time = datetime.datetime.now(datetime.timezone.utc)
    for item in remote_items:
        if "_id" in item:
            item_id = item["_id"]
            need_to_download = False
            local_path = working_path.joinpath(item["folder_path"]).joinpath(
                item["name"]
            )
            relative_path = str(Path(item["folder_path"]).joinpath(item["name"]))
            # compare with local file if any
            if local_path.is_file():
                # first get the date of the last modification of the local file
                relative_path_for_dict = relative_path.replace(os.path.sep, "/")
                if relative_path_for_dict in datetimes_dict:
                    local_time = datetimes_dict[relative_path_for_dict]
                else:
                    local_time = datetime.datetime.fromtimestamp(
                        local_path.stat().st_mtime, datetime.timezone.utc
                    )

                t = remote_last_update_time(update_data, relative_path, item_id)
                if t:
                    logger.debug(f"local time for {local_path} : {local_time}")
                    remote_time = datetime.datetime.fromtimestamp(
                        t / 1000, datetime.timezone.utc
                    )
                    logger.debug(f"remote time for {local_path} : {remote_time}")
                    if local_time < remote_time:
                        need_to_download = True

            # no local file
            else:
                logger.debug(f"local path {local_path} is missing, need to download")
                need_to_download = True
                remote_time = datetime.datetime.now(datetime.timezone.utc)

            if need_to_download:
                logger.info(f"download from server file to update {local_path}")
                if item["type"] == "doc":
                    client.get_document(project_id, item_id, dest_path=str(local_path))
                else:
                    assert item["type"] == "file"
                    client.get_file(project_id, item["_id"], dest_path=str(local_path))
                # Set local time for downloaded document to remote_time
                if local_path.is_file():
                    os.utime(
                        local_path, (remote_time.timestamp(), remote_time.timestamp())
                    )


def _pull(repo: Repo, client: SyncClient, project_id: str, git_branch: str) -> None:
    # attempt to "merge" the remote and the local working copy

    git = repo.git
    active_branch = repo.active_branch.name
    git.checkout(git_branch)
    working_path = Path(repo.working_tree_dir)
    logger.debug("find last commit using remote server")
    # for optimization purpose
    commit = None
    for commit in repo.iter_commits():
        if commit.message in COMMIT_MESSAGES:
            logger.debug(f"find this : {commit.message} -- {commit.hexsha}")
            break
    if commit is None:
        raise Exception(
            "Could not find any commit with a commit message of " + str(COMMIT_MESSAGES)
        )
    logger.debug(
        f"commit as reference for upload updates: {commit.message} -- {commit.hexsha}"
    )
    # mode détaché
    git.checkout(commit)

    try:
        # etat du serveur actuel
        data = client.get_project_data(project_id)
        remote_items = [item for item in walk_project_data(data)]
        # état (supposé) du serveur la dernière fois qu'on s'est synchronisé
        # on ne prend en compte que les fichier trackés par git
        # https://gitpython.readthedocs.io/en/stable/tutorial.html#the-tree-object
        objects = [Path(b.abspath) for b in repo.head.commit.tree.traverse()]
        objects.reverse()

        datetimes_dict = _get_datetime_from_git(repo, git_branch, objects, working_path)

        _sync_deleted_items(working_path, remote_items, objects)

        update_data = client.get_project_update_data(project_id)
        _sync_remote(
            client,
            project_id,
            working_path,
            remote_items,
            update_data,
            datetimes_dict,
        )
        # TODO reset en cas d'erreur ?
        # on se place sur la branche de synchro
        git.checkout(git_branch)
    except Exception as e:
        # hard reset ?
        git.reset("--hard")
        git.checkout(active_branch)
        raise e
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True):
        diff_index = repo.index.diff(None)
        logger.debug(
            f"""Modified files in server :
            {[d.a_path for d in diff_index.iter_change_type("M")]}"""
        )
        logger.debug(
            f"""New files in server :
            {[d.a_path for d in diff_index.iter_change_type("A")]}"""
        )
        logger.debug(
            f"""deleted files in server :
            {[d.a_path for d in diff_index.iter_change_type("D")]}"""
        )
        logger.debug(
            f"""renamed files in server :
            {[d.a_path for d in diff_index.iter_change_type("R")]}"""
        )
        logger.debug(
            f"""Path type changed in server:
            {[d.a_path for d in diff_index.iter_change_type("T")]}"""
        )
        update_ref(repo, message=COMMIT_MESSAGE_PREPULL, git_branch=git_branch)
    git.checkout(active_branch)
    git.merge(git_branch)



@cli.command(
    help=f"""Pull the files from sharelatex.

    In the current repository, it works as follows:

    1. Pull in the latest version of the remote project in ``{SYNC_BRANCH}``
    respectively the given branch.\n
    2. Attempt a merge in the working branch. If the merge can't be done automatically,
       you will be required to fix the conflict manually
    """
)
@_GIT_BRANCH_OPTION
@authentication_options
@log_options
@handle_exception(RepoNotCleanError)
def pull(
    auth_type: str,
    username: Optional[str],
    password: Optional[str],
    save_password: Optional[bool],
    ignore_saved_user_info: bool,
    verbose: int,
    git_branch: str,
) -> None:
    set_log_level(verbose)

    # Fail if the repo is not clean
    repo = get_clean_repo()
    base_url, project_id, https_cert_check = refresh_project_information(repo)
    auth_type, username, password = refresh_account_information(
        repo, auth_type, username, password, save_password, ignore_saved_user_info
    )
    client = exit_on_error(getClient, AUTHENTICATION_FAILED)(
        repo,
        base_url,
        auth_type,
        username,
        password,
        https_cert_check,
        save_password,
    )
    _pull(repo, client, project_id, git_branch=git_branch)


@cli.command()
@click.argument("projet_url", default="")
# , help="The project url (https://sharelatex.irisa.fr/1234567890
#   or https://sharelatex.irisa.fr/1234567890/invite/token/abcd12345 for invitation)")
@click.argument("directory", default="", type=click.Path(file_okay=False))
@click.option(
    "--https-cert-check/--no-https-cert-check",
    default=True,
    help="""force to check https certificate or not""",
)
@click.option(
    "--whole-project-download/--no-whole-project-download",
    default=True,
    help="""download whole project in a zip file from the server/ or download
 sequentially file by file from the server""",
)
@_GIT_BRANCH_OPTION
@authentication_options
@log_options
@handle_exception(RepoNotCleanError)
def clone(
    projet_url: str,
    directory: str,
    auth_type: str,
    username: Optional[str],
    password: Optional[str],
    save_password: Optional[bool],
    ignore_saved_user_info: bool,
    https_cert_check: bool,
    whole_project_download: bool,
    verbose: int,
    git_branch: str,
) -> None:
    f"""Get (clone) the files from an Overleaf project URL and create a local git repository

    The optional target directory will be created if it doesn't exist. The command
    fails if it already exists. Connection information can be saved in the local git
    config.

    The project URL must not be an anonymous project URL:
    Expected project URL format is :
      - http[s]://base_server_address/project/<project_id>
    or for invitation sended by email:
      - http[s]://base_server_address/project/<project_id>/invite/token/<token>

    It works as follow:
        1. join project (if invited)
        2. Download and unzip the remote project in the target directory\n
        3. Initialize a fresh git repository\n
        4. Create an extra ``{SYNC_BRANCH}`` to keep track of the remote versions of
           the project. This branch must not be updated manually.
    """
    set_log_level(verbose)
    s = urllib.parse.urlsplit(projet_url)
    base_url = f"{s.scheme}://{s.netloc}"
    parts = s.path.split("/")
    token = None
    # check if URL is an invitation (received by mail)
    if "invite" in parts:
        try:
            token_idx = parts.index("token")
            token = parts[token_idx + 1]
        except (ValueError, IndexError) as exc:
            raise ValueError(URL_MALFORMED_ERROR_MESSAGE) from exc
    try:
        proj_idx = parts.index("project")
        project_id = parts[proj_idx + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError(
            URL_MALFORMED_ERROR_MESSAGE + URL_SEEMS_TO_BE_ANONYMOUS_URL
        ) from exc
    if base_url == "":
        if "project" not in project_id:
            raise Exception(URL_MALFORMED_ERROR_MESSAGE + URL_SEEMS_TO_BE_ANONYMOUS_URL)
        raise Exception(URL_MALFORMED_ERROR_MESSAGE)
    if directory == "":
        directory_as_path = Path(os.getcwd())
        directory_as_path = Path(directory_as_path, project_id)
    else:
        directory_as_path = Path(directory)
    directory_as_path.mkdir(parents=True, exist_ok=False)

    repo = get_clean_repo(path=directory_as_path)

    base_url, project_id, https_cert_check = refresh_project_information(
        repo, base_url, project_id, https_cert_check
    )
    auth_type, username, password = refresh_account_information(
        repo, auth_type, username, password, save_password, ignore_saved_user_info
    )

    def clean_up() -> None:
        import shutil

        shutil.rmtree(directory_as_path)

    client = exit_on_error(getClient, AUTHENTICATION_FAILED, clean_up)(
        repo,
        base_url,
        auth_type,
        username,
        password,
        https_cert_check,
        save_password,
    )
    if token:
        # join invited project before download
        client.join(project_id, token)

    if whole_project_download:
        client.download_project(project_id, path=str(directory_as_path))
        update_ref(repo, message=COMMIT_MESSAGE_CLONE, git_branch=git_branch)
    else:
        update_ref(repo, message=COMMIT_MESSAGE_CLONE, git_branch=git_branch)
        _pull(repo, client, project_id, git_branch=git_branch)
    # TODO(msimonin): add a decent default .gitignore ?


def _upload(
    repo: Repo, client: SyncClient, project_data: ProjectData, path: str
) -> str:
    # initial factorisation effort
    path_as_path = Path(path)
    logger.debug(f"Uploading {path_as_path}")
    project_id = project_data["_id"]
    folder_id = client.check_or_create_folder(project_data, str(path_as_path.parent))
    p = Path(repo.working_dir).joinpath(path_as_path)
    client.upload_file(project_id, folder_id, str(p))
    return folder_id


def _push(
    force: bool,
    auth_type: str,
    username: Optional[str],
    password: Optional[str],
    save_password: Optional[bool],
    ignore_saved_user_info: bool,
    verbose: int,
    git_branch: str,
) -> None:
    set_log_level(verbose)

    def _delete(c_client: SyncClient, c_project_data: ProjectData, path: str) -> None:
        # initial factorisation effort
        path_as_path = Path(path)
        logger.debug(f"Deleting {path_as_path}")
        project_id = c_project_data["_id"]
        entities = walk_project_data(
            c_project_data,
            lambda x: Path(x["folder_path"]) == path_as_path.parent
            and x["name"] == path_as_path.name,  # noqa: W503
        )
        # there should be one
        entity = next(entities)
        if entity["type"] == "doc":
            c_client.delete_document(project_id, entity["_id"])
        elif entity["type"] == "file":
            c_client.delete_file(project_id, entity["_id"])

    repo = get_clean_repo()
    base_url, project_id, https_cert_check = refresh_project_information(repo)
    auth_type, username, password = refresh_account_information(
        repo, auth_type, username, password, save_password, ignore_saved_user_info
    )

    client = exit_on_error(getClient, AUTHENTICATION_FAILED)(
        repo,
        base_url,
        auth_type,
        username,
        password,
        https_cert_check,
        save_password,
    )

    if not force:
        _pull(repo, client, project_id, git_branch=git_branch)
    config = Config(repo)
    # prevent git returning quoted path in diff when file path has unicode char
    config.set_value("core", "quotepath", "off")
    master_commit = repo.commit("HEAD")
    sync_commit = repo.commit(git_branch)
    diff_index = sync_commit.diff(master_commit)

    project_data = client.get_project_data(project_id)
    folders = {f["folder_id"] for f in walk_folders(project_data)}

    logger.debug("Modify files to upload :")
    for d in diff_index.iter_change_type("M"):
        # iter_change_type("M") can also includes renamed files
        # (in the case the content get modified afterwards)
        # so skipping this special case here as this will be handle later
        if d.change_type == "R":
            continue
        if _upload(repo, client, project_data, d.a_path) not in folders:
            project_data = client.get_project_data(project_id)
            folders = {f["folder_id"] for f in walk_folders(project_data)}

    logger.debug("new files to upload :")
    for d in diff_index.iter_change_type("A"):
        if _upload(repo, client, project_data, d.a_path) not in folders:
            project_data = client.get_project_data(project_id)
            folders = {f["folder_id"] for f in walk_folders(project_data)}

    logger.debug("delete files :")
    for d in diff_index.iter_change_type("D"):
        _delete(client, project_data, d.a_path)

    logger.debug("rename files :")
    for d in diff_index.iter_change_type("R"):
        # git mv a b
        # for us this corresponds to
        # 1) deleting the old one (a)
        # 2) creating the new one (b)
        _delete(client, project_data, d.a_path)
        if _upload(repo, client, project_data, d.b_path) not in folders:
            project_data = client.get_project_data(project_id)
            folders = {f["folder_id"] for f in walk_folders(project_data)}
    logger.debug("Path type changes :")
    for d in diff_index.iter_change_type("T"):
        # This one is maybe
        # 1) deleting the old one (a)
        # 2) creating the new one (b)
        _delete(client, project_data, d.a_path)
        if _upload(repo, client, project_data, d.b_path) not in folders:
            project_data = client.get_project_data(project_id)
            folders = {f["folder_id"] for f in walk_folders(project_data)}
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True):
        update_ref(repo, message=COMMIT_MESSAGE_PUSH, git_branch=git_branch)


@cli.command()
@click.option("--force", is_flag=True, help="Force push", default=False)
@_GIT_BRANCH_OPTION
@click.option("--force", is_flag=True, help="Force push")
@authentication_options
@log_options
@handle_exception(RepoNotCleanError)
def push(
    force: bool,
    auth_type: str,
    username: Optional[str],
    password: Optional[str],
    save_password: Optional[bool],
    ignore_saved_user_info: bool,
    verbose: int,
    git_branch: str,
) -> None:
    """Synchronize the local copy with the remote version.

    This works as follows:

    1. The remote version is pulled (see the :program:`pull` command)\n
    2. After the merge succeed, the merged version is uploaded back to the remote
    server.\n
       Note that only the files that have changed (modified/added/removed) will
       be uploaded.
    """
    _push(
        force,
        auth_type,
        username,
        password,
        save_password,
        ignore_saved_user_info,
        verbose,
        git_branch=git_branch,
    )


@cli.command()
@click.argument("projectname")
@click.argument("base_url")
@click.option(
    "--https-cert-check/--no-https-cert-check",
    default=True,
    help="""force to check https certificate or not""",
)
@click.option(
    "--whole-project-upload/--no-whole-project-upload",
    default=True,
    help="""upload whole project in a zip file to the server/ or
upload sequentially file by file to the server""",
)
@click.option(
    "--rate-max-uploads-by-sec",
    default=0.4,
    help="""number of max uploads
 by seconds to the server (some servers limit the this rate),
 useful with --no-whole-project-upload""",
)
@_GIT_BRANCH_OPTION
@authentication_options
@log_options
@handle_exception(RepoNotCleanError)
def new(
    projectname: str,
    base_url: str,
    https_cert_check: bool,
    whole_project_upload: bool,
    rate_max_uploads_by_sec: float,
    auth_type: str,
    username: Optional[str],
    password: Optional[str],
    save_password: Optional[bool],
    ignore_saved_user_info: bool,
    verbose: int,
    git_branch: str,
) -> None:
    """
    Upload the current directory as a new sharelatex project.

    This literally creates a new remote project in sync with the local version.
    """
    set_log_level(verbose)
    repo = get_clean_repo()

    refresh_project_information(repo, base_url, "NOT SET", https_cert_check)
    auth_type, username, password = refresh_account_information(
        repo, auth_type, username, password, save_password, True
    )
    client = exit_on_error(getClient, AUTHENTICATION_FAILED)(
        repo,
        base_url,
        auth_type,
        username,
        password,
        https_cert_check,
        save_password,
    )

    iter_file = repo.tree().traverse()

    with tempfile.TemporaryDirectory() as tmp:
        archive_name = os.path.join(tmp, f"{projectname}.zip")

        with ZipFile(archive_name, "w") as z:
            for f in iter_file:
                logger.debug(f"Adding {f.path} to the archive {archive_name}")
                z.write(f.path)
                if not whole_project_upload and Path(f.path).is_file():
                    logger.debug("sequential upload, only one file in zip")
                    break
        response = client.upload(archive_name)
        project_id = response["project_id"]
        logger.info(f"Successfully uploaded {projectname} [{project_id}]")
        try:
            refresh_project_information(repo, base_url, project_id, https_cert_check)
            if not whole_project_upload:
                iter_file = repo.tree().traverse()
                project_data = client.get_project_data(project_id)
                upload_rate_limiter = RateLimiter(rate_max_uploads_by_sec)
                folders = {f["folder_id"] for f in walk_folders(project_data)}
                for f in iter_file:
                    if Path(f.path).is_file():
                        if _upload(repo, client, project_data, f.path) not in folders:
                            project_data = client.get_project_data(project_id)
                            folders = {
                                f["folder_id"] for f in walk_folders(project_data)
                            }
                        upload_rate_limiter.event_inc()
            update_ref(repo, message=COMMIT_MESSAGE_UPLOAD, git_branch=git_branch)
        except Exception as inst:
            logger.debug(f"delete failed project {project_id} into server ")
            client.delete(project_id, forever=True)
            raise inst

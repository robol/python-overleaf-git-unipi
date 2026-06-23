##################################################
# MIT License
##################################################
# File: olbrowserlogin.py
# Description: Overleaf Browser Login Utility
# Author: Moritz Glöckl, adapted by Leonardo Robol
# License: MIT
# Version: 1.2.0
##################################################

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtWebEngineWidgets import *
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage

# Where to get the CSRF Token and where to send the login request to
# JS snippet to extract the csrfToken
JAVASCRIPT_CSRF_EXTRACTOR = "document.getElementsByName('ol-csrfToken')[0].content"
# Name of the cookies we want to extract
COOKIE_NAMES = ["overleaf.sid"]

class QuietWebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        ignored = (
            "Error with Permissions-Policy header: Unrecognized feature"
            in message
        )
        if ignored:
            return

        super().javaScriptConsoleMessage(
            level, message, line_number, source_id
        )

class OlBrowserLoginWindow(QMainWindow):
    """
    Overleaf Browser Login Utility
    Opens a browser window to securely login the user and returns relevant login data.
    """

    def __init__(self, base_url, *args, **kwargs):
        super(OlBrowserLoginWindow, self).__init__(*args, **kwargs)

        self.webview = QWebEngineView()
        self._base_url = base_url

        self._cookies = {}
        self._csrf = ""
        self._login_success = False
        self.setWindowTitle("Overleaf Login")

        self.profile = QWebEngineProfile(self.webview)
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.handle_cookie_added)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)

        self.profile.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)

        webpage = QuietWebEnginePage(self.profile, self)
        self.webview.setPage(webpage)
        self.webview.load(QUrl.fromUserInput(self._base_url + "/login"))
        self.webview.loadFinished.connect(self.handle_load_finished)

        self.setCentralWidget(self.webview)
        self.resize(600, 800)

    def handle_load_finished(self):
        def callback(result):
            self._csrf = result
            self._login_success = True
            QCoreApplication.quit()

        if self.webview.url().toString() == (self._base_url + "/project"):
            self.webview.page().runJavaScript(
                JAVASCRIPT_CSRF_EXTRACTOR, 0, callback
            )

    def handle_cookie_added(self, cookie):
        cookie_name = cookie.name().data().decode('utf-8')
        if cookie_name in COOKIE_NAMES:
            self._cookies[cookie_name] = cookie.value().data().decode('utf-8')

    @property
    def cookies(self):
        return self._cookies

    @property
    def csrf(self):
        return self._csrf

    @property
    def login_success(self):
        return self._login_success


def login(base_url):
    from PySide6.QtCore import QLoggingCategory
    QLoggingCategory.setFilterRules('''\
    qt.webenginecontext.info=false
    ''')

    app = QApplication([])
    ol_browser_login_window = OlBrowserLoginWindow(base_url)
    ol_browser_login_window.show()
    app.exec()

    if not ol_browser_login_window.login_success:
        return None

    return {"cookie": ol_browser_login_window.cookies, "csrf": ol_browser_login_window.csrf}


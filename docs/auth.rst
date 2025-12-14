Authentication
==============

By default, ``sharelatex`` relies on the standard authentication method
for its two target APIs:

- https://overleaf.irisa.fr -- with the ``inria`` authentication method
- Overleaf CE (5.2.1) --  with the ``community`` authentication method.

Provided a working account, it should be accessible through the `Command-Line Interface <cli.html>`_.
Launching a command should yield the following interaction:


Connection methods
------------------

.. code-block:: console

    $ git slatex <subcommand>
    Username: ******
    Password: ******
    Do you want to save your password in your OS keyring system (y/n) ? ****

The username must match the one used in the web API, and so should the password in the default case.
To choose which one of the two APIs is to be targetted, a ``-a`` option may be appended to the command,
specifying an option between ``gitlab`` and ``community`` respectively.

.. warning:: There is a known issue for users of the ``gitlab`` interface for their ``inria`` account
    that prevents users from connecting to their account with the default authentication method
    **if they use the the two-factors** ("2FA") **authentication method** for the online INRIA tooling.
    In this precise case, it is advised to avoid the 2FA altogether by using a *cookie* from the
    web interface authentication of ``overleaf.irisa``.

    To use this method:

    - connect online to the `irisa <https://overleaf.irisa.fr>`_ website, using the gitlab 2FA
      authentication method,
    - open the developper tab of your favorite browser (usualy pressing the ``<F12>`` key),
    - find the cookie manager (e.g. in most browsers, this is under the *"storage"* tab, in
      the "cookies" section),
    - find a cookie named ``overleaf.sid``, and copy to your clipboard its *value* field
      (it should look like a long hash starting with ``s%3A``, containing alphanumeric caracters
      and special ones),
    - finaly, attempt to connect with the intended ``slatex`` command, specifying the ``cookie``
      option as the authentication method, and using the value of the cookie as the password.

    .. code-block:: console

        $ # The "cookie" option is the important thing here!
        $ git slatex <subcommand> -a cookie
        Username: ******
        Password: <your cookie goes here>
        Do you want to save your password in your OS keyring system (y/n) ? ****


Persistent sessions and password management
-------------------------------------------

Sessions are persistent and stored in the application directory (details might
differ based on the OS used). Is uses `appdirs
<https://github.com/ActiveState/appdirs>`_ internally.

Passwords are stored in your keyring service (Keychain, Kwallet ...) thanks to
the `keyring <https://pypi.org/project/keyring/>`_ library. Please refer to the
dedicated documentation for more information.

By picking the ``yes`` option when prompted after the username and password interaction,
``slatex`` should leverage those methods to remember your credentials. This includes
the ``cookie`` method.

Python API
----------

Here are some interfaces that are used internally to specify the different options
available under the ``-a`` flag. They may be useful for curious readers who are
interested in contributing other more intricate authentication methods.

.. autoclass:: sharelatex.OverleafGitlabAuthenticator
    :members:
    :undoc-members:
    :show-inheritance:

.. autoclass:: sharelatex.GitlabAuthenticator
    :members:
    :undoc-members:
    :show-inheritance:

.. autoclass:: sharelatex.CommunityAuthenticator
    :members:
    :undoc-members:
    :show-inheritance:

.. autoclass:: sharelatex.OverleafCookieAuthenticator
    :members:
    :undoc-members:
    :show-inheritance:

The classes above derive from this common interface

.. autoclass:: sharelatex.DefaultAuthenticator
    :members:
    :undoc-members:
    :show-inheritance:

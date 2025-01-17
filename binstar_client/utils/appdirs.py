# -*- coding: utf-8 -*-

# pylint: disable=redefined-outer-name,import-outside-toplevel,line-too-long
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring
# Copyright (c) 2005-2010 ActiveState Software Inc.

"""Utilities for determining application-specific dirs.

See <http://github.com/ActiveState/appdirs> for details and usage.
"""
# Dev Notes:
# - MSDN on where to store app data files:
#   http://support.microsoft.com/default.aspx?scid=kb;en-us;310294#XSLTH3194121123120121120120
# - Mac OS X: http://developer.apple.com/documentation/MacOSX/Conceptual/BPFileSystem/index.html
# - XDG spec for Un*x: http://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html

__version_info__ = (1, 2, 0)
__version__ = '.'.join(map(str, __version_info__))


import sys
import os


class AppDirsError(Exception):
    pass


def user_data_dir(appname, appauthor=None, version=None, roaming=False):
    r"""Return full path to the user-specific data dir for this application.

        "appname" is the name of application.
        "appauthor" (only required and used on Windows) is the name of the
            appauthor or distributing body for this application. Typically
            it is the owning company name.
        "version" is an optional version path element to append to the
            path. You might want to use this if you want multiple versions
            of your app to be able to run independently. If used, this
            would typically be "<major>.<minor>".
        "roaming" (boolean, default False) can be set True to use the Windows
            roaming appdata directory. That means that for users on a Windows
            network setup for roaming profiles, this user data will be
            sync'd on login. See
            <http://technet.microsoft.com/en-us/library/cc766489(WS.10).aspx>
            for a discussion of issues.

    Typical user data directories are:
        Mac OS X:               ~/Library/Application Support/<AppName>
        Unix:                   ~/.config/<appname>    # or in $XDG_CONFIG_HOME if defined
        Win XP (not roaming):   C:\Documents and Settings\<username>\Application Data\<AppAuthor>\<AppName>
        Win XP (roaming):
            C:\Documents and Settings\<username>\Local Settings\Application Data\<AppAuthor>\<AppName>
        Win 7  (not roaming):   C:\Users\<username>\AppData\Local\<AppAuthor>\<AppName>
        Win 7  (roaming):       C:\Users\<username>\AppData\Roaming\<AppAuthor>\<AppName>

    For Unix, we follow the XDG spec and support $XDG_CONFIG_HOME. We don't
    use $XDG_DATA_HOME as that data dir is mostly used at the time of
    installation, instead of the application adding data during runtime.
    Also, in practice, Linux apps tend to store their data in
    "~/.config/<appname>" instead of "~/.local/share/<appname>".
    """
    if sys.platform.startswith('win'):
        if appauthor is None:
            raise AppDirsError('must specify \'appauthor\' on Windows')
        const = roaming and 'CSIDL_APPDATA' or 'CSIDL_LOCAL_APPDATA'  # pylint: disable=consider-using-ternary
        path = os.path.join(_get_win_folder(const), appauthor, appname)
    elif sys.platform == 'darwin':
        path = os.path.join(os.path.expanduser('~/Library/Application Support/'), appname)
    else:
        path = os.path.join(os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), appname.lower())
    if version:
        path = os.path.join(path, version)
    return path


def site_data_dir(appname, appauthor=None, version=None):
    """Return full path to the user-shared data dir for this application.

        "appname" is the name of application.
        "appauthor" (only required and used on Windows) is the name of the
            appauthor or distributing body for this application. Typically
            it is the owning company name.
        "version" is an optional version path element to append to the
            path. You might want to use this if you want multiple versions
            of your app to be able to run independently. If used, this
            would typically be "<major>.<minor>".

    Typical user data directories are:
        Mac OS X:   /Library/Application Support/<AppName>
        Unix:       /etc/xdg/<appname>
        Win XP:     C:\\Documents and Settings\\All Users\\Application Data\\<AppAuthor>\\<AppName>
        Vista:      (Fail! "C:\\ProgramData" is a hidden *system* directory on Vista.)
        Win 7:      C:\\ProgramData\\<AppAuthor>\\<AppName>   # Hidden, but writeable on Win 7.

    For Unix, this is using the $XDG_CONFIG_DIRS[0] default.

    WARNING: Do not use this on Windows. See the Vista-Fail note above for why.
    """
    if sys.platform.startswith('win'):
        if appauthor is None:
            raise AppDirsError('must specify \'appauthor\' on Windows')
        path = os.path.join(_get_win_folder('CSIDL_COMMON_APPDATA'), appauthor, appname)
    elif sys.platform == 'darwin':
        path = os.path.join(os.path.expanduser('/Library/Application Support'), appname)
    else:
        # XDG default for $XDG_CONFIG_DIRS[0]. Perhaps should actually *use* that envvar, if defined.
        path = '/etc/xdg/' + appname.lower()
    if version:
        path = os.path.join(path, version)
    return path


def user_cache_dir(appname, appauthor=None, version=None, opinion=True):
    r"""Return full path to the user-specific cache dir for this application.

        "appname" is the name of application.
        "appauthor" (only required and used on Windows) is the name of the
            appauthor or distributing body for this application. Typically
            it is the owning company name.
        "version" is an optional version path element to append to the
            path. You might want to use this if you want multiple versions
            of your app to be able to run independently. If used, this
            would typically be "<major>.<minor>".
        "opinion" (boolean) can be False to disable the appending of
            "Cache" to the base app data dir for Windows. See
            discussion below.

    Typical user cache directories are:
        Mac OS X:   ~/Library/Caches/<AppName>
        Unix:       ~/.cache/<appname> (XDG default)
        Win XP:     C:\Documents and Settings\<username>\Local Settings\Application Data\<AppAuthor>\<AppName>\Cache
        Vista:      C:\Users\<username>\AppData\Local\<AppAuthor>\<AppName>\Cache

    On Windows the only suggestion in the MSDN docs is that local settings go in
    the `CSIDL_LOCAL_APPDATA` directory. This is identical to the non-roaming
    app data dir (the default returned by `user_data_dir` above). Apps typically
    put cache data somewhere *under* the given dir here. Some examples:
        ...\Mozilla\Firefox\Profiles\<ProfileName>\Cache
        ...\Acme\SuperApp\Cache\1.0
    OPINION: This function appends "Cache" to the `CSIDL_LOCAL_APPDATA` value.
    This can be disabled with the `opinion=False` option.
    """
    if sys.platform.startswith('win'):
        if appauthor is None:
            raise AppDirsError('must specify \'appauthor\' on Windows')
        path = os.path.join(_get_win_folder('CSIDL_LOCAL_APPDATA'), appauthor, appname)
        if opinion:
            path = os.path.join(path, 'Cache')
    elif sys.platform == 'darwin':
        path = os.path.join(os.path.expanduser('~/Library/Caches'), appname)
    else:
        path = os.path.join(os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache')), appname.lower())
    if version:
        path = os.path.join(path, version)
    return path


def user_log_dir(appname, appauthor=None, version=None, opinion=True):
    r"""Return full path to the user-specific log dir for this application.

        "appname" is the name of application.
        "appauthor" (only required and used on Windows) is the name of the
            appauthor or distributing body for this application. Typically
            it is the owning company name.
        "version" is an optional version path element to append to the
            path. You might want to use this if you want multiple versions
            of your app to be able to run independently. If used, this
            would typically be "<major>.<minor>".
        "opinion" (boolean) can be False to disable the appending of
            "Logs" to the base app data dir for Windows, and "log" to the
            base cache dir for Unix. See discussion below.

    Typical user cache directories are:
        Mac OS X:   ~/Library/Logs/<AppName>
        Unix:       ~/.cache/<appname>/log  # or under $XDG_CACHE_HOME if defined
        Win XP:     C:\Documents and Settings\<username>\Local Settings\Application Data\<AppAuthor>\<AppName>\Logs
        Vista:      C:\Users\<username>\AppData\Local\<AppAuthor>\<AppName>\Logs

    On Windows the only suggestion in the MSDN docs is that local settings
    go in the `CSIDL_LOCAL_APPDATA` directory. (Note: I'm interested in
    examples of what some windows apps use for a logs dir.)

    OPINION: This function appends "Logs" to the `CSIDL_LOCAL_APPDATA`
    value for Windows and appends "log" to the user cache dir for Unix.
    This can be disabled with the `opinion=False` option.
    """
    if sys.platform == 'darwin':
        path = os.path.join(os.path.expanduser('~/Library/Logs'), appname)
    elif sys.platform == 'win32':
        path = user_data_dir(appname, appauthor, version)
        version = False
        if opinion:
            path = os.path.join(path, 'Logs')
    else:
        path = user_cache_dir(appname, appauthor, version)
        version = False
        if opinion:
            path = os.path.join(path, 'log')
    if version:
        path = os.path.join(path, version)
    return path


class EnvAppDirs:

    def __init__(self, appname, appauthor, root_path):
        self.appname = appname
        self.appauthor = appauthor
        self.root_path = root_path

    @property
    def user_data_dir(self):
        return os.path.join(self.root_path, 'data')

    @property
    def site_data_dir(self):
        return os.path.join(self.root_path, 'data')

    @property
    def user_cache_dir(self):
        return os.path.join(self.root_path, 'cache')

    @property
    def user_log_dir(self):
        return os.path.join(self.root_path, 'log')


class AppDirs:
    """Convenience wrapper for getting application dirs."""

    def __init__(self, appname, appauthor, version=None, roaming=False):
        self.appname = appname
        self.appauthor = appauthor
        self.version = version
        self.roaming = roaming

    @property
    def user_data_dir(self):
        return user_data_dir(self.appname, self.appauthor, version=self.version, roaming=self.roaming)

    @property
    def site_data_dir(self):
        return site_data_dir(self.appname, self.appauthor, version=self.version)

    @property
    def user_cache_dir(self):
        return user_cache_dir(self.appname, self.appauthor, version=self.version)

    @property
    def user_log_dir(self):
        return user_log_dir(self.appname, self.appauthor, version=self.version)


# ---- internal support stuff

def _get_win_folder_from_registry(csidl_name):
    """
    This is a fallback technique at best. I'm not sure if using the registry for this guarantees us the correct answer
    for all CSIDL_* names.
    """
    import _winreg  # pylint: disable=import-error

    shell_folder_name = {
        'CSIDL_APPDATA': 'AppData',
        'CSIDL_COMMON_APPDATA': 'Common AppData',
        'CSIDL_LOCAL_APPDATA': 'Local AppData',
    }[csidl_name]

    key = _winreg.OpenKey(
        _winreg.HKEY_CURRENT_USER,
        r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
    )
    directory, item_type = _winreg.QueryValueEx(key, shell_folder_name)   # pylint: disable=unused-variable
    return directory


def _get_win_folder_with_pywin32(csidl_name):
    from win32com.shell import shellcon, shell  # pylint: disable=import-error
    directory = shell.SHGetFolderPath(0, getattr(shellcon, csidl_name), 0, 0)

    # Try to make this a unicode path because SHGetFolderPath does not return unicode strings when there is unicode data
    # in the path.
    try:
        directory = str(directory)

        # Downgrade to short path name if have highbit chars. See
        # <http://bugs.activestate.com/show_bug.cgi?id=85099>.
        has_high_char = False
        for char in directory:
            if ord(char) > 255:
                has_high_char = True
                break
        if has_high_char:
            try:
                import win32api
                directory = win32api.GetShortPathName(directory)
            except ImportError:
                pass
    except UnicodeError:
        pass
    return directory


def _get_win_folder_with_ctypes(csidl_name):
    import ctypes

    csidl_const = {
        'CSIDL_APPDATA': 26,
        'CSIDL_COMMON_APPDATA': 35,
        'CSIDL_LOCAL_APPDATA': 28,
    }[csidl_name]

    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl_const, None, 0, buf)

    # Downgrade to short path name if have highbit chars. See
    # <http://bugs.activestate.com/show_bug.cgi?id=85099>.
    has_high_char = False
    for char in buf:
        if ord(char) > 255:
            has_high_char = True
            break
    if has_high_char:
        buf2 = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(buf.value, buf2, 1024):
            buf = buf2

    return buf.value


if sys.platform == 'win32':
    try:
        import win32com.shell  # pylint: disable=unused-import
        _get_win_folder = _get_win_folder_with_pywin32
    except ImportError:
        try:
            import ctypes  # pylint: disable=unused-import
            _get_win_folder = _get_win_folder_with_ctypes
        except ImportError:
            _get_win_folder = _get_win_folder_from_registry


# ---- self test code

if __name__ == '__main__':
    APP_NAME = 'MyApp'
    APP_AUTHOR = 'MyCompany'

    props = ('user_data_dir', 'site_data_dir', 'user_cache_dir',
             'user_log_dir')

    print("-- app dirs (without optional 'version')")
    dirs = AppDirs(APP_NAME, APP_AUTHOR, version='1.0')
    for prop in props:
        print('%s: %s' % (prop, getattr(dirs, prop)))

    print("\n-- app dirs (with optional 'version')")
    dirs = AppDirs(APP_NAME, APP_AUTHOR)
    for prop in props:
        print('%s: %s' % (prop, getattr(dirs, prop)))

# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring,line-too-long,

"""

    anaconda upload CONDA_PACKAGE_1.bz2
    anaconda upload notebook.ipynb
    anaconda upload environment.yml

##### See Also

  * [Uploading a Conda Package](
  https://docs.anaconda.com/anaconda-repository/user-guide/tasks/pkgs/use-pkg-managers/#uploading-a-conda-package)
  * [Uploading a Standard Python Package](
  https://docs.anaconda.com/anaconda-repository/user-guide/tasks/pkgs/use-pkg-managers/#uploading-pypi-packages)

"""

from __future__ import unicode_literals

import argparse
import logging
import os
from glob import glob
from os.path import exists

import nbformat
from six.moves import input

from binstar_client import errors
from binstar_client.utils import bool_input, DEFAULT_CONFIG, get_config, get_server_api
from binstar_client.utils.config import PackageType
from binstar_client.utils.detect import detect_package_type, get_attrs
from binstar_client.utils.projects import upload_project

logger = logging.getLogger('binstar.upload')


def verbose_package_type(pkg_type, lowercase=True):
    verbose_type = pkg_type.label()
    if lowercase:
        verbose_type = verbose_type.lower()
    return verbose_type


def create_release(aserver_api, username,  # pylint: disable=too-many-arguments
                   package_name, version, release_attrs, announce=None):
    aserver_api.add_release(username, package_name, version, [], announce, release_attrs)


def create_release_interactive(aserver_api, username, package_name, version, release_attrs):
    logger.info('The release "%s/%s/%s" does not exist', username, package_name, version)

    if not bool_input('Would you like to create it now?'):
        logger.info('good-bye')
        raise SystemExit(-1)

    logger.info('Announcements are emailed to your package followers.')
    make_announcement = bool_input('Would you like to make an announcement to the package followers?', False)

    if make_announcement:
        announce = input('Markdown Announcement:\n')
    else:
        announce = ''

    aserver_api.add_release(username, package_name, version, [], announce, release_attrs)


def determine_package_type(filename, args):
    """
    return the file type from the inspected package or from the
    -t/--package-type argument
    """
    if args.package_type:
        return PackageType(args.package_type)

    logger.info('Detecting file type...')
    package_type = detect_package_type(filename)

    if package_type is None:
        message = 'Could not detect package type of file %r please ' \
                  'specify package type with option --package-type' % filename
        logger.error(message)
        raise errors.BinstarError(message)

    logger.info('File type is "%s"', package_type.label())

    return package_type


def get_package_name(args, package_attrs, package_type):
    if args.package:
        if 'name' in package_attrs:
            good_names = [package_attrs['name'].lower()]
            if package_type == PackageType.STANDARD_PYTHON:
                good_names.append(good_names[0].replace('-', '_'))
            if args.package.lower() not in good_names:
                msg = 'Package name on the command line " {}" does not match the package name in the file "{}"'.format(
                    args.package.lower(), package_attrs['name'].lower()
                )
                logger.error(msg)
                raise errors.BinstarError(msg)
        package_name = args.package
    else:
        if 'name' not in package_attrs:
            message = 'Could not detect package name for package type {}, please use the --package option'.format(
                package_type.label())
            logger.error(message)
            raise errors.BinstarError(message)
        package_name = package_attrs['name']

    return package_name


def get_version(args, release_attrs, package_type):
    if args.version:
        version = args.version
    else:
        if 'version' not in release_attrs:
            message = 'Could not detect package version for package type \"{}\", ' \
                      'please use the --version option'.format(package_type.label())
            logger.error(message)
            raise errors.BinstarError(message)
        version = release_attrs['version']
    return version


def add_package(aserver_api, args, username,  # pylint: disable=too-many-arguments
                package_name, package_attrs, package_type):
    try:
        return aserver_api.package(username, package_name)
    except errors.NotFound as not_found_error:
        if not args.auto_register:
            message = (
                    'Anaconda repository package %s/%s does not exist. '
                    'Please run "anaconda package --create" to create this package namespace on Anaconda.org.' %
                    (username, package_name)
            )
            logger.error(message)
            raise errors.UserError(message) from not_found_error

        if args.summary:
            summary = args.summary
        else:
            if 'summary' not in package_attrs:
                message = 'Could not detect package summary for ' \
                          'package type %s, please use the --summary option' % (package_type,)
                logger.error(message)
                raise errors.BinstarError(message) from not_found_error
            summary = package_attrs['summary']

        public = not args.private

        return aserver_api.add_package(
            username,
            package_name,
            summary,
            package_attrs.get('license'),
            public=public,
            attrs=package_attrs,
            license_url=package_attrs.get('license_url'),
            license_family=package_attrs.get('license_family'),
            package_type=package_type,
        )


def add_release(aserver_api, args, username,  # pylint: disable=too-many-arguments
                package_name, version, release_attrs):
    try:
        # Check if the release already exists
        aserver_api.release(username, package_name, version)

        # If it exists update public attrs if needed.
        if args.force_metadata_update:
            aserver_api.update_release(username, package_name, version, release_attrs)
    except errors.NotFound:
        if args.mode == 'interactive':
            create_release_interactive(aserver_api, username, package_name, version, release_attrs)
        else:
            create_release(aserver_api, username, package_name, version, release_attrs)


def remove_existing_file(aserver_api, args,  # pylint: disable=too-many-arguments,inconsistent-return-statements
                         username, package_name, version, file_attrs):
    try:
        aserver_api.distribution(username, package_name, version, file_attrs['basename'])
    except errors.NotFound:
        return False

    if args.mode == 'force':
        logger.warning('Distribution "%s" already exists. Removing.', file_attrs['basename'])
        aserver_api.remove_dist(username, package_name, version, file_attrs['basename'])

    if args.mode == 'interactive':
        if bool_input('Distribution "%s" already exists. Would you like to replace it?' % file_attrs['basename']):
            aserver_api.remove_dist(username, package_name, version, file_attrs['basename'])
        else:
            logger.info('Not replacing distribution "%s"', file_attrs['basename'])
            return True


def upload_package(filename, package_type,  # pylint: disable=inconsistent-return-statements,too-many-locals
                   aserver_api, username, args):
    logger.info('Extracting %s attributes for upload', verbose_package_type(package_type))

    try:
        package_attrs, release_attrs, file_attrs = get_attrs(package_type, filename, parser_args=args)
    except Exception as error:
        message = 'Trouble reading metadata from {}. Is this a valid {} package?'.format(
            filename, verbose_package_type(package_type)
        )
        logger.error(message)

        if args.show_traceback:
            raise

        raise errors.BinstarError(message) from error

    if args.build_id:
        file_attrs['attrs']['binstar_build'] = args.build_id

    if args.summary:
        release_attrs['summary'] = args.summary

    if args.description:
        release_attrs['description'] = args.description

    package_name = get_package_name(args, package_attrs, package_type)
    version = get_version(args, release_attrs, package_type)

    logger.info('Creating package "%s"', package_name)

    package = add_package(aserver_api, args, username, package_name, package_attrs, package_type)
    package_types = [PackageType(pkg_type) for pkg_type in package.get('package_types', [])]

    allowed_package_types = set(package_types)
    for group in [{PackageType.CONDA, PackageType.STANDARD_PYTHON}]:
        if allowed_package_types & group:
            allowed_package_types.update(group)

    if package_types and (package_type not in allowed_package_types):
        message = 'You already have a {} named \'{}\'. Use a different name for this {}.'.format(
            verbose_package_type(package_types[0] if package_types else ''), package_name,
            verbose_package_type(package_type),
        )
        logger.error(message)
        raise errors.BinstarError(message)

    logger.info('Creating release "%s"', version)

    add_release(aserver_api, args, username, package_name, version, release_attrs)
    binstar_package_type = file_attrs.pop('binstar_package_type', package_type)

    logger.info('Uploading file "%s/%s/%s/%s"', username, package_name, version, file_attrs['basename'])

    if remove_existing_file(aserver_api, args, username, package_name, version, file_attrs):
        return

    try:
        with open(filename, 'rb') as file:
            upload_info = aserver_api.upload(username, package_name, version, file_attrs['basename'], file,
                                             binstar_package_type, args.description,
                                             dependencies=file_attrs.get('dependencies'), attrs=file_attrs['attrs'],
                                             channels=args.labels)
    except errors.Conflict:
        upload_info = {}
        if args.mode != 'skip':
            # pylint: disable=implicit-str-concat
            logger.info(
                'Distribution already exists. Please use the -i/--interactive or --force or --skip options or '
                '`anaconda remove %s/%s/%s/%s',
                username,
                package_name,
                version,
                file_attrs['basename'],
            )
            raise
        logger.info('Distribution already exists. Skipping upload.\n')

    if upload_info:
        logger.info('Upload complete\n')

    return [package_name, upload_info]


def main(args):  # pylint: disable=too-many-branches,too-many-locals
    config = get_config(site=args.site)

    aserver_api = get_server_api(token=args.token, site=args.site, config=config)
    aserver_api.check_server()

    validate_username = True

    if args.user:
        username = args.user
    elif 'upload_user' in config:
        username = config['upload_user']
    else:
        validate_username = False
        user = aserver_api.user()
        username = user['login']

    logger.info('Using "%s" as upload username', username)

    if validate_username:
        try:
            aserver_api.user(username)
        except errors.NotFound as error:
            message = 'User "{}" does not exist'.format(username)
            logger.error(message)
            raise errors.BinstarError(message) from error

    uploaded_packages = []
    uploaded_projects = []

    # Flatten file list because of 'windows_glob' function
    files = sorted(set(fitem for fglob in args.files for fitem in fglob))

    for filename in files:
        if not exists(filename):
            message = 'File "{}" does not exist'.format(filename)
            logger.error(message)
            raise errors.BinstarError(message)
        logger.info("Processing '%s'", filename)

        package_type = determine_package_type(filename, args)

        if package_type is PackageType.PROJECT:
            uploaded_projects.append(upload_project(filename, args, username))
        else:
            if package_type is PackageType.NOTEBOOK and not args.mode == 'force':
                try:
                    with open(filename, 'rt', encoding='utf-8') as stream:
                        nbformat.read(stream, nbformat.NO_CONVERT)
                except Exception as error:  # pylint: disable=broad-except
                    logger.error("Invalid notebook file '%s': %s", filename, error)
                    logger.info('Use --force to upload the file anyways')
                    continue

            package_info = upload_package(
                filename,
                package_type=package_type,
                aserver_api=aserver_api,
                username=username,
                args=args)

            if package_info is not None and len(package_info) == 2:
                _package, _upload_info = package_info
                if _upload_info:
                    uploaded_packages.append((_package, _upload_info, package_type))

    for package, upload_info, package_type in uploaded_packages:
        package_url = upload_info.get('url', 'https://anaconda.org/%s/%s' % (username, package))
        logger.info('%s located at:\n%s\n', verbose_package_type(package_type), package_url)

    for project_name, url in uploaded_projects:
        logger.info('Project %s uploaded to %s.\n', project_name, url)


def pathname_list(item):
    if (os.name == 'nt') and any(character in {'*', '?'} for character in item):
        return glob(item)
    return [item]


def add_parser(subparsers):
    description = 'Upload packages to your Anaconda repository'
    parser = subparsers.add_parser(
        'upload',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help=description, description=description,
        epilog=__doc__,
    )

    parser.add_argument('files', nargs='+', help='Distributions to upload', default=[], type=pathname_list)

    label_help = (
            '{deprecation}Add this file to a specific {label}. ' +
            'Warning: if the file {label}s do not include "main", ' +
            'the file will not show up in your user {label}')

    parser.add_argument(
        '-c', '--channel',
        action='append',
        default=[],
        dest='labels',
        help=label_help.format(deprecation='[DEPRECATED]\n', label='channel'),
        metavar='CHANNELS',
    )
    parser.add_argument(
        '-l', '--label',
        action='append',
        dest='labels',
        help=label_help.format(deprecation='', label='label'),
    )
    parser.add_argument(
        '--no-progress',
        help="Don't show upload progress",
        action='store_true',
    )
    parser.add_argument(
        '-u', '--user',
        help='User account or Organization, defaults to the current user',
    )

    mgroup = parser.add_argument_group('metadata options')
    mgroup.add_argument(
        '-p', '--package',
        help='Defaults to the package name in the uploaded file',
    )
    mgroup.add_argument(
        '-v', '--version',
        help='Defaults to the package version in the uploaded file',
    )
    mgroup.add_argument(
        '-s', '--summary',
        help='Set the summary of the package',
    )
    mgroup.add_argument(
        '-t', '--package-type',
        help='Set the package type. Defaults to autodetect',
    )
    mgroup.add_argument(
        '-d', '--description',
        help='description of the file(s)',
    )
    mgroup.add_argument(
        '--thumbnail',
        help="Notebook's thumbnail image",
    )
    mgroup.add_argument(
        '--private',
        help='Create the package with private access',
        action='store_true',
    )

    register_group = parser.add_mutually_exclusive_group()
    register_group.add_argument(
        '--no-register',
        dest='auto_register',
        action='store_false',
        help="Don't create a new package namespace if it does not exist",
    )
    register_group.add_argument(
        '--register',
        dest='auto_register',
        action='store_true',
        help='Create a new package namespace if it does not exist',
    )

    parser.set_defaults(auto_register=DEFAULT_CONFIG.get('auto_register', True))
    parser.add_argument(
        '--build-id',
        help='Anaconda repository Build ID (internal only)',
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '-i', '--interactive',
        action='store_const',
        help='Run an interactive prompt if any packages are missing',
        dest='mode',
        const='interactive',
    )
    group.add_argument(
        '-f', '--fail',
        help='Fail if a package or release does not exist (default)',
        action='store_const',
        dest='mode',
        const='fail',
    )
    group.add_argument(
        '--force',
        help='Force a package upload regardless of errors',
        action='store_const',
        dest='mode',
        const='force',
    )
    group.add_argument(
        '--skip-existing',
        help='Skip errors on package batch upload if it already exists',
        action='store_const',
        dest='mode',
        const='skip',
    )
    group.add_argument(
        '-m', '--force-metadata-update',
        action='store_true',
        help='Overwrite existing release metadata with the metadata from the package.',
    )

    parser.set_defaults(main=main)

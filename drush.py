# coding: utf-8
#
# Copyright (C) 2016 Savoir-faire Linux Inc. (<www.savoirfairelinux.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals
from fabric.api import task, roles, env
from fabric.contrib.console import confirm
from fabric.colors import red, green
from fabric.utils import abort

from datetime import datetime

import helpers as h
import core as c

from git import isGitDirty


@task(alias='make')
@roles('local')
def make(action='install'):
    """
    Build the platform by running the Makefile specified in the local_vars.py configuration file.
    """

    if env.get('always_use_pty', True):
      if (isGitDirty()):
        if (not confirm(red('There are warnings on status of your repositories. '
                        'Do you want to continue and reset all changes to remote repositories'' states?'), default=False)):
          abort('Aborting "drush {}" since there might be a risk of loosing local data.'.format(action))

    drush_opts = "--prepare-install " if action != 'update' else ''

    # Update profile codebase
    if env.site_profile and env.site_profile != '':
        drush_opts += "--contrib-destination=profiles/{} ".format(env.site_profile)
        h.update_profile()

    if not env.get('always_use_pty', True):
        drush_opts += "--translations=" + env.site_languages + " "
    elif confirm(red('Say [Y] to {} the site at {} with the specified translation(s): {}. If you say [n] '
                     'the site will be installed in English only'.format(action, env.site_root, env.site_languages))):
        drush_opts += "--translations=" + env.site_languages + " "

    if env.get('always_use_pty', True):
        drush_opts += " --working-copy --no-gitinfofile"
    if not h.fab_exists('local', env.site_root):
        h.fab_run('local', "mkdir {}".format(env.site_root))
    with h.fab_cd('local', env.site_root):
        h.fab_run('local', 'drush make {} {} -y'.format(drush_opts, env.makefile))

@task
@roles('local')
def aliases():
    """
    Copy conf/aliases.drushrc.php in the site environment.
    """

    role = 'local'
    drush_aliases = env.site_drush_aliases
    workspace = env.workspace

    if not h.fab_exists(role, drush_aliases):
        h.fab_run(role, 'mkdir {}'.format(drush_aliases))
    with h.fab_cd(role, drush_aliases):
        # Create aliases
        if h.fab_exists(role, '{}/aliases.drushrc.php'.format(drush_aliases)):
            h.fab_run(role, 'rm {}/aliases.drushrc.php'.format(drush_aliases))
        h.fab_run(role, 'cp {}/conf/aliases.drushrc.php .'.format(workspace))

    print(green('Drush aliases have been copied to {} directory.'.format(drush_aliases)))


@task
@roles('docker')
def updatedb():
    """
    Run the available database updates. Similar to drush updatedb.
    """

    role = 'docker'

    with h.fab_cd(role, env.docker_site_root):
        h.fab_run(role, 'drush updatedb -y')
        h.hook_execute(env.hook_post_update, role)


@task
@roles('docker')
def site_install():
    """
    Run the site installation procedure.
    """

    role = 'docker'
    site_root = env.docker_site_root
    apache = env.apache_user
    profile = env.site_profile
    db_user = env.site_db_user
    db_pass = env.site_db_pass
    db_host = env.site_db_host
    db_name = env.site_db_name
    site_name = env.site_name
    site_admin_name = env.site_admin_user
    site_admin_pass = env.site_admin_pass
    site_subdir = env.site_subdir

    # Create first the database if necessary
    h.init_db('docker')

    with h.fab_cd(role, site_root):
        locale = '--locale="fr"' if env.locale else ''

        h.fab_run(role, 'sudo -u {} drush site-install {} {} --db-url=mysql://{}:{}@{}/{} --site-name="{}" '
                        '--account-name={} --account-pass={} --sites-subdir={} -y'.format(apache, profile, locale,
                                                                                          db_user, db_pass,
                                                                                          db_host, db_name, site_name,
                                                                                          site_admin_name,
                                                                                          site_admin_pass,
                                                                                          site_subdir))

        print(green('Site installed successfully!'))

        # Import db_dump if it exists.
        if 'db_dump' in env and env.db_dump is not False:
            c.db_import(env.db_dump, role)

    h.hook_execute(env.hook_post_install, role)


@task
@roles('docker')
def archive_dump(role='docker'):
    """
    Archive the platform for release or deployment.
    :param role Default 'role' where to run the task
    """

    with h.fab_cd(role, env.docker_site_root):
        platform = '{}-{}.tar.gz'.format(env.project_name, datetime.now().strftime('%Y%m%d_%H%M%S'))
        h.fab_run(role, 'rm -f {}/build/*.tar.gz'.format(env.docker_workspace))
        print(green('All tar.gz archives found in {}/build have been deleted.'.format(env.docker_workspace)))

        h.fab_run(
            role,
            'drush archive-dump --destination={}/build/{} --tags="sflinux {}" --generatorversion="2.x" '
            '--generator="Drupalizer::fab drush.archive_dump" --tar-options="--exclude=.git"'
            ''.format(env.docker_workspace, platform, env.project_name)
        )


@task
@roles('docker')
def gen_doc(role='docker'):
    """
    Generate README file
    :param role Default 'role' where to run the task
    """

    if h.fab_exists(role, '{}/README.adoc'.format(env.docker_workspace)):
        h.fab_run(role, 'asciidoctor -d book -b html5 -o {}/README.html {}/README.adoc'.
                  format(env.docker_workspace, env.docker_workspace))
        print(green('README.html generated in {}'.format(env.docker_workspace)))

    if h.fab_exists(role, '{}/CHANGELOG.adoc'.format(env.docker_workspace)):
        h.fab_run(role, 'asciidoctor -d book -b html5 -o {}/CHANGELOG.html {}/CHANGELOG.adoc'.
                  format(env.docker_workspace, env.docker_workspace))
        print(green('CHANGELOG.html generated in {}'.format(env.docker_workspace)))

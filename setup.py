# vim: expandtab
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import string
import random
import json
import getpass
import textwrap

INFO = u'\033[93m'
SHELL = u'\033[92m'
ERROR = u'\033[91m'
PROMPT = u'\033[96m'
RESET = u'\033[0m'

def call(msg, args):
    print(INFO + u'\n' + msg + RESET)
    print(SHELL + u'$ ' + u' '.join(args) + u'\n' + RESET)
    return subprocess.check_call(args)

class JsonFile(object):
    def __init__(self, inputfile, outputfile=None):
        self.inputfile = inputfile
        self.outputfile = outputfile or inputfile
        with open(inputfile) as json_file:
            self.data = json.load(json_file)

    def __enter__(self):
        return self.data

    def __exit__(self, type, value, traceback):
        if type is None:
            with open(self.outputfile, u'w') as json_file:
                json.dump(self.data, json_file, indent=2)

class Configure(object):
    def __init__(self, filename=u'setup.json'):
        self.filename = filename
        self.configured = {}
        try:
            with open(filename) as json_file:
                self.data = json.load(json_file)
        except IOError:
            self.data = {}

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if type is None:
            with open(self.filename, u'w') as json_file:
                json.dump(self.data, json_file, indent=2, sort_keys=True)

    def get(self, key):
        assert self.configured[key] == True
        return self.data[key]

    def auto(self, key, default):
        self.configured[key] = True
        return self.data.setdefault(key, default)

    def input(self, key, prompt, default=u'', required=False):
        configured = self.data.get(key, default)
        while True:
            inputed = raw_input(PROMPT + u'\n%s [%s]: ' % (prompt, configured) + RESET) or configured
            if required and not inputed:
                print(ERROR + u'\nError: The value is required.' + RESET)
                continue
            break
        self.configured[key] = True
        self.data[key] = inputed
        return inputed

    def input_password(self, key, prompt, hasher=None, required=False):
        configured = self.data.get(key, u'')
        while True:
            inputed = getpass.getpass(PROMPT + u'\n%s [%s]: ' % (prompt, u'*****' if configured else u'') + RESET)
            if required and not inputed and not configured:
                print(ERROR + u'\nError: The value is required.' + RESET)
                continue
            break
        if not hasher:
            hasher = lambda s: s
        hashed = hasher(inputed) if inputed else configured
        self.configured[key] = True
        self.data[key] = hashed
        return hashed

    def input_yes_no(self, key, prompt, default=u''):
        configured = self.data.get(key, default)
        while True:
            inputed = raw_input(PROMPT + u'\n%s Y/N [%s]: ' % (prompt, configured) + RESET) or configured
            if not inputed:
                print(ERROR + u'\nError: The value is required.' + RESET)
                continue
            value = inputed.upper()
            if value not in [u'Y', u'N']:
                print(ERROR + u'\nError: Enter Y or N.' + RESET)
                continue
            break
        self.configured[key] = True
        self.data[key] = value
        return value

    def input_choice(self, key, prompt, choices, default=u''):
        configured = self.data.get(key, default)
        configured_choice = u''
        print(INFO + u'\n%s:' % prompt + RESET)
        for idx, (value, label) in enumerate(choices):
            print(INFO + u' %d) %s' % (idx+1, label) + RESET)
            if value == configured:
                configured_choice = u'%d' % (idx+1)
        while True:
            inputed = raw_input(PROMPT + u'\n%s [%s]: ' % (prompt, configured_choice) + RESET) or configured_choice
            if not inputed:
                print(ERROR + u'\nError: The value is required.' + RESET)
                continue
            try:
                value, label = choices[int(inputed)-1]
            except (ValueError, IndexError):
                print(ERROR + u'\nError: Invalid choice.' + RESET)
                continue
            break
        self.configured[key] = True
        self.data[key] = value
        return value

class Settings(object):
    def __init__(self, filename=u'chcemvediet/settings/configured.py'):
        self.filename = filename
        self.lines = []
        self.comment(u'This file was autogenerated by `setup.py`. Do NOT edit it.')

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if type is None:
            with open(self.filename, u'w') as settings_file:
                settings_file.write(u'\n'.join(self.lines) + u'\n')

    def comment(self, text):
        for line in text.split(u'\n'):
            self.lines.append(u'# %s' % line)

    def include(self, filaname):
        self.lines.append(u'execfile(os.path.join(SETTINGS_PATH, %s))' % repr(filaname))

    def setting(self, name, value):
        self.lines.append(u'%s = %s' % (name, repr(value)))

def generate_secret_key(length, chars):
    sysrandom = random.SystemRandom()
    return u''.join(sysrandom.choice(chars) for i in range(length))


def configure_server_mode(configure, settings):
    print(INFO + textwrap.dedent(u"""
            Select server mode. Local development mode with no email infrastructure and
            online development mode with no email infrastructure do not send any emails at
            all. They just store them in the database. You can use admin interface to see
            emails sent from the application and to manually mock replies to them. Local
            development mode with dummy email infrastructure does not send real emails, it
            mocks local SMPT/IMAP servers, so you can use any local SMTP/IMAP client to read
            emails sent by the application and send your replies back to the application.
            Online development mode with working email infrastructure and dummy obligee
            email addresses sends real emails using Mandrill service, however, obligee email
            addresses are replaced with dummies, so you won't send any unsolicited emails to
            them.""") + RESET)
    server_mode = configure.input_choice(u'server_mode', u'Server mode', choices=(
            (u'local_with_no_mail',          u'Local development mode with no email infrastructure.'),
            (u'local_with_local_mail',       u'Local development mode with dummy email infrastructure.'),
            (u'dev_with_no_mail',            u'Online development mode with no email infrastructure.'),
            (u'dev_with_dummy_obligee_mail', u'Online development mode with working email infrastructure and dummy obligee email addresses.'),
            (u'production',                  u'Production mode.'),
            ))
    includes = {
            u'local_with_no_mail':          [u'server_local.py', u'mail_nomail.py'],
            u'local_with_local_mail':       [u'server_local.py', u'mail_dummymail.py'],
            u'dev_with_no_mail':            [u'server_dev.py',   u'mail_nomail.py'],
            u'dev_with_dummy_obligee_mail': [u'server_dev.py',   u'mail_mandrill.py'],
            u'production':                  [u'server_prod.py',  u'mail_mandrill.py'],
            }[server_mode]
    for include in includes:
        settings.include(include)

def install_requirements(configure):
    server_mode = configure.get(u'server_mode')
    enable_unittests = configure.input_yes_no(u'enable_unittests', u'Install requirements for unittesting?', default=u'N')
    requirements = {
            u'local_with_no_mail':          [u'-r', u'requirements/base.txt', u'-r', u'requirements/local.txt'],
            u'local_with_local_mail':       [u'-r', u'requirements/base.txt', u'-r', u'requirements/local.txt', u'-r', u'requirements/local_mail.txt'],
            u'dev_with_no_mail':            [u'-r', u'requirements/base.txt', u'-r', u'requirements/online.txt'],
            u'dev_with_dummy_obligee_mail': [u'-r', u'requirements/base.txt', u'-r', u'requirements/online.txt'],
            u'production':                  [u'-r', u'requirements/base.txt', u'-r', u'requirements/online.txt'],
            }[server_mode]
    requirements += {
            u'Y': [u'-r', u'requirements/tests.txt'],
            u'N': [],
            }[enable_unittests]
    call(u'Installing requirements for the selected server mode:', [u'env/bin/pip', u'install'] + requirements);

def configure_secret_key(configure, settings):
    secret_key = configure.auto(u'secret_key', generate_secret_key(100, string.digits + string.letters + string.punctuation))
    settings.setting(u'SECRET_KEY', secret_key)

def configure_email_addresses(configure, settings):
    server_domain = configure.input(u'server_domain', u'Server domain', default=u'chcemvediet.sk', required=True)

    print(INFO + textwrap.dedent(u"""
            Set admin e-mail. It will be used for lowlevel error reporting and
            administration e-mails.""") + RESET)
    admin_email = configure.input(u'admin_email', u'Admin e-mail', default=u'admin@%s' % server_domain, required=True)
    settings.setting(u'SERVER_EMAIL', admin_email)
    settings.setting(u'ADMINS[len(ADMINS):]', [(u'Admin', admin_email)])

    print(INFO + textwrap.dedent(u"""
            Set inforequest unique e-mail template. It will be used to generate unique from
            e-mail addresses used by inforequests. The unique e-mail template must contain
            '{token}' as a placeholder to distinguish individual inforequests. For instance
            '{token}@mail.example.com' may be expanded to 'lama@mail.example.com'.""") + RESET)
    inforequest_unique_email = configure.input(u'inforequest_unique_email', u'Inforequest unique e-mail', default=u'{token}@mail.%s' % server_domain, required=True)
    settings.setting(u'INFOREQUEST_UNIQUE_EMAIL', inforequest_unique_email)

    print(INFO + textwrap.dedent(u"""
            Set default from address. It will be used as the from e-mail addresses for all
            other e-mails.""") + RESET)
    default_from_email = configure.input(u'default_from_email', u'Default from e-mail', default=u'info@%s' % server_domain, required=True)
    settings.setting(u'DEFAULT_FROM_EMAIL', default_from_email)

    # Production mode uses real obligee emails.
    server_mode = configure.get(u'server_mode')
    if server_mode != u'production':
        print(INFO + textwrap.dedent(u"""
                To prevent unsolicited emails to obligees while testing we replace their
                addresses with dummies. Use '{name}' as a placeholder to distinguish individual
                obligees. For instance 'mail@{name}.example.com' may be expanded to
                'mail@martika-hnusta.example.com'."""))
        configure.input(u'obligee_dummy_mail', u'Obligee dummy e-mail', required=True)

def configure_devbar(configure, settings):
    server_mode = configure.get(u'server_mode')
    obligee_dummy_mail = configure.get(u'obligee_dummy_mail')
    devbar_message = {
            u'local_with_no_mail':          u'',
            u'local_with_local_mail':       u'',
            u'dev_with_no_mail':            u'<strong>Warning:</strong> This is a development server. No emails are sent anywhere. To view what would be sent, use <a href="/admin/mail/message/">admin interface</a>.',
            u'dev_with_dummy_obligee_mail': u'<strong>Warning:</strong> This is a development server. All obligee email addresses are replaced with dummies: %s.' % obligee_dummy_mail,
            u'production':                  u'',
            }[server_mode]
    settings.setting(u'DEVBAR_MESSAGE', devbar_message)

def configure_database(configure, settings):
    server_mode = configure.get(u'server_mode')
    if server_mode in [u'dev_with_no_mail', u'dev_with_dummy_obligee_mail', u'production']:
        print(INFO + textwrap.dedent(u"""
                Set MySQL database name, user and password.""") + RESET)
        db_name = configure.input(u'db_name', u'Database name', required=True)
        db_user = configure.input(u'db_user', u'Database user name', required=True)
        db_password = configure.input_password(u'db_password', u'Database user password', required=True)
        settings.setting(u'DATABASES[u"default"][u"NAME"]', db_name)
        settings.setting(u'DATABASES[u"default"][u"USER"]', db_user)
        settings.setting(u'DATABASES[u"default"][u"PASSWORD"]', db_password)

def configure_mandrill(configure, settings):
    server_mode = configure.get(u'server_mode')
    server_domain = configure.get(u'server_domain')
    if server_mode in [u'dev_with_dummy_obligee_mail', u'production']:
        print(INFO + textwrap.dedent(u"""
                Madrill is a transactional mail service we use to send emails. To setup it, you
                need to have a webhook URL Mandrill server can access. If you are running your
                server behing a firewall or NAT, you need to setup a tunelling reverse proxy to
                your localhost. See https://ngrok.com/ for instance. Please enter your webhook
                URL prefix. If using ngrok, your prefix should look like
                "https://<yoursubdomain>.ngrok.com/". If using a public server, the prefix
                should be "https://<yourdomain>/".""") + RESET)
        mandrill_webhook_https = configure.input_yes_no(u'mandrill_webhook_https', u'Use "https" for Mandrill Webhooks?', default=u'Y')
        mandrill_webhook_prefix = configure.input(u'mandrill_webhook_prefix', u'Mandrill Webhook Prefix', default=u'%s://%s/' % (u'https' if mandrill_webhook_https == u'Y' else u'http', server_domain), required=True)
        mandrill_webhook_secret = configure.auto(u'mandrill_webhook_secret', generate_secret_key(32, string.digits + string.letters))
        mandrill_webhook_url = u'%s/mandrill/webhook/?secret=%s' % (mandrill_webhook_prefix.rstrip(u'/'), mandrill_webhook_secret)
        mandrill_api_key = configure.input(u'mandrill_api_key', u'Mandrill API key', required=True)
        print(INFO + textwrap.dedent(u"""
                After you finish this configuration and run your server, you can open Mandrill
                webhook settings and create a webhook with the following URL:

                    %s

                It is not possible to create the webhook before you run your server, because
                Mandrill checks if the given URL works. After you create your webhooks, run this
                configuration once again and enter all their keys as given by Mandrill. If you
                are entering multiple webhook keys, separate them with space. Leave the key
                empty if you have not created the webhook yet."""
                % mandrill_webhook_url) + RESET)
        mandrill_webhook_keys = configure.input(u'mandrill_webhook_keys', u'Mandrill webhook keys')
        settings.setting(u'MANDRILL_WEBHOOK_SECRET', mandrill_webhook_secret)
        settings.setting(u'MANDRILL_WEBHOOK_URL', mandrill_webhook_url)
        settings.setting(u'MANDRILL_API_KEY', mandrill_api_key)
        settings.setting(u'MANDRILL_WEBHOOK_KEYS', mandrill_webhook_keys.split())

def load_fixtures(configure):
    res = []
    res.append(u'fixtures/sites_site.json')
    res.append(u'fixtures/auth_user.json')
    res.append(u'fixtures/socialaccount_socialapp.json')

    # Production mode uses real obligee data configured manually.
    server_mode = configure.get(u'server_mode')
    if server_mode != u'production':
        res.append(u'fixtures/obligees_obligee.json')

    return res

def configure_site_domain(configure):
    from django.contrib.sites.models import Site

    server_domain = configure.get(u'server_domain')
    site = Site.objects.get(name=u'chcemvediet')
    if server_domain != site.domain:
        site.domain = server_domain
        site.save()

def configure_admin_password(configure):
    from django.contrib.auth.models import User
    from django.contrib.auth.hashers import make_password

    print(INFO + textwrap.dedent(u"""
            Enter site admin password.""") + RESET)
    admin_password = configure.input_password(u'admin_password', u'Admin password', make_password, required=True)
    admin_email = configure.get(u'admin_email')
    admin = User.objects.get(username=u'admin')
    if admin_password != admin.password or admin_email != admin.email:
        admin.password = admin_password
        admin.email = admin_email
        admin.save()

def configure_social_accounts(configure):
    from allauth.socialaccount.models import SocialApp

    print(INFO + textwrap.dedent(u"""
            Enter your OAuth Client IDs and Secrets for social account providers. If you
            don't want to use some providers, just skip them by entering empty strings.
            Don't share the keys with anybody and never push them to git."""))
    for social_app in SocialApp.objects.all():
        client_id = configure.input(u'%s_client_id' % social_app.provider, u'%s Client ID' % social_app.name)
        secret = configure.input(u'%s_secret' % social_app.provider, u'%s Secret' % social_app.name)
        if client_id != social_app.client_id or secret != social_app.secret:
            social_app.client_id = client_id
            social_app.secret = secret
            social_app.save()

def configure_dummy_obligee_emails(configure):
    from chcemvediet.apps.obligees.models import Obligee, HistoricalObligee

    # Production mode uses real obligee emails.
    server_mode = configure.get(u'server_mode')
    if server_mode == u'production':
        return

    mail_tpl = configure.get(u'obligee_dummy_mail')
    for model in [Obligee, HistoricalObligee]:
        for obligee in model.objects.all():
            slug = obligee.slug[0:30].strip(u'-')
            mail = mail_tpl.format(name=slug)
            if mail != obligee.emails:
                obligee.emails = mail
                obligee.save()

def help_run_server(configure):
    server_mode = configure.get(u'server_mode')
    if server_mode in [u'local_with_no_mail', u'local_with_local_mail']:
        print(INFO + textwrap.dedent(u"""
                Your local testing server is configured and ready. Run it with:
                    $ env/bin/python manage.py runserver

                In another shell, run testing cronserver:
                    $ env/bin/python manage.py cronserver
                """) + RESET)
        if server_mode in [u'local_with_local_mail']:
            print(INFO + textwrap.dedent(u"""
                    In yet another shell, run dummy email infrastructure:
                        $ env/bin/python manage.py dummymail
                    """) + RESET)
    else:
        assert server_mode in [u'dev_with_no_mail', u'dev_with_dummy_obligee_mail', u'production']
        print(INFO + textwrap.dedent(u"""
                Make sure ``mod_wsgi`` Apache module is installed and enabled and add the
                following directives to your virtualhost configuration:

                    ServerName {domain}

                    ...

                    WSGIScriptAlias / {path}/chcemvediet/chcemvediet/wsgi.py
                    WSGIDaemonProcess {domain} user={user} group={group} python-path={path}/chcemvediet:{path}/chcemvediet/env/lib/python2.7/site-packages
                    WSGIProcessGroup {domain}

                    <Directory {path}/chcemvediet/chcemvediet>
                      <Files wsgi.py>
                        Order allow,deny
                        Allow from all
                      </Files>
                    </Directory>

                Where {path} is an absolute path to the repository, {domain} is your web domain
                and {user} and {group} are unix user and group names the server will run under.

                Finally add a cron job running the following command every minute:
                    cd {path} && env/bin/python manage.py runcrons
                """) + RESET)

def main():
    # Make sure we are in the project root directory
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    # Create a virtual environment
    if not os.path.isdir(u'env'):
        call(u'Creating a virtual Python environment: env/', [u'virtualenv', u'env']);

    # Make sure we are running within the virtual environment
    if sys.executable != os.path.abspath(u'env/bin/python'):
        try:
            call(u'Rerunning with: env/bin/python', [u'env/bin/python', u'setup.py']);
        except KeyboardInterrupt:
            pass
        sys.exit()

    with Configure() as configure:

        # Configure project settings
        with Settings() as settings:
            configure_server_mode(configure, settings)
            install_requirements(configure)
            configure_secret_key(configure, settings)
            configure_email_addresses(configure, settings)
            configure_devbar(configure, settings)
            configure_database(configure, settings)
            configure_mandrill(configure, settings)

        # Settings module is configured, so we may use Django now.
        os.environ.setdefault(u'DJANGO_SETTINGS_MODULE', u'chcemvediet.settings')
        from django.db.transaction import atomic
        from django.db.utils import DatabaseError
        from django.contrib.auth.models import User

        # Create/synchronize DB. We assume that DB is already created iff it contains User model.
        try:
            User.objects.count()
        except DatabaseError:
            call(u'Create DB:', [u'env/bin/python', u'manage.py', u'syncdb', u'--all', u'--noinput'])
            call(u'Skip DB migrations:', [u'env/bin/python', u'manage.py', u'migrate', u'--fake'])
            call(u'Load DB fixtures:', [u'env/bin/python', u'manage.py', u'loaddata'] + load_fixtures(configure))
        else:
            call(u'Synchronize DB:', [u'env/bin/python', u'manage.py', u'syncdb', u'--noinput'])
            call(u'Migrate DB:', [u'env/bin/python', u'manage.py', u'migrate'])

        # Configure database content
        with atomic():
            configure_site_domain(configure)
            configure_admin_password(configure)
            configure_social_accounts(configure)
            configure_dummy_obligee_emails(configure)

        # The server is configured and ready
        help_run_server(configure)


if __name__ == u'__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(ERROR + u'\nError: Keyboard Interrupt' + RESET)
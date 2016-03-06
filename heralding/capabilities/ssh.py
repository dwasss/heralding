# pylint: disable-msg=E1101
# Copyright (C) 2013 Johnny Vestergaard <jkv@unixcluster.dk>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import tempfile

from Crypto.PublicKey import RSA
from paramiko import RSAKey
from paramiko.ssh_exception import SSHException
from telnetsrv.paramiko_ssh import SSHHandler

from heralding.capabilities.handlerbase import HandlerBase
from heralding.capabilities.shared.shell import Commands

logger = logging.getLogger(__name__)


class SSH(HandlerBase):
    def __init__(self, options):
        logging.getLogger("telnetsrv.paramiko_ssh ").setLevel(logging.WARNING)
        logging.getLogger("paramiko").setLevel(logging.WARNING)

        # generate key
        rsa_key = RSA.generate(1024)
        priv_key_text = rsa_key.exportKey('PEM', pkcs=1)

        self.key = tempfile.mkstemp()[1]
        open(self.key, 'w').write(priv_key_text)
        super(SSH, self).__init__(options)

    def handle_session(self, gsocket, address):
        session = self.create_session(address)
        try:
            SshWrapper(address, None, gsocket, session, self.options, self.key)
        except (SSHException, EOFError) as ex:
            logger.debug('Unexpected end of ssh session: {0}. ({1})'.format(ex, session.id))
        finally:
            self.close_session(session)


class BeeTelnetHandler(Commands):
    def __init__(self, request, client_address, server, session):
        Commands.__init__(self, request, client_address, server, session)


class SshWrapper(SSHHandler):

    # reusing telnetsrv stuff
    telnet_handler = BeeTelnetHandler

    def __init__(self, client_address, server, socket, session, options, key):
        self.session = session
        self.auth_count = 0
        self.working_dir = None
        self.username = None

        SshWrapper.host_key = RSAKey(filename=key)
        # TODO: Figure out why this is necessary
        request = SshWrapper.dummy_request()
        request._sock = socket
        # TODO END

        SSHHandler.__init__(self, request, client_address, server)

    def authCallbackUsername(self, username):
        # make sure no one can logon
        raise

    def authCallback(self, username, password):
        self.session.activity()
        self.session.add_auth_attempt('plaintext', username=username, password=password)
        raise

    def finish(self):
        self.session.end_session()

    def setup(self):

        self.transport.load_server_moduli()

        self.transport.add_server_key(self.host_key)

        self.transport.start_server(server=self)

        while True:
            channel = self.transport.accept(20)
            if channel is None:
                # check to see if any thread is running
                any_running = False
                for _, thread in self.channels.items():
                    if thread.is_alive():
                        any_running = True
                        break
                if not any_running:
                    break
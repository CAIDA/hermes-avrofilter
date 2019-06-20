# Copyright 2019 The Regents of the University of California.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# Original version written by Shane Alcock <salcock@waikato.ac.nz>

from swift.common.utils import get_logger, split_path, list_from_csv
from swift.common.swob import Request, Response, wsgify
from swift.common.constraints import valid_api_version
from swift.common.request_helpers import get_param
from swift.proxy.controllers.base import get_container_info, get_object_info
from swift.common.swob import wsgify

from avro_streamer.avro_streamer import GenericStrippingAvroParser

class AvroFilterMiddleware(object):
    """
    Swift middleware for removing certain fields from downloaded Avro
    objects, depending on a user's role.

    Essentially, this allows the Avro objects to be selectively censored
    for different classes of user -- for instance, there may be sensitive
    data that is being collected that should only be made available to
    privileged users.

    See attached README.md file for instructions on how to configure this
    middleware appropriately.

    Stripping is only applied to objects that have a Content-Type of
    'application/vnd.caida.<datatype>.avro'.

    Requires: python-avro-streamer (https://github.com/CAIDA/python-avro-streamer)
    """

    def __init__(self, app, conf, logger=None):
        self.app = app

        if logger:
            self.logger = logger
        else:
            self.logger = get_logger(conf, log_route='avrofilter')

        # Any roles specified as "nostrip_roles" will always receive the
        # full uncensored Avro data
        if 'nostrip_roles' in conf:
            self.nostrip_roles = set([x.strip() \
                    for x in conf['nostrip_roles'].split(',')])
        else:
            self.nostrip_roles = set()

        # admin should always be a nostrip role
        self.nostrip_roles.add('admin')

        self.defaultstrip = {}
        self.dontstrip = {}

        # Any field mentioned in a "retain_keys" option will be stripped
        # by default, unless the user matches a role where that field is
        # explicitly listed as being retained

        # In other words: defaultstrip is the union of all of the fields that
        # are explicitly configured as retainable. Any "public" fields should
        # NOT be listed as a retained field for any role.
        for k,v in conf.iteritems():
            # The role that this option applies to is specified in the
            # prefix of the configuration option name
            # e.g. "swiftro_retain_keys" -> role = "swiftro"
            if not k.endswith("_retain_keys"):
                continue

            role = k[:-12]

            if role in self.dontstrip:
                self.logger.info("Warning: role '%s' appears multiple times in AvroFilterMiddleware configuration" % (role))
                # TODO only warn once per duplicate role
                continue

            self.dontstrip[role] = {}

            for ts in list_from_csv(v):
                ts = ts.strip()
                if len(ts) == 0:
                    continue

                # fields are listed using <datatype>:<fieldname> format, e.g.
                # "flowtuple:netacq_country"
                ts = ts.split(':')
                if len(ts) != 2:
                    self.logger.info("Invalid 'retain_keys' parameter format, should be <data type>:<field name> (not %s)" % (ts))
                    continue

                if ts[0] not in self.dontstrip[role]:
                    self.dontstrip[role][ts[0]] = set()
                if ts[0] not in self.defaultstrip:
                    self.defaultstrip[ts[0]] = set()

                self.dontstrip[role][ts[0]].add(ts[1])
                self.defaultstrip[ts[0]].add(ts[1])


    @wsgify
    def __call__(self, req):
        try:
            (version, account, container, obj) = \
                    split_path(req.path_info, 4, 4, True)
        except ValueError:
            return req.get_response(self.app)

        # Only worry about data fetches, not uploads.
        if not valid_api_version(version) or req.method not in ('GET', 'HEAD'):
            return req.get_response(self.app)

        # Get all roles that apply to the user making the request
        roles = set()
        if (req.environ.get('HTTP_X_IDENTITY_STATUS') == 'Confirmed' or \
                req.environ.get('HTTP_X_SERVICE_IDENTITY_STATUS') in \
                        (None, "Confirmed")):
            roles = set(list_from_csv(req.environ.get('HTTP_X_ROLES', '')))

        # If we have one of the "nostrip" roles, then don't do any stripping
        if roles.intersection(self.nostrip_roles):
            return req.get_response(self.app)

        # Perform the request and grab a response object that we can work
        # with
        resp = req.get_response(self.app)

        # Check that the requested object is actually a CAIDA avro file
        conttype = resp.headers.get("Content-Type", None)

        if conttype is None:
            return resp

        if not conttype.startswith("application/vnd.caida."):
            return resp

        if not conttype.endswith(".avro"):
            return resp

        dtype = conttype.replace("application/vnd.caida.", "", 1)[:-5]

        if dtype not in self.defaultstrip:
            return resp

        # Start by planning to strip all fields for this datatype that have
        # been explicitly appeared in the config file. Then for each role that
        # the user has, remove any fields from the strip set that should be
        # retained for that role.
        tostrip = self.defaultstrip[dtype]

        for r in roles:
            if r not in self.dontstrip:
                # No specified config for this role, so leave strip set as is
                continue

            if dtype not in self.dontstrip[r]:
                continue

            tostrip = tostrip - self.dontstrip[r][dtype]

        # Remove the Etag because otherwise swift clients get very upset
        # about the md5sum of the response body not matching the md5sum
        # in the Etag header :/
        if 'Etag' in resp.headers:
            del(resp.headers['Etag'])

        # If we are going to be stripping fields, replace our response
        # iterable with one that will parse the received Avro and remove
        # the desired fields. The swift proxy should handle the rest.
        x = GenericStrippingAvroParser(resp.app_iter, resp.body, tostrip)
        resp.app_iter = x

        return resp


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def avro_strip(app):
        return AvroFilterMiddleware(app, conf)
    return avro_strip


# vim: set sw=4 tabstop=4 softtabstop=4 expandtab :


# Hermes Avrofilter Middleware

Swift middleware for stripping of pre-specified fields from CAIDA
Avro records, depending on the requesting user's role. The stripping is
performed in-line, i.e. the full data is fetched from the object store, parsed
and then modified to remove the requested fields.

## Installing
This middleware requires the python-avro-streamer package, which is available
from https://github.com/CAIDA/python-avro-streamer

```
git clone git@github.com:caida/python-avro-streamer
cd python-avro-streamer/
python setup.py install
cd ..
git clone git@github.com:caida/hermes-avrofilter
cd hermes-avrofilter/
python setup.py install
```

## Plugin Configuration
To use this middleware, add `avrofilter` to your proxy server pipeline
immediately after your auth middleware(s) (such as `keystone_auth`,
`iprange_acl` or `tempauth`).

You should also add the following section to the bottom of your proxy
server configuration file:

```
[filter:avrofilter]
use = egg:avrofilter#avrofilter
nostrip_roles = superrole1, superrole2

role1_retain_keys = flowtuple:netacq_continent, flowtuple:netacq_country
role2_retain_keys = flowtuple:dest_ip, flowtuple:netacq_country
role3_retain_keys = dos:initial_packet, flowtuple:dest_ip
admin_retain_keys = flowtuple:secret_data
```

The `nostrip_roles` option allows you to specify which roles will NOT be
subject to any field stripping of fetched data, i.e. they will
receive the full unmodified data. `admin` is always assumed to be in this
group, so does not need to be specified in the config file.

The `*_retain_keys` options are used to tell the plugin which fields should
NOT be stripped for a user that has the role which is present in the prefix
portion of the option name. Each field to be retained must be specified using
the format <datatype>:<fieldname>. Once a field appears in a `retain_keys`
option, it will be stripped for all users **unless** that user matches a role
where that field is explicitly configured to be retained OR the user matches
one of the `nostrip_roles`.

So in the above example, users matching `role1` will not receive the
`dest_ip` field in any flowtuple data that they download, nor will they
receive the `initial_packet` field in the dos data. They will also not
receive the `secret_data` field -- in fact, nobody outside of the two
`superroles` will receive that field. `role3` users get the `initial_packet`
for dos and the `dest_ip` for flowtuple, but won't receive the two `netacq`
fields.

If a user does not match any of the roles that have explicit `retain_keys`
options and does not match any of the `no_strip` roles, then **all** of the
fields that appear in at least one `retain_keys` options will be stripped
whenever that user downloads Avro data from the swift object store.


### Object File Configuration

This middleware will only be applied to object files where the content
type matches a valid CAIDA avro content type. For example, flowtuple
records will have a content type of 'application/vnd.caida.flowtuple.avro'
and dos records will have a content type of 'application/vnd.caida.dos.avro'.
The content type should have been automatically set as part of the uploading
process.

Object files that have any other content type will be ignored by this
middleware and pushed to the client without modification.


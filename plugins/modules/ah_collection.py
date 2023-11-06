#!/usr/bin/python
# coding: utf-8 -*-

# (c) 2020, Sean Sullivan <@sean-m-sullivan>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}


DOCUMENTATION = """
---
module: ah_collection
author: "Sean Sullivan (@sean-m-sullivan), Tom Page <@Tompage1994>"
short_description: update, or destroy Automation Hub Collections.
description:
    - Upload, or destroy Automation Hub Collections. See
      U(https://www.ansible.com/) for an overview.
options:
    namespace:
      description:
        - Namespace name. Must be lower case containing only alphanumeric characters and underscores.
      required: True
      type: str
    name:
      description:
        - Collection name. Must be lower case containing only alphanumeric characters and underscores.
      required: True
      type: str
    version:
      description:
        - Collection Version. Must be lower case containing only alphanumeric characters and underscores.
      type: str
    repository:
      description:
        - Which Repository to publish to. Most likely this is 'published' or one that has been created.
      type: str
      default: 'published'
    path:
      description:
        - Collection artifact file path.
        - If version is not specified, version will be derived from file name.
      type: str
    wait:
      description:
        - Waits for the collection to be uploaded
      type: bool
      default: true
    auto_approve:
      description:
        - Approves a collection.
        - Requires version to be set.
      type: bool
      default: true
    interval:
      description:
        - The interval to request an update from Automation Hub when waiting for approval.
      required: False
      default: 10
      type: float
    timeout:
      description:
        - Waiting for the approval will abort after this
          amount of seconds
      type: int
    overwrite_existing:
      description:
        - Overwrites an existing collection.
        - Requires version to be set.
      type: bool
      default: false
    state:
      description:
        - Desired state of the resource.
        - If present with a path, will upload a collection artifact to Automation hub.
        - If present will return data on a collection.
        - If present with version, will return data on a collection version.
        - If absent without version, will delete the collection and all versions.
        - If absent with version, will delete only specified version.
      choices: ["present", "absent"]
      default: "present"
      type: str

extends_documentation_fragment: galaxy.galaxy.auth
"""


EXAMPLES = """
- name: Upload collection to automation hub
  galaxy.galaxy.ah_collection:
    namespace: awx
    name: awx
    path: /var/tmp/collections/awx-awx-15.0.0.tar.gz


- name: Remove collection
  galaxy.galaxy.ah_collection:
    namespace: test_collection
    name: test
    version: 4.1.2
    state: absent
...
"""

from ..module_utils.ah_module import AHModule
from ..module_utils.ah_api_module import AHAPIModule
import pathlib


def main():
    # Any additional arguments that are not fields of the item can be added here
    argument_spec = dict(
        namespace=dict(required=True),
        name=dict(required=True),
        path=dict(),
        wait=dict(type="bool", default=True),
        interval=dict(default=10.0, type="float"),
        timeout=dict(default=None, type="int"),
        auto_approve=dict(type="bool", default=True),
        overwrite_existing=dict(type="bool", default=False),
        version=dict(),
        repository=dict(default="published"),
        state=dict(choices=["present", "absent"], default="present"),
    )

    # Create a module for ourselves
    module = AHModule(argument_spec=argument_spec)
    api_module = AHAPIModule(argument_spec=argument_spec)

    # Extract our parameters
    namespace = module.params.get("namespace")
    name = module.params.get("name")
    path = module.params.get("path")
    wait = module.params.get("wait")
    interval = module.params.get("interval")
    timeout = module.params.get("timeout")
    overwrite_existing = module.params.get("overwrite_existing")
    auto_approve = module.params.get("auto_approve")
    version = module.params.get("version")
    repository = module.params.get("repository")
    state = module.params.get("state")

    # Endpoint moved in more recent versions
    vers = api_module.get_server_version()

    # approval, overwrite, and other methods needs a version, if one is not defined find it from the filename.
    if state == 'present':
        if version:
            pass
        elif path:
            version = path.split("-")[-1].replace('.tar.gz', '')
        else:
            module.fail_json(msg="If state is not present version must be supplied through the path or the version parameter.")

    # Attempt to look up an existing item based on the provided data
    if vers > "4.7.0":
        if version:
            collection_endpoint = module.build_collection_url(repository, namespace, name, version)
        else:
            collection_endpoint = module.build_collection_url(repository, namespace, name)
        existing_item = api_module.make_request("GET", collection_endpoint, **{"return_none_on_404": True})
        if existing_item is not None:
            module.json_output["endpoint"] = collection_endpoint
    elif vers < "4.7.0":
        if version:
            collection_endpoint = "collections/{0}/{1}/versions/{2}".format(namespace, name, version)
        else:
            collection_endpoint = "collections/{0}/{1}".format(namespace, name)
        existing_item = module.get_endpoint(collection_endpoint, **{"return_none_on_404": True})

    # If state is absent, check if it exists, delete and exit.
    if state == "absent":
        if existing_item is None:
            module.json_output["deleted"] = False
            module.json_output["changed"] = False
        else:
            # If the state was absent we can let the module delete it if needed, the module will handle exiting from this
            module.json_output["task"] = module.delete_endpoint(existing_item["json"]["href"])["json"]["task"]
            module.json_output["deleted"] = True
            module.json_output["changed"] = True
        module.exit_json(**module.json_output)
    else:
        file = pathlib.Path(path)
        if not file.exists():
            module.fail_json(msg="Could not find Collection {0}.{1} in path {2}".format(namespace, name, path))

    if path:
        collection_endpoint = "collections/{0}/{1}/versions/{2}".format(namespace, name, version)
        if existing_item is not None and overwrite_existing:
            # Delete collection
            module.json_output["task"] = module.delete_endpoint(existing_item["json"]["href"])["json"]["task"]
            module.json_output["deleted"] = True
            # Upload new collection
            module.upload(path, "artifacts/collections", wait, item_type="collections")
            module.json_output["changed"] = True
            module.json_output["endpoint"] = collection_endpoint
            # Get new collection version
            existing_item = module.get_endpoint(collection_endpoint, **{"return_none_on_404": True})
            if auto_approve:
                module.approve(
                    endpoint=collection_endpoint,
                    timeout=timeout,
                    interval=interval
                )
        elif existing_item is None:
            module.upload(path, "artifacts/collections", wait, item_type="collections")
            module.json_output["changed"] = True
            if auto_approve:
                module.approve(
                    endpoint=collection_endpoint,
                    repository=repository,
                    timeout=timeout,
                    interval=interval
                )
        else:
            module.json_output["changed"] = False
    else:
        if existing_item is None and state == "absent":
            module.json_output["deleted"] = False
            module.json_output["changed"] = False
        elif existing_item is None:
            if version:
                module.fail_json(msg="Could not find Collection {0}.{1} with_version {2}".format(namespace, name, version))
            else:
                module.fail_json(msg="Could not find Collection {0}.{1}".format(namespace, name))
        else:
            module.json_output["collection"] = existing_item["json"]

    # If state is absent, check if it exists, delete and exit.
    if state == "absent":
        if existing_item is None:
            module.json_output["deleted"] = False
            module.json_output["changed"] = False
        else:
            # If the state was absent we can let the module delete it if needed, the module will handle exiting from this
            module.json_output["task"] = module.delete_endpoint(existing_item["json"]["href"])["json"]["task"]
            module.json_output["deleted"] = True
            module.json_output["changed"] = True

    # If the state was present and we can Return information about the collection
    module.exit_json(**module.json_output)


if __name__ == "__main__":
    main()
